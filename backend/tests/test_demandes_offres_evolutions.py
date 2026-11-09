"""Demandes d'offres : transmission par variantes, avancement par compagnie,
fil de discussion, urgence sous 24 h.

Les routes sont appelées directement sur une base Mongo en mémoire.
"""
from __future__ import annotations

import asyncio
import copy
import io
import sys
from pathlib import Path

import pytest
from fastapi import APIRouter, HTTPException
from starlette.datastructures import FormData, Headers, UploadFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import email_service  # noqa: E402
from access_control import (  # noqa: E402
    PERM_DEMANDES_OFFRES_EDIT,
    PERM_DEMANDES_OFFRES_PROCESS,
    PERM_DEMANDES_OFFRES_VIEW,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    TENANT_USER_ID,
    permission_for_request,
    user_from_doc,
)
from demandes_offres_3p import COLLECTION, COLLECTION_DOCS, serialize_demande  # noqa: E402
from demandes_offres_ameliorations import (  # noqa: E402
    SUIVI_LABELS,
    SUIVI_PROCESS,
    etape_affichee,
    etat_transmission,
    urgentes_en_tete,
    validate_urgence_request,
)
from demandes_offres_messages import COLLECTION_MESSAGES, clean_message_content  # noqa: E402
from demandes_offres_routes import (  # noqa: E402
    MessageDemandeRequest,
    SuiviDemandeRequest,
    UrgenceRequest,
    attach_demandes_offres_routes,
)
from demandes_offres_transmission import (  # noqa: E402
    group_traitement_uploads,
    group_variante_uploads,
    missing_traitement_pieces,
    missing_variante_pieces,
    parse_nb_variantes,
    variante_field,
)


# --------------------------------------------------------------------------- base en mémoire

_MISSING = object()


def _get(doc, key):
    current = doc
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _eq(value, expected):
    if isinstance(value, list) and not isinstance(expected, list):
        return expected in value
    return value == expected


def _match(doc, query):
    for key, expected in (query or {}).items():
        if key == "$or":
            if not any(_match(doc, sub) for sub in expected):
                return False
            continue
        value = _get(doc, key)
        if isinstance(expected, dict) and any(str(k).startswith("$") for k in expected):
            for op, arg in expected.items():
                present = value is not _MISSING
                if op == "$ne" and present and _eq(value, arg):
                    return False
                if op == "$exists" and present != bool(arg):
                    return False
                if op == "$in" and not (present and any(_eq(value, a) for a in arg)):
                    return False
                if op == "$nin" and present and any(_eq(value, a) for a in arg):
                    return False
            continue
        if value is _MISSING or not _eq(value, expected):
            return False
    return True


def _project(doc, projection):
    out = copy.deepcopy(doc)
    out.pop("_id", None)
    for key, flag in (projection or {}).items():
        if flag == 0:
            out.pop(key, None)
    return out


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda r: str(r.get(key) or ""), reverse=direction == -1)
        return self

    async def to_list(self, limit=None):
        return self.rows[:limit] if limit else self.rows


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, projection=None, **_kw):
        for doc in self.docs:
            if _match(doc, query):
                return _project(doc, projection)
        return None

    def find(self, query=None, projection=None):
        return FakeCursor([_project(d, projection) for d in self.docs if _match(d, query or {})])

    async def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))

    def _apply(self, doc, update):
        for key, value in (update.get("$set") or {}).items():
            doc[key] = copy.deepcopy(value)
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
                return
        if upsert:
            doc = {k: v for k, v in query.items() if not isinstance(v, dict)}
            self._apply(doc, update)
            self.docs.append(doc)

    async def update_many(self, query, update):
        for doc in self.docs:
            if _match(doc, query):
                self._apply(doc, update)

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))


class FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self[name]


class FakeRequest:
    def __init__(self, items):
        self._form = FormData(items)

    async def form(self):
        return self._form


def _upload(name, data=b"%PDF-1.4 test", content_type="application/pdf"):
    return UploadFile(
        file=io.BytesIO(data),
        filename=name,
        size=len(data),
        headers=Headers({"content-type": content_type}),
    )


# --------------------------------------------------------------------------- fixtures

def _user(role, user_id, prenom, nom, email):
    return user_from_doc({
        "user_id": user_id,
        "email": email,
        "prenom": prenom,
        "nom": nom,
        "name": f"{prenom} {nom}",
        "role": role,
        "conseiller": f"{prenom} {nom}",
        "active": True,
    })


