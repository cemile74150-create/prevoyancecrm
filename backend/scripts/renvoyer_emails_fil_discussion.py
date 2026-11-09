"""Renvoie l'e-mail des messages déjà postés dans le fil de discussion.

Aucun message n'est ajouté au fil : seul l'e-mail est renvoyé, avec les
destinataires calculés par le code actuel de l'API (agent → boîte
``OFFRES_EMAIL_TO`` ; gestionnaire → agent, sans copie aux boîtes
personnelles des gestionnaires). Option ``--cloche`` : ajoute la cloche au gestionnaire
attribué pour les messages écrits par un autre gestionnaire.

Simulation par défaut. L'envoi exige ``--execute`` et ``--confirmer-base``.
Connexion : ``MONGO_URL``, ``DB_NAME``, ``TENANT_USER_ID`` et SMTP de l'API.
Hors du réseau Railway, ``RENVOI_MONGO_URL`` (URL publique de MongoDB) prend
le pas sur ``MONGO_URL`` interne. L'URI et les secrets ne sont jamais
affichés ; les adresses sont masquées.

    python backend/scripts/renvoyer_emails_fil_discussion.py --numero OFF-2026-0137
    python backend/scripts/renvoyer_emails_fil_discussion.py --depuis 2026-11-09 --execute --confirmer-base prevoyancecrm
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from access_control import TENANT_USER_ID, user_from_doc  # noqa: E402
from demandes_offres_3p import COLLECTION  # noqa: E402
from demandes_offres_messages import COLLECTION_MESSAGES, ROLE_AGENT, ROLE_GESTIONNAIRE  # noqa: E402
from demandes_offres_routes import attach_demandes_offres_routes  # noqa: E402
import email_service  # noqa: E402

POST_MESSAGE_PATH = "/demandes-offres/{demande_id}/messages"


def masque(addr: str) -> str:
    local, _, domain = (addr or "").partition("@")
    return f"{local}@…" if domain else "?"


def _compact(text: str) -> str:
    return " ".join((text or "").split()).lower()


async def deja_recu(db, row: dict, demande_id: str, recipients: list[str]) -> bool:
    """Un e-mail fil « sent » de la demande, adressé à l'un des destinataires, contient déjà ce message.

    Message sans texte : e-mail envoyé dans les 15 minutes suivant le message.
    """
    cibles = {r.lower() for r in recipients}
    extrait = _compact(row.get("contenu") or "")[:80]
    created = str(row.get("created_at") or "")
    logs = db[email_service.EMAIL_LOGS_COLLECTION].find(
        {"ref_id": demande_id, "type": email_service.MAIL_TYPE_FIL_DISCUSSION, "status": "sent"},
        {"_id": 0, "to": 1, "cc": 1, "body_text": 1, "created_at": 1},
    )
    async for log in logs:
        adresses = {(log.get("to") or "").strip().lower()} | {(c or "").strip().lower() for c in log.get("cc") or []}
        if not cibles & adresses:
            continue
        if extrait:
            if extrait in _compact(log.get("body_text") or ""):
                return True
        elif created and log.get("created_at"):
            ecart = _date(log["created_at"]) - _date(created)
            if timedelta(0) <= ecart <= timedelta(minutes=15):
                return True
    return False


def _date(value) -> datetime:
    if isinstance(value, datetime):
        d = value
    else:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def fonctions_api(db) -> dict:
    """Fonctions internes de la route POST messages (mêmes règles que la prod)."""
    router = APIRouter()
    attach_demandes_offres_routes(
        router,
        db=db,
        put_object=lambda *a, **k: None,
        local_storage_fallback=lambda *a, **k: None,
        file_response_headers=lambda *a, **k: {},
        mime_types={},
        app_name="script",
        root_dir=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        load_storage_bytes=lambda path: b"",
    )
    endpoint = next(
        r.endpoint for r in router.routes
        if r.path == POST_MESSAGE_PATH and "POST" in r.methods
    )
    cells = dict(zip(endpoint.__code__.co_freevars, endpoint.__closure__ or ()))
    noms = ("resolve_fil_discussion_email_to", "try_send_email", "write_offre_notification", "actor_name")
    manquants = [n for n in noms if n not in cells]
    if manquants:
        raise RuntimeError(f"Route POST messages modifiée, fonctions introuvables : {manquants}")
    return {n: cells[n].cell_contents for n in noms}


def brancher_journal_email(db) -> None:
    async def _persist(doc: dict) -> None:
        if not doc or not doc.get("id"):
            return
        coll = db[email_service.EMAIL_LOGS_COLLECTION]
        existing = await coll.find_one({"id": doc["id"]}, {"_id": 0})
        if existing:
            merged = {**existing, **doc}
            if existing.get("created_at"):
                merged["created_at"] = existing["created_at"]
            await coll.update_one({"id": doc["id"]}, {"$set": merged})
        else:
            await coll.insert_one(doc)

    email_service.set_email_log_persist(_persist)


def _args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--numero", action="append", default=[], help="OFF-AAAA-NNNN (répétable)")
    p.add_argument("--depuis", default="", help="messages créés à partir de cette date ISO")
    p.add_argument("--message-id", action="append", default=[], help="limiter à ces messages (répétable)")
    p.add_argument("--cloche", action="store_true", help="cloche au gestionnaire attribué si un autre gestionnaire a écrit")
    p.add_argument("--seulement-non-recus", action="store_true",
                   help="ignorer les messages dont le destinataire actuel a déjà reçu l'e-mail (journal email_logs)")
    p.add_argument("--execute", action="store_true", help="envoie réellement les e-mails")
    p.add_argument("--confirmer-base", default="", help="nom de la base, obligatoire avec --execute")
    p.add_argument("--db", default="", help="nom de la base (défaut : DB_NAME)")
    return p.parse_args(argv)


async def run(args) -> int:
    url = (os.environ.get("RENVOI_MONGO_URL") or os.environ.get("MONGO_URL") or "").strip()
    db_name = (args.db or os.environ.get("DB_NAME") or "").strip()
    if not url or not db_name:
        print("MONGO_URL / DB_NAME manquants", file=sys.stderr)
        return 1
    if not (args.numero or args.depuis or args.message_id):
        print("Préciser --numero, --depuis ou --message-id", file=sys.stderr)
        return 1
    if args.execute and args.confirmer_base != db_name:
        print(f"--execute exige --confirmer-base {db_name}", file=sys.stderr)
        return 1

    db = AsyncIOMotorClient(url, serverSelectionTimeoutMS=15000)[db_name]
    brancher_journal_email(db)
    api = fonctions_api(db)
    print(f"Mode : {'ENVOI' if args.execute else 'SIMULATION (aucun envoi)'} · base {db_name} · tenant {TENANT_USER_ID}")
    print(f"E-mails offres activés : {email_service.offres_email_enabled()}")

    dem_filter = {"user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}}
    if args.numero:
        dem_filter["numero"] = {"$in": args.numero}
    msg_filter: dict = {}
    if args.depuis:
        msg_filter["created_at"] = {"$gte": args.depuis}
    if args.message_id:
        msg_filter["id"] = {"$in": args.message_id}
    if args.numero:
        ids = [d["id"] async for d in db[COLLECTION].find(dem_filter, {"_id": 0, "id": 1})]
        msg_filter["demande_id"] = {"$in": ids}

    rows = await db[COLLECTION_MESSAGES].find(msg_filter, {"_id": 0}).sort("created_at", 1).to_list(500)
    print(f"Messages trouvés : {len(rows)}\n")

    compteur = Counter()
    par_destinataire = Counter()
    demandes: dict = {}
    for row in rows:
        did = row.get("demande_id")
        if did not in demandes:
            demandes[did] = await db[COLLECTION].find_one({**dem_filter, "id": did}, {"_id": 0})
        doc = demandes[did]
        if not doc:
            compteur["demande introuvable / hors périmètre"] += 1
            continue
        sender_doc = await db.users.find_one(
            {"$or": [{"user_id": row.get("expediteur_id")}, {"account_id": row.get("expediteur_id")}]},
            {"_id": 0, "password_hash": 0, "password": 0},
        )
        if not sender_doc or not sender_doc.get("email"):
            compteur["expéditeur introuvable"] += 1
            print(f"  {doc.get('numero')} · {row.get('created_at')} · expéditeur introuvable, ignoré")
            continue
        sender = user_from_doc(sender_doc)
        role = row.get("expediteur_role") or ROLE_AGENT
        recipients = await api["resolve_fil_discussion_email_to"](doc, role=role, sender=sender)
        previous = await db[email_service.EMAIL_LOGS_COLLECTION].count_documents({
            "ref_id": did, "type": email_service.MAIL_TYPE_FIL_DISCUSSION, "status": "sent",
        })
        apercu = (row.get("contenu") or "").replace("\n", " ")[:60]
        print(f"- {doc.get('numero')} · {str(row.get('created_at'))[:19]} · {row.get('expediteur_nom')} ({role}) · « {apercu} »"
              f" · id {row.get('id')}")
        print(f"    À : {masque(recipients[0]) if recipients else '—'} · Cc : {', '.join(masque(r) for r in recipients[1:]) or '—'}"
              f" · e-mails fil déjà journalisés pour la demande : {previous}")
        if not recipients:
            compteur["sans destinataire"] += 1
            continue
        if args.seulement_non_recus and await deja_recu(db, row, did, recipients):
            print("    déjà reçu par ce destinataire, ignoré")
            compteur["déjà reçus"] += 1
            continue
        if not args.execute:
            compteur["à renvoyer"] += 1
            continue

        mail_doc = {**doc, "fil_message_author": row.get("expediteur_nom") or api["actor_name"](sender),
                    "fil_message_role": role}
        event = "fil_discussion_gestionnaire" if role == ROLE_AGENT else "fil_discussion_agent"
        sent, error = await api["try_send_email"](
            mail_doc, event=event, note=row.get("contenu") or "",
            to_override=recipients[0], cc=recipients[1:] or None,
        )
        print(f"    → {'envoyé' if sent else 'ÉCHEC : ' + (error or '?')}")
        compteur["envoyés" if sent else "échecs"] += 1
        if sent:
            for r in recipients:
                par_destinataire[masque(r)] += 1

        gid = (doc.get("gestionnaire_id") or "").strip()
        if args.cloche and role == ROLE_GESTIONNAIRE and gid and gid != sender.account_id:
            contenu = row.get("contenu") or ""
            await api["write_offre_notification"](
                doc=doc, event="message",
                title=f"Nouveau message — {doc.get('numero') or ''}".strip(),
                message=f"{row.get('expediteur_nom')} : {contenu if len(contenu) <= 120 else contenu[:117] + '…'}",
                audience="conseiller", account_ids=[gid],
            )
            compteur["cloches ajoutées"] += 1

    print("\nBilan :", dict(compteur) or "rien")
    if par_destinataire:
        print("Destinataires (À + Cc) :", dict(par_destinataire))
    return 0 if not compteur.get("échecs") else 2


def main(argv=None) -> int:
    return asyncio.run(run(_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
