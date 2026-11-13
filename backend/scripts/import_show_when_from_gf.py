"""
Merge Gravity Forms conditionalLogic into existing offre_form_schemas.

Only updates `show_when` (and a small fidelity stamp). Does not change labels,
types, options, order, pages, or UI design.

Usage:
  python scripts/extract_gf_conditional_logic.py
  python scripts/import_show_when_from_gf.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "offre_form_schemas"
CL_DIR = ROOT / "offre_form_sources" / "conditional_logic"
REPORT = ROOT / "offre_form_sources" / "import_show_when_report.json"


def _norm_show_when(sw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not sw or not isinstance(sw, dict):
        return None
    rules = sw.get("rules") or []
    if not rules:
        return None
    return {
        "logic": sw.get("logic") or "all",
        "rules": [
            {
                "field": r.get("field"),
                "op": r.get("op") or "is",
                "value": r.get("value"),
            }
            for r in rules
            if r.get("field") is not None
        ],
    }


def _same_show_when(a: Any, b: Any) -> bool:
    return _norm_show_when(a) == _norm_show_when(b)


def load_cl(gid: int) -> dict[str, Any] | None:
    path = CL_DIR / f"{gid}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def apply_to_schema(data: dict[str, Any], cl: dict[str, Any]) -> dict[str, Any]:
    fields_cl: dict[str, Any] = cl.get("fields") or {}
    by_gf: dict[int, dict[str, Any]] = {}
    for fid_s, sw in fields_cl.items():
        try:
            fid = int(fid_s)
        except (TypeError, ValueError):
            continue
        by_gf[fid] = {
            "logic": sw.get("logic") or "all",
            "rules": list(sw.get("rules") or []),
        }

    stats = {
        "fields_total": 0,
        "matched_gf_ids": 0,
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "kept_existing_unmatched": 0,
        "orphan_gf_conditionals": [],
        "unmapped_existing_show_when": [],
    }

    seen_gf: set[int] = set()
    for field in data.get("fields") or []:
        if not isinstance(field, dict):
            continue
        stats["fields_total"] += 1
        gf_id = field.get("gf_field_id")
        if gf_id is None:
            # try parse from id "36_50"
            raw_id = str(field.get("id") or "")
            if "_" in raw_id:
                try:
                    gf_id = int(raw_id.split("_", 1)[1].split("_")[0])
                except ValueError:
                    gf_id = None
        if not isinstance(gf_id, int) or gf_id not in by_gf:
            if field.get("show_when"):
                stats["kept_existing_unmatched"] += 1
                stats["unmapped_existing_show_when"].append(field.get("name") or field.get("id"))
            continue

        seen_gf.add(gf_id)
        stats["matched_gf_ids"] += 1
        new_sw = by_gf[gf_id]
        old_sw = field.get("show_when")
        if _same_show_when(old_sw, new_sw):
            stats["unchanged"] += 1
            continue
        field["show_when"] = new_sw
        if old_sw:
            stats["updated"] += 1
        else:
            stats["added"] += 1

    for fid in sorted(by_gf.keys()):
        if fid not in seen_gf:
            stats["orphan_gf_conditionals"].append(fid)

    data["show_when_import"] = {
        "gravity_form_id": cl.get("gravity_form_id"),
        "source_file": cl.get("source_file"),
        "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conditional_fields_in_export": len(fields_cl),
        "added": stats["added"],
        "updated": stats["updated"],
        "unchanged": stats["unchanged"],
    }
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not CL_DIR.exists():
        raise SystemExit(f"Missing {CL_DIR} — run extract_gf_conditional_logic.py first")

    report: dict[str, Any] = {
        "dry_run": args.dry_run,
        "schemas": [],
        "totals": {"added": 0, "updated": 0, "unchanged": 0, "no_export": 0},
        "gaps": {
            "no_js_conditional_export": [],
            "export_with_zero_rules": [],
            "orphan_conditionals": [],
        },
    }

    for path in sorted(SCHEMAS.glob("*.json")):
        if path.name in {"index.json", "menu.json"}:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = data.get("fields") or []
        if not fields:
            continue
        gid = data.get("gravity_form_id")
        row: dict[str, Any] = {
            "schema_file": path.name,
            "schema_id": data.get("id") or path.stem,
            "gravity_form_id": gid,
            "fields_count": len(fields),
            "show_when_before": sum(1 for f in fields if f.get("show_when")),
        }
        if not isinstance(gid, int):
            row["status"] = "no_gravity_id"
            report["gaps"]["no_js_conditional_export"].append(row["schema_id"])
            report["totals"]["no_export"] += 1
            report["schemas"].append(row)
            continue

        cl = load_cl(gid)
        if not cl or not (cl.get("fields") or {}):
            row["status"] = "no_js_blob_or_empty"
            report["gaps"]["no_js_conditional_export" if not cl else "export_with_zero_rules"].append(
                row["schema_id"]
            )
            report["totals"]["no_export"] += 1
            report["schemas"].append(row)
            continue

        stats = apply_to_schema(data, cl)
        row.update(stats)
        row["show_when_after"] = sum(1 for f in data.get("fields") or [] if f.get("show_when"))
        row["status"] = "imported"
        report["totals"]["added"] += stats["added"]
        report["totals"]["updated"] += stats["updated"]
        report["totals"]["unchanged"] += stats["unchanged"]
        if stats["orphan_gf_conditionals"]:
            report["gaps"]["orphan_conditionals"].append(
                {"schema_id": row["schema_id"], "gf_field_ids": stats["orphan_gf_conditionals"]}
            )

        if not args.dry_run and (stats["added"] or stats["updated"] or True):
            # Always rewrite stamp; only field bodies change when added/updated
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        report["schemas"].append(row)

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"added={report['totals']['added']} updated={report['totals']['updated']} "
        f"unchanged={report['totals']['unchanged']} no_export={report['totals']['no_export']}"
    )
    print(f"report={REPORT}")


if __name__ == "__main__":
    main()
