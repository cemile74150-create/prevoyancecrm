"""Module Éligibilité : seed, création réservée, appartenances, droits CRM (cas A à K)."""
import asyncio
import copy
import re
import sys
from pathlib import Path

import pytest
from fastapi import APIRouter, HTTPException
from pymongo.errors import DuplicateKeyError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import eligibility as elig  # noqa: E402
from access_control import (  # noqa: E402
    PERM_CLIENTS_EDIT,
    PERM_CLIENTS_VIEW,
    PERM_DOSSIERS_EDIT,
    PERM_DOSSIERS_VIEW,
    ROLE_ADMIN,
    ROLE_CONSEILLER,
    TENANT_USER_ID,
    can_access_client,
    permission_for_request,
    user_from_doc,
)
from eligibility_routes import EligibilityListCreate, attach_eligibility_routes  # noqa: E402

MANAGER_ID = "user_cemile_test"


# ---------------- Fausse base Mongo (opérateurs utilisés par le module) ----------------
def _match_value(value, cond):
    if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
        for op, arg in cond.items():
            if op == "$ne" and value == arg:
                return False
            if op == "$in" and value not in arg:
                return False
            if op == "$exists" and (value is not None) != bool(arg):
                return False
            if op == "$regex":
                flags = re.IGNORECASE if "i" in (cond.get("$options") or "") else 0
                if not isinstance(value, str) or not re.search(arg, value, flags):
                    return False
        return True
    return value == cond


def _matches(doc, query):
    for key, cond in query.items():
        if key == "$or":
            if not any(_matches(doc, sub) for sub in cond):
                return False
        elif key == "$and":
            if not all(_matches(doc, sub) for sub in cond):
                return False
        elif not _match_value(doc.get(key), cond):
            return False
    return True


def _project(doc, projection):
    out = copy.deepcopy(doc)
    if projection and projection.get("_id") == 0:
        out.pop("_id", None)
    included = [k for k, v in (projection or {}).items() if v and k != "_id"]
    if included:
        out = {k: v for k, v in out.items() if k in included or (k == "_id" and projection.get("_id") != 0)}
    return out


class _Result:
    def __init__(self, **kw):
        self.upserted_id = kw.get("upserted_id")
        self.deleted_count = kw.get("deleted_count", 0)
        self.modified_count = kw.get("modified_count", 0)


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, length):
        return self._rows if length is None else self._rows[:length]


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.unique = []

    async def create_index(self, keys, unique=False, **_):
        if unique:
            self.unique.append(tuple(k for k, _ in keys))

    def _check_unique(self, doc, ignore=None):
        for fields in self.unique:
            for other in self.docs:
                if other is ignore:
                    continue
                if all(other.get(f) == doc.get(f) for f in fields):
                    raise DuplicateKeyError("dup")
        if any(o.get("_id") == doc.get("_id") for o in self.docs if o is not ignore):
            raise DuplicateKeyError("dup _id")

    async def insert_one(self, doc):
        doc = copy.deepcopy(doc)
        doc.setdefault("_id", f"auto-{len(self.docs)}-{id(doc)}")
        self._check_unique(doc)
        self.docs.append(doc)
        return _Result()

    async def find_one(self, query, projection=None):
        for d in self.docs:
            if _matches(d, query):
                return _project(d, projection)
        return None

    def find(self, query=None, projection=None):
        return _Cursor([_project(d, projection) for d in self.docs if _matches(d, query or {})])

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return _Result(modified_count=1)
        if not upsert:
            return _Result()
        doc = {k: v for k, v in query.items() if not k.startswith("$") and not isinstance(v, dict)}
        doc.update(update.get("$setOnInsert", {}))
        doc.update(update.get("$set", {}))
        await self.insert_one(doc)
        return _Result(upserted_id=doc.get("_id"))

    async def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _matches(d, query):
                del self.docs[i]
                return _Result(deleted_count=1)
        return _Result()

    async def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, query)]
        return _Result(deleted_count=before - len(self.docs))


class FakeDb:
    def __init__(self):
        self._colls = {}

    def __getitem__(self, name):
        return self._colls.setdefault(name, FakeCollection())

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


# ---------------- Comptes et fiches ----------------
def _user(account_id, role, *, prenom, nom, email, perms=None, see_all=None):
    doc = {
        "user_id": account_id,
        "email": email,
        "prenom": prenom,
        "nom": nom,
        "role": role,
    }
    if perms is not None:
        doc["permissions"] = perms
    if see_all is not None:
        doc["see_all_dossiers"] = see_all
    return user_from_doc(doc)