AGENT = _user(ROLE_CONSEILLER, "agent-1", "Camille", "Durand", "camille@test.ch")
AUTRE_AGENT = _user(ROLE_CONSEILLER, "agent-2", "Alex", "Martin", "alex@test.ch")
GESTION = _user(ROLE_GESTIONNAIRE_OFFRES, "gest-1", "Lea", "Gestion", "lea@test.ch")


def _demande(compagnies, **extra):
    return {
        "id": "dem-1",
        "user_id": TENANT_USER_ID,
        "numero": "OFF-2026-0001",
        "statut": "Demande envoyée",
        "form_type": "pilier3_legacy",
        "compagnies": list(compagnies),
        "created_by_account_id": AGENT.account_id,
        "agent_label": "Camille Durand",
        "agent_email": "camille@test.ch",
        "prenom": "Jean",
        "nom": "Client",
        "date_envoi": "2026-11-01T08:00:00+00:00",
        "created_at": "2026-10-30T08:00:00+00:00",
        "updated_at": "2026-11-01T08:00:00+00:00",
        "historique": [],
        "is_deleted": False,
        **extra,
    }


class Harness:
    def __init__(self, demande, monkeypatch):
        self.db = FakeDb()
        self.storage = {}
        self.email_calls = 0
        router = APIRouter()

        def put_object(key, data, content_type):
            self.storage[key] = data
            return {"path": key, "size": len(data)}

        attach_demandes_offres_routes(
            router,
            db=self.db,
            put_object=put_object,
            local_storage_fallback=lambda *a, **k: None,
            file_response_headers=lambda name, inline=False: {"Content-Disposition": f"attachment; filename={name}"},
            mime_types={"pdf": "application/pdf"},
            app_name="test",
            root_dir=str(ROOT),
            load_storage_bytes=lambda path: self.storage[path],
        )
        self.routes = {}
        for route in router.routes:
            for method in route.methods:
                self.routes[(method, route.path)] = route.endpoint
        asyncio.run(self.db[COLLECTION].insert_one(demande))

        def offres_email_enabled():
            self.email_calls += 1
            return False

        monkeypatch.setattr(email_service, "offres_email_enabled", offres_email_enabled)

    def call(self, method, path, **kwargs):
        return asyncio.run(self.routes[(method, path)](**kwargs))

    def demande(self):
        return asyncio.run(self.db[COLLECTION].find_one({"id": "dem-1"}))

    def notifications(self, event="recue"):
        return [n for n in self.db["offre_notifications"].docs if n.get("event") == event]

    def transmettre_variantes(self, compagnie, nb, *, autre=(), token=None, user=GESTION):
        items = []
        for index in range(1, nb + 1):
            items.append((variante_field(index, "offre"), _upload(f"{compagnie}-v{index}-offre.pdf")))
            items.append((variante_field(index, "cga"), _upload(f"{compagnie}-v{index}-cga.pdf")))
            if index in autre:
                items.append((variante_field(index, "autre"), _upload(f"{compagnie}-v{index}-autre.pdf")))
        return self.call(
            "POST", "/demandes-offres/{demande_id}/offre",
            request=FakeRequest(items), demande_id="dem-1", compagnie=compagnie,
            date_reception="2026-11-05", reference=None, montant_prime=None, type_contrat=None,
            garanties=None, duree=None, commentaires=None, file=None,
            nb_variantes=str(nb), parcours="reponses_compagnies", client_token=token, user=user,
        )

    def transmettre_simple(self, compagnie, *, commentaire="", token=None, autre=False):
        items = [
            ("offre", _upload(f"{compagnie}-offre.pdf")),
            ("cga", _upload(f"{compagnie}-cga.pdf")),
        ]
        if autre:
            items.append(("autre", _upload(f"{compagnie}-autre.pdf")))
        return self.call(
            "POST", "/demandes-offres/{demande_id}/offre",
            request=FakeRequest(items), demande_id="dem-1",
            compagnie=compagnie, date_reception="2026-11-05", reference=None, montant_prime=None,
            type_contrat=None, garanties=None, duree=None, commentaires=commentaire, file=None,
            nb_variantes=None, parcours="traitement", client_token=token, user=GESTION,
        )


@pytest.fixture
def trois_compagnies(monkeypatch):
    return Harness(_demande(["AXA", "Zurich", "Helvetia"]), monkeypatch)


# --------------------------------------------------------------------------- variantes

