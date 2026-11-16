"""Unit tests for CRM access permissions."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from access_control import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_CEO,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    ROLES,
    ROLE_LABELS,
    LEGACY_PERMISSION_KEYS,
    PERMISSION_KEYS,
    PERMISSION_CATALOG,
    PHASE2_USERS_MANAGE_INHERITED_KEYS,
    PERM_USERS_MANAGE,
    PERM_MESSAGERIE_VIEW,
    PERM_ENTREPRISES_VIEW,
    PERM_ENTREPRISES_CREATE,
    PERM_ENTREPRISES_UPDATE,
    PERM_SUIVI_TECHNIQUE_VIEW,
    PERM_ROLES_MANAGE,
    PERM_CLIENTS_VIEW,
    PERM_CLIENTS_EDIT,
    PERM_CLIENTS_CREATE,
    PERM_DOSSIERS_VIEW,
    PERM_DOSSIERS_EDIT,
    PERM_DOCUMENTS_ADD,
    PERM_SUIVI_3P_VIEW,
    PERM_SUIVI_3P_EDIT,
    PERM_DEMANDES_OFFRES_PROCESS,
    PERM_RAPPELS_VIEW,
    PERM_RAPPELS_EDIT,
    PERM_LAMAL_MODULE_ACCESS,
    default_permissions,
    default_see_all_dossiers,
    resolve_permissions,
    resolve_effective_permissions,
    resolve_see_all_dossiers,
    role_seed_document,
    role_template_permissions,
    ensure_roles_seeded,
    backfill_phase2_admin_module_permissions,
    merge_phase2_permission_keys,
    split_permission_key,
    user_from_doc,
    is_global_viewer,
    can_access_client,
    clients_base_query,
    force_conseiller_on_write,
    permission_for_request,
    has_perm,
    require_perm,
)


def _doc(**kwargs):
    base = {
        "user_id": "user_valentin",
        "email": "valentin@cabinet.ch",
        "prenom": "Valentin",
        "nom": "Lugnier",
        "name": "Valentin Lugnier",
        "role": ROLE_CONSEILLER,
        "conseiller": "Valentin Lugnier",
        "active": True,
    }
    base.update(kwargs)
    return base


def test_conseiller_defaults_hide_user_admin_and_other_dossiers():
    perms = default_permissions(ROLE_CONSEILLER)
    assert perms[PERM_CLIENTS_VIEW] is True
    assert perms[PERM_USERS_MANAGE] is False
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        assert perms[key] is False
    assert perms[PERM_ROLES_MANAGE] is False
    assert default_see_all_dossiers(ROLE_CONSEILLER) is False


def test_admin_defaults_see_all_and_manage_users():
    perms = default_permissions(ROLE_ADMIN)
    assert perms[PERM_USERS_MANAGE] is True
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        assert perms[key] is True
    assert perms[PERM_ROLES_MANAGE] is False
    assert default_see_all_dossiers(ROLE_ADMIN) is True
    assert default_see_all_dossiers(ROLE_CEO) is True
    assert default_permissions(ROLE_CEO)[PERM_USERS_MANAGE] is False
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        assert default_permissions(ROLE_CEO)[key] is False


def test_stored_permission_override():
    doc = _doc(permissions={PERM_CLIENTS_VIEW: False, PERM_USERS_MANAGE: False})
    perms = resolve_permissions(doc)
    assert perms[PERM_CLIENTS_VIEW] is False
    assert perms[PERM_CLIENTS_CREATE] is True


def test_legacy_user_without_permissions_dict():
    admin = resolve_permissions({"role": ROLE_ADMIN, "can_manage_users": True})
    assert admin[PERM_USERS_MANAGE] is True
    conseiller = resolve_permissions({"role": ROLE_CONSEILLER})
    assert conseiller[PERM_USERS_MANAGE] is False
    assert resolve_see_all_dossiers({"role": ROLE_ADMIN}) is True
    assert resolve_see_all_dossiers({"role": ROLE_CONSEILLER}) is False
    assert resolve_see_all_dossiers({"role": ROLE_CONSEILLER, "see_all_dossiers": True}) is True


def test_conseiller_with_all_dossiers_flag():
    user = user_from_doc(_doc(see_all_dossiers=True))
    assert is_global_viewer(user) is True
    assert can_access_client(user, {"conseiller": "Alberto Mendes"}) is True
    q = clients_base_query(user)
    assert "conseiller" not in q


def test_conseiller_scoped_to_own_dossiers():
    user = user_from_doc(_doc())
    assert is_global_viewer(user) is False
    assert can_access_client(user, {"conseiller": "Valentin Lugnier"}) is True
    assert can_access_client(user, {"conseiller": "Alberto Mendes"}) is False
    q = clients_base_query(user)
    assert "$or" in q
    assert any(
        isinstance(clause.get("conseiller"), dict) and clause["conseiller"].get("$options") == "i"
        for clause in q["$or"]
    )
    assert force_conseiller_on_write(user, "Alberto Mendes") == "Valentin Lugnier"


def test_conseiller_sees_dossiers_case_insensitive_and_by_email():
    """Compte « Valentin LUGNIER » voit aussi les dossiers « Valentin Lugnier » / agent_email."""
    user = user_from_doc(_doc(conseiller="Valentin LUGNIER", email="vlugnier@agencemendes.ch"))
    assert can_access_client(user, {"conseiller": "Valentin Lugnier"}) is True
    assert can_access_client(user, {"conseiller": "valentin lugnier"}) is True
    assert can_access_client(user, {"agent_email": "vlugnier@agencemendes.ch"}) is True
    assert can_access_client(user, {"agent_email": "VLUGNIER@agencemendes.ch"}) is True
    assert can_access_client(user, {"conseiller": "Alberto Mendes"}) is False
    q = clients_base_query(user, for_dossiers=True)
    assert q["in_dossiers"] == {"$ne": False}
    assert any(
        (c.get("agent_email") or {}).get("$regex", "").lower().find("vlugnier") >= 0
        for c in q["$or"]
    )


def test_admin_still_sees_all_dossiers():
    user = user_from_doc(_doc(role=ROLE_ADMIN, see_all_dossiers=True, conseiller=None))
    assert is_global_viewer(user) is True
    q = clients_base_query(user, for_dossiers=True)
    assert "$or" not in q
    assert "conseiller" not in q


def test_dossiers_scope_excludes_hub_stubs():
    user = user_from_doc(_doc(see_all_dossiers=True))
    q_all = clients_base_query(user, for_dossiers=False)
    assert "in_dossiers" not in q_all
    q_dos = clients_base_query(user, for_dossiers=True)
    assert q_dos["in_dossiers"] == {"$ne": False}


def test_route_permissions():
    assert permission_for_request("GET", "/api/auth/me") is None
    assert permission_for_request("GET", "/api/users") == PERM_USERS_MANAGE
    assert permission_for_request("GET", "/api/clients") == (
        PERM_CLIENTS_VIEW,
        PERM_DOSSIERS_VIEW,
        "agenda.view",
        PERM_RAPPELS_VIEW,
        "demandes_offres.view",
        "suivi_3p.view",
    )
    assert permission_for_request("POST", "/api/clients") == (PERM_CLIENTS_CREATE, "dossiers.create")
    assert permission_for_request("PATCH", "/api/clients/abc/statut") == PERM_DOSSIERS_EDIT
    assert permission_for_request("GET", "/api/dossiers/stats") == PERM_DOSSIERS_VIEW
    assert permission_for_request("PATCH", "/api/clients/abc/lpp-funds/person") == PERM_DOSSIERS_EDIT
    assert permission_for_request("POST", "/api/clients/abc/documents") == PERM_DOCUMENTS_ADD
    assert permission_for_request("GET", "/api/clients/abc/journal") == (
        PERM_CLIENTS_VIEW,
        PERM_DOSSIERS_VIEW,
    )
    assert permission_for_request("POST", "/api/clients/abc/journal") == PERM_CLIENTS_EDIT
    assert permission_for_request("PATCH", "/api/clients/abc/journal/act1") == PERM_CLIENTS_EDIT
    assert permission_for_request("PATCH", "/api/clients/abc/journal/act1/treated") == PERM_CLIENTS_EDIT
    assert permission_for_request("DELETE", "/api/clients/abc/journal/act1") == PERM_CLIENTS_EDIT
    assert permission_for_request("GET", "/api/suivi-3p") == PERM_SUIVI_3P_VIEW
    assert permission_for_request("PUT", "/api/suivi-3p/abc") == PERM_SUIVI_3P_EDIT
    assert permission_for_request("GET", "/api/rappels") == PERM_RAPPELS_VIEW
    assert permission_for_request("GET", "/api/rappels/email-status") == PERM_RAPPELS_VIEW
    assert permission_for_request("POST", "/api/rappels") == PERM_RAPPELS_EDIT
    assert permission_for_request("GET", "/api/users/conseillers") is None


def test_has_perm_reads_user_permissions():
    user = user_from_doc(_doc(permissions={PERM_CLIENTS_VIEW: False}))
    assert has_perm(user, PERM_CLIENTS_VIEW) is False
    assert has_perm(user, PERM_CLIENTS_CREATE) is True
    assert has_perm(user, PERM_USERS_MANAGE) is False


# ---------- Phase 1 RBAC : roles seed + resolve_effective + deny nouvelles clés ----------


def test_legacy_permission_keys_match_catalog():
    assert LEGACY_PERMISSION_KEYS == frozenset(PERMISSION_KEYS)
    assert PERM_USERS_MANAGE in LEGACY_PERMISSION_KEYS


def test_split_permission_key_module_action_convention():
    assert split_permission_key("clients.view") == {"module": "clients", "action": "view"}
    assert split_permission_key("demandes_offres.process") == {
        "module": "demandes_offres",
        "action": "process",
    }
    assert split_permission_key(PERM_LAMAL_MODULE_ACCESS) == {
        "module": PERM_LAMAL_MODULE_ACCESS,
        "action": "access",
    }


def test_permission_catalog_has_module_action_metadata():
    for group in PERMISSION_CATALOG:
        for item in group["items"]:
            assert item.get("module")
            assert item.get("action")
            assert item["key"]
            meta = split_permission_key(item["key"])
            assert item["module"] == meta["module"]
            assert item["action"] == meta["action"]


def test_role_seed_document_matches_default_permissions():
    for role_id in ROLES:
        doc = role_seed_document(role_id, updated_at="2026-01-01T00:00:00+00:00")
        assert doc["id"] == role_id
        assert doc["label"] == ROLE_LABELS[role_id]
        assert doc["active"] is True
        assert doc["permissions"] == default_permissions(role_id)
        assert doc["see_all_dossiers_default"] == default_see_all_dossiers(role_id)
        assert doc["updated_at"] == "2026-01-01T00:00:00+00:00"


def test_role_template_from_seed_doc():
    seed = role_seed_document(ROLE_GESTIONNAIRE_OFFRES)
    assert role_template_permissions(ROLE_GESTIONNAIRE_OFFRES, role_doc=seed) == default_permissions(
        ROLE_GESTIONNAIRE_OFFRES
    )


def _historical_resolve_permissions(doc: dict):
    """Comportement pré-Phase 1 (snapshot + LAMal), pour non-régression."""
    from access_control import sanitize_permissions, is_named_alberto_mendes, LAMAL_OWNER_EMAIL

    role = doc.get("role") or ROLE_CONSEILLER
    stored = doc.get("permissions")
    if isinstance(stored, dict) and stored:
        perms = sanitize_permissions(stored, role)
    else:
        perms = default_permissions(role)
        if doc.get("can_manage_users"):
            perms[PERM_USERS_MANAGE] = True
    email = (doc.get("email") or "").strip().lower()
    perms[PERM_LAMAL_MODULE_ACCESS] = email == LAMAL_OWNER_EMAIL or is_named_alberto_mendes(doc)
    return perms


def test_resolve_effective_matches_historical_behavior():
    cases = [
        _doc(),
        _doc(role=ROLE_ADMIN, permissions=default_permissions(ROLE_ADMIN)),
        _doc(role=ROLE_CEO),
        _doc(role=ROLE_GESTIONNAIRE_OFFRES),
        _doc(permissions={PERM_CLIENTS_VIEW: False, PERM_USERS_MANAGE: False}),
        {"role": ROLE_ADMIN, "can_manage_users": True},
        {"role": ROLE_CONSEILLER},
        _doc(email="cdemirtas@agencemendes.ch", role=ROLE_ADMIN),
    ]
    for doc in cases:
        effective = resolve_effective_permissions(doc)
        assert effective == _historical_resolve_permissions(doc)
        assert resolve_permissions(doc) == effective


def test_empty_permission_overrides_keeps_current_behavior():
    doc = _doc(permissions={PERM_CLIENTS_VIEW: False}, permission_overrides={})
    assert resolve_effective_permissions(doc) == resolve_permissions(
        {k: v for k, v in doc.items() if k != "permission_overrides"}
    )
    doc2 = _doc(permission_overrides=None)
    assert resolve_effective_permissions(doc2)[PERM_CLIENTS_VIEW] is True
    assert resolve_effective_permissions(doc2)[PERM_USERS_MANAGE] is False
    assert resolve_effective_permissions(doc2)[PERM_DEMANDES_OFFRES_PROCESS] is False


def test_permission_overrides_overlay_on_template():
    doc = _doc(
        permissions=default_permissions(ROLE_CONSEILLER),
        permission_overrides={PERM_CLIENTS_VIEW: False, PERM_DEMANDES_OFFRES_PROCESS: True},
    )
    perms = resolve_effective_permissions(doc)
    assert perms[PERM_CLIENTS_VIEW] is False
    assert perms[PERM_DEMANDES_OFFRES_PROCESS] is True
    # LAMal non contournable via override
    assert perms[PERM_LAMAL_MODULE_ACCESS] is False


def test_admin_effective_permissions_unchanged():
    user = user_from_doc(
        _doc(
            role=ROLE_ADMIN,
            email="admin@cabinet.ch",
            permissions=default_permissions(ROLE_ADMIN),
            see_all_dossiers=True,
            conseiller=None,
        )
    )
    assert has_perm(user, PERM_USERS_MANAGE) is True
    assert has_perm(user, PERM_MESSAGERIE_VIEW) is True
    assert has_perm(user, PERM_ENTREPRISES_VIEW) is True
    assert has_perm(user, PERM_SUIVI_TECHNIQUE_VIEW) is True
    assert has_perm(user, PERM_ROLES_MANAGE) is False
    assert has_perm(user, PERM_CLIENTS_VIEW) is True
    assert has_perm(user, PERM_DEMANDES_OFFRES_PROCESS) is True
    assert is_global_viewer(user) is True
    assert user.permissions[PERM_USERS_MANAGE] is True


def test_conseiller_effective_permissions_unchanged():
    user = user_from_doc(_doc())
    assert has_perm(user, PERM_USERS_MANAGE) is False
    assert has_perm(user, PERM_MESSAGERIE_VIEW) is False
    assert has_perm(user, PERM_ENTREPRISES_VIEW) is False
    assert has_perm(user, PERM_SUIVI_TECHNIQUE_VIEW) is False
    assert has_perm(user, PERM_CLIENTS_VIEW) is True
    assert has_perm(user, PERM_DEMANDES_OFFRES_PROCESS) is False
    assert is_global_viewer(user) is False


def test_unknown_permission_key_is_denied():
    user = user_from_doc(_doc(role=ROLE_ADMIN, see_all_dossiers=True))
    assert PERM_MESSAGERIE_VIEW in LEGACY_PERMISSION_KEYS
    assert has_perm(user, PERM_MESSAGERIE_VIEW) is True
    assert has_perm(user, "totally.unknown.flag") is False
    assert has_perm(user, PERM_USERS_MANAGE) is True
    assert has_perm(user, PERM_ROLES_MANAGE) is False


def test_legacy_missing_catalog_key_still_allowed():
    """Clé du catalogue absente du snapshot → allow (comportement historique)."""
    user = user_from_doc(_doc())
    # Simule un snapshot incomplet (ne doit pas arriver en prod après resolve, mais has_perm legacy).
    user.permissions = {PERM_CLIENTS_VIEW: True}
    assert has_perm(user, PERM_CLIENTS_CREATE) is True
    assert has_perm(user, "future_module.view") is False


class _FakeFindCursor:
    def __init__(self, rows):
        self._rows = list(rows)

    def __aiter__(self):
        self._iter = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeRolesColl:
    def __init__(self):
        self.rows = []

    async def find_one(self, query, projection=None):
        for row in self.rows:
            if row.get("id") == query.get("id"):
                return {"_id": "x"} if projection else dict(row)
        return None

    def find(self, query=None, projection=None):
        out = []
        for i, row in enumerate(self.rows):
            copy = dict(row)
            copy.setdefault("_id", f"role_{i}")
            out.append(copy)
        return _FakeFindCursor(out)

    async def insert_one(self, doc):
        self.rows.append(dict(doc))
        return None

    async def update_one(self, query, update):
        for row in self.rows:
            if query.get("_id") is not None and row.get("_id") == query.get("_id"):
                row.update(update.get("$set") or {})
                return
            if query.get("id") is not None and row.get("id") == query.get("id"):
                row.update(update.get("$set") or {})
                return


class _FakeUsersColl:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def find(self, query=None, projection=None):
        out = []
        for i, row in enumerate(self.rows):
            copy = dict(row)
            copy.setdefault("_id", f"user_{i}")
            out.append(copy)
        return _FakeFindCursor(out)

    async def update_one(self, query, update):
        for row in self.rows:
            if query.get("_id") is not None and row.get("_id") == query.get("_id"):
                row.update(update.get("$set") or {})
                return
            if query.get("user_id") is not None and row.get("user_id") == query.get("user_id"):
                row.update(update.get("$set") or {})
                return


class _FakeRolesDb:
    def __init__(self, users=None):
        self.roles = _FakeRolesColl()
        self.users = _FakeUsersColl(users)
        self.access_policy_journal = _FakeJournalColl()

    def __getitem__(self, name):
        if name == "roles":
            return self.roles
        if name == "access_policy_journal":
            return self.access_policy_journal
        raise KeyError(name)


class _FakeJournalColl:
    def __init__(self):
        self.rows = []

    async def insert_one(self, doc):
        self.rows.append(dict(doc))


def test_ensure_roles_seeded_inserts_four_roles_once():
    db = _FakeRolesDb()

    first = asyncio.run(ensure_roles_seeded(db))
    assert first["created"] == 4
    assert first["skipped"] == 0
    assert len(db.roles.rows) == 4
    ids = {r["id"] for r in db.roles.rows}
    assert ids == set(ROLES)
    for row in db.roles.rows:
        assert row["permissions"] == default_permissions(row["id"])

    second = asyncio.run(ensure_roles_seeded(db))
    assert second["created"] == 0
    assert second["skipped"] == 4
    assert len(db.roles.rows) == 4
    # Journal minimal au premier seed
    assert any(e.get("event_type") == "roles_seed" for e in db.access_policy_journal.rows)


# ---------- Phase 2 RBAC : modules admin indépendants ----------


def test_phase2_route_permissions_split_admin_modules():
    assert permission_for_request("GET", "/api/emails") == PERM_MESSAGERIE_VIEW
    assert permission_for_request("GET", "/api/admin/email-logs") == PERM_MESSAGERIE_VIEW
    assert permission_for_request("GET", "/api/rappel-email-logs") == PERM_MESSAGERIE_VIEW
    assert permission_for_request("GET", "/api/entreprises") == PERM_ENTREPRISES_VIEW
    assert permission_for_request("POST", "/api/entreprises") == PERM_ENTREPRISES_CREATE
    assert permission_for_request("PUT", "/api/entreprises/abc") == PERM_ENTREPRISES_UPDATE
    assert permission_for_request("POST", "/api/entreprises/ensure-agence-mendes") == PERM_ENTREPRISES_CREATE
    assert permission_for_request("GET", "/api/admin/tech-status") == PERM_SUIVI_TECHNIQUE_VIEW
    assert permission_for_request("POST", "/api/admin/tech-status/run-audit") == PERM_SUIVI_TECHNIQUE_VIEW
    # Autres routes admin / users restent users.manage
    assert permission_for_request("GET", "/api/users") == PERM_USERS_MANAGE
    assert permission_for_request("POST", "/api/admin/smtp-test") == PERM_USERS_MANAGE


def test_phase2_users_manage_true_inherits_missing_flags():
    # Snapshot pré-Phase 2 : users.manage true, nouvelles clés absentes.
    old_admin = default_permissions(ROLE_ADMIN)
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        old_admin.pop(key, None)
    old_admin.pop(PERM_ROLES_MANAGE, None)
    perms = resolve_effective_permissions(_doc(role=ROLE_ADMIN, permissions=old_admin))
    assert perms[PERM_USERS_MANAGE] is True
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        assert perms[key] is True
    assert perms[PERM_ROLES_MANAGE] is False


def test_phase2_users_manage_false_inherits_false():
    old = default_permissions(ROLE_CONSEILLER)
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        old.pop(key, None)
    old.pop(PERM_ROLES_MANAGE, None)
    perms = resolve_effective_permissions(_doc(permissions=old))
    assert perms[PERM_USERS_MANAGE] is False
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        assert perms[key] is False


def test_phase2_explicit_messagerie_only_keeps_independence():
    base = default_permissions(ROLE_CONSEILLER)
    base[PERM_MESSAGERIE_VIEW] = True
    base[PERM_USERS_MANAGE] = False
    user = user_from_doc(_doc(permissions=base))
    assert has_perm(user, PERM_MESSAGERIE_VIEW) is True
    assert has_perm(user, PERM_USERS_MANAGE) is False
    assert has_perm(user, PERM_ENTREPRISES_VIEW) is False
    assert has_perm(user, PERM_SUIVI_TECHNIQUE_VIEW) is False
    require_perm(user, PERM_MESSAGERIE_VIEW)
    try:
        require_perm(user, PERM_USERS_MANAGE)
        assert False, "expected 403"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403


def test_phase2_merge_backfill_keys():
    merged, changed = merge_phase2_permission_keys(
        {PERM_USERS_MANAGE: True, PERM_CLIENTS_VIEW: True},
        manage=True,
    )
    assert changed is True
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        assert merged[key] is True
    assert merged[PERM_ROLES_MANAGE] is False
    merged2, changed2 = merge_phase2_permission_keys(merged, manage=True)
    assert changed2 is False


def test_phase2_backfill_users_and_roles():
    # Rôles seed Phase 1 sans clés Phase 2.
    admin_perms = default_permissions(ROLE_ADMIN)
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        admin_perms.pop(key, None)
    admin_perms.pop(PERM_ROLES_MANAGE, None)
    conseil_perms = default_permissions(ROLE_CONSEILLER)
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        conseil_perms.pop(key, None)
    conseil_perms.pop(PERM_ROLES_MANAGE, None)

    db = _FakeRolesDb(
        users=[
            {
                "_id": "u1",
                "user_id": "admin1",
                "role": ROLE_ADMIN,
                "permissions": dict(admin_perms),
            },
            {
                "_id": "u2",
                "user_id": "c1",
                "role": ROLE_CONSEILLER,
                "permissions": dict(conseil_perms),
            },
        ]
    )
    db.roles.rows = [
        {"_id": "r1", "id": ROLE_ADMIN, "permissions": dict(admin_perms)},
        {"_id": "r2", "id": ROLE_CONSEILLER, "permissions": dict(conseil_perms)},
    ]
    result = asyncio.run(backfill_phase2_admin_module_permissions(db))
    assert result["users_updated"] == 2
    assert result["roles_updated"] == 2
    admin_user = next(u for u in db.users.rows if u["user_id"] == "admin1")
    conseil_user = next(u for u in db.users.rows if u["user_id"] == "c1")
    for key in PHASE2_USERS_MANAGE_INHERITED_KEYS:
        assert admin_user["permissions"][key] is True
        assert conseil_user["permissions"][key] is False
    assert admin_user["permissions"][PERM_ROLES_MANAGE] is False
    # Idempotent
    second = asyncio.run(backfill_phase2_admin_module_permissions(db))
    assert second["users_updated"] == 0
    assert second["roles_updated"] == 0
