"""Rappel unique, 21 jours après la transmission d'une offre à l'agent.

Les dossiers anciens sans date de transmission enregistrée par ce mécanisme
ne sont pas relancés : pas d'envoi rétroactif groupé.
Un simple changement d'avancement n'appelle pas ce module.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from demandes_offres_3p import (
    COLLECTION,
    history_entry,
    now_iso,
    pick_conseiller_email_from_demande,
)
from demandes_offres_ameliorations import etape_affichee

RELANCE_DELAY = timedelta(days=21)
CLAIM_TTL = timedelta(minutes=30)
CLOSING_STEPS = {"envoyee_client", "signee", "annulee", "refusee", "non_signee"}
_NOT_SENT = {
    "$or": [
        {"relance_agent_21j_sent_at": {"$exists": False}},
        {"relance_agent_21j_sent_at": None},
        {"relance_agent_21j_sent_at": ""},
    ]
}


def _parse_iso(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def relance_agent_decision(doc: dict, now: datetime) -> str:
    """send, wait, skip ou retry.

    skip : issue déjà renseignée, ou aucune transmission datée.
    wait : transmis depuis moins de 21 jours.
    send : premier rappel dû.
    retry : un envoi précédent a échoué, ou une réservation a expiré.
    """
    if doc.get("relance_agent_21j_sent_at"):
        return "skip"
    if etape_affichee(doc) in CLOSING_STEPS:
        return "skip"
    transmitted = _parse_iso(doc.get("offre_transmise_agent_at"))
    if transmitted is None:
        return "skip"
    moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if moment.astimezone(timezone.utc) - transmitted < RELANCE_DELAY:
        return "wait"
    claim = _parse_iso(doc.get("relance_agent_21j_claim_at"))
    if doc.get("relance_agent_21j_claim") and claim and moment.astimezone(timezone.utc) - claim < CLAIM_TTL:
        return "skip"
    if doc.get("relance_agent_21j_last_error"):
        return "retry"
    return "send"


def _zurich_label(moment: datetime) -> str:
    from zoneinfo import ZoneInfo

    local = moment.astimezone(ZoneInfo("Europe/Zurich"))
    return local.strftime("%d.%m.%Y %H:%M")


async def _recipient_email(db, doc: dict) -> str:
    direct = pick_conseiller_email_from_demande(doc) or ""
    if "@" in direct:
        return direct
    for key in ("created_by_account_id", "agent_account_id", "created_by"):
        account_id = str(doc.get(key) or "").strip()
        if not account_id:
            continue
        user = await db.users.find_one(
            {"$or": [{"user_id": account_id}, {"account_id": account_id}], "active": {"$ne": False}},
            {"_id": 0, "email": 1},
        )
        email = str((user or {}).get("email") or "").strip()
        if "@" in email:
            return email
    return ""


async def process_relances_agent_21j(db, *, now: Optional[datetime] = None, limit: int = 200) -> dict:
    from email_service import (
        MAIL_TYPE_RELANCE_AGENT_21J,
        format_relance_agent_21j_email,
        offres_email_enabled,
        send_email_async,
    )

    moment = now or datetime.now(timezone.utc)
    stats = {"scanned": 0, "sent": 0, "skipped": 0, "waiting": 0, "failed": 0, "no_recipient": 0}
    if not offres_email_enabled():
        return {**stats, "disabled": True}
    cursor = db[COLLECTION].find(
        {
            "is_deleted": {"$ne": True},
            "offre_transmise_agent_at": {"$exists": True, "$nin": [None, ""]},
            **_NOT_SENT,
        },
        {"_id": 0},
    )
    rows = await cursor.to_list(limit)
    for doc in rows:
        stats["scanned"] += 1
        decision = relance_agent_decision(doc, moment)
        if decision == "wait":
            stats["waiting"] += 1
            continue
        if decision == "skip":
            stats["skipped"] += 1
            continue
        email = await _recipient_email(db, doc)
        if "@" not in email:
            stats["no_recipient"] += 1
            await db[COLLECTION].update_one(
                {"id": doc.get("id")},
                {"$set": {
                    "relance_agent_21j_last_error": "Destinataire introuvable",
                    "relance_agent_21j_claim": False,
                    "updated_at": now_iso(),
                }},
            )
            continue
        token = str(uuid.uuid4())
        expiry = (moment.astimezone(timezone.utc) - CLAIM_TTL).isoformat()
        claimed = await db[COLLECTION].update_one(
            {
                "id": doc.get("id"),
                "$and": [
                    _NOT_SENT,
                    {"$or": [
                        {"relance_agent_21j_claim": {"$in": [None, False, ""]}},
                        {"relance_agent_21j_claim_at": {"$lt": expiry}},
                        {"relance_agent_21j_claim_at": {"$exists": False}},
                    ]},
                ],
            },
            {"$set": {
                "relance_agent_21j_claim": token,
                "relance_agent_21j_claim_at": now_iso(),
            }},
        )
        if getattr(claimed, "modified_count", 0) != 1:
            stats["skipped"] += 1
            continue
        subject, body_text, body_html = format_relance_agent_21j_email(doc)
        ok, err = await send_email_async(
            email,
            subject,
            body_text,
            body_html=body_html,
            mail_type=MAIL_TYPE_RELANCE_AGENT_21J,
            log_meta={"demande_id": doc.get("id"), "numero": doc.get("numero")},
        )
        if not ok:
            stats["failed"] += 1
            await db[COLLECTION].update_one(
                {"id": doc.get("id"), "relance_agent_21j_claim": token},
                {"$set": {
                    "relance_agent_21j_claim": False,
                    "relance_agent_21j_last_error": (err or "Envoi impossible")[:300],
                    "updated_at": now_iso(),
                }},
            )
            continue
        stamp = now_iso()
        label = _zurich_label(_parse_iso(stamp) or moment)
        await db[COLLECTION].update_one(
            {"id": doc.get("id"), "relance_agent_21j_claim": token},
            {
                "$set": {
                    "relance_agent_21j_sent_at": stamp,
                    "relance_agent_21j_claim": False,
                    "relance_agent_21j_last_error": "",
                    "updated_at": stamp,
                },
                "$push": {
                    "historique": history_entry(
                        f"Relance automatique envoyée à l'agent — {label}",
                        by_name="Le service des Offres",
                        detail=f"E-mail envoyé à {email}",
                        statut=doc.get("statut"),
                        meta={"relance_agent_21j": True, "to": email},
                    ),
                },
            },
        )
        stats["sent"] += 1
    return stats
