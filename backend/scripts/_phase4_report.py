"""Rapport comparatif Phase 4 (offline, non-prod)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pdf_generator  # noqa: E402
from offre_extract import extract_offre_fields, map_extract_to_form  # noqa: E402
from offre_extract_company_adapters import score_extraction_coverage  # noqa: E402
from offre_form_types import load_form_schema  # noqa: E402

FIXTURES = BACKEND / "tests" / "fixtures"
ELVIA_PDF = Path(r"C:\Users\offic\Desktop\Insurance Porsche & Toyota 2026.pdf")

cases = [
    (
        "ELVIA",
        FIXTURES / "elvia_porsche_toyota_2026.txt",
        "elvia.pdf",
        "voyage",
        {"prenom": "Fernando", "nom": "Gasca", "npa": "7134", "montant_prime": 1243.9, "compagnie": "ELVIA"},
    ),
    (
        "Mobilière",
        FIXTURES / "mobiliere_vehicule_synth.txt",
        "m.pdf",
        "vehicule",
        {"prenom": "Sophie", "nom": "Martin", "npa": "1003", "montant_prime": 890.5, "compagnie": "Mobilière"},
    ),
    (
        "Vaudoise",
        FIXTURES / "vaudoise_vehicule_synth.txt",
        "v.pdf",
        "vehicule",
        {"prenom": "Lucas", "nom": "Favre", "npa": "1800", "montant_prime": 720.0, "compagnie": "Vaudoise"},
    ),
    (
        "AXA",
        FIXTURES / "axa_vehicule_synth.txt",
        "a.pdf",
        "vehicule",
        {"prenom": "Marc", "nom": "Dubois", "npa": "8001", "montant_prime": 1150.0, "compagnie": "AXA"},
    ),
    (
        "Zurich",
        FIXTURES / "zurich_vehicule_synth.txt",
        "z.pdf",
        "vehicule",
        {"prenom": "Elena", "nom": "Rossi", "npa": "1205", "montant_prime": 980.4, "compagnie": "Zurich"},
    ),
]

print("| Compagnie | OK | Manquants | Incorrects | filled_keys | Prime |")
print("|---|---:|---:|---:|---:|---:|")
for name, path, fn, ft, exp in cases:
    text = path.read_text(encoding="utf-8")
    pdf_generator._extract_pdf_text = lambda _b, t=text: t
    ex = extract_offre_fields(b"%PDF", filename=fn)
    mapped = map_extract_to_form(ex, form_type=ft)
    flat = dict(ex)
    p = mapped["form_payload"]
    exp2 = dict(exp)
    if ft == "voyage":
        flat["marque_v1"] = p.get("input_48")
        flat["marque_v2"] = p.get("input_90")
        flat["garage"] = p.get("input_58")
        exp2.update({"marque_v1": "Toyota", "marque_v2": "Porsche", "garage": "Garage au domicile"})
    else:
        flat["marque_vehicule"] = p.get("input_48")
        flat["garage"] = p.get("input_58")
        brands = {"Mobilière": "Volkswagen", "Vaudoise": "Renault", "AXA": "Bmw", "Zurich": "Audi"}
        exp2.update({"marque_vehicule": brands[name], "garage": "Garage au domicile"})
    sc = score_extraction_coverage(flat, expected=exp2)
    c = sc["counts"]
    print(
        f"| {name} | {c['ok']} | {c['missing']} | {c['incorrect']} | "
        f"{len(mapped['filled_keys'])} | {ex.get('montant_prime')} |"
    )

text = (FIXTURES / "elvia_porsche_toyota_2026.txt").read_text(encoding="utf-8")
pdf_generator._extract_pdf_text = lambda _b: text
ex = extract_offre_fields(b"%PDF", filename="Insurance Porsche & Toyota 2026.pdf")
mapped = map_extract_to_form(ex, form_type="voyage")
schema = load_form_schema("voyage")
names = {(f.get("name") or f.get("id")) for f in schema["fields"] if isinstance(f, dict)}
assert all(k in names for k in mapped["filled_keys"])
tv = [k for k, v in mapped["field_statuses"].items() if v.get("status") == "to_verify"]
print("A1 filled", len(mapped["filled_keys"]), "all_in_schema=True", "prime", mapped["fields"]["montant_prime"])
print("to_verify", tv)

if ELVIA_PDF.exists():
    importlib.reload(pdf_generator)
    r = extract_offre_fields(ELVIA_PDF.read_bytes(), filename=ELVIA_PDF.name)
    m = map_extract_to_form(r, form_type="voyage")
    print(
        "REAL_PDF prime",
        r["montant_prime"],
        "filled",
        len(m["filled_keys"]),
        "v1",
        m["form_payload"].get("input_48"),
        "v2",
        m["form_payload"].get("input_90"),
    )
