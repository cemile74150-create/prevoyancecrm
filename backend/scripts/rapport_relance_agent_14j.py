"""Rapport en lecture seule : rappel agent 14 jours et « Dossiers en retard ».

Aucun e-mail, aucune écriture. Liste les dossiers que le prochain passage horaire
relancerait (OFF, agent, destinataire, jours depuis « Offres transmises à
l'agent »), ceux bloqués par la date de mise en service, et les dossiers en
retard (traitement non terminé, RDV client proche ou passé).

Connexion : ``MONGO_URL`` et ``DB_NAME`` (variables de l'API), ou ``--local``
pour ``mongodb://localhost:27017``. L'URI n'est jamais affichée.

    python backend/scripts/rapport_relance_agent_14j.py --local --db leosoft_test
    python backend/scripts/rapport_relance_agent_14j.py --depuis 2026-11-01
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient  # noqa: E402

from demandes_offres_3p import COLLECTION, pick_conseiller_email_from_demande  # noqa: E402
from demandes_offres_pilotage import (  # noqa: E402
    RDV_RETARD_JOURS,
    commercial_code,
    dans_pilotage,
    en_retard_rdv,
    rdv_client_date,
    relance_depart_at,
    traitement_code,
)
from demandes_offres_relance_agent import (  # noqa: E402
    MAX_ENVOIS_PAR_PASSAGE,
    SETTINGS_ID,
    _date_from_setting,
    _zurich_date,
    relance_agent_decision,
)


def _hote(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return "local" if host in {"localhost", "127.0.0.1", "::1"} else "distant (masqué)"


def _args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--local", action="store_true", help="Mongo locale mongodb://localhost:27017")
    p.add_argument("--db", default="", help="nom de la base (défaut : DB_NAME)")
    p.add_argument("--depuis", default="", help="simuler une date de mise en service AAAA-MM-JJ")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _args(argv)
    url = "mongodb://localhost:27017" if args.local else (os.environ.get("MONGO_URL") or "").strip()
    db_name = (args.db or os.environ.get("DB_NAME") or "").strip()
    if not url or not db_name:
        print("MONGO_URL / DB_NAME manquants (ou utiliser --local --db <base>)", file=sys.stderr)
        return 1
    db = MongoClient(url, serverSelectionTimeoutMS=15000)[db_name]
    now = datetime.now(timezone.utc)
    today = _zurich_date(now)
    stored = db["crm_settings"].find_one({"id": SETTINGS_ID}, {"_id": 0}) or {}
    enregistree = _date_from_setting(os.environ.get("OFFRES_RELANCE_14J_DEPUIS")) or _date_from_setting(
        stored.get("active_depuis")
    )
    depuis = _date_from_setting(args.depuis) or enregistree or today
    tenant = (os.environ.get("TENANT_USER_ID") or "").strip()
    scope = {"is_deleted": {"$ne": True}, **({"user_id": tenant} if tenant else {})}
    docs = [d for d in db[COLLECTION].find(scope, {"_id": 0}) if dans_pilotage(d)]

    print("Mode : LECTURE SEULE (aucun e-mail, aucune écriture)")
    print(f"Base : {db_name} · hôte {_hote(url)} · aujourd'hui (Zurich) {today.isoformat()}")
    print(f"Mise en service enregistrée : {enregistree.isoformat() if enregistree else 'aucune (posée au 1er passage)'}"
          f" · date utilisée : {depuis.isoformat()} · max {MAX_ENVOIS_PAR_PASSAGE} e-mails / passage")

    non_renseignes = [d for d in docs if commercial_code(d) not in {"signee", "non_signee"}
                      and traitement_code(d) == "offre_transmise"]
    a_relancer, bloques, sans_date, deja = [], [], [], []
    for doc in non_renseignes:
        if doc.get("relance_agent_14j_sent_at") or doc.get("relance_agent_21j_sent_at"):
            deja.append(doc)
            continue
        start = relance_depart_at(doc)
        if not start:
            sans_date.append(doc)
            continue
        decision = relance_agent_decision(doc, now, mise_en_service=depuis)
        jours = (today - _zurich_date(datetime.fromisoformat(start.replace("Z", "+00:00")))).days
        ligne = (doc.get("numero"), doc.get("agent_label") or "—", pick_conseiller_email_from_demande(doc) or "?",
                 start[:10], jours)
        if decision in {"send", "retry"}:
            a_relancer.append(ligne)
        elif decision == "skip" and jours >= 14:
            bloques.append(ligne)

    print(f"\nOffres transmises à l'agent sans décision finale : {len(non_renseignes)}")
    print(f"  déjà relancés : {len(deja)} · sans date de transmission complète : {len(sans_date)}")
    print(f"\nSeraient relancés au prochain passage : {len(a_relancer)}")
    for numero, agent, email, start, jours in sorted(a_relancer, key=lambda r: -r[4]):
        print(f"  {numero} · {agent} <{email}> · transmis le {start} · {jours} j")
    print(f"\n> 14 j mais échéance avant la mise en service (jamais relancés automatiquement) : {len(bloques)}")
    for numero, agent, email, start, jours in sorted(bloques, key=lambda r: -r[4]):
        print(f"  {numero} · {agent} <{email}> · transmis le {start} · {jours} j")

    retard = [d for d in docs if en_retard_rdv(d, now)]
    print(f"\nDossiers en retard (traitement non terminé, RDV ≤ {RDV_RETARD_JOURS} j ou passé) : {len(retard)}")
    for doc in sorted(retard, key=lambda d: rdv_client_date(d) or date.max):
        print(f"  {doc.get('numero')} · RDV {rdv_client_date(doc)} · {traitement_code(doc)} · {doc.get('agent_label') or '—'}")
    print("\nRapport terminé : aucune écriture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
