"""Migration conseiller_account_id — COPIE LOCALE UNIQUEMENT.

Décisions validées (2026-11-12 / précisées 2026-11-13) :
- Service Fiscal : pas d'account_id (option B) — déjà hors « sure »
- BONVESTING / Jordy Bonvin : exclus tant que non confirmés
- Alberto Mendes et Pascal Maret : inclus dans la migration (libellés sure)
- DOS-0232 / DOS-0235 (couples Pascal+Alberto) : stamp Pascal uniquement ;
  libellés conseiller de chaque membre inchangés ; Alberto garde l'accès admin
- Ambiguës / vides / impossibles (hors override couple) : aucune écriture
- Production : interdite (hôte localhost obligatoire)

    python scripts/migrer_attribution_copie.py --local --db leosoft_mendes_migration_sim --dry-run
    python scripts/migrer_attribution_copie.py --local --db leosoft_mendes_migration_sim --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from attribution_matching import (  # noqa: E402
    build_account_index,
    classify_collection,
)
from conseiller_identity import normalize_conseiller_key  # noqa: E402
from pymongo import MongoClient  # noqa: E402

# Comptes / libellés exclus jusqu'à validation métier
EXCLUDED_ACCOUNT_IDS = {
    "user_161136756f02": "bonvesting_jordy_pending_validation",  # BONVESTING / Jordy Bonvin
}
EXCLUDED_LABEL_KEYS = {
    normalize_conseiller_key("Jordy Bonvin"): "bonvesting_jordy_pending_validation",
    normalize_conseiller_key("BONVESTING SNC"): "bonvesting_jordy_pending_validation",
}
SERVICE_FISCAL_KEY = normalize_conseiller_key("Service Fiscal (Impot)")

# Couples Pascal/Alberto : account_id → Pascal ; libellés conservés tels quels.
PASCAL_ACCOUNT_ID = "user_6c6401fa3365"
PASCAL_ACCOUNT_LABEL = "Pascal Maret"
FORCE_PASCAL_DOSSIER_REFS = frozenset({"DOS-0232", "DOS-0235"})


def _hote(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return "local" if host in {"localhost", "127.0.0.1", "::1"} else "distant"


def _ref(doc: dict) -> str:
    return str(doc.get("numero_dossier") or doc.get("id") or "?")


def _is_excluded(doc: dict, row: dict) -> tuple[bool, str]:
    label = str(doc.get("conseiller") or doc.get("agent_label") or "").strip()
    key = normalize_conseiller_key(label)
    if key == SERVICE_FISCAL_KEY or "service fiscal" in key:
        return True, "service_fiscal_option_b"
    if key in EXCLUDED_LABEL_KEYS:
        return True, EXCLUDED_LABEL_KEYS[key]
    aid = str(row.get("account_id") or "").strip()
    if aid in EXCLUDED_ACCOUNT_IDS:
        return True, EXCLUDED_ACCOUNT_IDS[aid]
    return False, ""


def plan_writes(db) -> dict:
    users = list(db.users.find({}, {"_id": 0, "password_hash": 0}))
    clients = list(
        db.clients.find(
            {"source_import": {"$ne": "suivi_3p_excel"}},
            {
                "_id": 0,
                "id": 1,
                "numero_dossier": 1,
                "conseiller": 1,
                "agent_label": 1,
                "agent_email": 1,
                "conseiller_email": 1,
                "conseiller_account_id": 1,
                "linked_spouse_id": 1,
            },
        )
    )
    accounts = build_account_index(users)
    spouses = {c["id"]: c for c in clients if c.get("id")}
    rows = classify_collection(clients, accounts, spouses_by_id=spouses)
    by_id = {r["id"]: r for r in rows}

    to_write = []
    skipped = []
    for doc in clients:
        row = by_id[doc["id"]]
        ref = _ref(doc)
        excl, why = _is_excluded(doc, row)
        if excl:
            skipped.append({"ref": ref, "reason": why, "match_status": row["status"]})
            continue

        # Override couple : stamp Pascal, ne pas réécrire le libellé conseiller.
        if ref in FORCE_PASCAL_DOSSIER_REFS:
            existing = str(doc.get("conseiller_account_id") or "").strip()
            if existing == PASCAL_ACCOUNT_ID:
                skipped.append(
                    {
                        "ref": ref,
                        "reason": "deja_a_jour",
                        "match_status": row["status"],
                        "note": "force_pascal_couple",
                        "conseiller_label_preserved": doc.get("conseiller"),
                    }
                )
                continue
            to_write.append(
                {
                    "id": doc["id"],
                    "ref": ref,
                    "conseiller": doc.get("conseiller"),
                    "account_id": PASCAL_ACCOUNT_ID,
                    "account_label": PASCAL_ACCOUNT_LABEL,
                    "previous_account_id": existing or None,
                    "override": "force_pascal_couple",
                    "match_status_before": row["status"],
                    "match_reason_before": row.get("reason"),
                    "label_unchanged": True,
                }
            )
            continue

        if row["status"] != "sure" or not row.get("account_id"):
            skipped.append(
                {
                    "ref": ref,
                    "reason": f"non_migre_{row['status']}",
                    "match_status": row["status"],
                    "match_reason": row.get("reason"),
                }
            )
            continue
        existing = str(doc.get("conseiller_account_id") or "").strip()
        if existing == row["account_id"]:
            skipped.append({"ref": ref, "reason": "deja_a_jour", "match_status": "sure"})
            continue
        to_write.append(
            {
                "id": doc["id"],
                "ref": ref,
                "conseiller": doc.get("conseiller"),
                "account_id": row["account_id"],
                "account_label": row.get("account_label"),
                "previous_account_id": existing or None,
            }
        )

    force_pascal = [w for w in to_write if w.get("override") == "force_pascal_couple"]
    return {
        "clients_total": len(clients),
        "to_write": to_write,
        "skipped": skipped,
        "counts": {
            "to_write": len(to_write),
            "skipped": len(skipped),
            "excluded_bonvesting": sum(1 for s in skipped if s["reason"] == "bonvesting_jordy_pending_validation"),
            "excluded_service_fiscal": sum(1 for s in skipped if s["reason"] == "service_fiscal_option_b"),
            "force_pascal_couple": len(force_pascal),
            "alberto_account_writes": sum(
                1 for w in to_write if w.get("account_id") == "user_8250e6c40fa7"
            ),
            "pascal_account_writes": sum(
                1 for w in to_write if w.get("account_id") == PASCAL_ACCOUNT_ID
            ),
            "non_sure": sum(1 for s in skipped if str(s["reason"]).startswith("non_migre_")),
        },
    }


def apply_writes(db, plan: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    modified = 0
    log = []
    for item in plan["to_write"]:
        res = db.clients.update_one(
            {"id": item["id"]},
            {
                "$set": {
                    "conseiller_account_id": item["account_id"],
                    "conseiller_account_id_migrated_at": now,
                    "conseiller_account_id_migration": "local_sim_2026-11-12",
                }
            },
        )
        modified += int(res.modified_count or 0)
        log.append({**item, "modified": bool(res.modified_count)})
    journal_doc = {
        "applied_at": now,
        "modified_count": modified,
        "planned_count": len(plan["to_write"]),
        "items": log,
        "host": "localhost_only",
        "exclusions_preserved": [
            "service_fiscal",
            "bonvesting_jordy",
            "non_attribues",
        ],
        "overrides": ["force_pascal_couple_DOS-0232_DOS-0235"],
    }
    db["_attribution_migration_log"].delete_many({})
    db["_attribution_migration_log"].insert_one(journal_doc)
    # Miroir dans le journal d'accès (même forme que la prod préparée)
    db["access_policy_journal"].insert_one(
        {
            "id": f"ape_mig_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "event_type": "attribution_migration",
            "actor_account_id": None,
            "actor_email": "local_script",
            "detail": {
                "modified_count": modified,
                "planned_count": len(plan["to_write"]),
                "db": db.name,
            },
            "created_at": now,
        }
    )
    return {"modified_count": modified, "planned_count": len(plan["to_write"])}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--local", action="store_true", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--json", dest="json_path", default="")
    args = p.parse_args(argv)
    if args.dry_run == args.apply:
        print("Choisir exactement une option : --dry-run ou --apply", file=sys.stderr)
        return 2
    url = "mongodb://127.0.0.1:27017"
    if _hote(url) != "local":
        return 3
    if args.db in {"prevoyancecrm", "admin", "local"}:
        print("Abort: base interdite", file=sys.stderr)
        return 4

    client = MongoClient(url, serverSelectionTimeoutMS=10000)
    db = client[args.db]
    plan = plan_writes(db)
    report = {
        "mode": "DRY_RUN" if args.dry_run else "APPLY_LOCAL_COPY",
        "db": args.db,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": plan["counts"],
        "clients_total": plan["clients_total"],
        "sample_writes": plan["to_write"][:15],
        "excluded_bonvesting_refs": [
            s["ref"] for s in plan["skipped"] if s["reason"] == "bonvesting_jordy_pending_validation"
        ],
    }
    if args.apply:
        result = apply_writes(db, plan)
        report["apply_result"] = result
    client.close()

    print(json.dumps({k: report[k] for k in ("mode", "db", "counts", "clients_total", "apply_result") if k in report}, ensure_ascii=False, indent=2))
    print(f"Écritures prévues: {plan['counts']['to_write']}")
    print(f"Exclus BONVESTING: {plan['counts']['excluded_bonvesting']} → {report['excluded_bonvesting_refs']}")
    print(f"Exclus Service Fiscal: {plan['counts']['excluded_service_fiscal']}")
    print(f"Override couples Pascal (DOS-0232/0235): {plan['counts'].get('force_pascal_couple', 0)}")
    print(f"Écritures compte Alberto: {plan['counts'].get('alberto_account_writes', 0)}")
    print(f"Écritures compte Pascal: {plan['counts'].get('pascal_account_writes', 0)}")
    print(f"Non sûrs / autres skips: {plan['counts']['non_sure']}")

    if args.json_path:
        path = Path(args.json_path)
        # rapport hors dépôt : inclure plan complet
        full = {**report, "to_write": plan["to_write"], "skipped_summary_by_reason": {}}
        from collections import Counter

        full["skipped_summary_by_reason"] = dict(Counter(s["reason"] for s in plan["skipped"]))
        path.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
        print("JSON", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
