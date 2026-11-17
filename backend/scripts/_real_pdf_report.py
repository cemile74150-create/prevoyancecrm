"""
Harness réutilisable — rapport d'extraction PDF réels multi-compagnies / multi-branches.

Usage:
  python scripts/_real_pdf_report.py
  python scripts/_real_pdf_report.py "C:\\path\\offre.pdf" --form-type pilier3
  python scripts/_real_pdf_report.py --dir "C:\\Users\\offic\\Desktop\\offres-3p"
  python scripts/_real_pdf_report.py --preset 3p

Ne déploie rien. Sortie Markdown stdout + JSON optionnel (--json out.json).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from offre_extract import extract_offre_fields, map_extract_to_form  # noqa: E402
from offre_extract_company_adapters import (  # noqa: E402
    detect_company_adapter,
    score_extraction_coverage,
)
from offre_extract_structured import suggest_form_type  # noqa: E402

# PDF réels connus (auto + 3P) — mettre à jour quand Cemile dépose d'autres polices
KNOWN_REAL_PDFS = [
    Path(r"C:\Users\offic\Desktop\Insurance Porsche & Toyota 2026.pdf"),
]

PRESET_3P_PDFS = [
    Path(r"C:\Users\offic\Desktop\Dossier client\CHABLOZ Jean Michel et Vanessa\3p axa vanessa.pdf"),
    Path(r"C:\Users\offic\Desktop\Dossier client\CHABLOZ Jean Michel et Vanessa\AXA 3A Jean.pdf"),
    Path(r"C:\Users\offic\Desktop\Dossier client\MAY Jean Yves\Jean-Yves May Axa.pdf"),
    Path(r"C:\Users\offic\Desktop\Dossier client\MAY Jean Yves\Jean-Yves May Zurich.pdf"),
    Path(r"C:\Users\offic\Downloads\HELFER William - Vaudoise Serenity Benefit Plan.pdf"),
    Path(r"C:\Users\offic\Desktop\Dossier client\STEMPFEL Benoit\Nouvelles offres sans différé\Offre VAUDOISE 935K 15 ans.pdf"),
    Path(r"C:\Users\offic\Desktop\Dossier client\MARTI René et Fatima\MARTI René et Fatima\Offres Vaudoise\Vaudoise RC 640k 15 ans.pdf"),
    Path(r"C:\Users\offic\Downloads\WAHLEN Emmanuel-20261019T131930Z-1-001\WAHLEN Emmanuel\AXA 3a L50 1124952 Corinne.pdf"),
    Path(r"C:\Users\offic\Desktop\Insurance Porsche & Toyota 2026.pdf"),
]

# Attentes manuelles pour scoring (None = pas de score attendu)
EXPECTED_BY_STEM: dict[str, dict[str, Any]] = {
    "Insurance Porsche & Toyota 2026": {
        "prenom": "Fernando",
        "nom": "Gasca",
        "npa": "7134",
        "montant_prime": 1243.9,
        "compagnie": "ELVIA",
        "reference_police": "T309497274",
        "form_type": "voyage",
        "objets_min": 2,
    },
    "Offre VAUDOISE 935K 15 ans": {
        "prenom": "Benoit",
        "nom": "Stempfel",
        "compagnie": "Vaudoise",
        "type_pilier": "3b",
        "duree": 15,
        "montant_investi": 935000.0,
        "form_type": "pilier3",
    },
    "Vaudoise RC 640k 15 ans": {
        "prenom": "René",
        "nom": "Marti",
        "compagnie": "Vaudoise",
        "type_pilier": "3b",
        "duree": 15,
        "montant_investi": 640000.0,
        "form_type": "pilier3",
    },
    "Jean-Yves May Axa": {
        "prenom": "Jean-Yves",
        "nom": "May",
        "compagnie": "AXA",
        "type_pilier": "3a",
        "montant_prime": 3865.0,
        "form_type": "pilier3",
    },
}

CRM_KEYS = (
    "prenom",
    "nom",
    "npa",
    "ville",
    "adresse",
    "date_naissance",
    "montant_prime",
    "montant_investi",
    "rente_mensuelle_garantie",
    "duree",
    "type_pilier",
    "compagnie",
    "reference_police",
    "date_debut",
    "date_fin",
    "nationalite",
    "civilite",
    "telephone",
    "email",
    "periodicite",
)


def _pick_form_type(raw: dict, override: Optional[str]) -> str:
    if override:
        return override
    suggested = raw.get("form_type_suggere")
    if suggested:
        return str(suggested)
    structured = raw.get("structured") or {}
    if isinstance(structured, dict):
        sug = suggest_form_type(structured) or (structured.get("meta") or {}).get("form_type_suggere")
        if sug:
            return str(sug)
    objets = raw.get("objets") or []
    veh = [o for o in objets if isinstance(o, dict) and o.get("type") == "vehicule"]
    if len(veh) >= 2:
        return "voyage"
    if len(veh) == 1:
        return "vehicule"
    # Ne plus forcer « voyage » par défaut (cassait les PDF 3P scannés).
    if raw.get("type_pilier") or raw.get("rente_mensuelle_garantie") or raw.get("montant_investi"):
        return "pilier3"
    return "pilier3"


def analyze_pdf(path: Path, *, form_type: Optional[str] = None) -> dict[str, Any]:
    data = path.read_bytes()
    raw = extract_offre_fields(data, filename=path.name)
    ft = _pick_form_type(raw, form_type)
    mapped = map_extract_to_form(raw, form_type=ft)
    text = raw.get("_text") or ""
    adapter = detect_company_adapter(text, path.name)
    objets = raw.get("objets") or []
    vehicules = [o for o in objets if isinstance(o, dict) and o.get("type") == "vehicule"]
    structured = raw.get("structured") if isinstance(raw.get("structured"), dict) else {}
    branche = None
    if isinstance(structured, dict):
        br = structured.get("branche") or {}
        branche = br.get("value") if isinstance(br, dict) else br

    expected = EXPECTED_BY_STEM.get(path.stem) or {}
    score_expected = {k: v for k, v in expected.items() if k not in ("form_type", "objets_min")}
    score = (
        score_extraction_coverage(raw, expected=score_expected)
        if score_expected
        else {"ok": [], "missing": [], "incorrect": [], "counts": {"ok": 0, "missing": 0, "incorrect": 0}}
    )

    filled_crm = {k: raw.get(k) for k in CRM_KEYS if raw.get(k) not in (None, "", "Non indiqué")}
    present_unmapped: list[str] = []

    def _obj_has_coverage(key: str) -> bool:
        for o in vehicules:
            if not isinstance(o, dict):
                continue
            cov = o.get("couvertures") or {}
            if isinstance(cov, dict):
                node = cov.get(key) or cov.get("franchise_collision") or cov.get("protection_bonus_collision")
                if isinstance(node, dict) and node.get("value") not in (None, ""):
                    return True
                if key == "franchise" and (cov.get("franchise_collision") or {}).get("value") not in (None, ""):
                    return True
                if key == "bonus" and (
                    (cov.get("protection_bonus_collision") or {}).get("value") not in (None, "")
                    or (cov.get("rc_protection_bonus") or {}).get("value") not in (None, "")
                ):
                    return True
            node = o.get(key) or o.get("leasing")
            if isinstance(node, dict) and node.get("value") not in (None, ""):
                return True
            if key == "leasing" and (o.get("leasing") or {}).get("value") not in (None, ""):
                return True
        return False

    # Heuristique auto : mots visibles dans le PDF absents des objets / flat
    if (branche or "").startswith("vehicule") or ft in {"voyage", "vehicule"}:
        for needle, label, check in (
            ("franchise", "franchise_detail", "franchise"),
            ("bonus", "bonus_malus", "bonus"),
            ("leasing", "leasing_global", "leasing"),
        ):
            if needle in text.casefold() and not _obj_has_coverage(check):
                present_unmapped.append(label)

    # Heuristique 3P
    if (branche == "pilier3" or ft.startswith("pilier3")) and text:
        low = text.casefold()
        if ("rente" in low or "fraction mensuelle" in low) and raw.get("rente_mensuelle_garantie") in (None, ""):
            present_unmapped.append("rente_mensuelle")
        if ("prime unique" in low or "montant investi" in low) and raw.get("montant_investi") in (None, ""):
            present_unmapped.append("montant_investi")
        if ("3a" in low or "3b" in low) and raw.get("type_pilier") in (None, ""):
            present_unmapped.append("type_pilier")

    if not (text or "").strip():
        present_unmapped.append("texte_pdf_vide_ocr_indisponible")

    payload = mapped.get("form_payload") or {}
    return {
        "path": str(path),
        "size_kb": round(path.stat().st_size / 1024, 1),
        "mtime": path.stat().st_mtime,
        "company_adapter": getattr(adapter, "company_id", None) or raw.get("compagnie"),
        "branche": branche,
        "form_type_suggere": raw.get("form_type_suggere") or ft,
        "form_type_used": ft,
        "montant_prime": raw.get("montant_prime"),
        "montant_prime_mapped": (mapped.get("fields") or {}).get("montant_prime"),
        "montant_investi": raw.get("montant_investi"),
        "rente_mensuelle_garantie": raw.get("rente_mensuelle_garantie"),
        "duree": raw.get("duree"),
        "type_pilier": raw.get("type_pilier"),
        "objets_count": len(objets),
        "vehicules_count": len(vehicules),
        "vehicules": [
            {
                "index": v.get("index"),
                "marque": (v.get("marque") or {}).get("value") if isinstance(v.get("marque"), dict) else v.get("marque"),
                "modele": (v.get("modele") or {}).get("value") if isinstance(v.get("modele"), dict) else v.get("modele"),
                "plaque": (v.get("plaque") or {}).get("value") if isinstance(v.get("plaque"), dict) else v.get("plaque"),
            }
            for v in vehicules
        ],
        "filled_crm": filled_crm,
        "filled_keys_count": len(mapped.get("filled_keys") or []),
        "filled_keys_sample": list(mapped.get("filled_keys") or [])[:25],
        "payload_marque_v1": payload.get("input_48"),
        "payload_marque_v2": payload.get("input_90"),
        "payload_garage": payload.get("input_58"),
        "score": score,
        "expected": expected,
        "present_in_pdf_unrecognized": present_unmapped,
        "to_verify": [
            k
            for k, v in (mapped.get("field_statuses") or {}).items()
            if isinstance(v, dict) and v.get("status") == "to_verify"
        ],
        "issues": _issues(raw, mapped, expected, ft),
        "text_len": len(text or ""),
    }


def _issues(raw: dict, mapped: dict, expected: dict, ft: str) -> list[str]:
    issues: list[str] = []
    text_len = int(raw.get("_raw_text_len") or len(raw.get("_text") or ""))
    if text_len == 0:
        issues.append("pdf_sans_texte_ocr_echec")
    is_3p = ft.startswith("pilier3") or raw.get("type_pilier") or (raw.get("form_type_suggere") or "") == "pilier3"
    if is_3p:
        if raw.get("montant_prime") in (None, "") and raw.get("montant_investi") in (None, ""):
            issues.append("prime_ou_investi_non_extrait")
        if raw.get("prenom") in (None, "") and raw.get("nom") in (None, ""):
            issues.append("identite_absente")
    else:
        if raw.get("montant_prime") in (None, ""):
            issues.append("prime_annuelle_non_extraite")
        if (mapped.get("fields") or {}).get("montant_prime") in (None, ""):
            issues.append("prime_non_mappee_dans_fields")
    if expected.get("montant_prime") is not None and raw.get("montant_prime") != expected.get("montant_prime"):
        issues.append(
            f"prime_mismatch_extrait={raw.get('montant_prime')}_attendu={expected.get('montant_prime')}"
        )
    if expected.get("montant_investi") is not None and raw.get("montant_investi") != expected.get("montant_investi"):
        issues.append(
            f"investi_mismatch_extrait={raw.get('montant_investi')}_attendu={expected.get('montant_investi')}"
        )
    if expected.get("objets_min") and len(raw.get("objets") or []) < int(expected["objets_min"]):
        issues.append("objets_insuffisants")
    if expected.get("form_type") and ft != expected["form_type"] and raw.get("form_type_suggere") != expected["form_type"]:
        issues.append(f"form_type_suggere_inattendu={raw.get('form_type_suggere')}")
    if not raw.get("form_type_suggere") and text_len > 0:
        issues.append("form_type_suggere_absent")
    return issues


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Rapport PDF réels — extraction LeoSoft (multi-branches)",
        "",
        f"Fichiers analysés : **{len(rows)}**",
        "",
    ]
    if not rows:
        lines.extend(
            [
                "> Aucun PDF réel trouvé.",
                "",
                "Attendre de Cemile : polices/offres **AXA, Zurich, Vaudoise, Mobilière** (auto et/ou 3P).",
                "",
            ]
        )
        return "\n".join(lines)

    lines.append(
        "| PDF | Compagnie | branche | form_type | prime / investi / rente | filled | OK | manquants | incorrects | problèmes |"
    )
    lines.append("|---|---|---|---|---|---:|---:|---:|---:|---|")
    for r in rows:
        c = (r.get("score") or {}).get("counts") or {}
        money = "{pr} / {inv} / {re}".format(
            pr=r.get("montant_prime"),
            inv=r.get("montant_investi"),
            re=r.get("rente_mensuelle_garantie"),
        )
        lines.append(
            "| {name} | {co} | {br} | {ft} | {money} | {fk} | {ok} | {mi} | {inc} | {iss} |".format(
                name=Path(r["path"]).name,
                co=r.get("company_adapter") or "?",
                br=r.get("branche") or "—",
                ft=r.get("form_type_suggere") or r.get("form_type_used"),
                money=money,
                fk=r.get("filled_keys_count"),
                ok=c.get("ok", 0),
                mi=c.get("missing", 0),
                inc=c.get("incorrect", 0),
                iss=", ".join(r.get("issues") or []) or "—",
            )
        )
    lines.append("")
    for r in rows:
        lines.append(f"## {Path(r['path']).name}")
        lines.append("")
        lines.append(f"- Chemin : `{r['path']}` ({r['size_kb']} KB, texte={r.get('text_len')} car.)")
        lines.append(
            f"- Compagnie / branche / form_type : **{r.get('company_adapter')}** / `{r.get('branche')}` / `{r.get('form_type_suggere')}`"
        )
        lines.append(
            f"- Prime / investi / rente / durée / type : "
            f"**{r.get('montant_prime')}** / `{r.get('montant_investi')}` / "
            f"`{r.get('rente_mensuelle_garantie')}` / `{r.get('duree')}` / `{r.get('type_pilier')}`"
        )
        lines.append(f"- Véhicules : {r.get('vehicules')}")
        lines.append(f"- CRM remplis ({len(r.get('filled_crm') or {})}) : `{json.dumps(r.get('filled_crm'), ensure_ascii=False)}`")
        sc = r.get("score") or {}
        lines.append(
            f"- Counts scoring : OK={sc.get('ok')} | manquants={sc.get('missing')} | incorrects={sc.get('incorrect')}"
        )
        if r.get("present_in_pdf_unrecognized"):
            lines.append(f"- Présents PDF non reconnus (heuristique) : {r['present_in_pdf_unrecognized']}")
        if r.get("issues"):
            lines.append(f"- Problèmes : {r['issues']}")
        lines.append(
            f"- Préremplissage schéma : {r.get('filled_keys_count')} champs "
            f"(ex. v1=`{r.get('payload_marque_v1')}`, v2=`{r.get('payload_marque_v2')}`, garage=`{r.get('payload_garage')}`)"
        )
        lines.append("")
    return "\n".join(lines)


def collect_pdfs(paths: list[Path], directory: Optional[Path], preset: Optional[str]) -> list[Path]:
    found: list[Path] = []
    if preset == "3p":
        found.extend([p for p in PRESET_3P_PDFS if p.is_file()])
    for p in paths:
        if p.is_file() and p.suffix.lower() == ".pdf":
            found.append(p)
    if directory and directory.is_dir():
        found.extend(sorted(directory.rglob("*.pdf")))
    if not found:
        found = [p for p in KNOWN_REAL_PDFS if p.is_file()]
    # dédup
    uniq: dict[str, Path] = {}
    for p in found:
        uniq[str(p.resolve())] = p
    return list(uniq.values())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rapport extraction PDF réels LeoSoft")
    parser.add_argument("pdfs", nargs="*", type=Path, help="PDF à analyser")
    parser.add_argument("--dir", type=Path, help="Dossier de PDF réels")
    parser.add_argument("--preset", choices=["3p"], help="Jeu de PDF 3P + ELVIA connus")
    parser.add_argument("--form-type", type=str, default=None)
    parser.add_argument("--json", type=Path, help="Écrire le rapport JSON")
    args = parser.parse_args(argv)

    pdfs = collect_pdfs(list(args.pdfs or []), args.dir, args.preset)
    rows = [analyze_pdf(p, form_type=args.form_type) for p in pdfs]
    md = render_markdown(rows)
    print(md)
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nJSON écrit : {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