def test_nombre_de_variantes_par_defaut_et_entier_positif():
    assert parse_nb_variantes(None) == 1
    assert parse_nb_variantes("") == 1
    assert parse_nb_variantes("  ") == 1
    assert parse_nb_variantes("3") == 3
    for bad in ("0", "-1", "1.5", "abc", "21"):
        with pytest.raises(ValueError):
            parse_nb_variantes(bad)


def test_trois_variantes_donnent_trois_blocs_offre_cga_autre():
    items = [
        (variante_field(i, piece), object())
        for i in (1, 2, 3)
        for piece in ("offre", "cga")
    ]
    groups = group_variante_uploads(items, 3)
    assert sorted(groups) == [1, 2, 3]
    for index in (1, 2, 3):
        assert set(groups[index]) == {"offre", "cga", "autre"}
        assert len(groups[index]["offre"]) == 1
        assert len(groups[index]["cga"]) == 1
        assert groups[index]["autre"] == []
    assert missing_variante_pieces(groups, 3) == []
    sans_cga = group_variante_uploads([(variante_field(1, "offre"), object())], 1)
    assert missing_variante_pieces(sans_cga, 1) == ["Variante 1 : CGA"]
    with pytest.raises(ValueError):
        group_variante_uploads([(variante_field(4, "offre"), object())], 3)


def test_traitement_exige_offre_et_cga_avec_types():
    groups = group_traitement_uploads([
        ("offre", object()),
        ("cga", object()),
        ("autre", object()),
        ("files", object()),  # legacy → offre
    ])
    assert len(groups["offre"]) == 2
    assert len(groups["cga"]) == 1
    assert len(groups["autre"]) == 1
    assert missing_traitement_pieces(groups) == []
    assert missing_traitement_pieces(group_traitement_uploads([("offre", object())])) == ["CGA"]


def test_documents_lies_a_la_bonne_variante(trois_compagnies):
    h = trois_compagnies
    h.transmettre_variantes("AXA", 3, autre=(2,))
    stored = h.db[COLLECTION_DOCS].docs
    assert len(stored) == 7
    for doc in stored:
        assert doc["demande_id"] == "dem-1"
        assert doc["category"] == "Offre compagnie"
        assert doc["compagnie"] == "AXA"
        assert doc["original_filename"].startswith(f"AXA-v{doc['variante']}-")
        expected_kind = {"offre": "Offre", "cga": "CGA", "autre": "Autre document"}[
            doc["original_filename"].rsplit("-", 1)[1].removesuffix(".pdf")
        ]
        assert doc["piece_kind"] == expected_kind
    offer = h.demande()["offres"][0]
    assert offer["nb_variantes"] == 3
    transmission = offer["transmissions"][0]
    assert transmission["parcours"] == "reponses_compagnies"
    assert transmission["date_reception"] == "2026-11-05"
    by_id = {d["id"]: d for d in stored}
    for variante in transmission["variantes"]:
        for piece, ids in variante["documents"].items():
            for doc_id in ids:
                assert by_id[doc_id]["variante"] == variante["index"]
    assert len(transmission["variantes"][1]["documents"]["autre"]) == 1
    assert {d.get("variante") for d in offer["documents"]} == {1, 2, 3}


def test_piece_obligatoire_manquante_refusee_sans_rien_enregistrer(trois_compagnies):
    h = trois_compagnies
    with pytest.raises(HTTPException) as exc:
        h.call(
            "POST", "/demandes-offres/{demande_id}/offre",
            request=FakeRequest([(variante_field(1, "offre"), _upload("o.pdf"))]), demande_id="dem-1",
            compagnie="AXA", date_reception="2026-11-05", reference=None, montant_prime=None,
            type_contrat=None, garanties=None, duree=None, commentaires=None, file=None,
            nb_variantes="1", parcours="reponses_compagnies", client_token=None, user=GESTION,
        )
    assert exc.value.status_code == 422
    assert "CGA" in exc.value.detail
    assert h.db[COLLECTION_DOCS].docs == []
    assert not h.demande().get("offres")


def test_transmission_supplementaire_meme_compagnie_conserve_les_documents(trois_compagnies):
    h = trois_compagnies
    h.transmettre_variantes("AXA", 1)
    h.transmettre_variantes("AXA", 2)
    offer = h.demande()["offres"][0]
    assert len(offer["transmissions"]) == 2
    assert len(offer["documents"]) == 6
    assert offer["nb_variantes"] == 3


# --------------------------------------------------------------------------- avancement par compagnie

