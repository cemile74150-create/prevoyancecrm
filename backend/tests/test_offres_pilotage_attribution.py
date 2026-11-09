"""Suivi des offres : attribution des dossiers, statuts traitement / commercial,
périmètre personnel du gestionnaire, droits d'écriture.

Les routes sont appelées directement sur une base Mongo en mémoire.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import demandes_offres_routes  # noqa: E402
import email_service  # noqa: E402
from access_control import (  # noqa: E402
    PERM_DEMANDES_OFFRES_PROCESS,
    PERM_USERS_MANAGE,
    ROLE_ADMIN,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    TENANT_USER_ID,
    permission_for_request,
    user_from_doc,
)
from demandes_offres_3p import COLLECTION, serialize_demande  # noqa: E402
from demandes_offres_pilotage import (  # noqa: E402
    BOUTONS_TRAITER,
    COMMERCIAL_LABELS,
    RDV_RETARD_JOURS,
    TRAITEMENT_CODES,
    bouton_traiter,
    commercial_code,
    compute_pilotage,
    en_retard_rdv,
    filtrer_lignes,
    pilotage_tags,
    refus_ecriture_gestion,
    traitement_code,
    transmis_agent_at,
)
from demandes_offres_routes import (  # noqa: E402
    ReattributionRequest,
    attach_demandes_offres_routes,
    gestion_write_target,
)

NOW = datetime(2026, 11, 9, 10, tzinfo=timezone.utc)

# --------------------------------------------------------------------------- base en mémoire

_MISSING = object()


def _get(doc, key):
    current = doc
    for part in key.split("."):
        if isinstance(current, list):
            values = [item.get(part, _MISSING) for item in current if isinstance(item, dict)]
            values = [v for v in values if v is not _MISSING]
            return values if values else _MISSING
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _eq(value, expected):
    if isinstance(value, list) and not isinstance(expected, list):
        return expected in value
    return value == expected


def _regex(value, pattern, options):
    flags = re.I if "i" in (options or "") else 0
    values = value if isinstance(value, list) else [value]
    return any(isinstance(v, str) and re.search(pattern, v, flags) for v in values)


def _match(doc, query):
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_match(doc, sub) for sub in expected):
                return False
            continue
        if key == "$and":
            if not all(_match(doc, sub) for sub in expected):
                return False
            continue
        value = _get(doc, key)
        present = value is not _MISSING
        if isinstance(expected, dict) and any(str(k).startswith("$") for k in expected):
            for op, arg in expected.items():
                if op == "$ne" and present and _eq(value, arg):
                    return False
                if op == "$exists" and present != bool(arg):
                    return False
                if op == "$in" and not any(_eq(value if present else None, a) for a in arg):
                    return False
                if op == "$nin" and present and any(_eq(value, a) for a in arg):
                    return False
                if op == "$lt" and not (present and value is not None and value < arg):
                    return False
                if op == "$regex" and not (present and _regex(value, arg, expected.get("$options"))):
                    return False
            continue
        if expected is None:
            if present and value is not None:
                return False
            continue
        if not present or not _eq(value, expected):
            return False
    return True


class _Result:
    def __init__(self, n):
        self.modified_count = n
        self.matched_count = n


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda r: str(r.get(key) or ""), reverse=direction == -1)
        return self

    async def to_list(self, limit=None):
        return self.rows[:limit] if limit else self.rows


class FakeCollection:
    def __init__(self, interleave=False):
        self.docs = []
        self.interleave = interleave

    async def find_one(self, query, projection=None, **_kw):
        found = None
        for doc in self.docs:
            if _match(doc, query):
                found = copy.deepcopy(doc)
                found.pop("_id", None)
                break
        if self.interleave:
            await asyncio.sleep(0)
        return found

    def find(self, query=None, projection=None):
        return FakeCursor([copy.deepcopy(d) for d in self.docs if _match(d, query or {})])

    async def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))

    def _apply(self, doc, update):
        for key, value in (update.get("$set") or {}).items():
            doc[key] = copy.deepcopy(value)
        for key, value in (update.get("$setOnInsert") or {}).items():
            doc.setdefault(key, copy.deepcopy(value))
        for key, value in (update.get("$push") or {}).items():
            items = value["$each"] if isinstance(value, dict) and "$each" in value else [value]
            doc.setdefault(key, []).extend(copy.deepcopy(items))
        for key, value in (update.get("$addToSet") or {}).items():
            target = doc.setdefault(key, [])
            if value not in target:
                target.append(value)
        for key, value in (update.get("$inc") or {}).items():
            doc[key] = (doc.get(key) or 0) + value

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _match(doc, query):
                self._apply(doc, update)
                return _Result(1)
        if upsert:
            doc = {k: v for k, v in query.items() if not isinstance(v, dict) and not k.startswith("$")}
            self._apply(doc, update)
            self.docs.append(doc)
        return _Result(0)

    async def update_many(self, query, update):
        n = 0
        for doc in self.docs:
            if _match(doc, query):
                self._apply(doc, update)
                n += 1
        return _Result(n)

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))


class FakeDb:
    def __init__(self, interleave=False):
        self.collections = {}
        self.interleave = interleave

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection(interleave=self.interleave and name == COLLECTION)
        return self.collections[name]

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]


# --------------------------------------------------------------------------- comptes et dossiers

def _user_doc(role, user_id, prenom, nom):
    return {
        "user_id": user_id,
        "email": f"{user_id}@test.ch",
        "prenom": prenom,
        "nom": nom,
        "name": f"{prenom} {nom}",
        "role": role,
        "conseiller": f"{prenom} {nom}",
        "active": True,
    }


USERS = [
    _user_doc(ROLE_ADMIN, "admin-1", "Ada", "Admin"),
    _user_doc(ROLE_GESTIONNAIRE_OFFRES, "gest-1", "Lea", "Gestion"),
    _user_doc(ROLE_GESTIONNAIRE_OFFRES, "gest-2", "Marc", "Offres"),
    _user_doc(ROLE_CONSEILLER, "agent-1", "Camille", "Durand"),
    _user_doc(ROLE_CONSEILLER, "agent-2", "Alex", "Martin"),
]
ADMIN, G1, G2, AGENT, AUTRE_AGENT = (user_from_doc(u) for u in USERS)


def _demande(did, **extra):
    base = {
        "id": did,
        "user_id": TENANT_USER_ID,
        "numero": f"OFF-2026-{did[-4:]}",
        "statut": "Demande envoyée",
        "form_type": "pilier3_legacy",
        "compagnies": ["AXA"],
        "created_by_account_id": AGENT.account_id,
        "agent_label": "Camille Durand",
        "agent_email": "agent-1@test.ch",
        "prenom": "Jean",
        "nom": "Client",
        "date_envoi": "2026-11-01T08:00:00+00:00",
        "created_at": "2026-10-30T08:00:00+00:00",
        "updated_at": "2026-11-01T08:00:00+00:00",
        "historique": [],
        "is_deleted": False,
    }
    base.update(extra)
    return base


class Harness:
    def __init__(self, demandes, monkeypatch, *, interleave=False):
        self.db = FakeDb(interleave=interleave)
        router = APIRouter()
        attach_demandes_offres_routes(
            router,
            db=self.db,
            put_object=lambda key, data, content_type: {"path": key, "size": len(data)},
            local_storage_fallback=lambda *a, **k: None,
            file_response_headers=lambda name, inline=False: {},
            mime_types={"pdf": "application/pdf"},
            app_name="test",
            root_dir=str(ROOT),
            load_storage_bytes=lambda path: b"",
        )
        self.router = router
        self.routes = {}
        for route in router.routes:
            for method in route.methods:
                self.routes[(method, route.path)] = route.endpoint
        for doc in demandes:
            asyncio.run(self.db[COLLECTION].insert_one(doc))
        for doc in USERS:
            asyncio.run(self.db["users"].insert_one(doc))
        monkeypatch.setattr(email_service, "offres_email_enabled", lambda: False)

    def endpoint(self, method, path):
        return self.routes[(method, path)]

    def call(self, method, path, **kwargs):
        endpoint = self.endpoint(method, path)
        params = inspect.signature(endpoint).parameters
        for name, param in params.items():
            if name not in kwargs and param.default is not inspect.Parameter.empty:
                default = param.default
                kwargs[name] = getattr(default, "default", default)
        return asyncio.run(endpoint(**kwargs))

    def doc(self, did):
        return asyncio.run(self.db[COLLECTION].find_one({"id": did}))

    def attribuer(self, did, user):
        return self.call("POST", "/demandes-offres/{demande_id}/attribuer", demande_id=did, user=user)

    def reattribuer(self, did, user, cible, motif=None):
        return self.call(
            "POST", "/demandes-offres/{demande_id}/reattribuer",
            demande_id=did, payload=ReattributionRequest(gestionnaire_id=cible, motif=motif), user=user,
        )

    def liste(self, user, **kw):
        return self.call("GET", "/demandes-offres", user=user, **kw)

    def pilotage(self, user, **kw):
        return self.call("GET", "/demandes-offres/pilotage", user=user, **kw)


def _status(exc):
    return exc.value.status_code


# --------------------------------------------------------------------------- attribution

def test_m_attribuer_enregistre_le_gestionnaire_et_passe_en_cours(monkeypatch):
    h = Harness([_demande("d-0001")], monkeypatch)
    out = h.attribuer("d-0001", G1)
    doc = h.doc("d-0001")
    assert doc["gestionnaire_id"] == G1.account_id
    assert doc["gestionnaire_nom"] == "Lea Gestion"
    assert doc["gestionnaire_attribue_at"]
    assert doc["suivi_etape"] == "en_cours"
    assert doc["attributions_historique"][-1]["type"] == "auto_attribution"
    assert any(item.get("action") == "Dossier attribué" for item in doc["historique"])
    assert out["gestionnaire_nom"] == "Lea Gestion"
    assert out["statut_traitement"] == "en_cours"
    assert out["bouton_traiter"]["label"] == "En cours"
    again = h.attribuer("d-0001", G1)
    assert again["gestionnaire_id"] == G1.account_id
    assert len(h.doc("d-0001")["attributions_historique"]) == 1


def test_m_attribuer_ne_recule_pas_un_dossier_plus_avance(monkeypatch):
    h = Harness([_demande("d-0002", suivi_etape="attente_compagnie")], monkeypatch)
    h.attribuer("d-0002", G1)
    assert h.doc("d-0002")["suivi_etape"] == "attente_compagnie"


def test_m_attribuer_refuse_un_dossier_deja_pris(monkeypatch):
    h = Harness([_demande("d-0003")], monkeypatch)
    h.attribuer("d-0003", G1)
    with pytest.raises(HTTPException) as exc:
        h.attribuer("d-0003", G2)
    assert _status(exc) == 409
    assert "Lea Gestion" in exc.value.detail
    assert h.doc("d-0003")["gestionnaire_id"] == G1.account_id


def test_attribution_simultanee_un_seul_gagnant(monkeypatch):
    h = Harness([_demande("d-0004")], monkeypatch, interleave=True)
    endpoint = h.endpoint("POST", "/demandes-offres/{demande_id}/attribuer")

    async def course():
        return await asyncio.gather(
            endpoint(demande_id="d-0004", user=G1),
            endpoint(demande_id="d-0004", user=G2),
            return_exceptions=True,
        )

    results = asyncio.run(course())
    errors = [r for r in results if isinstance(r, HTTPException)]
    wins = [r for r in results if isinstance(r, dict)]
    assert len(wins) == 1 and len(errors) == 1
    assert errors[0].status_code == 409
    doc = h.doc("d-0004")
    assert doc["gestionnaire_id"] == wins[0]["gestionnaire_id"]
    assert len(doc["attributions_historique"]) == 1


def test_m_attribuer_reserve_aux_gestionnaires_et_aux_demandes_soumises(monkeypatch):
    h = Harness([_demande("d-0005"), _demande("d-0006", statut="Brouillon")], monkeypatch)
    with pytest.raises(HTTPException) as exc:
        h.attribuer("d-0005", AGENT)
    assert _status(exc) == 403
    with pytest.raises(HTTPException) as exc:
        h.attribuer("d-0006", G1)
    assert _status(exc) == 409
    assert not h.doc("d-0005").get("gestionnaire_id")


def test_reattribution_admin_avec_historique(monkeypatch):
    h = Harness([_demande("d-0007")], monkeypatch)
    h.attribuer("d-0007", G1)
    out = h.reattribuer("d-0007", ADMIN, G2.account_id, motif="Absence")
    doc = h.doc("d-0007")
    assert doc["gestionnaire_id"] == G2.account_id
    assert doc["gestionnaire_nom"] == "Marc Offres"
    last = doc["attributions_historique"][-1]
    assert last["type"] == "reattribution"
    assert last["ancien_id"] == G1.account_id and last["nouveau_id"] == G2.account_id
    assert last["motif"] == "Absence" and last["par_nom"] == "Ada Admin"
    assert any(item.get("action") == "Dossier réattribué" for item in doc["historique"])
    assert out["gestionnaire_id"] == G2.account_id
    notes = h.db["offre_notifications"].docs
    assert any(n.get("event") == "attribuee_gestionnaire" for n in notes)


def test_reattribution_refusee_aux_gestionnaires_et_cible_inconnue(monkeypatch):
    h = Harness([_demande("d-0008")], monkeypatch)
    h.attribuer("d-0008", G1)
    with pytest.raises(HTTPException) as exc:
        h.reattribuer("d-0008", G1, G2.account_id)
    assert _status(exc) == 403
    with pytest.raises(HTTPException) as exc:
        h.reattribuer("d-0008", AGENT, G2.account_id)
    assert _status(exc) == 403
    with pytest.raises(HTTPException) as exc:
        h.reattribuer("d-0008", ADMIN, AGENT.account_id)
    assert _status(exc) == 422
    assert h.doc("d-0008")["gestionnaire_id"] == G1.account_id


def test_permissions_des_routes_d_attribution():
    assert permission_for_request("POST", "/api/demandes-offres/d1/attribuer") == PERM_DEMANDES_OFFRES_PROCESS
    assert permission_for_request("POST", "/api/demandes-offres/d1/reattribuer") == (
        PERM_DEMANDES_OFFRES_PROCESS, PERM_USERS_MANAGE,
    )


# --------------------------------------------------------------------------- droits d'écriture

def test_gestionnaire_ne_modifie_pas_le_dossier_d_un_collegue():
    doc = _demande("d-0009", gestionnaire_id=G1.account_id, gestionnaire_nom="Lea Gestion")
    assert refus_ecriture_gestion(doc, G1) is None
    assert "Lea Gestion" in refus_ecriture_gestion(doc, G2)
    assert refus_ecriture_gestion(doc, ADMIN) is None
    assert refus_ecriture_gestion(doc, AGENT) is None
    assert refus_ecriture_gestion(_demande("d-0010"), G2) is None
    assert gestion_write_target("POST", "/api/demandes-offres/d-0009/suivi") == "d-0009"
    assert gestion_write_target("POST", "/api/demandes-offres/d-0009/offre") == "d-0009"
    assert gestion_write_target("DELETE", "/api/demandes-offres/d-0009/erreurs/e1") == "d-0009"
    assert gestion_write_target("POST", "/api/demandes-offres/d-0009/attribuer") is None
    assert gestion_write_target("GET", "/api/demandes-offres/d-0009") is None


def test_dependance_utilisateur_renvoie_403_sur_le_dossier_d_un_collegue(monkeypatch):
    doc = _demande("d-0011", gestionnaire_id=G1.account_id, gestionnaire_nom="Lea Gestion")
    h = Harness([doc], monkeypatch)
    dependency = inspect.signature(
        h.endpoint("POST", "/demandes-offres/{demande_id}/attribuer")
    ).parameters["user"].default.dependency
    current = {"user": G2}

    async def fake_session(db, request, authorization):
        return current["user"]

    monkeypatch.setattr(demandes_offres_routes, "resolve_session_user", fake_session)

    class Url:
        def __init__(self, path):
            self.path = path

    class Req:
        def __init__(self, method, path):
            self.method = method
            self.url = Url(path)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(Req("POST", "/api/demandes-offres/d-0011/suivi"), None))
    assert _status(exc) == 403
    assert asyncio.run(dependency(Req("GET", "/api/demandes-offres/d-0011"), None)) is G2
    current["user"] = G1
    assert asyncio.run(dependency(Req("POST", "/api/demandes-offres/d-0011/suivi"), None)) is G1
    current["user"] = ADMIN
    assert asyncio.run(dependency(Req("POST", "/api/demandes-offres/d-0011/suivi"), None)) is ADMIN


# --------------------------------------------------------------------------- périmètres

def _jeu_de_dossiers():
    return [
        _demande("d-0101"),
        _demande("d-0102", gestionnaire_id=G1.account_id, gestionnaire_nom="Lea Gestion", suivi_etape="en_cours"),
        _demande("d-0103", gestionnaire_id=G1.account_id, gestionnaire_nom="Lea Gestion",
                 suivi_etape="attente_compagnie",
                 suivi_evenements=[{"etape": "relance", "at": "2026-11-03T09:00:00+00:00"}]),
        _demande("d-0104", gestionnaire_id=G2.account_id, gestionnaire_nom="Marc Offres",
                 suivi_etape="attente_compagnie"),
        _demande("d-0105", gestionnaire_id=G2.account_id, gestionnaire_nom="Marc Offres",
                 statut="Offre reçue", suivi_etape="offres_partielles"),
        _demande("d-0106", gestionnaire_id=G1.account_id, gestionnaire_nom="Lea Gestion",
                 statut="Offre reçue", suivi_etape="offre_transmise",
                 docs_mis_a_disposition_at="2026-10-10T08:00:00+00:00",
                 suivi_evenements=[
                     {"etape": "offres_partielles", "at": "2026-10-10T08:00:00+00:00"},
                     {"etape": "offre_transmise", "at": "2026-10-20T08:00:00+00:00"},
                 ]),
        _demande("d-0107", statut="Offre signée", created_by_account_id=AUTRE_AGENT.account_id,
                 agent_label="Alex Martin", agent_email="agent-2@test.ch",
                 docs_mis_a_disposition_at="2026-10-01T08:00:00+00:00"),
        _demande("d-0108", statut="Offre non signée", gestionnaire_id=G2.account_id, gestionnaire_nom="Marc Offres",
                 docs_mis_a_disposition_at="2026-10-01T08:00:00+00:00"),
        _demande("d-0109", statut="Offre envoyée au client", gestionnaire_id=G1.account_id,
                 gestionnaire_nom="Lea Gestion", docs_mis_a_disposition_at="2026-10-15T08:00:00+00:00",
                 offres_transmises_agent_at="2026-10-15T08:00:00+00:00",
                 envoi_client={"at": "2026-10-16T08:00:00+00:00", "by": "Camille Durand", "by_id": "agent-1"}),
        _demande("d-0110", statut="Brouillon"),
    ]


def test_espace_personnel_ne_montre_que_mes_dossiers(monkeypatch):
    h = Harness(_jeu_de_dossiers(), monkeypatch)
    mine = h.liste(G1, perimetre="personnel")
    assert sorted(r["id"] for r in mine) == ["d-0102", "d-0103", "d-0106", "d-0109"]
    theirs = h.liste(G2, perimetre="personnel")
    assert sorted(r["id"] for r in theirs) == ["d-0104", "d-0105", "d-0108"]
    perso = h.pilotage(G1, perimetre="personnel")
    assert perso["perimetre"] == "personnel"
    assert perso["indicateurs"]["soumises"] == 4
    assert perso["indicateurs"]["non_attribuees"] == 0
    assert perso["gestionnaires"] == []
    with pytest.raises(HTTPException) as exc:
        h.liste(AGENT, perimetre="personnel")
    assert _status(exc) == 403


def test_six_compteurs_traitement_et_cartes_globales(monkeypatch):
    h = Harness(_jeu_de_dossiers(), monkeypatch)
    data = h.pilotage(G1)
    ind = data["indicateurs"]
    assert data["perimetre"] == "global"
    assert ind["soumises"] == 9
    assert ind["non_attribuees"] == 2 and ind["attribuees"] == 7
    assert [t["code"] for t in data["traitement"]] == list(TRAITEMENT_CODES)
    counts = {t["code"]: t["count"] for t in data["traitement"]}
    assert counts == {
        "en_attente": 1,
        "en_cours": 1,
        "attente_compagnie": 1,
        "relance": 1,
        "offres_partielles": 1,
        "offre_transmise": 4,
    }
    assert sum(counts.values()) == ind["soumises"]
    assert ind["en_cours_global"] == 4 and ind["termines"] == 4
    assert ind["commercial:signee"] == 1 and ind["commercial:non_signee"] == 1
    assert ind["attente_decision"] == 1
    assert ind["commercial:non_renseigne"] == 1
    assert data["taux_signature"] == 50.0
    assert [s["id"] for s in data["pipeline"]] == ["attribution", "traitement", "commercial"]
    lignes = {g["id"]: g for g in data["gestionnaires"]}
    assert lignes[G1.account_id]["attribues"] == 4
    assert lignes[G1.account_id]["attente_compagnie"] == 1
    assert lignes[G2.account_id]["attribues"] == 3 and lignes[G2.account_id]["non_signes"] == 1
    assert data["gestionnaires"][-1]["id"] == "non_attribue"
    assert data["gestionnaires"][-1]["attribues"] == 2
    assert ADMIN.account_id not in lignes or lignes[ADMIN.account_id]["attribues"] == 0


def test_filtres_par_indicateur_gestionnaire_et_statuts(monkeypatch):
    h = Harness(_jeu_de_dossiers(), monkeypatch)
    assert sorted(r["id"] for r in h.liste(ADMIN, gestionnaire="non_attribue")) == ["d-0101", "d-0107"]
    assert sorted(r["id"] for r in h.liste(ADMIN, indicateur="traitement:relance")) == ["d-0103"]
    assert sorted(r["id"] for r in h.liste(ADMIN, statut_commercial="signee")) == ["d-0107"]
    cumul = h.liste(ADMIN, gestionnaire=G1.account_id, statut_traitement="offre_transmise")
    assert sorted(r["id"] for r in cumul) == ["d-0106", "d-0109"]
    decisions = h.liste(ADMIN, indicateur="decision_a_renseigner")
    assert sorted(r["id"] for r in decisions) == ["d-0106", "d-0109"]


def test_agent_ne_voit_que_ses_demandes_dans_le_pilotage(monkeypatch):
    h = Harness(_jeu_de_dossiers(), monkeypatch)
    data = h.pilotage(AGENT)
    assert data["perimetre"] == "agent"
    assert data["gestionnaires"] == []
    assert data["indicateurs"]["soumises"] == 8
    with pytest.raises(HTTPException) as exc:
        h.call("GET", "/demandes-offres/gestionnaires", user=AGENT)
    assert _status(exc) == 403
    noms = [g["nom"] for g in h.call("GET", "/demandes-offres/gestionnaires", user=ADMIN)]
    assert "Lea Gestion" in noms and "Marc Offres" in noms and "Camille Durand" not in noms


# --------------------------------------------------------------------------- statuts et colonnes

def test_statut_traitement_et_statut_commercial_sont_distincts():
    signee = _demande("d-0201", statut="Offre signée", suivi_etape="offre_transmise")
    assert traitement_code(signee) == "offre_transmise"
    assert commercial_code(signee) == "signee"
    ancien = _demande("d-0202", statut="Offre reçue")
    assert commercial_code(ancien) == "non_renseigne"
    assert COMMERCIAL_LABELS["non_renseigne"] == "Statut non renseigné"
    out = serialize_demande(_demande("d-0203", statut="Offre envoyée au client",
                                     envoi_client={"at": "2026-11-02T08:00:00+00:00", "by": "Camille Durand"}),
                            viewer=AGENT)
    assert out["statut_commercial"] == "transmise_client"
    assert out["statut_commercial_label"] == "Offre transmise au client"
    assert out["statut_commercial_at"] == "2026-11-02T08:00:00+00:00"
    assert out["statut_traitement_label"]
    assert out["can_suivi_commercial"] is True
    other = serialize_demande(_demande("d-0204"), viewer=AUTRE_AGENT)
    assert other["can_suivi_commercial"] is False


def test_libelles_dynamiques_du_bouton_traiter():
    attendu = {
        "en_attente": ("Traiter", "bleu"),
        "en_cours": ("En cours", "orange"),
        "attente_compagnie": ("Attente compagnie", "jaune"),
        "relance": ("Relancée", "violet"),
        "offres_partielles": ("Transmission partielle", None),
        "offre_transmise": ("Transmise", "vert"),
    }
    for code, (label, couleur) in attendu.items():
        assert BOUTONS_TRAITER[code]["label"] == label
        if couleur:
            assert BOUTONS_TRAITER[code]["couleur"] == couleur
    assert bouton_traiter(_demande("d-0301"))["label"] == "Traiter"
    relancee = _demande("d-0302", suivi_etape="attente_compagnie",
                        suivi_evenements=[{"etape": "relance", "at": "2026-11-03T09:00:00+00:00"}])
    assert bouton_traiter(relancee)["label"] == "Relancée"


def test_anciens_dossiers_restent_lisibles(monkeypatch):
    anciens = [
        {"id": "old-1", "user_id": TENANT_USER_ID, "numero": "OFF-2024-0001", "statut": "Offre signée",
         "historique": [{"action": "Offre signée", "at": "2024-03-01T09:15:00"}]},
        {"id": "old-2", "user_id": TENANT_USER_ID, "numero": "OFF-2024-0002", "statut": "Offre reçue",
         "offre": {"compagnie": "AXA", "received_at": "2024-02-01T09:00:00", "document_id": "x"}},
        {"id": "old-3", "user_id": TENANT_USER_ID, "numero": "OFF-2024-0003", "statut": "Demande envoyée"},
    ]
    for doc in anciens:
        out = serialize_demande(doc, viewer=G1)
        assert out["attribution"] == "non_attribuee"
        assert out["gestionnaire_id"] is None
        assert out["statut_traitement"] in TRAITEMENT_CODES
        assert out["bouton_traiter"]["label"]
    assert serialize_demande(anciens[1], viewer=G1)["statut_commercial_label"] == "Statut non renseigné"
    data = compute_pilotage(anciens)
    assert data["indicateurs"]["non_attribuees"] == 3
    assert data["indicateurs"]["relance_14j_envoyee"] == 0
    h = Harness(anciens, monkeypatch)
    assert len(h.liste(ADMIN)) == 3


def test_tags_et_filtres_partagent_la_meme_source():
    rows = _jeu_de_dossiers()
    data = compute_pilotage(rows)
    for key, count in data["indicateurs"].items():
        assert len(filtrer_lignes(rows, tag=key)) == count, key
    assert "soumises" not in pilotage_tags(_demande("d-0401", statut="Brouillon"))
    assert "soumises" not in pilotage_tags(_demande("d-0402", statut="Demande annulée"))


def test_tableau_decision_client_signale_les_depassements():
    rows = _jeu_de_dossiers()
    data = compute_pilotage(rows, now=NOW)
    lignes = {d["id"]: d for d in data["decisions_a_renseigner"]}
    assert set(lignes) == {"d-0106", "d-0109"}
    assert lignes["d-0106"]["jours"] == 20 and lignes["d-0106"]["depasse_14j"] is True
    assert lignes["d-0106"]["transmis_agent_at"] == "2026-10-20T08:00:00+00:00"
    assert lignes["d-0106"]["docs_transmis_at"] == "2026-10-10T08:00:00+00:00"
    assert lignes["d-0109"]["statut_commercial"] == "transmise_client"
    assert lignes["d-0109"]["agent"] == "Camille Durand"
    assert "rappel_envoye_at" in lignes["d-0109"]


def test_en_retard_traitement_non_termine_et_rdv_proche():
    # NOW = 09.11.2026 ; seuil RDV_RETARD_JOURS = 5 jours calendaires (Europe/Zurich).
    assert RDV_RETARD_JOURS == 5
    cas = {
        "attente-rdv-dans-5j": (_demande("r1", date_prochain_rdv="2026-11-14"), True),
        "attente-rdv-dans-6j": (_demande("r2", date_prochain_rdv="2026-11-15"), False),
        "attente-rdv-passe": (_demande("r3", date_prochain_rdv="2026-11-01"), True),
        "sans-rdv": (_demande("r4", date_prochain_rdv="", date_envoi="2026-09-01T08:00:00+00:00"), False),
        "en-cours": (_demande("r5", suivi_etape="en_cours", date_prochain_rdv="2026-11-10"), True),
        "partielle": (_demande("r6", statut="Offre reçue", suivi_etape="offres_partielles",
                               date_prochain_rdv="2026-11-10"), True),
        "transmise": (_demande("r7", statut="Offre reçue", suivi_etape="offre_transmise",
                               date_prochain_rdv="2026-11-10"), False),
        "signee": (_demande("r8", statut="Offre signée", date_prochain_rdv="2026-11-01"), False),
        "annulee": (_demande("r9", statut="Demande annulée", date_prochain_rdv="2026-11-01"), False),
    }
    for nom, (doc, attendu) in cas.items():
        assert en_retard_rdv(doc, NOW) is attendu, nom
        assert ("en_retard" in pilotage_tags(doc, NOW)) is attendu, nom
    # 08.11 23:30 UTC = 09.11 00:30 à Zurich : RDV le 14.11 à J+5.
    tard = datetime(2026, 11, 8, 23, 30, tzinfo=timezone.utc)
    assert en_retard_rdv(_demande("r10", date_prochain_rdv="2026-11-14"), tard) is True


def test_delai_14j_part_de_offres_transmises_a_l_agent():
    partiel = _demande("t1", statut="Offre reçue", suivi_etape="offres_partielles",
                       docs_mis_a_disposition_at="2026-10-01T08:00:00+00:00",
                       offre_transmise_agent_at="2026-10-01T08:00:00+00:00",
                       suivi_evenements=[{"etape": "offres_partielles", "at": "2026-10-01T08:00:00+00:00"}])
    assert transmis_agent_at(partiel) is None
    decision = compute_pilotage([partiel], now=NOW)["decisions_a_renseigner"][0]
    assert decision["jours"] is None and decision["depasse_14j"] is False
    complet = dict(partiel, suivi_etape="offre_transmise", suivi_evenements=[
        *partiel["suivi_evenements"],
        {"etape": "offre_transmise", "at": "2026-10-30T08:00:00+00:00"},
    ])
    assert transmis_agent_at(complet) == "2026-10-30T08:00:00+00:00"
    decision = compute_pilotage([complet], now=NOW)["decisions_a_renseigner"][0]
    assert decision["jours"] == 10 and decision["depasse_14j"] is False
    assert transmis_agent_at(dict(complet, offres_transmises_agent_at="2026-10-25T08:00:00+00:00")) == (
        "2026-10-25T08:00:00+00:00"
    )
