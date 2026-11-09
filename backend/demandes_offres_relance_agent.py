"""Rappel unique à l'agent, 14 jours calendaires après la mise à disposition des documents.

Remplace l'ancien rappel à 21 jours (même module, même tâche serveur) :
- départ du délai : première mise à disposition des documents
  (``docs_mis_a_disposition_at``, à défaut ``offre_transmise_agent_at``) ;
  un ajout ultérieur de documents ne repousse pas l'échéance ;
- offre signée, non signée, refusée ou annulée : aucun e-mail ;
- offre transmise au client sans décision, ou statut non renseigné : e-mail à l'agent seul ;
- un dossier déjà relancé par l'ancien rappel 21 jours n'est pas relancé une seconde fois ;
- pas d'envoi rétroactif groupé : la première exécution enregistre sa date de mise
  en service (``crm_settings`` id ``offres_relance_14j``, ou variable
  ``OFFRES_RELANCE_14J_DEPUIS`` au format AAAA-MM-JJ). Un dossier dont l'échéance
  J+14 tombe avant cette date n'est jamais relancé.
Un simple changement d'avancement n'appelle pas ce module.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from demandes_offres_3p import (
    COLLECTION,
    history_entry,
    now_iso,
    pick_conseiller_email_from_demande,
)
from demandes_offres_pilotage import (
    COMMERCIAL_NON_SIGNEE,
    COMMERCIAL_SIGNEE,
    commercial_code,
    dans_pilotage,
    relance_depart_at,
)

RELANCE_DELAY_DAYS = 14
RELANCE_DELAY = timedelta(days=RELANCE_DELAY_DAYS)
CLAIM_TTL = timedelta(minutes=30)
SETTINGS_ID = "offres_relance_14j"
DECISIONS_FINALES = {COMMERCIAL_SIGNEE, COMMERCIAL_NON_SIGNEE}
_NOT_SENT = {
    "$or": [
        {"relance_agent_14j_sent_at": {"$exists": False}},
        {"relance_agent_14j_sent_at": None},
        {"relance_agent_14j_sent_at": ""},
    ]
}
_NOT_SENT_21J = {
    "$or": [
        {"relance_agent_21j_sent_at": {"$exists": False}},
        {"relance_agent_21j_sent_at": None},
        {"relance_agent_21j_sent_at": ""},
    ]
}
_HAS_START = {
    "$or": [
        {"docs_mis_a_disposition_at": {"$exists": True, "$nin": [None, ""]}},
        {"offre_transmise_agent_at": {"$exists": True, "$nin": [None, ""]}},
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


def _zurich_date(moment: datetime) -> date:
    from zoneinfo import ZoneInfo

    return moment.astimezone(ZoneInfo("Europe/Zurich")).date()


def _zurich_label(moment: datetime) -> str:
    from zoneinfo import ZoneInfo

    local = moment.astimezone(ZoneInfo("Europe/Zurich"))
    return local.strftime("%d.%m.%Y %H:%M")


def echeance_relance(doc: dict) -> Optional[date]:
    """Jour (Europe/Zurich) où le rappel devient dû : départ + 14 jours calendaires."""
    start = _parse_iso(relance_depart_at(doc))
    if start is None:
        return None
    return _zurich_date(start) + RELANCE_DELAY


def relance_agent_decision(doc: dict, now: datetime, *, mise_en_service: Optional[date] = None) -> str:
    """send, wait, skip ou retry.

    skip : décision déjà connue, rappel déjà envoyé (14 ou 21 jours), aucun départ daté,
           brouillon/annulée, ou échéance antérieure à la mise en service.
    wait : moins de 14 jours calendaires depuis la mise à disposition.
    send : premier rappel dû.
    retry : un envoi précédent a échoué.
    """
    if doc.get("relance_agent_14j_sent_at") or doc.get("relance_agent_21j_sent_at"):
        return "skip"
    if not dans_pilotage(doc):
        return "skip"
    if commercial_code(doc) in DECISIONS_FINALES:
        return "skip"
    due = echeance_relance(doc)
    if due is None:
        return "skip"
    moment = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if _zurich_date(moment) < due:
        return "wait"
    if mise_en_service is not None and due < mise_en_service:
        return "skip"
    claim = _parse_iso(doc.get("relance_agent_14j_claim_at"))
    if doc.get("relance_agent_14j_claim") and claim and moment.astimezone(timezone.utc) - claim < CLAIM_TTL:
        return "skip"
    if doc.get("relance_agent_14j_last_error"):
        return "retry"
    return "send"


def _date_from_setting(value: Any) -> Optional[date]:
    raw = str(value or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


async def mise_en_service_relance(db, moment: datetime) -> date:
    """Date de mise en service du rappel 14 jours, posée une seule fois."""
    forced = _date_from_setting(os.environ.get("OFFRES_RELANCE_14J_DEPUIS"))
    if forced:
        return forced
    settings = db["crm_settings"]
    stored = await settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    found = _date_from_setting((stored or {}).get("active_depuis"))
    if found:
        return found
    today = _zurich_date(moment).isoformat()
    await settings.update_one(
        {"id": SETTINGS_ID},
        {"$setOnInsert": {"id": SETTINGS_ID, "active_depuis": today, "created_at": now_iso()}},
        upsert=True,
    )
    stored = await settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    return _date_from_setting((stored or {}).get("active_depuis")) or date.fromisoformat(today)


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


async def process_relances_agent_14j(db, *, now: Optional[datetime] = None, limit: int = 200) -> dict:
    from email_service import (
        MAIL_TYPE_RELANCE_AGENT_14J,
        format_relance_agent_14j_email,
        offres_email_enabled,
        send_email_async,
    )

    moment = now or datetime.now(timezone.utc)
    stats = {"scanned": 0, "sent": 0, "skipped": 0, "waiting": 0, "failed": 0, "no_recipient": 0}
    if not offres_email_enabled():
        return {**stats, "disabled": True}
    depuis = await mise_en_service_relance(db, moment)
    stats["active_depuis"] = depuis.isoformat()
    cursor = db[COLLECTION].find(
        {
            "is_deleted": {"$ne": True},
            "$and": [_HAS_START, _NOT_SENT, _NOT_SENT_21J],
        },
        {"_id": 0},
    )
    rows = await cursor.to_list(limit)
    for doc in rows:
        stats["scanned"] += 1
        decision = relance_agent_decision(doc, moment, mise_en_service=depuis)
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
                    "relance_agent_14j_last_error": "Destinataire introuvable",
                    "relance_agent_14j_claim": False,
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
                    _NOT_SENT_21J,
                    {"$or": [
                        {"relance_agent_14j_claim": {"$in": [None, False, ""]}},
                        {"relance_agent_14j_claim_at": {"$lt": expiry}},
                        {"relance_agent_14j_claim_at": {"$exists": False}},
                    ]},
                ],
            },
            {"$set": {
                "relance_agent_14j_claim": token,
                "relance_agent_14j_claim_at": now_iso(),
            }},
        )
        if getattr(claimed, "modified_count", 0) != 1:
            stats["skipped"] += 1
            continue
        depart = relance_depart_at(doc)
        subject, body_text, body_html = format_relance_agent_14j_email(doc, depart)
        ok, err = await send_email_async(
            email,
            subject,
            body_text,
            body_html=body_html,
            mail_type=MAIL_TYPE_RELANCE_AGENT_14J,
            log_meta={"demande_id": doc.get("id"), "numero": doc.get("numero")},
        )
        if not ok:
            stats["failed"] += 1
            await db[COLLECTION].update_one(
                {"id": doc.get("id"), "relance_agent_14j_claim": token},
                {"$set": {
                    "relance_agent_14j_claim": False,
                    "relance_agent_14j_last_error": (err or "Envoi impossible")[:300],
                    "updated_at": now_iso(),
                }},
            )
            continue
        stamp = now_iso()
        label = _zurich_label(_parse_iso(stamp) or moment)
        await db[COLLECTION].update_one(
            {"id": doc.get("id"), "relance_agent_14j_claim": token},
            {
                "$set": {
                    "relance_agent_14j_sent_at": stamp,
                    "relance_agent_14j_to": email,
                    "relance_agent_14j_claim": False,
                    "relance_agent_14j_last_error": "",
                    "updated_at": stamp,
                },
                "$push": {
                    "historique": history_entry(
                        f"Rappel automatique 14 jours envoyé à l'agent — {label}",
                        by_name="Le service des Offres",
                        detail=f"E-mail envoyé à {email} : décision client à renseigner",
                        statut=doc.get("statut"),
                        meta={"relance_agent_14j": True, "to": email, "depart": depart},
                    ),
                },
            },
        )
        stats["sent"] += 1
    return stats
