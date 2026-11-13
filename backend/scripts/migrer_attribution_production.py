"""Migration conseiller_account_id en PRODUCTION — accord Cemile obligatoire.

Sécurité :
- N'écrit QUE conseiller_account_id (+ métadonnées migration / journal)
- Ne touche PAS ACCESS_MODE, users, permissions, libellés conseiller
- Exige un plan attendu (243) ; tout écart → STOP sans écriture
- Refuse d'écraser un stamp existant différent du plan
- Journal rollback : previous values par id

    # Dry-run (lecture seule) — MONGO_URL/DB_NAME injectés (ex. railway run)
    python scripts/migrer_attribution_production.py --dry-run \\
      --expected-json %TEMP%/leosoft_mig_apply_sim243.json \\
      --expected-count 243

    # Apply uniquement si fingerprint OK
    python scripts/migrer_attribution_production.py --apply \\
      --cemile-autorise-production-243 \\
      --expected-json %TEMP%/leosoft_mig_apply_sim243.json \\
      --expected-count 243 \\
      --journal %TEMP%/leosoft_mig_prod_journal.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _SCRIPTS)

from migrer_attribution_copie import plan_writes  # noqa: E402
from pymongo import MongoClient  # noqa: E402

FORBIDDEN_DB_HINTS = {"admin", "local", "config"}


def _hote(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return "local" if host in {"localhost", "127.0.0.1", "::1"} else "distant"


def _load_expected(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("to_write") or []
    expected: dict[str, str] = {}
    for row in rows:
        cid = str(row.get("id") or "").strip()
        aid = str(row.get("account_id") or "").strip()
        if not cid or not aid:
            raise SystemExit(f"Plan attendu invalide: {row!r}")
        if cid in expected and expected[cid] != aid:
            raise SystemExit(f"Plan attendu conflictuel pour {cid}")
        expected[cid] = aid
    return expected


def _fingerprint(mapping: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(mapping.items())


def build_prod_plan(db, expected: dict[str, str]) -> dict:
    """Compare plan moteur vs attendu ; détecte anomalies sans écrire."""
    engine = plan_writes(db)
    by_id = {w["id"]: w for w in engine["to_write"]}
    # Inclure deja_a_jour qui matchent le plan (pas dans to_write)
    clients = {
        c["id"]: c
        for c in db.clients.find(
            {"id": {"$in": list(expected.keys())}},
            {"_id": 0, "id": 1, "numero_dossier": 1, "conseiller": 1, "conseiller_account_id": 1},
        )
    }

    anomalies: list[dict] = []
    to_write: list[dict] = []
    already_ok: list[dict] = []

    # 1) Chaque id attendu doit exister et aboutir au bon account_id
    for cid, want_aid in expected.items():
        doc = clients.get(cid)
        if not doc:
            anomalies.append({"id": cid, "kind": "missing_client"})
            continue
        existing = str(doc.get("conseiller_account_id") or "").strip()
        planned = by_id.get(cid)
        # Si le moteur veut écrire autre chose
        if planned and planned["account_id"] != want_aid:
            anomalies.append(
                {
                    "id": cid,
                    "ref": doc.get("numero_dossier"),
                    "kind": "engine_differs_from_expected",
                    "expected": want_aid,
                    "engine": planned["account_id"],
                }
            )
            continue
        # Si pas dans to_write moteur : soit déjà OK, soit classé skip
        if not planned:
            if existing == want_aid:
                already_ok.append(
                    {
                        "id": cid,
                        "ref": doc.get("numero_dossier"),
                        "account_id": want_aid,
                        "conseiller": doc.get("conseiller"),
                    }
                )
                continue
            # Chercher skip reason
            skip = next((s for s in engine["skipped"] if s.get("ref") == doc.get("numero_dossier")), None)
            anomalies.append(
                {
                    "id": cid,
                    "ref": doc.get("numero_dossier"),
                    "kind": "expected_not_planned",
                    "existing": existing or None,
                    "expected": want_aid,
                    "skip": skip,
                }
            )
            continue
        # Stamp existant différent → ne pas écraser
        if existing and existing != want_aid:
            anomalies.append(
                {
                    "id": cid,
                    "ref": doc.get("numero_dossier"),
                    "kind": "would_overwrite_recent_stamp",
                    "existing": existing,
                    "expected": want_aid,
                }
            )
            continue
        if existing == want_aid:
            already_ok.append(
                {
                    "id": cid,
                    "ref": doc.get("numero_dossier"),
                    "account_id": want_aid,
                    "conseiller": doc.get("conseiller"),
                }
            )
            continue
        to_write.append(
            {
                "id": cid,
                "ref": doc.get("numero_dossier"),
                "conseiller": doc.get("conseiller"),
                "account_id": want_aid,
                "account_label": planned.get("account_label"),
                "previous_account_id": existing or None,
                "override": planned.get("override"),
                "label_unchanged": True,
            }
        )

    # 2) Écritures moteur hors périmètre : signalées, non bloquantes, non appliquées
    reported_extras = [
        {
            "id": w["id"],
            "ref": w.get("ref"),
            "kind": "extra_outside_expected_not_applied",
            "account_id": w.get("account_id"),
            "conseiller": w.get("conseiller"),
        }
        for w in engine["to_write"]
        if w["id"] not in expected
    ]

    return {
        "engine_counts": engine["counts"],
        "clients_total": engine["clients_total"],
        "expected_count": len(expected),
        "to_write": to_write,
        "already_ok": already_ok,
        "anomalies": anomalies,
        "reported_extras": reported_extras,
        "skipped_engine": engine["skipped"],
        "ok_for_apply": len(anomalies) == 0 and (len(to_write) + len(already_ok)) == len(expected),
    }


def apply_writes(db, to_write: list[dict], journal_path: Path) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    log_items = []
    modified = 0
    for item in to_write:
        # Garde-fou atomique : n'écrit que si stamp absent ou déjà égal
        filt = {
            "id": item["id"],
            "$or": [
                {"conseiller_account_id": {"$exists": False}},
                {"conseiller_account_id": None},
                {"conseiller_account_id": ""},
                {"conseiller_account_id": item["account_id"]},
            ],
        }
        res = db.clients.update_one(
            filt,
            {
                "$set": {
                    "conseiller_account_id": item["account_id"],
                    "conseiller_account_id_migrated_at": now,
                    "conseiller_account_id_migration": "prod_243_2026-11-13",
                }
            },
        )
        ok = bool(res.modified_count or res.matched_count)
        if res.modified_count:
            modified += 1
        if not res.matched_count:
            raise RuntimeError(f"Refuse écriture (filtre stamp) id={item['id']} ref={item.get('ref')}")
        log_items.append({**item, "modified": bool(res.modified_count), "matched": bool(res.matched_count)})

    journal = {
        "applied_at": now,
        "host": _hote(os.environ.get("MONGO_URL") or ""),
        "db": db.name,
        "migration": "prod_243_2026-11-13",
        "modified_count": modified,
        "planned_count": len(to_write),
        "items": log_items,
        "rollback_hint": "Pour chaque item: $unset conseiller_account_id ou $set previous_account_id",
        "access_mode_untouched": True,
        "permissions_untouched": True,
        "labels_untouched": True,
    }
    db["_attribution_migration_log"].insert_one({**journal, "items": log_items})
    db["access_policy_journal"].insert_one(
        {
            "id": f"ape_mig_prod_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "event_type": "attribution_migration_prod_243",
            "actor_account_id": None,
            "actor_email": "cemile_autorise_script",
            "detail": {
                "modified_count": modified,
                "planned_count": len(to_write),
                "db": db.name,
                "access_mode": "unchanged",
            },
            "created_at": now,
        }
    )
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"modified_count": modified, "planned_count": len(to_write), "journal": str(journal_path)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--cemile-autorise-production-243", action="store_true")
    p.add_argument("--expected-json", required=True)
    p.add_argument("--expected-count", type=int, default=243)
    p.add_argument("--journal", default="")
    p.add_argument("--report-json", default="")
    args = p.parse_args(argv)

    if args.dry_run == args.apply:
        print("Choisir --dry-run ou --apply", file=sys.stderr)
        return 2
    if args.apply and not args.cemile_autorise_production_243:
        print("Refuse apply sans --cemile-autorise-production-243", file=sys.stderr)
        return 3

    url = (os.environ.get("MONGO_URL") or "").strip()
    db_name = (os.environ.get("DB_NAME") or "").strip()
    if not url or not db_name:
        print("MONGO_URL et DB_NAME requis", file=sys.stderr)
        return 4
    if db_name in FORBIDDEN_DB_HINTS:
        print("DB interdite", file=sys.stderr)
        return 5
    if _hote(url) == "local":
        print("Refuse: cette procédure vise la production (hôte non local)", file=sys.stderr)
        return 6

    expected = _load_expected(Path(args.expected_json))
    if len(expected) != args.expected_count:
        print(
            f"STOP: plan attendu count={len(expected)} != {args.expected_count}",
            file=sys.stderr,
        )
        return 7

    client = MongoClient(url, serverSelectionTimeoutMS=20000)
    db = client[db_name]
    # Sanity: ne pas toucher si ACCESS_MODE runtime forcé dual/strict via app_settings
    settings = db.app_settings.find_one({"key": "access_policy"}, {"_id": 0}) or {}
    mode = str((settings.get("value") or {}).get("mode") or "").strip().lower()
    if mode in {"dual", "strict"}:
        print(f"STOP: access_policy runtime mode={mode} (attendu legacy/absent)", file=sys.stderr)
        client.close()
        return 8

    plan = build_prod_plan(db, expected)
    report = {
        "mode": "DRY_RUN" if args.dry_run else "APPLY",
        "db": db_name,
        "host_kind": _hote(url),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expected_count": args.expected_count,
        "to_write_count": len(plan["to_write"]),
        "already_ok_count": len(plan["already_ok"]),
        "anomalies_count": len(plan["anomalies"]),
        "reported_extras_count": len(plan.get("reported_extras") or []),
        "reported_extras": plan.get("reported_extras") or [],
        "engine_counts": plan["engine_counts"],
        "clients_total": plan["clients_total"],
        "ok_for_apply": plan["ok_for_apply"],
        "anomalies_sample": plan["anomalies"][:30],
        "sample_writes": plan["to_write"][:10],
        "runtime_access_policy_mode": mode or None,
    }

    print(json.dumps({k: report[k] for k in report if k != "sample_writes"}, ensure_ascii=False, indent=2))

    if not plan["ok_for_apply"]:
        print("STOP: écart vs périmètre validé — aucune écriture", file=sys.stderr)
        if args.report_json:
            Path(args.report_json).write_text(
                json.dumps(
                    {
                        **report,
                        "anomalies": plan["anomalies"],
                        "reported_extras": plan.get("reported_extras") or [],
                        "to_write": plan["to_write"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        client.close()
        return 10

    if args.dry_run:
        if args.report_json:
            Path(args.report_json).write_text(
                json.dumps(
                    {
                        **report,
                        "to_write": plan["to_write"],
                        "already_ok": plan["already_ok"],
                        "reported_extras": plan.get("reported_extras") or [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        extras_n = len(plan.get("reported_extras") or [])
        print(
            f"DRY-RUN OK — à écrire: {len(plan['to_write'])}, déjà OK: {len(plan['already_ok'])}, "
            f"extras hors périmètre (non appliqués): {extras_n}"
        )
        client.close()
        return 0

    journal_path = Path(args.journal or os.path.join(os.environ.get("TEMP") or "/tmp", "leosoft_mig_prod_journal.json"))
    result = apply_writes(db, plan["to_write"], journal_path)
    report["apply_result"] = result
    if args.report_json:
        Path(args.report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"apply_result": result}, ensure_ascii=False, indent=2))
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
