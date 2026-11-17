"""Simulation lecture seule : accès actuel vs accès après rattachement sûr.

Ne écrit rien. Travaille uniquement sur une base locale (--require-local-host).
Les sorties JSON vont hors dépôt (Temp / AgentStores).

    python scripts/simulation_acces_attribution.py --local --db leosoft_mendes_attribution_copy --require-local-host --json %TEMP%/simu.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from access_control import (  # noqa: E402
    ROLE_CONSEILLER,
    can_access_client,
    is_global_viewer,
    user_from_doc,
)
from attribution_matching import (  # noqa: E402
    _full_name_equal,
    build_account_index,
    classify_collection,
    match_record_to_accounts,
    planned_access_by_account_id,
)
from conseiller_identity import normalize_conseiller_key  # noqa: E402
from pymongo import MongoClient  # noqa: E402


def _hote(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return "local" if host in {"localhost", "127.0.0.1", "::1"} else "distant"


def _load(db):
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
                "agent_account_id": 1,
                "created_by_account_id": 1,
                "linked_spouse_id": 1,
            },
        )
    )
    return users, clients


def _ref(doc: dict) -> str:
    return str(doc.get("numero_dossier") or doc.get("id") or "?")


def build_simulation(users: list, clients: list) -> dict:
    accounts = build_account_index(users)
    spouses = {c["id"]: c for c in clients if c.get("id")}
    rows = classify_collection(clients, accounts, spouses_by_id=spouses)
    by_id = {r["id"]: r for r in rows}

    # --- 1. Ventilation exacte des 241 sûrs ---
    sure_by_account: dict = defaultdict(lambda: {"count": 0, "labels": set(), "account_label": None, "refs": []})
    name_qa_ok = 0
    name_qa_warn = []
    for doc in clients:
        row = by_id[doc["id"]]
        if row.get("status") != "sure":
            continue
        aid = row["account_id"]
        bucket = sure_by_account[aid]
        bucket["count"] += 1
        bucket["account_label"] = row.get("account_label")
        label = str(doc.get("conseiller") or doc.get("agent_label") or "").strip()
        if label:
            bucket["labels"].add(label)
        bucket["refs"].append(_ref(doc))
        # Contrôle nom complet
        acc = next(a for a in accounts if a.account_id == aid)
        label_ok = any(_full_name_equal(label, lab) for lab in acc.labels) if label else False
        email_ok = row.get("reason") in {"email_conseiller_unique", "account_id_existant"}
        if label_ok or email_ok:
            name_qa_ok += 1
        else:
            name_qa_warn.append(
                {
                    "ref": _ref(doc),
                    "conseiller": label,
                    "account_label": row.get("account_label"),
                    "reason": row.get("reason"),
                    "detail": "Match sûr mais libellé ≠ jetons complets du compte (vérifier)",
                }
            )

    ventilation = [
        {
            "account_id": aid,
            "account_label": data["account_label"],
            "dossiers_surs": data["count"],
            "libelles": sorted(data["labels"]),
        }
        for aid, data in sorted(sure_by_account.items(), key=lambda x: -x[1]["count"])
    ]
    sum_surs = sum(v["dossiers_surs"] for v in ventilation)

    # --- 2. Service Fiscal ---
    fiscal = [c for c in clients if "service fiscal" in normalize_conseiller_key(c.get("conseiller") or "")]
    fiscal_access = {"global_viewers": [], "conseillers_match_actuel": []}
    for udoc in users:
        user = user_from_doc(udoc)
        if not user.active:
            continue
        if is_global_viewer(user):
            fiscal_access["global_viewers"].append(
                {"account_id": user.account_id, "name": user.name, "role": user.role}
            )
            continue
        # Un conseiller voit-il au moins un dossier Service Fiscal aujourd'hui ?
        hits = [ _ref(c) for c in fiscal if can_access_client(user, c) ]
        if hits:
            fiscal_access["conseillers_match_actuel"].append(
                {"account_id": user.account_id, "name": user.name, "nb": len(hits)}
            )

    # --- 3. Anomalies détaillées ---
    anomalies = []
    for doc in clients:
        row = by_id[doc["id"]]
        if row["status"] == "sure":
            continue
        anomalies.append(
            {
                "ref": _ref(doc),
                "conseiller": doc.get("conseiller") or doc.get("agent_label"),
                "status": row["status"],
                "reason": row["reason"],
                "detail": row.get("detail"),
                "candidates": row.get("candidates") or [],
                "linked_spouse_id": doc.get("linked_spouse_id"),
            }
        )
    anomalies.sort(key=lambda a: (a["reason"], a.get("conseiller") or "", a["ref"]))

    # --- 4. Simulation accès par conseiller ---
    # Future : sure docs get conseiller_account_id ; others keep no account_id
    # → conseiller only sees docs where planned id == self; ambiguous/empty/impossible
    #   disappear from conseiller view unless we keep name fallback (we simulate cutover strict).
    simulated_docs = []
    for doc in clients:
        row = by_id[doc["id"]]
        clone = dict(doc)
        if row["status"] == "sure" and row.get("account_id"):
            clone["conseiller_account_id"] = row["account_id"]
        else:
            clone.pop("conseiller_account_id", None)
        simulated_docs.append(clone)
    sim_by_id = {d["id"]: d for d in simulated_docs}

    per_user = []
    for udoc in users:
        user = user_from_doc(udoc)
        if user.role != ROLE_CONSEILLER or not user.active:
            continue
        if is_global_viewer(user):
            continue  # supervision inchangée — traité à part
        current_ids = {c["id"] for c in clients if can_access_client(user, c)}
        future_ids = {
            d["id"]
            for d in simulated_docs
            if planned_access_by_account_id(user, d)
        }
        lost = current_ids - future_ids
        gained = future_ids - current_ids  # should be rare (homonym fixes)
        # "accessibles aujourd'hui par erreur" = current via name, but sure match is another account
        erroneous = []
        for cid in sorted(current_ids):
            row = by_id[cid]
            if row["status"] == "sure" and row.get("account_id") and row["account_id"] != user.account_id:
                erroneous.append({"ref": _ref(next(c for c in clients if c["id"] == cid)), "owned_by": row.get("account_label")})
            # also partial name access to impossible/ambiguous that aren't "theirs"
        lost_detail = []
        for cid in sorted(lost):
            row = by_id[cid]
            lost_detail.append(
                {
                    "ref": _ref(next(c for c in clients if c["id"] == cid)),
                    "conseiller": (next(c for c in clients if c["id"] == cid)).get("conseiller"),
                    "status_match": row["status"],
                    "reason": row["reason"],
                }
            )
        per_user.append(
            {
                "account_id": user.account_id,
                "name": user.name,
                "conseiller": user.conseiller,
                "acces_actuel": len(current_ids),
                "acces_futur": len(future_ids),
                "perdus": len(lost),
                "gagnes": len(gained),
                "acces_errones_aujourd_hui": erroneous,
                "dossiers_perdus_detail": lost_detail,
                "refs_actuel": sorted(_ref(c) for c in clients if c["id"] in current_ids),
                "refs_futur": sorted(_ref(d) for d in simulated_docs if d["id"] in future_ids),
            }
        )
    per_user.sort(key=lambda x: x["name"].casefold())

    supervisors = []
    for udoc in users:
        user = user_from_doc(udoc)
        if user.active and is_global_viewer(user):
            supervisors.append({"account_id": user.account_id, "name": user.name, "role": user.role})

    return {
        "mode": "LECTURE_SEULE_SIMULATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clients_total": len(clients),
        "sure_total": sum_surs,
        "ventilation_surs": ventilation,
        "ventilation_checksum": sum_surs,
        "name_qa": {"ok": name_qa_ok, "warn": name_qa_warn, "warn_count": len(name_qa_warn)},
        "service_fiscal": {
            "count": len(fiscal),
            "refs": sorted(_ref(c) for c in fiscal),
            "qui_y_accede_aujourd_hui": fiscal_access,
            "apres_migration_stricte": {
                "conseillers": "plus aucun (pas d'account_id sûr)",
                "superviseurs_see_all": "inchangé — voient toujours les 43",
                "options": [
                    "Créer un compte technique « Service Fiscal » et rattacher les 43 fiches (manuel)",
                    "Laisser sans account_id : visibles uniquement des comptes see_all (admin/CEO/gestionnaire)",
                    "Réattribuer chaque dossier à un conseiller nommé (manuel)",
                ],
            },
        },
        "anomalies": anomalies,
        "anomalies_count": len(anomalies),
        "simulation_par_conseiller": per_user,
        "superviseurs_inchanges": supervisors,
        "notes": [
            "Aucune écriture MongoDB. Simulation en mémoire uniquement.",
            "Bascule simulée = stricte sur conseiller_account_id (sans fallback nom).",
            "Les dossiers non sûrs disparaissent de la vue conseiller, restent pour see_all.",
        ],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--local", action="store_true")
    p.add_argument("--db", required=True)
    p.add_argument("--require-local-host", action="store_true")
    p.add_argument("--json", dest="json_path", default="")
    args = p.parse_args(argv)
    url = "mongodb://127.0.0.1:27017" if args.local else (os.environ.get("MONGO_URL") or "")
    if args.require_local_host and _hote(url) != "local":
        print("Abort: hôte non local", file=sys.stderr)
        return 3
    client = MongoClient(url, serverSelectionTimeoutMS=10000)
    # lecture seule : pas d'écriture
    users, clients = _load(client[args.db])
    client.close()
    report = build_simulation(users, clients)
    print(f"Clients={report['clients_total']} Sûrs={report['sure_total']} (checksum={report['ventilation_checksum']})")
    print("Ventilation complète :")
    for v in report["ventilation_surs"]:
        print(f"  {v['dossiers_surs']:3d}  {v['account_label']}  {v['libelles']}")
    print(f"Name QA ok={report['name_qa']['ok']} warn={report['name_qa']['warn_count']}")
    print(f"Service Fiscal={report['service_fiscal']['count']}")
    print(f"Anomalies={report['anomalies_count']}")
    print(f"Conseillers simulés={len(report['simulation_par_conseiller'])}")
    if args.json_path:
        path = Path(args.json_path)
        if "leosoft-saisie-preneur" in str(path.resolve()) and "Temp" not in str(path) and "AgentStores" not in str(path):
            print("Refuse JSON dans le dépôt", file=sys.stderr)
            return 4
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("JSON", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
