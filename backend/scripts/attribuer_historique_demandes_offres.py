"""Attribue les anciennes demandes d'offres au gestionnaire qui les a traitées.

Simulation par défaut : aucune écriture. L'écriture exige ``--execute`` et
``--confirmer-base <nom de la base>``. Réexécution sans effet sur les dossiers
déjà attribués (à la main ou par cette migration).

Connexion : ``MONGO_URL`` et ``DB_NAME`` (variables de l'API), ou ``--local``
pour ``mongodb://localhost:27017``. L'URI n'est jamais affichée.

    python backend/scripts/attribuer_historique_demandes_offres.py --local --db leosoft_visuel_20261105
    python backend/scripts/attribuer_historique_demandes_offres.py --rapport rapport.json
    python backend/scripts/attribuer_historique_demandes_offres.py --execute --confirmer-base prevoyancecrm
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient  # noqa: E402

from access_control import can_process_offres, user_from_doc  # noqa: E402
from demandes_offres_3p import COLLECTION  # noqa: E402
from demandes_offres_attribution_historique import (  # noqa: E402
    DECISION_AMBIGUE,
    DECISION_ATTRIBUABLE,
    DECISION_DEJA_MANUELLE,
    DECISION_DEJA_MIGREE,
    DECISION_HORS_PILOTAGE,
    DECISION_NON_IDENTIFIEE,
    DECISION_SANS_DROITS,
    DECISION_SANS_TRAITEMENT,
    Annuaire,
    normaliser,
    patch_attribution,
    planifier,
)
from demandes_offres_pilotage import non_attribuee_filter  # noqa: E402

LIBELLES = {
    DECISION_HORS_PILOTAGE: "Hors pilotage (brouillon / supprimée / annulée)",
    DECISION_DEJA_MANUELLE: "Déjà attribuées manuellement (skip)",
    DECISION_DEJA_MIGREE: "Déjà attribuées par cette migration (skip)",
    DECISION_ATTRIBUABLE: "Attribuables",
    DECISION_AMBIGUE: "Ambiguës (non attribuées)",
    DECISION_NON_IDENTIFIEE: "Auteur sans compte utilisateur (non attribuées)",
    DECISION_SANS_DROITS: "Compte inactif ou sans droit gestionnaire (non attribuées)",
    DECISION_SANS_TRAITEMENT: "Aucune action de traitement (non attribuées)",
}


class LectureSeule:
    """Collection Mongo réduite aux lectures : la simulation ne peut rien écrire."""

    def __init__(self, collection):
        self._c = collection

    def find(self, *args, **kwargs):
        return self._c.find(*args, **kwargs)

    def count_documents(self, *args, **kwargs):
        return self._c.count_documents(*args, **kwargs)


def _hote(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return "local" if host in {"localhost", "127.0.0.1", "::1"} else "distant (masqué)"


def _args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="simulation, aucune écriture (défaut)")
    mode.add_argument("--execute", action="store_true", help="écrit les attributions")
    p.add_argument("--confirmer-base", default="", help="nom de la base, obligatoire avec --execute")
    p.add_argument("--local", action="store_true", help="Mongo locale mongodb://localhost:27017")
    p.add_argument("--db", default="", help="nom de la base (défaut : DB_NAME)")
    p.add_argument("--rapport", default="", help="fichier JSON du détail par demande")
    p.add_argument("--exemple", action="append", default=[], help="client à détailler (répétable)")
    p.add_argument("--exemples-max", type=int, default=15)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _args(argv)
    url = "mongodb://localhost:27017" if args.local else (os.environ.get("MONGO_URL") or "").strip()
    db_name = (args.db or os.environ.get("DB_NAME") or "").strip()
    if not url or not db_name:
        print("MONGO_URL / DB_NAME manquants (ou utiliser --local --db <base>)", file=sys.stderr)
        return 1
    if args.execute and args.confirmer_base != db_name:
        print(f"--execute exige --confirmer-base {db_name}", file=sys.stderr)
        return 1

    client = MongoClient(url, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    demandes = db[COLLECTION] if args.execute else LectureSeule(db[COLLECTION])
    users = LectureSeule(db["users"])
    tenant = (os.environ.get("TENANT_USER_ID") or "").strip()
    scope = {"user_id": tenant} if tenant else {}

    print(f"Mode : {'EXECUTION (écriture)' if args.execute else 'SIMULATION (aucune écriture)'}")
    print(f"Base : {db_name} · hôte {_hote(url)}" + (f" · tenant {tenant}" if tenant else ""))

    annuaire = Annuaire.depuis_users(
        users.find({}, {"_id": 0, "password_hash": 0, "password": 0}),
        user_from_doc,
        can_process_offres,
    )
    docs = list(demandes.find(scope, {"_id": 0}))
    decisions = planifier(docs, annuaire)
    counts = Counter(d.decision for d in decisions)
    par_gestionnaire = defaultdict(list)
    for d in decisions:
        if d.decision == DECISION_ATTRIBUABLE:
            par_gestionnaire[d.gestionnaire_nom].append(d)

    print(f"\nComptes utilisateurs : {len({c.id for c in annuaire.comptes})} "
          f"· gestionnaires actifs : {len({c.id for c in annuaire.comptes if c.actif and c.gestionnaire})}")
    print(f"Demandes scannées : {len(decisions)}")
    for code, label in LIBELLES.items():
        print(f"  {label} : {counts.get(code, 0)}")

    print("\nAttribuables par gestionnaire :")
    for nom, items in sorted(par_gestionnaire.items(), key=lambda kv: (-len(kv[1]), kv[0].casefold())):
        multi = sum(1 for d in items if len(d.gestionnaires_vus) > 1)
        print(f"  {nom} : {len(items)}" + (f" (dont {multi} avec plusieurs gestionnaires dans l'historique)" if multi else ""))
    if not par_gestionnaire:
        print("  —")

    for code in (DECISION_AMBIGUE, DECISION_NON_IDENTIFIEE, DECISION_SANS_DROITS):
        items = [d for d in decisions if d.decision == code]
        if items:
            print(f"\n{LIBELLES[code]} :")
            for d in items[: args.exemples_max]:
                cands = ", ".join(f"{c['nom']} [{c['id']}]" for c in d.candidats) or "aucun"
                print(f"  {d.numero} · {d.client} · {d.raison} · candidats : {cands}")
            if len(items) > args.exemples_max:
                print(f"  … {len(items) - args.exemples_max} autres (voir --rapport)")

    print("\nExemples attribuables :")
    for d in [d for d in decisions if d.decision == DECISION_ATTRIBUABLE][: args.exemples_max]:
        print(f"  {d.numero} · {d.client} · agent {d.agent} → {d.gestionnaire_nom} "
              f"(« {d.action} » {str(d.action_at or '')[:10]})")

    cibles = [normaliser(x) for x in (args.exemple or ["Perseguers"])]
    trouves = [d for d in decisions if any(c in normaliser(d.client) for c in cibles)]
    print(f"\nRecherche exemple ({', '.join(args.exemple or ['Perseguers'])}) : {len(trouves)} demande(s)")
    for d in trouves:
        print(f"  {d.numero} · {d.client} · agent {d.agent} · {LIBELLES[d.decision]} · "
              f"gestionnaire {d.gestionnaire_nom or '—'} · {d.raison or ''} · vus : {', '.join(d.gestionnaires_vus) or '—'}")

    if args.rapport:
        with open(args.rapport, "w", encoding="utf-8") as fh:
            json.dump(
                {"base": db_name, "mode": "execute" if args.execute else "dry-run",
                 "compteurs": dict(counts), "demandes": [d.as_dict() for d in decisions]},
                fh, ensure_ascii=False, indent=1,
            )
        print(f"\nRapport détaillé : {args.rapport}")

    if not args.execute:
        print("\nSimulation terminée : aucune écriture.")
        return 0

    stamp = datetime.now(timezone.utc).isoformat()
    ecrites = concurrentes = 0
    for d in decisions:
        if d.decision != DECISION_ATTRIBUABLE:
            continue
        filt = {"id": d.demande_id, "is_deleted": {"$ne": True}, **scope, **non_attribuee_filter()}
        result = demandes.update_one(filt, patch_attribution(d, stamp=stamp))
        if result.modified_count:
            ecrites += 1
        else:
            concurrentes += 1
    print(f"\nAttributions écrites : {ecrites} · déjà attribuées entre-temps : {concurrentes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