def test_une_compagnie_sur_trois_partiellement_transmise(trois_compagnies):
    h = trois_compagnies
    result = h.transmettre_variantes("AXA", 1)
    assert result["etape_suivi"] == "offres_partielles"
    assert result["etape_suivi_label"] == "Offres partiellement transmises à l'agent"
    assert result["transmission"]["etat"] == "partielle"
    assert result["transmission"]["manquantes"] == ["Zurich", "Helvetia"]
    assert result["statut"] != "Offre reçue"
    assert h.demande()["offre_transmise_agent_at"]


def test_trois_compagnies_sur_trois_transmises_par_les_deux_parcours(trois_compagnies):
    h = trois_compagnies
    h.transmettre_variantes("AXA", 2)
    h.transmettre_simple("Zurich", commentaire="Prime annuelle", autre=True)
    result = h.transmettre_variantes("Helvetia", 1)
    assert result["etape_suivi"] == "offre_transmise"
    assert result["etape_suivi_label"] == "Offres transmises à l'agent"
    assert result["transmission"]["etat"] == "complete"
    assert result["transmission"]["nb_transmises"] == 3
    assert h.demande()["suivi_etape"] == "offre_transmise"
    assert [e["etape"] for e in h.demande()["suivi_evenements"]] == ["offres_partielles", "offre_transmise"]
    zurich = next(o for o in h.demande()["offres"] if o["compagnie"] == "Zurich")
    assert zurich["transmissions"][0]["parcours"] == "traitement"
    assert zurich["transmissions"][0]["commentaire"] == "Prime annuelle"
    zurich_docs = [d for d in h.db[COLLECTION_DOCS].docs if d["compagnie"] == "Zurich"]
    assert {d["piece_kind"] for d in zurich_docs} == {"Offre", "CGA", "Autre document"}
    assert all("variante" not in d for d in zurich_docs)


def test_traitement_refuse_sans_cga(trois_compagnies):
    h = trois_compagnies
    with pytest.raises(HTTPException) as exc:
        h.call(
            "POST", "/demandes-offres/{demande_id}/offre",
            request=FakeRequest([("offre", _upload("seul.pdf"))]), demande_id="dem-1",
            compagnie="AXA", date_reception="2026-11-05", reference=None, montant_prime=None,
            type_contrat=None, garanties=None, duree=None, commentaires=None, file=None,
            nb_variantes=None, parcours="traitement", client_token=None, user=GESTION,
        )
    assert exc.value.status_code == 422
    assert "CGA" in exc.value.detail
    assert h.db[COLLECTION_DOCS].docs == []


def test_trois_variantes_d_une_compagnie_ne_comptent_qu_une_compagnie(trois_compagnies, monkeypatch):
    h = trois_compagnies
    result = h.transmettre_variantes("AXA", 3)
    assert result["transmission"]["nb_transmises"] == 1
    assert result["etape_suivi"] == "offres_partielles"

    seule = Harness(_demande(["AXA"]), monkeypatch)
    result = seule.transmettre_variantes("AXA", 3)
    assert result["transmission"]["nb_transmises"] == 1
    assert result["etape_suivi"] == "offre_transmise"
    assert result["etape_suivi_label"] == "Offres transmises à l'agent"


def test_recalcul_si_les_compagnies_sollicitees_changent():
    doc = _demande(["AXA"], suivi_etape="offre_transmise", suivi_auto=True,
                   offres=[{"compagnie": "AXA", "date_reception": "2026-11-05", "documents": []}])
    assert etape_affichee(doc) == "offre_transmise"
    doc["compagnies"] = ["AXA", "Zurich"]
    assert etape_affichee(doc) == "offres_partielles"


def test_une_issue_du_workflow_n_est_pas_ecrasee(monkeypatch):
    h = Harness(_demande(["AXA", "Zurich"], statut="Offre envoyée au client"), monkeypatch)
    result = h.transmettre_simple("AXA")
    assert result["etape_suivi"] == "envoyee_client"
    assert not h.demande().get("suivi_etape")


def test_compagnie_seulement_marquee_incomplete_ne_compte_pas():
    doc = _demande(["AXA", "Zurich"], offres=[
        {"compagnie": "AXA", "date_reception": "2026-11-05"},
        {"compagnie": "Zurich", "statut": "Incomplète", "documents": []},
    ])
    assert etat_transmission(doc)["etat"] == "partielle"