CEMILE = _user(MANAGER_ID, ROLE_ADMIN, prenom="Cemile", nom="Demirtas", email="cemile@test.invalid")
OTHER_ADMIN = _user("user_admin2", ROLE_ADMIN, prenom="Autre", nom="Admin", email="admin2@test.invalid")
CONSEILLER = _user("user_cons", ROLE_CONSEILLER, prenom="Paul", nom="Martin", email="paul@test.invalid")
READ_ONLY = _user(
    "user_ro", ROLE_CONSEILLER, prenom="Lea", nom="Lecture", email="lea@test.invalid",
    perms={PERM_CLIENTS_EDIT: False, PERM_DOSSIERS_EDIT: False}, see_all=True,
)


def _client(cid, prenom, nom, numero, conseiller, statut="Nouveau"):
    return {
        "id": cid,
        "user_id": TENANT_USER_ID,
        "prenom": prenom,
        "nom": nom,
        "numero_dossier": numero,
        "telephone": "079 000 00 00",
        "email": f"{cid}@client.invalid",
        "statut": statut,
        "conseiller": conseiller,
        "dossier_id": f"dos-{cid}",
    }


def _fold(text):
    import unicodedata

    s = unicodedata.normalize("NFD", str(text or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").casefold().strip()


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv(elig.MANAGER_ENV, MANAGER_ID)
    db = FakeDb()
    journal = []

    async def require_client(client_id, user):
        c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
        if not c:
            raise HTTPException(status_code=404, detail="Client introuvable")
        if not can_access_client(user, c):
            raise HTTPException(status_code=403, detail="Accès non autorisé à ce dossier")
        return c

    async def log_action(user_id, client_id, description, dossier_id=None):
        journal.append((client_id, description))

    router = APIRouter(prefix="/api")
    attach_eligibility_routes(
        router,
        db=db,
        get_current_user=lambda: None,
        require_client=require_client,
        decrypt_client=lambda d: d,
        normalize_statut=lambda s: s or "Nouveau",
        fold_search=_fold,
        log_action=log_action,
    )
    endpoints = {(m, r.path): r.endpoint for r in router.routes for m in r.methods}

    def call(method, path, **kwargs):
        return _run(endpoints[(method, "/api" + path)](**kwargs))

    loop_db = _run(_seed(db))
    assert loop_db == 2
    return {"db": db, "call": call, "journal": journal}


async def _seed(db):
    for c in (
        _client("c1", "Alice", "Zéphyr", "DOS-0001", "Paul Martin"),
        _client("c2", "Bruno", "Ândré", "DOS-0002", "Paul Martin", statut="À présenter"),
        _client("c3", "Chloé", "Autre", "DOS-0003", "Quelqu'un d'autre"),
    ):
        await db.clients.insert_one(c)
    return await elig.ensure_setup(db)


def _lists(env, user=CEMILE):
    return env["call"]("GET", "/eligibility/lists", user=user)


def _list_id(env, name):
    return next(item["id"] for item in _lists(env)["lists"] if item["name"] == name)


PLACEMENT = "Placement à tranche"
RETRAITE = "Retraite populaire – rente viagère à taux réduit"


# ---------------- A. Seed idempotent ----------------
def test_a_seed_creates_two_lists_once(env):
    db = env["db"]
    assert _run(elig.ensure_setup(db)) == 0
    assert _run(elig.ensure_setup(db)) == 0
    names = [d["name"] for d in db[elig.LISTS_COLLECTION].docs]
    assert names == [PLACEMENT, RETRAITE]
    assert all(d["created_by"] == elig.SEED_AUTHOR and d["is_active"] for d in db[elig.LISTS_COLLECTION].docs)


# ---------------- B. Liste des listes ----------------
def test_b_lists_endpoint_returns_counts_and_create_flag(env):
    data = _lists(env)
    assert data["total"] == 2
    assert [item["client_count"] for item in data["lists"]] == [0, 0]
    assert data["can_create"] is True
    assert _lists(env, OTHER_ADMIN)["can_create"] is False
    assert _lists(env, CONSEILLER)["can_create"] is False


# ---------------- C. Création par Cemile ----------------
def test_c_manager_creates_list_and_duplicates_are_refused(env):
    created = env["call"]("POST", "/eligibility/lists", payload=EligibilityListCreate(name="  Rachat   LPP  "), user=CEMILE)
    assert created["name"] == "Rachat LPP" and created["client_count"] == 0
    stored = env["db"][elig.LISTS_COLLECTION].docs[-1]
    assert stored["created_by"] == MANAGER_ID and stored["normalized_name"] == "rachat lpp"
    for dup in ("rachat lpp", "RACHAT LPP", "Retraite populaire - rente viagere a taux reduit"):
        with pytest.raises(HTTPException) as exc:
            env["call"]("POST", "/eligibility/lists", payload=EligibilityListCreate(name=dup), user=CEMILE)
        assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        env["call"]("POST", "/eligibility/lists", payload=EligibilityListCreate(name="   "), user=CEMILE)
    assert exc.value.status_code == 400
    assert _lists(env)["total"] == 3


# ---------------- D. Création refusée aux autres ----------------
def test_d_other_accounts_cannot_create_even_admin(env, monkeypatch):
    for user in (OTHER_ADMIN, CONSEILLER):
        with pytest.raises(HTTPException) as exc:
            env["call"]("POST", "/eligibility/lists", payload=EligibilityListCreate(name="Pirate"), user=user)
        assert exc.value.status_code == 403
    monkeypatch.delenv(elig.MANAGER_ENV)
    with pytest.raises(HTTPException) as exc:
        env["call"]("POST", "/eligibility/lists", payload=EligibilityListCreate(name="Sans config"), user=CEMILE)
    assert exc.value.status_code == 403
    assert _lists(env)["can_create"] is False
    assert _lists(env)["total"] == 2


# ---------------- E. Cocher : idempotent, journal une fois ----------------
def test_e_check_is_saved_once_and_logged_once(env):
    lid = _list_id(env, PLACEMENT)
    first = env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c1", list_id=lid, user=CONSEILLER)
    again = env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c1", list_id=lid, user=CONSEILLER)
    assert first["created"] is True and again["created"] is False
    rows = env["db"][elig.MEMBERSHIPS_COLLECTION].docs
    assert len(rows) == 1 and rows[0]["added_by"] == "user_cons"
    assert env["journal"] == [("c1", f"Éligibilité : ajouté à la liste « {PLACEMENT} »")]
    tab = env["call"]("GET", "/clients/{client_id}/eligibility", client_id="c1", user=CONSEILLER)
    assert [(i["name"], i["checked"]) for i in tab["lists"]] == [(PLACEMENT, True), (RETRAITE, False)]
    assert tab["can_edit"] is True


# ---------------- F. Plusieurs listes ----------------
def test_f_client_can_belong_to_several_lists(env):
    for name in (PLACEMENT, RETRAITE):
        env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c2", list_id=_list_id(env, name), user=CEMILE)
    tab = env["call"]("GET", "/clients/{client_id}/eligibility", client_id="c2", user=CEMILE)
    assert all(i["checked"] for i in tab["lists"])
    assert [i["client_count"] for i in _lists(env)["lists"]] == [1, 1]


# ---------------- G. Décocher : seule l'association disparaît ----------------
def test_g_uncheck_removes_only_the_association(env):
    p, r = _list_id(env, PLACEMENT), _list_id(env, RETRAITE)
    for lid in (p, r):
        env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c1", list_id=lid, user=CEMILE)
    out = env["call"]("DELETE", "/clients/{client_id}/eligibility/{list_id}", client_id="c1", list_id=p, user=CEMILE)
    again = env["call"]("DELETE", "/clients/{client_id}/eligibility/{list_id}", client_id="c1", list_id=p, user=CEMILE)
    assert out["removed"] is True and again["removed"] is False
    db = env["db"]
    assert [(m["list_id"], m["client_id"]) for m in db[elig.MEMBERSHIPS_COLLECTION].docs] == [(r, "c1")]
    assert len(db[elig.LISTS_COLLECTION].docs) == 2
    assert _run(db.clients.find_one({"id": "c1"})) is not None
    listed = env["call"]("GET", "/eligibility/lists/{list_id}/clients", list_id=p, user=CEMILE, q=None, page=1, page_size=50)
    assert listed["total"] == 0


# ---------------- H. Clients d'une liste : périmètre, recherche, pagination ----------------
def test_h_list_clients_respect_scope_search_and_pages(env):
    lid = _list_id(env, PLACEMENT)
    for cid in ("c1", "c2", "c3"):
        env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id=cid, list_id=lid, user=CEMILE)
    call = lambda user, **kw: env["call"](  # noqa: E731
        "GET", "/eligibility/lists/{list_id}/clients", list_id=lid, user=user,
        q=kw.get("q"), page=kw.get("page", 1), page_size=kw.get("page_size", 50),
    )
    admin = call(CEMILE)
    assert admin["total"] == 3
    assert [c["nom"] for c in admin["items"]] == ["Ândré", "Autre", "Zéphyr"]
    row = admin["items"][0]
    assert set(row) >= {"id", "prenom", "nom", "numero_dossier", "telephone", "email", "statut"}
    assert row["statut"] == "À présenter"
    cons = call(CONSEILLER)
    assert {c["id"] for c in cons["items"]} == {"c1", "c2"}
    assert [i["client_count"] for i in _lists(env, CONSEILLER)["lists"]] == [2, 0]
    assert [c["id"] for c in call(CEMILE, q="zephyr")["items"]] == ["c1"]
    assert [c["id"] for c in call(CEMILE, q="bruno andre")["items"]] == ["c2"]
    assert [c["id"] for c in call(CEMILE, q="DOS-0003")["items"]] == ["c3"]
    assert call(CEMILE, q="introuvable")["items"] == []
    page2 = call(CEMILE, page=2, page_size=2)
    assert page2["total"] == 3 and [c["id"] for c in page2["items"]] == ["c1"]
    with pytest.raises(HTTPException) as exc:
        env["call"](
            "GET", "/eligibility/lists/{list_id}/clients", list_id="inconnue", user=CEMILE, q=None, page=1, page_size=50,
        )
    assert exc.value.status_code == 404


# ---------------- I. Droits sur la fiche ----------------
def test_i_client_access_and_edit_rights(env):
    lid = _list_id(env, PLACEMENT)
    for method in ("PUT", "DELETE"):
        with pytest.raises(HTTPException) as exc:
            env["call"](method, "/clients/{client_id}/eligibility/{list_id}", client_id="c3", list_id=lid, user=CONSEILLER)
        assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        env["call"]("GET", "/clients/{client_id}/eligibility", client_id="c3", user=CONSEILLER)
    assert exc.value.status_code == 403
    tab = env["call"]("GET", "/clients/{client_id}/eligibility", client_id="c3", user=READ_ONLY)
    assert tab["can_edit"] is False
    with pytest.raises(HTTPException) as exc:
        env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c3", list_id=lid, user=READ_ONLY)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="inconnu", list_id=lid, user=CEMILE)
    assert exc.value.status_code == 404
    assert env["db"][elig.MEMBERSHIPS_COLLECTION].docs == []


# ---------------- J. Liste inactive ----------------
def test_j_inactive_list_is_hidden_and_locked(env):
    db = env["db"]
    lid = _list_id(env, RETRAITE)
    env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c1", list_id=lid, user=CEMILE)
    next(d for d in db[elig.LISTS_COLLECTION].docs if d["_id"] == lid)["is_active"] = False
    assert [i["name"] for i in _lists(env)["lists"]] == [PLACEMENT]
    tab = env["call"]("GET", "/clients/{client_id}/eligibility", client_id="c1", user=CEMILE)
    assert [i["name"] for i in tab["lists"]] == [PLACEMENT]
    with pytest.raises(HTTPException) as exc:
        env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c2", list_id=lid, user=CEMILE)
    assert exc.value.status_code == 409
    assert env["call"]("DELETE", "/clients/{client_id}/eligibility/{list_id}", client_id="c1", list_id=lid, user=CEMILE)["removed"]
    assert _run(elig.ensure_setup(db)) == 0
    assert next(d for d in db[elig.LISTS_COLLECTION].docs if d["_id"] == lid)["is_active"] is False


# ---------------- K. Table des droits et suppression de fiche ----------------
def test_k_route_permissions_and_client_deletion(env):
    view = (PERM_CLIENTS_VIEW, PERM_DOSSIERS_VIEW)
    edit = (PERM_CLIENTS_EDIT, PERM_DOSSIERS_EDIT)
    assert permission_for_request("GET", "/api/eligibility/lists") == view
    assert permission_for_request("GET", "/api/eligibility/lists/abc/clients") == view
    assert permission_for_request("GET", "/api/clients/c1/eligibility") == view
    assert permission_for_request("PUT", "/api/clients/c1/eligibility/abc") == edit
    assert permission_for_request("DELETE", "/api/clients/c1/eligibility/abc") == edit
    assert permission_for_request("POST", "/api/eligibility/lists") is None
    assert permission_for_request("DELETE", "/api/clients/c1") == (
        "clients.delete", "dossiers.delete",
    )
    db = env["db"]
    for name in (PLACEMENT, RETRAITE):
        env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c1", list_id=_list_id(env, name), user=CEMILE)
    env["call"]("PUT", "/clients/{client_id}/eligibility/{list_id}", client_id="c2", list_id=_list_id(env, PLACEMENT), user=CEMILE)
    assert _run(elig.remove_client_memberships(db, "c1")) == 2
    assert [m["client_id"] for m in db[elig.MEMBERSHIPS_COLLECTION].docs] == ["c2"]


def test_normalized_name_ignores_case_accents_and_dashes():
    assert elig.normalize_list_name(RETRAITE) == elig.normalize_list_name("retraite POPULAIRE-rente viagere a taux reduit")
    assert elig.normalize_list_name("Placement à tranche") == "placement a tranche"
    with pytest.raises(ValueError):
        elig.clean_list_name("x" * (elig.LIST_NAME_MAX + 1))
