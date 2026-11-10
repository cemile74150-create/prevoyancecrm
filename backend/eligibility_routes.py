"""Routes du module Éligibilité.

Les droits de route (lecture / modification) sont déclarés dans access_control._ROUTE_PERMISSIONS.
Ici : accès au dossier, droit de modification et création réservée au compte gestionnaire.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel

from access_control import (
    PERM_CLIENTS_EDIT,
    PERM_DOSSIERS_EDIT,
    User,
    can_access_client,
    clients_base_query,
    has_any_perm,
)
import eligibility as elig

logger = logging.getLogger(__name__)

EDIT_PERMS = (PERM_CLIENTS_EDIT, PERM_DOSSIERS_EDIT)


class EligibilityListCreate(BaseModel):
    name: str


def can_edit_client_eligibility(user: User, client: dict) -> bool:
    """Cocher / décocher : droit de modification et dossier attribué (ou vue globale)."""
    return has_any_perm(user, EDIT_PERMS) and can_access_client(user, client)


def attach_eligibility_routes(
    api_router,
    *,
    db,
    get_current_user: Callable,
    require_client: Callable[[str, User], Awaitable[dict]],
    decrypt_client: Callable[[Optional[dict]], Optional[dict]],
    normalize_statut: Callable[[Optional[str]], str],
    fold_search: Callable[[object], str],
    log_action: Optional[Callable[..., Awaitable[None]]] = None,
):
    lists_coll = db[elig.LISTS_COLLECTION]
    members_coll = db[elig.MEMBERSHIPS_COLLECTION]

    async def _get_list_or_404(list_id: str) -> dict:
        doc = await lists_coll.find_one({"_id": list_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Liste introuvable")
        return doc

    async def _visible_client_ids(user: User, client_ids: list[str]) -> set[str]:
        if not client_ids:
            return set()
        query = clients_base_query(user)
        query["id"] = {"$in": client_ids}
        rows = await db.clients.find(query, {"_id": 0, "id": 1}).to_list(len(client_ids) + 1)
        return {r["id"] for r in rows if r.get("id")}

    async def _journal(user: User, client: dict, text: str) -> None:
        if not log_action:
            return
        try:
            await log_action(user.user_id, client["id"], text, client.get("dossier_id"))
        except Exception:
            logger.exception("Journal éligibilité non enregistré client=%s", client.get("id"))

    @api_router.get("/eligibility/lists")
    async def list_eligibility_lists(user: User = Depends(get_current_user)):
        lists = await elig.active_lists(db)
        list_ids = [d["_id"] for d in lists]
        members = await members_coll.find(
            {"list_id": {"$in": list_ids}}, {"_id": 0, "list_id": 1, "client_id": 1}
        ).to_list(None)
        visible = await _visible_client_ids(user, sorted({m["client_id"] for m in members}))
        counts: dict[str, int] = {}
        for m in members:
            if m["client_id"] in visible:
                counts[m["list_id"]] = counts.get(m["list_id"], 0) + 1
        return {
            "lists": [elig.public_list(d, counts.get(d["_id"], 0)) for d in lists],
            "total": len(lists),
            "can_create": elig.can_create_lists(user),
        }

    @api_router.post("/eligibility/lists", status_code=201)
    async def create_eligibility_list(payload: EligibilityListCreate, user: User = Depends(get_current_user)):
        if not elig.can_create_lists(user):
            raise HTTPException(status_code=403, detail="Création de liste réservée au compte gestionnaire de l'éligibilité")
        try:
            doc = await elig.create_list(db, payload.name, user.account_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return elig.public_list(doc, 0)

    @api_router.get("/eligibility/lists/{list_id}/clients")
    async def list_eligibility_clients(
        list_id: str,
        q: Optional[str] = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        user: User = Depends(get_current_user),
    ):
        doc = await _get_list_or_404(list_id)
        members = await members_coll.find({"list_id": list_id}, {"_id": 0, "client_id": 1}).to_list(None)
        client_ids = sorted({m["client_id"] for m in members})
        clients: list[dict] = []
        if client_ids:
            query = clients_base_query(user)
            query["id"] = {"$in": client_ids}
            raw = await db.clients.find(query, {"_id": 0}).to_list(len(client_ids) + 1)
            clients = [decrypt_client(c) for c in raw]
        folded = fold_search(q)
        matched = [c for c in clients if elig.client_matches(c, folded, fold_search)]
        matched.sort(key=lambda c: elig.client_sort_key(c, fold_search))
        start = (page - 1) * page_size
        return {
            "list": elig.public_list(doc, len(clients)),
            "items": [elig.public_client_row(c, normalize_statut) for c in matched[start:start + page_size]],
            "total": len(matched),
            "page": page,
            "page_size": page_size,
        }

    @api_router.get("/clients/{client_id}/eligibility")
    async def get_client_eligibility(client_id: str, user: User = Depends(get_current_user)):
        client = await require_client(client_id, user)
        lists = await elig.active_lists(db)
        rows = await members_coll.find({"client_id": client_id}, {"_id": 0}).to_list(None)
        by_list = {r["list_id"]: r for r in rows}
        items = []
        for d in lists:
            m = by_list.get(d["_id"])
            items.append({
                **elig.public_list(d),
                "checked": m is not None,
                "added_at": m.get("added_at") if m else None,
                "added_by_name": m.get("added_by_name") if m else None,
            })
        return {
            "client_id": client_id,
            "can_edit": can_edit_client_eligibility(user, client),
            "lists": items,
        }

    async def _require_editable_client(client_id: str, user: User) -> dict:
        client = await require_client(client_id, user)
        if not can_edit_client_eligibility(user, client):
            raise HTTPException(status_code=403, detail="Modification de l'éligibilité non autorisée pour ce dossier")
        return client

    @api_router.put("/clients/{client_id}/eligibility/{list_id}")
    async def add_client_eligibility(client_id: str, list_id: str, user: User = Depends(get_current_user)):
        client = await _require_editable_client(client_id, user)
        doc = await _get_list_or_404(list_id)
        if doc.get("is_active") is False:
            raise HTTPException(status_code=409, detail="Cette liste n'est plus active")
        created = await elig.add_membership(db, list_id, client_id, user.account_id, user.name)
        if created:
            await _journal(user, client, f"Éligibilité : ajouté à la liste « {doc.get('name')} »")
        return {"client_id": client_id, "list_id": list_id, "checked": True, "created": created}

    @api_router.delete("/clients/{client_id}/eligibility/{list_id}")
    async def remove_client_eligibility(client_id: str, list_id: str, user: User = Depends(get_current_user)):
        client = await _require_editable_client(client_id, user)
        doc = await _get_list_or_404(list_id)
        removed = await elig.remove_membership(db, list_id, client_id)
        if removed:
            await _journal(user, client, f"Éligibilité : retiré de la liste « {doc.get('name')} »")
        return {"client_id": client_id, "list_id": list_id, "checked": False, "removed": removed}
