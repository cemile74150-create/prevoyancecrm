"""Prénom must stay free text in Demandes d'offres schemas."""
from __future__ import annotations

import unicodedata

from offre_form_types import list_form_types, load_form_schema


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


CIV = {"monsieur", "madame", "mr", "mme", "homme", "femme", "masculin", "feminin"}


def test_prenom_fields_are_free_text_across_all_schemas():
    issues = []
    for meta in list_form_types(active_only=False):
        fid = meta.get("id")
        if meta.get("renderer") == "legacy_wizard":
            continue
        schema = load_form_schema(fid) or {}
        for field in schema.get("fields") or []:
            lab = _fold(field.get("label") or "")
            if "prenom" not in lab:
                continue
            if field.get("type") == "section":
                continue
            opts = field.get("options") or []
            civ_opts = [o for o in opts if _fold(str(o)) in CIV]
            if field.get("type") != "text" or civ_opts or opts:
                issues.append((fid, field.get("id"), field.get("label"), field.get("type"), opts[:4]))
    assert not issues, f"Prénom fields still wrong: {issues}"


def test_sanitize_clears_leaked_civilite_on_prenom():
    # Direct unit: assurances_particulier historically had Monsieur/Madame on Prénom
    schema = load_form_schema("assurances_particulier")
    assert schema
    prenom = next(f for f in schema["fields"] if _fold(f.get("label") or "") == "prenom")
    assert prenom["type"] == "text"
    assert prenom.get("options") in ([], None)
