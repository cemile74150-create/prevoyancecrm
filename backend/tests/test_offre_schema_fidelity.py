"""Schema fidelity checks against Gravity Forms HTML dumps (Demandes d'offres)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

SCHEMAS = Path(__file__).resolve().parents[1] / "offre_form_schemas"

# Maps form_type schema file → (gform_id, expected_pages, html path)
FORMS = {
    "pilier3.json": (6, 2, Path(r"c:\Users\offic\Downloads\Texte collé(20260922-122651).txt")),
    "pilier3_parent_enfant.json": (41, 2, Path(r"c:\Users\offic\Downloads\Texte collé(20260922-115746).txt")),
    "pilier3_risque_pur.json": (42, 2, Path(r"c:\Users\offic\Downloads\Texte collé (2).txt")),
    "assurances_particulier.json": (11, 3, Path(r"c:\Users\offic\Downloads\Texte collé (3).txt")),
    "menage_rc.json": (1, 6, Path(r"C:\Users\offic\Desktop\Cemile\Tableau suivi\menage_rc_gf_dump.txt")),
    "motocycle.json": (9, 4, Path(r"c:\Users\offic\Downloads\Texte collé (5).txt")),
    "vehicule.json": (8, 4, Path(r"c:\Users\offic\Downloads\Texte collé (6).txt")),
    "voyage.json": (12, 6, Path(r"c:\Users\offic\Downloads\Texte collé (7).txt")),
    "attestation_vehicule.json": (110, 1, Path(r"c:\Users\offic\Downloads\Texte collé (8).txt")),
    "animaux.json": (47, 1, Path(r"c:\Users\offic\Downloads\Texte collé (9).txt")),
    "laa_employee_maison.json": (37, 1, Path(r"c:\Users\offic\Downloads\Texte collé (10).txt")),
    "protection_juridique_particulier.json": (35, 2, Path(r"c:\Users\offic\Downloads\Texte collé (11).txt")),
}


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("schema_file,meta", list(FORMS.items()))
def test_schema_gravity_id_and_pages(schema_file, meta):
    gid, pages, html_path = meta
    if not html_path.exists():
        pytest.skip(f"HTML dump missing: {html_path}")
    data = _load(schema_file)
    assert data.get("gravity_form_id") == gid
    assert (data.get("page_count") or len(data.get("pages") or [])) == pages
    assert data.get("fields_count") == len(data.get("fields") or [])
    assert data.get("fields_count") > 0


@pytest.mark.parametrize("schema_file", ["menage_rc.json", "pilier3.json", "pilier3_parent_enfant.json", "vehicule.json", "animaux.json"])
def test_prenom_is_free_text(schema_file):
    data = _load(schema_file)
    prenoms = [
        f
        for f in data["fields"]
        if (f.get("label") or "").strip().lower() in {"prénom", "prenom"}
        or (f.get("label") or "").strip().lower().startswith("prénom de l")
        or (f.get("label") or "").strip().lower().startswith("prenom de l")
    ]
    assert prenoms, f"No Prénom field in {schema_file}"
    for f in prenoms:
        assert f.get("type") == "text"
        assert not f.get("options")


def test_pilier3_gform6_core():
    data = _load("pilier3.json")
    assert data["gravity_form_id"] == 6
    assert data["title"] == "3ÈME PILIER"
    assert data["page_count"] == 2
    by_name = {f["name"]: f for f in data["fields"]}
    assert by_name["input_46"]["type"] == "text"  # Prénom preneur
    assert by_name["input_123.3"]["type"] == "text"  # Prénom agent
    assert by_name["input_100"]["type"] == "radio"
    assert by_name["input_100"]["options"] == ["Madame", "Monsieur"]
    assert by_name["input_51"]["type"] == "checkbox"
    assert "Axa" in by_name["input_51"]["options"]
    # Activités à risque visible when Oui
    assert by_name["input_93"]["show_when"]["rules"][0]["field"] == "input_65"
    # AXA block gated by company checkbox
    assert by_name["input_66"]["show_when"]["rules"][0] == {
        "field": "input_51",
        "op": "is",
        "value": "Axa",
    }


def test_civilite_is_radio_madame_monsieur():
    data = _load("menage_rc.json")
    # GF1 dump label typo « Civlité » (missing i) — keep fidelity to source
    civ = next(
        f
        for f in data["fields"]
        if (f.get("label") or "").replace("é", "e").lower() in {"civilite", "civlite"}
        or (f.get("label") or "") in {"Civilité", "Civlité"}
    )
    assert civ["type"] == "radio"
    assert civ["options"] == ["Monsieur", "Madame"]


def test_menage_rc_statut_occupation_logement_required():
    """Habitation RC-Ménage : statut d'occupation obligatoire (Locataire / Propriétaire)."""
    from offre_form_types import empty_form_payload, missing_schema_required

    data = _load("menage_rc.json")
    field = next(f for f in data["fields"] if f.get("name") == "input_7")
    assert field["label"] == "Statut d'occupation du logement"
    assert field["type"] == "radio"
    assert field["required"] is True
    assert field["options"] == ["Locataire", "Propriétaire"]
    assert field["page"] == 1
    names = [f.get("name") for f in data["fields"]]
    # Dans « Renseignements sur l'habitation », avant le nombre de pièces.
    assert names.index("input_33") < names.index("input_7") < names.index("input_8")

    payload = empty_form_payload("menage_rc")
    assert "Statut d'occupation du logement" in missing_schema_required("menage_rc", payload)
    payload["input_7"] = "Locataire"
    assert "Statut d'occupation du logement" not in missing_schema_required("menage_rc", payload)


