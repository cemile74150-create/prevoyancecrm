"""Rapport d'attribution conseiller → compte (LECTURE SEULE).

Ne modifie aucune donnée MongoDB, aucune permission, aucun fichier métier.
Lit uniquement les champs conseiller (libellé / e-mail agent), jamais les
coordonnées client.

Connexion :
  --fixture     jeux de données intégrés (aucun Mongo)
  --local --db  Mongo locale isolée
  MONGO_URL + DB_NAME uniquement si vous le demandez explicitement (pas de
  défaut production silencieux : sans --fixture/--local il faut les deux vars)

    python backend/scripts/rapport_attribution_conseillers.py --fixture
    python backend/scripts/rapport_attribution_conseillers.py --local --db leosoft_attribution_test
    python backend/scripts/rapport_attribution_conseillers.py --json out/rapport.json
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
    count_inactive_and_missing,
    per_conseiller_stats,
    redact_row_for_export,
    summarize_results,
)


def _hote(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return "local" if host in {"localhost", "127.0.0.1", "::1"} else "distant (masqué)"


def _fixture_payload() -> dict:
    """Jeu isolé pour démontrer le rapport sans Mongo."""
    users = [
        {
            "user_id": "user_valentin",
            "email": "vlugnier@agencemendes.ch",
            "prenom": "Valentin",
            "nom": "Lugnier",
            "name": "Valentin Lugnier",
            "role": "conseiller",
            "conseiller": "Valentin Lugnier",
            "active": True,
        },
        {
            "user_id": "user_martin_a",
            "email": "martin.a@agencemendes.ch",
            "prenom": "Martin",
            "nom": "Albert",
            "name": "Martin Albert",
            "role": "conseiller",
            "conseiller": "Martin Albert",
            "active": True,
        },
        {
            "user_id": "user_martin_b",
            "email": "martin.b@agencemendes.ch",
            "prenom": "Martin",
            "nom": "Bernard",
            "name": "Martin Bernard",
            "role": "conseiller",
            "conseiller": "Martin Bernard",
            "active": True,
        },
        {
            "user_id": "user_admin",
            "email": "admin@agencemendes.ch",
            "prenom": "Cemile",
            "nom": "Demirtas",
            "name": "Cemile Demirtas",
            "role": "admin",
            "conseiller": None,
            "active": True,
            "see_all_dossiers": True,
        },
        {
            "user_id": "user_inactif",
            "email": "ex@agencemendes.ch",
            "prenom": "Ex",
            "nom": "Conseiller",
            "name": "Ex Conseiller",
            "role": "conseiller",
            "conseiller": "Ex Conseiller",
            "active": False,
        },
    ]
    clients = [
        {
            "id": "c1",
            "prenom": "Alice",
            "nom": "Dupont",
            "email": "alice.client@example.com",
            "telephone": "0790000001",
            "conseiller": "Valentin Lugnier",
            "numero_dossier": "DOS-0001",
        },
        {
            "id": "c2",
            "prenom": "Bob",
            "nom": "Martin",
            "email": "bob@example.com",
            "conseiller": "valentin lugnier",
            "agent_email": "vlugnier@agencemendes.ch",
            "numero_dossier": "DOS-0002",
        },
        {
            "id": "c3",
            "prenom": "Carla",
            "nom": "Noir",
            "conseiller": "Martin",
            "numero_dossier": "DOS-0003",
        },
        {
            "id": "c4",
            "prenom": "Dan",
            "nom": "Blanc",
            "conseiller": "Non attribué",
            "numero_dossier": "DOS-0004",
        },
        {
            "id": "c5",
            "prenom": "Eve",
            "nom": "Vert",
            "conseiller": "Personne Inconnue",
            "numero_dossier": "DOS-0005",
        },
        {
            "id": "c6",
            "prenom": "Fay",
            "nom": "Bleu",
            "conseiller": "Ex Conseiller",
            "numero_dossier": "DOS-0006",
        },
        {
            "id": "c7",
            "prenom": "Guy",
            "nom": "Couple",
            "conseiller": "Valentin Lugnier",
            "linked_spouse_id": "c8",
            "numero_dossier": "DOS-0007",
        },
        {
            "id": "c8",
            "prenom": "Hana",
            "nom": "Couple",
            "conseiller": "Martin Albert",
            "linked_spouse_id": "c7",
            "numero_dossier": "DOS-0007b",
        },
    ]
    offres = [
        {
            "id": "o1",
            "numero": "OFF-1",
            "agent_label": "Valentin Lugnier",
            "agent_email": "vlugnier@agencemendes.ch",
            "agent_account_id": "user_valentin",
            "prenom": "Client",
            "nom": "Offre",
        },
        {
            "id": "o2",
            "numero": "OFF-2",
            "agent_label": "Martin",
            "prenom": "Autre",
            "nom": "Offre",
        },
    ]
    suivi = [
        {
            "id": "s1",
            "prenom": "Suivi",
            "nom": "Un",
            "conseiller": "Martin Albert",
        }
    ]
    return {"users": users, "clients": clients, "offres": offres, "suivi_3p": suivi}


def _load_mongo(url: str, db_name: str) -> dict:
    from pymongo import MongoClient

    client = MongoClient(url, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    # Projection : jamais besoin du contenu document / PII hors champs utiles au matching.
    user_proj = {
        "_id": 0,
        "user_id": 1,
        "email": 1,
        "prenom": 1,
        "nom": 1,
        "name": 1,
        "role": 1,
        "conseiller": 1,
        "active": 1,
        "see_all_dossiers": 1,
        "permissions": 1,
    }
    client_proj = {
        "_id": 0,
        "id": 1,
        "prenom": 1,
        "nom": 1,
        "dossier_label": 1,
        "numero_dossier": 1,
        "conseiller": 1,
        "agent_label": 1,
        "agent_email": 1,
        "conseiller_email": 1,
        "conseiller_account_id": 1,
        "agent_account_id": 1,
        "created_by_account_id": 1,
        "linked_spouse_id": 1,
        # email/telephone client volontairement exclus de la projection
    }
    offre_proj = {
        "_id": 0,
        "id": 1,
        "numero": 1,
        "prenom": 1,
        "nom": 1,
        "client_label": 1,
        "agent_label": 1,
        "agent_email": 1,
        "conseiller_email": 1,
        "agent_account_id": 1,
        "created_by_account_id": 1,
        "conseiller": 1,
        "is_deleted": 1,
    }
    users = list(db.users.find({}, user_proj))
    clients = list(db.clients.find({"source_import": {"$ne": "suivi_3p_excel"}}, client_proj))
    suivi = list(db.suivi_3p_clients.find({}, client_proj)) if "suivi_3p_clients" in db.list_collection_names() else []
    # Nom de collection offres
    offres_coll = "demandes_offres_3p"
    offres = []
    if offres_coll in db.list_collection_names():
        offres = list(db[offres_coll].find({"is_deleted": {"$ne": True}}, offre_proj))
    client.close()
    return {"users": users, "clients": clients, "offres": offres, "suivi_3p": suivi}


def _collection_block(name: str, records: list, rows: list, accounts) -> dict:
    anoms = [redact_row_for_export(r) for r in rows if r.get("status") in {"ambiguous", "empty", "impossible"}]
    return {
        "summary": summarize_results(rows),
        "inactive_or_missing": count_inactive_and_missing(rows),
        "par_conseiller": per_conseiller_stats(records, rows, accounts),
        "anomalies": anoms,
        "sure_count": sum(1 for r in rows if r.get("status") == "sure"),
    }


def build_report(payload: dict, *, source: str) -> dict:
    accounts = build_account_index(payload["users"])
    clients = payload.get("clients") or []
    offres = payload.get("offres") or []
    suivi = payload.get("suivi_3p") or []
    spouses = {c["id"]: c for c in clients if c.get("id")}
    client_rows = classify_collection(clients, accounts, spouses_by_id=spouses)
    offre_rows = classify_collection(offres, accounts)
    suivi_rows = classify_collection(suivi, accounts)

    report = {
        "mode": "LECTURE_SEULE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "accounts_active": sum(1 for a in accounts if a.active),
        "accounts_total": len(accounts),
        "collections": {
            "clients": _collection_block("clients", clients, client_rows, accounts),
            "demandes_offres": _collection_block("demandes_offres", offres, offre_rows, accounts),
            "suivi_3p": _collection_block("suivi_3p", suivi, suivi_rows, accounts),
        },
        "totals": summarize_results(client_rows + offre_rows + suivi_rows),
        "notes": [
            "Matching sur conseiller / agent_label / agent_email / conseiller_email / account_id existants uniquement.",
            "Les e-mails et téléphones clients ne sont ni lus ni utilisés.",
            "Export anomalies : ref dossier + libellé conseiller uniquement (pas de PII client).",
            "Aucune écriture MongoDB. Aucune permission modifiée.",
            "Les dossiers ambigus restent tels quels jusqu'à décision manuelle (étape ultérieure).",
        ],
    }
    return report


def _print_human(report: dict) -> None:
    print("Mode : LECTURE SEULE — aucune écriture MongoDB, aucune permission modifiée")
    print(f"Source : {report['source']}")
    print(f"Généré : {report['generated_at']}")
    print(f"Comptes : {report['accounts_active']} actifs / {report['accounts_total']} total")
    print()
    for name, block in report["collections"].items():
        s = block["summary"]
        miss = block["inactive_or_missing"]
        print(f"=== {name} ===")
        print(f"  Total                      : {s['total']}")
        print(f"  Association certaine       : {s['sure']}")
        print(f"  Attribution ambiguë        : {s['ambiguous']}")
        print(f"  Sans conseiller (vide)     : {s['empty']}")
        print(f"  Impossible (aucun compte)  : {s['impossible']}")
        print(
            f"  Inactif / id sans compte / sans match : "
            f"{miss['compte_inactif']} / {miss['account_id_sans_compte']} / {miss['aucun_compte_correspondant']}"
        )
        print("  Par raison :")
        for reason, n in sorted((s.get("by_reason") or {}).items(), key=lambda x: (-x[1], x[0])):
            print(f"    - {reason}: {n}")
        print("  Par conseiller (libellé actuel → rattachements sûrs) :")
        for row in (block.get("par_conseiller") or [])[:40]:
            print(
                f"    · {row['conseiller_label']!r}: actuels={row['dossiers_actuels']} "
                f"surs={row['rattaches_surs']} ambigus={row['ambigus']} "
                f"vides={row['vides']} impossibles={row['impossibles']} "
                f"→ {row.get('account_label_cible') or '—'}"
            )
        if len(block.get("par_conseiller") or []) > 40:
            print(f"    … +{len(block['par_conseiller']) - 40} libellés (voir JSON)")
        anoms = block["anomalies"]
        print(f"  Anomalies à revue manuelle : {len(anoms)}")
        for row in anoms[:25]:
            print(
                f"    · {row.get('ref')} | conseiller={row.get('conseiller')!r} | "
                f"{row.get('status')}/{row.get('reason')} | {row.get('detail')}"
            )
        if len(anoms) > 25:
            print(f"    … +{len(anoms) - 25} (liste complète dans le JSON hors dépôt)")
        print()
    tot = report["totals"]
    print("=== TOTAL ===")
    print(
        f"  total={tot['total']} sure={tot['sure']} ambiguous={tot['ambiguous']} "
        f"empty={tot['empty']} impossible={tot['impossible']}"
    )


def _args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", action="store_true", help="Jeu de données intégré (aucun Mongo)")
    p.add_argument("--local", action="store_true", help="Mongo locale mongodb://localhost:27017")
    p.add_argument("--db", default="", help="Nom de la base (avec --local ou MONGO_URL)")
    p.add_argument(
        "--require-local-host",
        action="store_true",
        help="Refuse toute URI dont l'hôte n'est pas localhost (copie isolée)",
    )
    p.add_argument("--json", dest="json_path", default="", help="Écrire le rapport JSON (hors dépôt Git)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _args(argv)
    if args.fixture:
        payload = _fixture_payload()
        source = "fixture-intégré (aucun Mongo)"
    else:
        url = "mongodb://localhost:27017" if args.local else (os.environ.get("MONGO_URL") or "").strip()
        db_name = (args.db or os.environ.get("DB_NAME") or "").strip()
        if not args.local and not (os.environ.get("MONGO_URL") or "").strip():
            print(
                "Refuse de se connecter sans --fixture, --local, ou MONGO_URL explicite.",
                file=sys.stderr,
            )
            return 2
        if not url or not db_name:
            print("DB_NAME / --db manquant.", file=sys.stderr)
            return 2
        if args.require_local_host and _hote(url) != "local":
            print("Abort : --require-local-host exige localhost.", file=sys.stderr)
            return 3
        if not args.local and _hote(url) != "local":
            print(
                "Attention : hôte distant détecté. Lecture seule uniquement — "
                "aucune écriture ne sera exécutée.",
                file=sys.stderr,
            )
        payload = _load_mongo(url, db_name)
        source = f"mongo:{db_name}@{_hote(url)}"

    report = build_report(payload, source=source)
    _print_human(report)
    if args.json_path:
        path = Path(args.json_path)
        # Garde-fou : ne pas écrire dans le dépôt Git
        resolved = path.resolve()
        repo_markers = ("leosoft-saisie-preneur", "prevoyancecrm")
        if any(m in str(resolved).replace("\\", "/") for m in repo_markers) and "AppData" not in str(resolved):
            if "AgentStores" not in str(resolved) and "Temp" not in str(resolved):
                print(
                    f"Refuse d'écrire le JSON dans le dépôt : {resolved}. "
                    "Utilisez un chemin Temp / AgentStores.",
                    file=sys.stderr,
                )
                return 4
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON écrit : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