def test_offres_partielles_selectionnable_manuellement(trois_compagnies):
    """Le gestionnaire peut poser offres_partielles sans attendre l'auto-calcul."""
    h = trois_compagnies
    assert "offres_partielles" in SUIVI_PROCESS
    result = h.call(
        "POST",
        "/demandes-offres/{demande_id}/suivi",
        demande_id="dem-1",
        payload=SuiviDemandeRequest(etape="offres_partielles"),
        user=GESTION,
    )
    assert result["etape_suivi"] == "offres_partielles"
    assert result["etape_suivi_label"] == "Offres partiellement transmises à l'agent"
    assert h.demande()["suivi_etape"] == "offres_partielles"
    assert h.demande().get("suivi_auto") is False
    assert h.demande()["suivi_evenements"][-1]["etape"] == "offres_partielles"

    # 1/3 transmise : l'étape manuelle reste partielle et la file doit la garder
    apres = h.transmettre_variantes("AXA", 1)
    assert apres["etape_suivi"] == "offres_partielles"
    assert apres["transmission"]["etat"] == "partielle"
    assert apres["etape_suivi"] != "offre_transmise"


def test_etape_affichee_conserve_offres_partielles_manuel_sans_transmission():
    doc = _demande(["AXA", "Zurich", "Helvetia"], suivi_etape="offres_partielles", suivi_auto=False)
    assert etape_affichee(doc) == "offres_partielles"


# --------------------------------------------------------------------------- notifications

def test_notification_et_email_une_seule_fois_par_transmission(trois_compagnies):
    h = trois_compagnies
    h.transmettre_variantes("AXA", 2, token="tok-1")
    assert len(h.notifications()) == 1
    assert h.email_calls == 1
    again = h.transmettre_variantes("AXA", 2, token="tok-1")
    assert again["transmission_deja_enregistree"] is True
    assert len(h.notifications()) == 1
    assert h.email_calls == 1
    assert len(h.db[COLLECTION_DOCS].docs) == 4
    assert len(h.demande()["offres"][0]["transmissions"]) == 1


# --------------------------------------------------------------------------- compatibilité

def test_ancien_dossier_sans_nouveaux_champs_reste_lisible():
    old = {
        "id": "old-1",
        "numero": "OFF-2024-0042",
        "statut": "Offre reçue",
        "compagnies": ["AXA", "Zurich"],
        "suivi_etape": "offre_transmise",
        "urgente": True,
        "urgence_motif": "RDV client demain",
        "offre": {"compagnie": "AXA", "document_id": "doc-legacy", "received_at": "2024-03-01"},
    }
    out = serialize_demande(old, docs=[], viewer=GESTION)
    assert out["etape_suivi"] == "offre_transmise"
    assert out["urgente"] is True
    assert out["urgence_delai"] == ""
    assert out["offres"][0]["documents"][0]["id"] == "doc-legacy"
    assert out["transmission"]["etat"] == "partielle"
    cards = out["reponses_compagnies"]
    assert cards[0]["transmissions"] == []


# --------------------------------------------------------------------------- urgence

def test_urgence_refusee_sans_case(trois_compagnies):
    assert validate_urgence_request(True, "Client pressé", False)
    with pytest.raises(HTTPException) as exc:
        trois_compagnies.call(
            "POST", "/demandes-offres/{demande_id}/urgence", demande_id="dem-1",
            payload=UrgenceRequest(urgente=True, motif="Client pressé", delai_24h=False), user=AGENT,
        )
    assert exc.value.status_code == 422
    assert "24 h" in exc.value.detail
    assert not trois_compagnies.demande().get("urgente")


def test_urgence_refusee_sans_motif(trois_compagnies):
    assert validate_urgence_request(True, "  ", True)
    with pytest.raises(HTTPException) as exc:
        trois_compagnies.call(
            "POST", "/demandes-offres/{demande_id}/urgence", demande_id="dem-1",
            payload=UrgenceRequest(urgente=True, motif="  ", delai_24h=True), user=AGENT,
        )
    assert exc.value.status_code == 422
    assert "motif" in exc.value.detail
    assert not trois_compagnies.demande().get("urgente")


def test_urgence_valide_prioritaire_avec_motif_et_delai(trois_compagnies):
    h = trois_compagnies
    result = h.call(
        "POST", "/demandes-offres/{demande_id}/urgence", demande_id="dem-1",
        payload=UrgenceRequest(urgente=True, motif="Signature vendredi", delai_24h=True), user=AGENT,
    )
    stored = h.demande()
    assert stored["urgente"] is True
    assert stored["urgence_motif"] == "Signature vendredi"
    assert stored["urgence_delai"] == "moins_24h"
    assert stored["urgence_echeance_at"] > stored["urgence_at"]
    assert result["urgence_delai"] == "moins_24h"
    assert "moins de 24 heures" in stored["historique"][-1]["detail"]
    rows = urgentes_en_tete([{"id": "a"}, {"id": "dem-1", **stored}, {"id": "b"}])
    assert rows[0]["id"] == "dem-1"
    assert validate_urgence_request(False, "", False) is None