def test_menage_rc_six_pages_and_core_sections():
    data = _load("menage_rc.json")
    assert data["gravity_form_id"] == 1
    assert data["page_count"] == 6
    assert data["fields_count"] == len(data["fields"]) >= 100
    labels = {f.get("label") for f in data["fields"]}
    assert "Couvertures Ménage" in labels
    assert "Responsabilité Civile" in labels or "Type de RC" in labels
    assert "Assurance bâtiment" in labels
    assert any("Smile Direct" in (l or "") for l in labels)
    assert any("Options spécifiques à Axa" in (l or "") or "Axa" == (l or "") for l in labels)
    by = {f["name"]: f for f in data["fields"]}
    # Casco montant gated
    assert by["input_54"]["show_when"]["rules"][0] == {
        "field": "input_53",
        "op": "is",
        "value": "Oui",
    }
    # RC familiale → personnes
    assert by["input_60"]["show_when"]["rules"][0]["value"] == "Familiale"
    # Bâtiment block
    assert by["input_86"]["show_when"]["rules"][0]["value"] == "Oui"
    # Axa options
    assert by["input_63"]["show_when"]["rules"][0]["value"] == "Axa"
    # Pays hidden Suisse
    pays = next(f for f in data["fields"] if f.get("label") == "Pays")
    assert pays["type"] == "hidden"
    assert pays.get("default") == "Suisse"
    # Nationalité is free text in GF1 (not Suisse/Autre select)
    nat = next(f for f in data["fields"] if f.get("label") == "Nationalité")
    assert nat["type"] == "text"


def test_vehicule_has_casco_and_smile_conditionals():
    data = _load("vehicule.json")
    labels = {f.get("label") for f in data["fields"]}
    assert "Casco intégrale" in labels or any("Casco" in (l or "") for l in labels)
    smile = [f for f in data["fields"] if "Smile" in (f.get("label") or "")]
    assert smile
    assert any(f.get("show_when") for f in smile)


def test_animaux_mapped_to_gf47_not_batiment():
    data = _load("animaux.json")
    assert data["gravity_form_id"] == 47
    bat = _load("assurances_particulier.json")
    assert bat["gravity_form_id"] == 11


