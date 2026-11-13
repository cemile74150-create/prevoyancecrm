"""Generate GAPS.md from manifest + import report."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "offre_form_sources"
SCHEMAS = ROOT / "offre_form_schemas"


def main() -> None:
    manifest = json.loads((SOURCES / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((SOURCES / "import_show_when_report.json").read_text(encoding="utf-8"))

    lines = [
        "# Gaps — conditions d’affichage DOT → LeoSoft",
        "",
        "Généré par `scripts/report_show_when_gaps.py`.",
        "",
        "## Résumé import",
        "",
        f"- Ajoutés : **{report['totals']['added']}**",
        f"- Mis à jour : **{report['totals']['updated']}**",
        f"- Inchangés : **{report['totals']['unchanged']}**",
        f"- Sans export JS utilisable : **{report['totals']['no_export']}**",
        "",
        "## Formulaires sans `gf_form_conditional_logic` récupérable",
        "",
        "Ces schémas conservent leurs `show_when` déjà présents (s’il y en a).",
        "Pour les compléter : export JSON Gravity Forms (admin WP) ou nouveau dump HTML contenant le blob JS.",
        "",
    ]

    no_export = set(report["gaps"].get("no_js_conditional_export") or [])
    zero_rules = set(report["gaps"].get("export_with_zero_rules") or [])
    for cov in manifest.get("schema_coverage") or []:
        sid = cov["schema_id"]
        if sid not in no_export and sid not in zero_rules and cov.get("extracted_conditional_fields"):
            continue
        lines.append(
            f"- `{sid}` (GF {cov.get('gravity_form_id')}) — "
            f"champs={cov.get('fields_count')}, show_when existants={cov.get('existing_show_when')}, "
            f"règles extraites={cov.get('extracted_conditional_fields')}, "
            f"marqueurs HTML={cov.get('html_markers')}"
        )

    lines.extend(
        [
            "",
            "## Conditionnels GF orphelins (id présent dans le blob, absent du schéma LeoSoft)",
            "",
        ]
    )
    orphans = report["gaps"].get("orphan_conditionals") or []
    if not orphans:
        lines.append("_Aucun._")
    else:
        for row in orphans:
            lines.append(f"- `{row['schema_id']}` : gf_field_id {row['gf_field_ids']}")

    lines.extend(
        [
            "",
            "## Ce qui reste impossible sans nouvel export DOT",
            "",
            "1. Toute règle absente du blob JS **et** absente du JSON LeoSoft actuel.",
            "2. Les stubs `gf_*.json` / `menage.json` sans champs.",
            "3. Reconstruction heuristique « champ suivant un Oui/Non » sans marqueur GF — volontairement non appliquée.",
            "",
            "## Schémas actifs — couverture `show_when`",
            "",
            "| Schéma | GF | Champs | show_when |",
            "|--------|----|--------|-----------|",
        ]
    )

    for path in sorted(SCHEMAS.glob("*.json")):
        if path.name in {"index.json", "menu.json"}:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = data.get("fields") or []
        if not fields:
            continue
        sw = sum(1 for f in fields if f.get("show_when"))
        lines.append(
            f"| `{data.get('id') or path.stem}` | {data.get('gravity_form_id')} | {len(fields)} | {sw} |"
        )

    out = SOURCES / "GAPS.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