# --------------------------------------------------------------------------- fil de discussion

def test_agent_envoie_et_gestionnaire_repond(trois_compagnies):
    h = trois_compagnies
    before = h.demande()
    with pytest.raises(ValueError):
        clean_message_content("   ")
    with pytest.raises(HTTPException) as exc:
        h.call("POST", "/demandes-offres/{demande_id}/messages", demande_id="dem-1",
               payload=MessageDemandeRequest(contenu="  "), user=AGENT)
    assert exc.value.status_code == 422

    h.call("POST", "/demandes-offres/{demande_id}/messages", demande_id="dem-1",
           payload=MessageDemandeRequest(contenu="Le client préfère AXA"), user=AGENT)
    vu_gestion = h.call("GET", "/demandes-offres/{demande_id}/messages", demande_id="dem-1",
                        marquer_lu=True, user=GESTION)
    assert vu_gestion["non_lus"] == 1
    h.call("POST", "/demandes-offres/{demande_id}/messages", demande_id="dem-1",
           payload=MessageDemandeRequest(contenu="Bien noté, je relance AXA"), user=GESTION)

    thread = h.call("GET", "/demandes-offres/{demande_id}/messages", demande_id="dem-1",
                    marquer_lu=True, user=AGENT)
    assert [m["contenu"] for m in thread["messages"]] == ["Le client préfère AXA", "Bien noté, je relance AXA"]
    first, second = thread["messages"]
    assert first["expediteur_role"] == "agent" and first["expediteur_nom"] == "Camille Durand"
    assert second["expediteur_role"] == "gestionnaire" and second["expediteur_nom"] == "Lea Gestion"
    assert first["demande_id"] == "dem-1" and first["created_at"] <= second["created_at"]
    assert first["mine"] is True and second["mine"] is False
    assert thread["non_lus"] == 1
    assert thread["peut_ecrire"] is True
    again = h.call("GET", "/demandes-offres/{demande_id}/messages", demande_id="dem-1",
                   marquer_lu=True, user=AGENT)
    assert again["non_lus"] == 0
    assert len(h.db[COLLECTION_MESSAGES].docs) == 2

    after = h.demande()
    assert after["statut"] == before["statut"]
    assert after["updated_at"] == before["updated_at"]
    assert len(h.db[COLLECTION].docs) == 1
    assert len(h.notifications("message")) == 2


def test_utilisateur_non_autorise_recoit_403_sur_le_fil_et_les_documents(trois_compagnies):
    h = trois_compagnies
    h.transmettre_simple("AXA")
    doc_id = h.db[COLLECTION_DOCS].docs[0]["id"]
    ok = h.call("GET", "/demandes-offres/documents/{doc_id}/download", doc_id=doc_id, user=AGENT)
    assert ok.status_code == 200
    for call in (
        lambda: h.call("GET", "/demandes-offres/{demande_id}/messages", demande_id="dem-1",
                       marquer_lu=True, user=AUTRE_AGENT),
        lambda: h.call("POST", "/demandes-offres/{demande_id}/messages", demande_id="dem-1",
                       payload=MessageDemandeRequest(contenu="Bonjour"), user=AUTRE_AGENT),
        lambda: h.call("GET", "/demandes-offres/documents/{doc_id}/download", doc_id=doc_id,
                       user=AUTRE_AGENT),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 403
    assert h.db[COLLECTION_MESSAGES].docs == []


def test_permissions_des_routes_du_fil():
    assert permission_for_request("GET", "/api/demandes-offres/abc/messages") == PERM_DEMANDES_OFFRES_VIEW
    assert permission_for_request("POST", "/api/demandes-offres/abc/messages") == (
        PERM_DEMANDES_OFFRES_EDIT,
        PERM_DEMANDES_OFFRES_PROCESS,
    )


def test_libelles_d_avancement():
    assert SUIVI_LABELS["offre_transmise"] == "Offres transmises à l'agent"
    assert SUIVI_LABELS["offres_partielles"] == "Offres partiellement transmises à l'agent"