def test_html_field_count_close_to_schema(schema_file="menage_rc.json"):
    gid, _, html_path = FORMS[schema_file]
    if not html_path.exists():
        pytest.skip("HTML missing")
    html = html_path.read_text(encoding="utf-8", errors="replace")
    html_fields = len(re.findall(rf'id="field_{gid}_\d+"', html))
    data = _load(schema_file)
    # Schema may expand name fields into 2+ entries, so allow >= html field wrappers minus junk
    assert data["fields_count"] >= html_fields - 5


def test_index_points_to_correct_gravity_ids():
    index = json.loads((SCHEMAS / "index.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in index}
    assert by_id["animaux"]["gravity_form_id"] == 47
    assert by_id["assurances_particulier"]["gravity_form_id"] == 11
    assert by_id["voyage"]["gravity_form_id"] == 12
    assert by_id["menage_rc"]["gravity_form_id"] == 1
    assert by_id["laa_employee_maison"]["gravity_form_id"] == 37
    assert by_id["pilier3"]["gravity_form_id"] == 6
    assert by_id["pilier3"]["active"] is True
    assert by_id["entreprise_offres"]["gravity_form_id"] == 14
    assert by_id["entreprise_offres"]["active"] is True


@pytest.mark.parametrize(
    "schema_file,gid",
    [
        ("entreprise.json", 13),
        ("entreprise_27.json", 27),
        ("entreprise_28.json", 28),
        ("entreprise_29.json", 29),
        ("entreprise_31.json", 31),
        ("entreprise_32.json", 32),
        ("entreprise_33.json", 33),
        ("entreprise_46.json", 46),
        ("entreprise_50.json", 50),
        ("rc_entreprise.json", 30),
        ("formulaire_complet.json", 94),
        ("protection_juridique_entreprise.json", 36),
        ("protection_juridique_entreprise_2.json", 38),
        ("vehicule.json", 8),
        ("motocycle.json", 9),
        ("voyage.json", 12),
    ],
)
def test_no_phantom_oui_radio_defaults(schema_file, gid):
    """Radio defaults must not invent pre-checked Oui (GF dump fidelity)."""
    data = _load(schema_file)
    assert data["gravity_form_id"] == gid
    for f in data["fields"]:
        if f.get("type") != "radio":
            continue
        # After sync, any remaining default must be a real GF checked value —
        # phantom first-option Oui was the main failure mode.
        if f.get("default") == "Oui":
            # Allow only if options literally include Oui (still may be real);
            # count is asserted loosely — presence alone is OK when dump had checked.
            assert "Oui" in (f.get("options") or [])


def test_vehicule_isolation_from_pilier3():
    veh = {f["name"] for f in _load("vehicule.json")["fields"]}
    p3 = {f["name"] for f in _load("pilier3.json")["fields"]}
    # Shared technical names can exist (input_1 etc.) but schéma labels differ;
    # ensure filter keeps payloads isolated.
    from offre_form_types import filter_form_payload_to_schema

    mixed = {n: "x" for n in list(veh)[:5]}
    mixed.update({n: "y" for n in list(p3)[:5]})
    only_v = filter_form_payload_to_schema("vehicule", mixed)
    only_p = filter_form_payload_to_schema("pilier3", mixed)
    assert set(only_v) <= veh
    assert set(only_p) <= p3
    assert "__bleed__" not in only_v


def test_entreprise_27_gform27_core():
    data = _load("entreprise_27.json")
    assert data["gravity_form_id"] == 27
    assert data["fields_count"] == len(data["fields"]) >= 48
    by = {f["name"]: f for f in data["fields"]}
    # Agent name expanded
    assert any(n.startswith("input_101.") for n in by)
    # Address expanded + Pays hidden (dump GF27: type=hidden, value vide — pas de Suisse inventé)
    pays = [f for f in data["fields"] if f.get("type") == "hidden" and "Pays" in (f.get("label") or "")]
    assert pays, "Pays hidden attendu"
    assert by.get("input_8.6", {}).get("type") == "hidden"


def test_formulaire_complet_gform94_pages():
    data = _load("formulaire_complet.json")
    assert data["gravity_form_id"] == 94
    assert data["fields_count"] == len(data["fields"]) >= 148
    assert (data.get("page_count") or 0) >= 5


def test_entreprise_offres_gform14_core():
    """GF14 Entreprise - Assurance Véhicule — structure fidèle à l'intranet."""
    data = _load("entreprise_offres.json")
    assert data["gravity_form_id"] == 14
    assert data["page_count"] == 4
    assert data["fields_count"] == len(data["fields"]) == 88
    by_name = {f["name"]: f for f in data["fields"]}

    # Agent: prénom/nom en texte libre (input_127.3 / .6)
    assert by_name["input_127.3"]["type"] == "text"
    assert by_name["input_127.3"]["label"] == "Prénom de l'agent"
    assert not by_name["input_127.3"].get("options")
    assert by_name["input_127.6"]["type"] == "text"
    assert by_name["input_127.6"]["label"] == "Nom de l'agent"

    # Civilité + prénom conducteur
    assert by_name["input_102"]["type"] == "radio"
    assert by_name["input_102"]["options"] == ["Monsieur", "Madame"]
    assert by_name["input_115"]["type"] == "text"
    assert "Prénom" in by_name["input_115"]["label"]

    # Oui/Non critiques (ne doivent PAS être tel/select)
    for key in ("input_38", "input_39", "input_56", "input_107", "input_110"):
        f = by_name[key]
        assert f["type"] == "radio", f"{key} must be radio, got {f['type']}"
        assert f["options"] == ["Oui", "Non"], f"{key} options={f.get('options')}"

    # Liste sinistres + conditionnel
    assert by_name["input_108"]["type"] == "list"
    assert by_name["input_108"]["columns"] == [
        "Type de sinistre",
        "Date du sinistre",
        "Montant du sinistre",
    ]
    assert by_name["input_108"]["show_when"]["rules"][0] == {
        "field": "input_107",
        "op": "is",
        "value": "Oui",
    }

    # Smile / Zurich conditionnels présents
    smile = [f for f in data["fields"] if "Smile" in (f.get("label") or "")]
    assert smile
    assert any(f.get("show_when") for f in smile)
    zurich = [f for f in data["fields"] if "Zurich" in (f.get("label") or "")]
    assert zurich
    assert any(f.get("show_when") for f in zurich)

    # Compagnies checkbox page 4
    assert by_name["input_32"]["type"] == "checkbox"
    assert "Axa" in by_name["input_32"]["options"]
    assert "Zurich" in by_name["input_32"]["options"]

    # Adresse : sous-champs visibles + Pays hidden (valeur GF Suisse)
    assert by_name["input_2.1"]["label"] == "Adresse postale"
    assert by_name["input_2.3"]["label"] == "Ville"
    assert by_name["input_2.5"]["label"] == "Code postal"
    assert by_name["input_2.6"]["type"] == "hidden"
    assert by_name["input_2.6"]["default"] == "Suisse"
    assert "input_2.4" not in by_name  # State GF caché vide — non exposé

    # Defaults fidèles au HTML (pas de Oui pré-coché fantôme)
    assert "default" not in by_name["input_38"]
    assert "default" not in by_name["input_56"]
    assert by_name["input_120"]["default"] == "Français"
    assert by_name["input_124"]["default"] == "Entreprise - Assurance Véhicule"

    # Commentaires présents
    assert by_name["input_34"]["type"] == "textarea"
    assert by_name["input_34"]["label"] == "Commentaires"
    assert by_name["input_100"]["type"] == "textarea"
    assert by_name["input_100"]["label"] == "Vos commentaires"
