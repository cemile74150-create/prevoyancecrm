"""La colonne RDV client lit la date du formulaire, pas la date d'envoi."""
from demandes_offres_3p import serialize_demande
from demandes_offres_ameliorations import filter_rdv_a_venir, sort_demandes
from offre_form_types import (
    list_form_types,
    load_form_schema,
    rdv_client_depuis_formulaire,
    rdv_client_effectif,
)


def _fold(label: str) -> str:
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", label or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _champs_rdv(schema: dict) -> list[dict]:
    found = []
    for field in schema.get("fields") or []:
        if not isinstance(field, dict):
            continue
        if field.get("type") not in {"date", "text", None, ""}:
            continue
        key = _fold(field.get("label") or "")
        if "client" in key.split() and "rendez vous" in key:
            found.append(field)
    return found


def test_chaque_schema_mappe_sa_cle_de_rendez_vous():
    hits = 0
    seen_names = set()
    for form in list_form_types(active_only=False):
        schema = load_form_schema(form["id"]) or {}
        for field in _champs_rdv(schema):
            name = field.get("name") or field.get("id")
            assert name, (form["id"], field.get("label"))
            date, heure = rdv_client_depuis_formulaire(form["id"], {name: "09.11.2026 14:30"})
            assert date == "2026-11-09", (form["id"], name, field.get("label"), date)
            assert heure == "14:30"
            seen_names.add(name)
            if field.get("id") and field.get("id") != name:
                via_id, _ = rdv_client_depuis_formulaire(form["id"], {field["id"]: "09.11.2026"})
                assert via_id == "2026-11-09", (form["id"], field["id"])
            label = field.get("label")
            via_label, _ = rdv_client_depuis_formulaire(form["id"], {label: "09/11/2026"})
            assert via_label == "2026-11-09", (form["id"], label)
            hits += 1
    assert hits >= 20
    assert len(seen_names) > 1


def test_ignore_date_envoi_creation_et_autres_dates_du_formulaire():
    schema = load_form_schema("vehicule") or {}
    autres = [
        field for field in (schema.get("fields") or [])
        if field.get("type") == "date" and field not in _champs_rdv(schema)
    ]
    assert autres, "le schéma véhicule doit avoir une autre date que le RDV"
    payload = {autres[0].get("name"): "01.01.2026"}
    assert rdv_client_depuis_formulaire("vehicule", payload) == ("", "")
    doc = {
        "form_type": "vehicule",
        "form_payload": payload,
        "date_envoi": "2026-11-06",
        "created_at": "2026-11-06T08:00:00",
        "date_prochain_rdv": "",
    }
    assert rdv_client_effectif(doc) == ("", "")


def test_sous_champs_et_dictionnaire_gravity():
    date, heure = rdv_client_depuis_formulaire(
        "entreprise_46",
        {"input_60.1": "09", "input_60.2": "11", "input_60.3": "2026"},
    )
    assert (date, heure) == ("2026-11-09", "")
    date, heure = rdv_client_depuis_formulaire(
        "pilier3",
        {"input_44": {"day": "9", "month": "11", "year": "2026", "heure": "8:05"}},
    )
    assert date == "2026-11-09"
    assert heure == "08:05"


def test_serialize_garde_date_prochain_rdv_et_expose_le_formulaire():
    doc = {
        "id": "d-rdv",
        "statut": "Demande envoyée",
        "form_type": "vehicule",
        "date_prochain_rdv": "2026-12-01",
        "heure_rdv": "08:15",
        "date_envoi": "2026-11-06T09:00:00",
        "created_at": "2026-11-01T10:00:00",
        "form_payload": {"input_35": "09.11.2026"},
    }
    out = serialize_demande(doc)
    assert out["date_prochain_rdv"] == "2026-12-01"
    assert out["heure_rdv"] == "08:15"
    assert out["rdv_client_formulaire"] == {"date": "2026-11-09", "heure": ""}
    assert out["date_envoi"] == "2026-11-06T09:00:00"
    assert rdv_client_effectif(out) == ("2026-12-01", "08:15")


def test_serialize_date_formulaire_quand_date_prochain_rdv_est_vide():
    doc = {
        "id": "d-form",
        "statut": "Demande envoyée",
        "form_type": "vehicule",
        "date_prochain_rdv": "",
        "heure_rdv": "",
        "date_envoi": "2026-11-06",
        "created_at": "2026-11-06T08:00:00",
        "form_payload": {"input_35": "09.11.2026"},
    }
    out = serialize_demande(doc)
    assert out["date_prochain_rdv"] == ""
    assert out["rdv_client_formulaire"]["date"] == "2026-11-09"
    assert out["date_envoi"] == "2026-11-06"
    assert rdv_client_effectif(out) == ("2026-11-09", "")


def test_tri_rdv_utilise_le_formulaire_sans_prendre_la_date_envoi():
    rows = [
        {
            "id": "envoi",
            "date_prochain_rdv": "",
            "date_envoi": "2026-11-06",
            "created_at": "2026-11-06",
            "form_type": "vehicule",
            "form_payload": {},
        },
        {
            "id": "formulaire",
            "date_prochain_rdv": "",
            "date_envoi": "2026-11-01",
            "created_at": "2026-11-01",
            "form_type": "entreprise_46",
            "form_payload": {"input_60": "09.11.2026"},
        },
        {
            "id": "stocke",
            "date_prochain_rdv": "2026-11-20",
            "heure_rdv": "09:00",
            "date_envoi": "2026-10-01",
            "form_type": "vehicule",
            "form_payload": {"input_35": "01.01.2026"},
        },
    ]
    ordered = [row["id"] for row in sort_demandes(rows, "rdv_asc", today="2026-11-06")]
    assert ordered == ["formulaire", "stocke", "envoi"]
    upcoming = [row["id"] for row in filter_rdv_a_venir(rows, True, today="2026-11-06")]
    assert upcoming == ["formulaire", "stocke"]
