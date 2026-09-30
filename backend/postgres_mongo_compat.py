"""
Compatibilité Mongo-like pour Postgres (SQLAlchemy).

But:
- permettre à l’app FastAPI de continuer à appeler `db.<collection>.find_one/find/update_one/...`
  comme avant (Motor/MongoDB),
- tout en stockant les documents dans PostgreSQL (tables + JSONB `data`).

Note:
- Pour limiter la complexité de traduction Mongo→SQL, les filtres Mongo sont évalués en Python
  sur `row.data`. Les requêtes restent correctes pour la migration, au prix de performances
  plus faibles (dataset modestes ici).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Sequence, Tuple, Type, Union

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import get_engine
from db.models import (
    AppMigration,
    ActionLog,
    Appointment,
    Client,
    Demande,
    Document,
    EmailLog,
    FormLibrary,
    Note,
    RappelEmailLog,
    Suivi3PClient,
    Suivi3PDocument,
    Suivi3PPendingDocument,
    Task,
    User,
    UserSession,
)
from sqlalchemy.orm import sessionmaker


class UpdateResult:
    def __init__(self, matched_count: int, modified_count: int):
        self.matched_count = matched_count
        self.modified_count = modified_count


class DeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


def _get_nested(doc: dict, key: str) -> Any:
    # Pas de support deep-nesting nécessaire (l’app actuelle utilise des clés simples)
    return doc.get(key)


def _match_field(doc: dict, field: str, condition: Any) -> bool:
    if not isinstance(condition, dict):
        return _get_nested(doc, field) == condition

    # Support d’opérateurs Mongo utilisés dans server.py
    for op, value in condition.items():
        v = _get_nested(doc, field)
        if op == "$ne":
            if v == value:
                return False
        elif op == "$in":
            if v not in (value or []):
                return False
        elif op == "$nin":
            if v in (value or []):
                return False
        elif op == "$exists":
            exists = field in doc
            if bool(value) != exists:
                return False
        elif op == "$gte":
            if v is None or v < value:
                return False
        elif op == "$lte":
            if v is None or v > value:
                return False
        elif op == "$not":
            # value attendu comme condition simple ou dict d’opérateurs
            # Exemple hypothétique: {"field": {"$not": {"$eq": ...}}}
            # Non utilisé actuellement, mais on gère pour robustesse basique.
            inner_ok = _match_field(doc, field, value)
            if inner_ok:
                return False
        else:
            raise NotImplementedError(f"Mongo operator not supported: {op}")

    return True


def mongo_match(doc: dict, query: dict) -> bool:
    if not query:
        return True

    # Opérateurs booléens
    if "$or" in query:
        if not any(mongo_match(doc, q) for q in (query.get("$or") or [])):
            return False
    if "$and" in query:
        if not all(mongo_match(doc, q) for q in (query.get("$and") or [])):
            return False

    for k, cond in query.items():
        if k in ("$or", "$and"):
            continue
        if not _match_field(doc, k, cond):
            return False

    return True


def apply_projection(doc: dict, projection: Optional[dict]) -> dict:
    if projection is None:
        return dict(doc)

    proj = dict(projection or {})
    if not proj:
        return dict(doc)

    # En MongoDB, si projection contient des 1 => inclusion (mode "only these fields")
    include_only = any(v == 1 for k, v in proj.items() if k != "_id")

    # Toujours ignore _id
    if include_only:
        out: Dict[str, Any] = {}
        for k, v in proj.items():
            if k == "_id":
                continue
            if v == 1 and k in doc:
                out[k] = doc[k]
        return out

    # exclusion par défaut (projection avec 0)
    out2 = dict(doc)
    for k, v in proj.items():
        if k == "_id":
            continue
        if v == 0 and k in out2:
            out2.pop(k, None)
    return out2


def sort_docs(docs: List[dict], field: str, direction: int) -> List[dict]:
    reverse = direction == -1
    def key_fn(d: dict):
        v = d.get(field)
        return "" if v is None else v

    return sorted(docs, key=key_fn, reverse=reverse)


class FindCursorCompat:
    def __init__(self, collection: "CollectionCompat", query: dict, projection: Optional[dict]):
        self._collection = collection
        self._query = query or {}
        self._projection = projection
        self._sort: Optional[Tuple[str, int]] = None
        self._docs_cache: Optional[List[dict]] = None

    async def _ensure_loaded(self) -> None:
        if self._docs_cache is not None:
            return
        rows = await self._collection._fetch_candidates(self._query)
        docs: List[dict] = []
        for r in rows:
            d = self._collection._row_to_doc(r)
            if mongo_match(d, self._query):
                docs.append(apply_projection(d, self._projection))
        self._docs_cache = docs

    def sort(self, field: str, direction: int):
        self._sort = (field, direction)
        return self

    async def to_list(self, length: int) -> List[dict]:
        await self._ensure_loaded()
        docs = list(self._docs_cache or [])
        if self._sort:
            docs = sort_docs(docs, self._sort[0], self._sort[1])
        return docs[:length] if length is not None else docs

    def __aiter__(self) -> AsyncIterator[dict]:
        async def gen():
            await self._ensure_loaded()
            docs = list(self._docs_cache or [])
            if self._sort:
                docs = sort_docs(docs, self._sort[0], self._sort[1])
            for d in docs:
                yield d
        return gen()


class CollectionCompat:
    def __init__(self, session_factory: sessionmaker, model: Type[Any], pk_field: str):
        self._session_factory = session_factory
        self._model = model
        self._pk_field = pk_field

    async def _fetch_candidates(self, query: dict) -> List[Any]:
        # Coarse filter: si user_id ou id est présent, réduire côté SQL
        stmt = select(self._model)
        if isinstance(query, dict):
            if "id" in query and hasattr(self._model, "id"):
                stmt = stmt.where(getattr(self._model, "id") == query["id"])
            elif "session_token" in query and hasattr(self._model, "session_token"):
                stmt = stmt.where(getattr(self._model, "session_token") == query["session_token"])
            elif "user_id" in query and hasattr(self._model, "user_id"):
                stmt = stmt.where(getattr(self._model, "user_id") == query["user_id"])
        async with self._session_factory() as session:
            res = await session.execute(stmt)
            return list(res.scalars().all())

    def _row_to_doc(self, row: Any) -> dict:
        doc = dict(getattr(row, "data") or {})
        # S’assure que les champs clés existent pour le matching
        for field in ("id", "user_id", "session_token", "client_id", "dossier_id", "suivi_3p_client_id", "storage_path"):
            if hasattr(row, field) and field not in doc:
                doc[field] = getattr(row, field)
        return doc

    def find(self, query: dict, projection: Optional[dict] = None) -> FindCursorCompat:
        return FindCursorCompat(self, query or {}, projection)

    async def find_one(self, query: dict, projection: Optional[dict] = None) -> Optional[dict]:
        cursor = self.find(query, projection)
        lst = await cursor.to_list(1)
        return lst[0] if lst else None

    async def insert_one(self, doc: dict) -> None:
        async with self._session_factory() as session:
            row_kwargs: Dict[str, Any] = {}

            # Remplit aussi les colonnes explicites si elles existent dans le modèle
            for col in self._model.__table__.columns:
                name = col.name
                if name == "data":
                    continue
                if name not in doc:
                    continue
                val = doc[name]
                # Colonnes DateTime : les ISO strings restent dans JSONB `data`
                col_type = str(getattr(col, "type", "") or "")
                if "DateTime" in col_type and isinstance(val, str):
                    continue
                row_kwargs[name] = val

            row_kwargs["data"] = doc
            session.add(self._model(**row_kwargs))
            await session.commit()

    async def update_one(self, query: dict, update: dict) -> UpdateResult:
        rows = await self._fetch_candidates(query or {})
        matched: List[Any] = []
        for r in rows:
            d = self._row_to_doc(r)
            if mongo_match(d, query or {}):
                matched.append(r)
        matched_count = len(matched)
        if matched_count == 0:
            return UpdateResult(0, 0)

        # 1er match seulement
        r = matched[0]
        new_doc = self._apply_update(self._row_to_doc(r), update)
        if new_doc != self._row_to_doc(r):
            modified_count = 1
        else:
            modified_count = 0

        async with self._session_factory() as session:
            pk_val = getattr(r, self._pk_field)
            stmt = (
                select(self._model)
                .where(getattr(self._model, self._pk_field) == pk_val)
                .limit(1)
            )
            obj = (await session.execute(stmt)).scalars().first()
            if obj is not None:
                obj.data = new_doc
            await session.commit()

        return UpdateResult(matched_count=1, modified_count=modified_count)

    def _apply_update(self, doc: dict, update: dict) -> dict:
        out = dict(doc)
        update = update or {}

        if "$set" in update:
            for k, v in (update.get("$set") or {}).items():
                out[k] = v
        if "$unset" in update:
            for k in (update.get("$unset") or {}).keys():
                out.pop(k, None)

        return out

    async def update_many(self, query: dict, update: dict) -> UpdateResult:
        rows = await self._fetch_candidates(query or {})
        matched_docs: List[Any] = []
        for r in rows:
            d = self._row_to_doc(r)
            if mongo_match(d, query or {}):
                matched_docs.append(r)

        matched_count = len(matched_docs)
        if matched_count == 0:
            return UpdateResult(0, 0)

        modified_count = 0
        async with self._session_factory() as session:
            for r in matched_docs:
                pk_val = getattr(r, self._pk_field)
                stmt = select(self._model).where(getattr(self._model, self._pk_field) == pk_val).limit(1)
                obj = (await session.execute(stmt)).scalars().first()
                if obj is None:
                    continue
                old_doc = dict(obj.data or {})
                new_doc = self._apply_update(old_doc, update)
                if new_doc != old_doc:
                    modified_count += 1
                obj.data = new_doc
            await session.commit()

        return UpdateResult(matched_count=matched_count, modified_count=modified_count)

    async def delete_one(self, query: dict) -> DeleteResult:
        rows = await self._fetch_candidates(query or {})
        for r in rows:
            d = self._row_to_doc(r)
            if mongo_match(d, query or {}):
                pk_val = getattr(r, self._pk_field)
                async with self._session_factory() as session:
                    await session.execute(delete(self._model).where(getattr(self._model, self._pk_field) == pk_val))
                    await session.commit()
                return DeleteResult(1)
        return DeleteResult(0)

    async def delete_many(self, query: dict) -> DeleteResult:
        rows = await self._fetch_candidates(query or {})
        to_delete: List[Any] = []
        for r in rows:
            d = self._row_to_doc(r)
            if mongo_match(d, query or {}):
                to_delete.append(r)
        if not to_delete:
            return DeleteResult(0)

        async with self._session_factory() as session:
            for r in to_delete:
                pk_val = getattr(r, self._pk_field)
                await session.execute(delete(self._model).where(getattr(self._model, self._pk_field) == pk_val))
            await session.commit()

        return DeleteResult(len(to_delete))

    async def count_documents(self, query: dict) -> int:
        rows = await self._fetch_candidates(query or {})
        cnt = 0
        for r in rows:
            d = self._row_to_doc(r)
            if mongo_match(d, query or {}):
                cnt += 1
        return cnt


class PostgresMongoCompatDB:
    """
    Objet `db` compatible avec le code existant.
    """

    def __init__(self):
        engine = get_engine()
        self._session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

        self.users = CollectionCompat(self._session_factory, User, pk_field="user_id")
        self.user_sessions = CollectionCompat(self._session_factory, UserSession, pk_field="session_token")
        self.clients = CollectionCompat(self._session_factory, Client, pk_field="id")
        self.notes = CollectionCompat(self._session_factory, Note, pk_field="id")
        self.demandes = CollectionCompat(self._session_factory, Demande, pk_field="id")
        self.actions = CollectionCompat(self._session_factory, ActionLog, pk_field="id")
        self.documents = CollectionCompat(self._session_factory, Document, pk_field="id")
        self.form_library = CollectionCompat(self._session_factory, FormLibrary, pk_field="id")
        self.appointments = CollectionCompat(self._session_factory, Appointment, pk_field="id")
        self.tasks = CollectionCompat(self._session_factory, Task, pk_field="id")
        self.app_migrations = CollectionCompat(self._session_factory, AppMigration, pk_field="id")
        self.rappel_email_logs = CollectionCompat(self._session_factory, RappelEmailLog, pk_field="id")
        self.email_logs = CollectionCompat(self._session_factory, EmailLog, pk_field="id")

        self._collections = {
            "suivi_3p_clients": CollectionCompat(self._session_factory, Suivi3PClient, pk_field="id"),
            "suivi_3p_documents": CollectionCompat(self._session_factory, Suivi3PDocument, pk_field="id"),
            "suivi_3p_pending_documents": CollectionCompat(self._session_factory, Suivi3PPendingDocument, pk_field="id"),
            "rappel_email_logs": self.rappel_email_logs,
            "email_logs": self.email_logs,
        }

    def __getitem__(self, name: str) -> CollectionCompat:
        if name in self._collections:
            return self._collections[name]
        raise KeyError(name)

