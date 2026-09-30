"""Rappels auto : checklist Envoyé→Reçu après 1,5 mois ; LPP vérif. à +1 mois."""
from __future__ import annotations

import calendar
import logging
import uuid
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

FOLLOWUP_DAYS = 45  # 1 mois et demi (checklist / documents)
LPP_VERIFY_MONTHS = 1  # rappel LPP à J+1 mois calendaire
RAPPEL_TYPE = "demande_envoi_relance"
RAPPEL_TYPE_LPP_VERIFY = "lpp_caisse_verify"
SOURCE_CHECKLIST = "checklist"
SOURCE_LPP = "lpp_caisse"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    text = text[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def add_calendar_months(d: date, months: int = 1) -> date:
    """Ajoute N mois calendaires en conservant le jour (ex. 17/09 → 17/10)."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def due_date_from_sent(sent_at: Any) -> Optional[date]:
    d = _parse_date(sent_at)
    if not d:
        return None
    return d + timedelta(days=FOLLOWUP_DAYS)


def due_date_lpp_verify(sent_at: Any) -> Optional[date]:
    d = _parse_date(sent_at)
    if not d:
        return None
    return add_calendar_months(d, LPP_VERIFY_MONTHS)


def is_followup_due(sent_at: Any, *, today: Optional[date] = None) -> bool:
    due = due_date_from_sent(sent_at)
    if not due:
        return False
    ref = today or datetime.now(timezone.utc).date()
    return ref >= due


def source_key_checklist(client_id: str, document_name: str) -> str:
    return f"{client_id}|{SOURCE_CHECKLIST}|{str(document_name or '').strip()}"


def source_key_lpp(client_id: str, tracking_id: str, person: str = "") -> str:
    """Identifiant unique : client + caisse (tracking) + personne + type."""
    person_part = str(person or "").strip() or "_"
    return f"{client_id}|{SOURCE_LPP}|{str(tracking_id or '').strip()}|{person_part}|verify"


def enrich_checklist_entry(prev: Optional[dict], new: Optional[dict], *, now_iso: Optional[str] = None) -> dict:
    """Fusionne un item checklist en gérant sent/received indépendamment + dates."""
    now = now_iso or _now_iso()
    prev = prev if isinstance(prev, dict) else {}
    new = new if isinstance(new, dict) else {}

    sent = bool(new.get("sent"))
    received = bool(new.get("received"))
    sent_at = prev.get("sent_at") or new.get("sent_at")
    received_at = prev.get("received_at") or new.get("received_at")
    if "effectue" in new:
        effectue = bool(new.get("effectue"))
    else:
        effectue = bool(prev.get("effectue"))

    was_sent = bool(prev.get("sent"))
    was_received = bool(prev.get("received"))

    if sent and not was_sent:
        sent_at = now
    if not sent:
        sent_at = None
    if received and not was_received:
        received_at = now
        if not sent:
            sent = True
            sent_at = sent_at or now
    if not received:
        received_at = None

    out = {
        "sent": sent,
        "received": received,
        "sent_at": sent_at,
        "received_at": received_at,
        "effectue": effectue,
    }
    for k, v in new.items():
        if k not in out:
            out[k] = v
    return out


def enrich_checklist_map(previous: Optional[dict], incoming: Optional[dict]) -> dict:
    prev = previous if isinstance(previous, dict) else {}
    inc = incoming if isinstance(incoming, dict) else {}
    now = _now_iso()
    keys = set(prev.keys()) | set(inc.keys())
    result = {}
    for name in keys:
        result[name] = enrich_checklist_entry(prev.get(name), inc.get(name), now_iso=now)
    return result


def enrich_lpp_tracking_list(previous: Optional[List[dict]], incoming: List[dict]) -> List[dict]:
    prev_list = [e for e in (previous or []) if isinstance(e, dict)]
    by_id = {str(e.get("id") or ""): e for e in prev_list if e.get("id")}
    by_person_name = {
        f"{str(e.get('person') or '').strip().casefold()}|{str(e.get('name') or '').strip().casefold()}": e
        for e in prev_list
        if e.get("name")
    }
    by_name = {
        str(e.get("name") or "").strip().casefold(): e
        for e in prev_list
        if e.get("name")
    }
    now = _now_iso()
    out = []
    for entry in incoming or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        eid = str(entry.get("id") or "")
        person = str(entry.get("person") or "").strip()
        pname_key = f"{person.casefold()}|{str(entry.get('name') or '').strip().casefold()}"
        prior = (
            by_id.get(eid)
            or by_person_name.get(pname_key)
            or (by_name.get(str(entry.get("name") or "").strip().casefold()) if not person else None)
            or {}
        )
        if not person:
            person = str(prior.get("person") or "").strip()
        sent = bool(entry.get("sent"))
        received = bool(entry.get("received"))
        sent_at = prior.get("sent_at") or entry.get("sent_at")
        received_at = prior.get("received_at") or entry.get("received_at")
        was_sent = bool(prior.get("sent"))
        was_received = bool(prior.get("received"))
        if sent and not was_sent:
            sent_at = now
        if not sent:
            sent_at = None
        if received and not was_received:
            received_at = now
            if not sent:
                sent = True
                sent_at = sent_at or now
        if not received:
            received_at = None
        out.append({
            **prior,
            **entry,
            "id": entry.get("id") or prior.get("id") or str(uuid.uuid4()),
            "name": entry.get("name"),
            "person": person or prior.get("person") or "",
            "address": entry.get("address") or prior.get("address") or "",
            "reference": entry.get("reference") or prior.get("reference") or "",
            "sent": sent,
            "received": received,
            "sent_at": sent_at,
            "received_at": received_at,
        })
    return out


def build_rappel_payload(
    *,
    user_id: str,
    client: dict,
    source_key: str,
    demande_label: str,
    caisse_label: Optional[str],
    sent_at: Any,
    dossier_id: Optional[str] = None,
) -> dict:
    due = due_date_from_sent(sent_at)
    due_s = due.isoformat() if due else datetime.now(timezone.utc).date().isoformat()
    sent_s = (_parse_date(sent_at) or datetime.now(timezone.utc).date()).isoformat()
    caisse = (caisse_label or demande_label or "—").strip()
    titre = f"Réponse toujours pas reçue — relancer ({caisse})"
    desc_lines = [
        f"Demande : {demande_label}",
        f"Caisse / organisme : {caisse}",
        f"Envoyé le : {sent_s}",
        f"Aucune réponse (« Reçu ») après {FOLLOWUP_DAYS} jours (1 mois et demi).",
        "Relancer la caisse / l'organisme.",
    ]
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "client_id": client.get("id"),
        "dossier_id": dossier_id or client.get("dossier_id") or client.get("id"),
        "titre": titre,
        "description": "\n".join(desc_lines),
        "date": due_s,
        "heure": "09:00",
        "priorite": "haute",
        "statut": "a_faire",
        "done": False,
        "author": "Système CRM",
        "created_by": "system",
        "send_email": False,
        "notify_crm": True,
        "notify_email": None,
        "email_sent": False,
        "email_notified_offsets": [],
        "email_notified_at": None,
        "conseiller": client.get("conseiller"),
        "created_at": _now_iso(),
        "done_at": None,
        "done_by": None,
        "done_by_name": None,
        "type": RAPPEL_TYPE,
        "source_type": RAPPEL_TYPE,
        "source_key": source_key,
        "source_demande": demande_label,
        "source_caisse": caisse,
        "source_sent_at": sent_at,
    }


def build_lpp_verify_rappel_payload(
    *,
    user_id: str,
    client: dict,
    source_key: str,
    caisse_label: str,
    person: str,
    sent_at: Any,
    dossier_id: Optional[str] = None,
) -> dict:
    due = due_date_lpp_verify(sent_at)
    due_s = due.isoformat() if due else datetime.now(timezone.utc).date().isoformat()
    caisse = (caisse_label or "—").strip()
    who = (person or "le client").strip() or "le client"
    titre = f"Vérifier si nous avons reçu le courrier LPP de {caisse} pour {who}."
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "client_id": client.get("id"),
        "dossier_id": dossier_id or client.get("dossier_id") or client.get("id"),
        "titre": titre,
        "description": titre,
        "date": due_s,
        "heure": "09:00",
        "priorite": "normale",
        "statut": "a_faire",
        "done": False,
        "author": "Système CRM",
        "created_by": "system",
        "send_email": False,
        "notify_crm": True,
        "notify_email": None,
        "email_sent": False,
        "email_notified_offsets": [],
        "email_notified_at": None,
        "conseiller": client.get("conseiller"),
        "created_at": _now_iso(),
        "done_at": None,
        "done_by": None,
        "done_by_name": None,
        "type": RAPPEL_TYPE_LPP_VERIFY,
        "source_type": RAPPEL_TYPE_LPP_VERIFY,
        "source_key": source_key,
        "source_demande": "Demande LPP / décompte",
        "source_caisse": caisse,
        "source_person": who,
        "source_sent_at": sent_at,
    }


async def resolve_open_relance(db, *, user_id: str, source_key: str) -> int:
    """Marque comme terminés les rappels auto ouverts pour cette source."""
    now = _now_iso()
    res = await db.demandes.update_many(
        {
            "user_id": user_id,
            "source_key": source_key,
            "type": {"$in": [RAPPEL_TYPE, RAPPEL_TYPE_LPP_VERIFY]},
            "done": {"$ne": True},
        },
        {
            "$set": {
                "done": True,
                "statut": "termine",
                "done_at": now,
                "done_by": "system",
                "done_by_name": "Système CRM (Reçu coché)",
            }
        },
    )
    return int(getattr(res, "modified_count", 0) or 0)


async def ensure_relance_rappel(
    db,
    *,
    user_id: str,
    client: dict,
    source_key: str,
    demande_label: str,
    caisse_label: Optional[str],
    sent_at: Any,
    received: bool,
    dossier_id: Optional[str] = None,
) -> Optional[dict]:
    """Crée un rappel checklist si dû, ou résout s'il est reçu. Idempotent."""
    if received or not sent_at:
        await resolve_open_relance(db, user_id=user_id, source_key=source_key)
        return None
    if not is_followup_due(sent_at):
        return None

    existing = await db.demandes.find_one(
        {
            "user_id": user_id,
            "source_key": source_key,
            "type": RAPPEL_TYPE,
            "done": {"$ne": True},
        },
        {"_id": 0},
    )
    if existing:
        return existing

    doc = build_rappel_payload(
        user_id=user_id,
        client=client,
        source_key=source_key,
        demande_label=demande_label,
        caisse_label=caisse_label,
        sent_at=sent_at,
        dossier_id=dossier_id,
    )
    await db.demandes.insert_one(doc)
    doc.pop("_id", None)
    logger.info(
        "Rappel relance créé client=%s source=%s due=%s",
        client.get("id"),
        source_key,
        doc.get("date"),
    )
    return doc


async def ensure_lpp_verify_rappel(
    db,
    *,
    user_id: str,
    client: dict,
    source_key: str,
    caisse_label: str,
    person: str,
    sent_at: Any,
    received: bool,
    dossier_id: Optional[str] = None,
) -> Tuple[Optional[dict], bool]:
    """Crée immédiatement un rappel LPP à +1 mois. Retourne (doc, created)."""
    if received or not sent_at:
        await resolve_open_relance(db, user_id=user_id, source_key=source_key)
        return None, False

    existing = await db.demandes.find_one(
        {
            "user_id": user_id,
            "source_key": source_key,
            "type": {"$in": [RAPPEL_TYPE_LPP_VERIFY, RAPPEL_TYPE]},
            "done": {"$ne": True},
        },
        {"_id": 0},
    )
    if existing:
        return existing, False

    doc = build_lpp_verify_rappel_payload(
        user_id=user_id,
        client=client,
        source_key=source_key,
        caisse_label=caisse_label,
        person=person,
        sent_at=sent_at,
        dossier_id=dossier_id,
    )
    await db.demandes.insert_one(doc)
    doc.pop("_id", None)
    logger.info(
        "Rappel LPP +1 mois créé client=%s source=%s due=%s",
        client.get("id"),
        source_key,
        doc.get("date"),
    )
    return doc, True


async def sync_client_relances(db, *, user_id: str, client: dict, dossier_id: Optional[str] = None) -> dict:
    """Synchronise rappels checklist (45 j) + LPP (immédiat, date +1 mois)."""
    created = 0
    resolved = 0
    cid = client.get("id")
    if not cid:
        return {"created": 0, "resolved": 0}

    checklist = client.get("document_checklist") or {}
    if isinstance(checklist, dict):
        for name, entry in checklist.items():
            if not isinstance(entry, dict):
                continue
            sent_at = entry.get("sent_at") if (entry.get("sent") and entry.get("sent_at")) else None
            if entry.get("sent") and not entry.get("sent_at") and not entry.get("received"):
                continue
            sk = source_key_checklist(cid, name)
            received = bool(entry.get("received"))
            existing = await db.demandes.find_one(
                {
                    "user_id": user_id,
                    "source_key": sk,
                    "type": RAPPEL_TYPE,
                    "done": {"$ne": True},
                },
                {"_id": 0, "id": 1},
            )
            if received or not sent_at:
                resolved += await resolve_open_relance(db, user_id=user_id, source_key=sk)
                continue
            if not is_followup_due(sent_at) or existing:
                continue
            doc = await ensure_relance_rappel(
                db,
                user_id=user_id,
                client=client,
                source_key=sk,
                demande_label=str(name),
                caisse_label=str(name),
                sent_at=sent_at,
                received=False,
                dossier_id=dossier_id,
            )
            if doc:
                created += 1

    tracking = client.get("lpp_caisse_tracking") or []
    if isinstance(tracking, list):
        for entry in tracking:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            tid = entry.get("id") or str(entry.get("name"))
            person = str(entry.get("person") or "").strip()
            sk = source_key_lpp(cid, tid, person)
            legacy = f"{cid}|{SOURCE_LPP}|{tid}"
            sent_at = entry.get("sent_at") if (entry.get("sent") and entry.get("sent_at")) else None
            received = bool(entry.get("received"))
            if received or not sent_at:
                resolved += await resolve_open_relance(db, user_id=user_id, source_key=sk)
                if legacy != sk:
                    resolved += await resolve_open_relance(db, user_id=user_id, source_key=legacy)
                continue
            if entry.get("sent") and not entry.get("sent_at"):
                continue
            _doc, was_created = await ensure_lpp_verify_rappel(
                db,
                user_id=user_id,
                client=client,
                source_key=sk,
                caisse_label=str(entry.get("name")),
                person=person or "le client",
                sent_at=sent_at,
                received=False,
                dossier_id=dossier_id,
            )
            if was_created:
                created += 1

    return {"created": created, "resolved": resolved}


async def list_missing_sent_at(db, *, user_id: Optional[str] = None) -> dict:
    """Liste les Envoyé sans sent_at (non récupérables sans historique)."""
    query: dict = {}
    if user_id:
        query["user_id"] = user_id
    query["$or"] = [
        {"document_checklist": {"$exists": True}},
        {"lpp_caisse_tracking": {"$exists": True}},
    ]
    missing = []
    recoverable = []
    clients = await db.clients.find(
        query,
        {
            "_id": 0,
            "id": 1,
            "prenom": 1,
            "nom": 1,
            "numero_dossier": 1,
            "conseiller": 1,
            "document_checklist": 1,
            "lpp_caisse_tracking": 1,
        },
    ).to_list(20000)

    for c in clients:
        client_name = f"{c.get('prenom') or ''} {c.get('nom') or ''}".strip() or "—"
        dossier = c.get("numero_dossier") or "—"
        cl = c.get("document_checklist") or {}
        if isinstance(cl, dict):
            for label, e in cl.items():
                if not isinstance(e, dict):
                    continue
                if not e.get("sent") or e.get("received"):
                    continue
                row = {
                    "client_id": c.get("id"),
                    "client": client_name,
                    "numero_dossier": dossier,
                    "conseiller": c.get("conseiller") or "",
                    "source": "checklist",
                    "label": label,
                    "sent_at": e.get("sent_at"),
                }
                if e.get("sent_at"):
                    recoverable.append(row)
                else:
                    missing.append(row)
        for e in c.get("lpp_caisse_tracking") or []:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            if not e.get("sent") or e.get("received"):
                continue
            row = {
                "client_id": c.get("id"),
                "client": client_name,
                "numero_dossier": dossier,
                "conseiller": c.get("conseiller") or "",
                "source": "lpp_caisse",
                "label": e.get("name"),
                "sent_at": e.get("sent_at"),
            }
            if e.get("sent_at"):
                recoverable.append(row)
            else:
                missing.append(row)

    return {
        "history_available_for_checkbox": False,
        "history_note": (
            "Le CRM n'a jamais journalisé le moment où la case « Envoyé » était cochée "
            "(pas d'entrée dans actions / pas d'audit de document_checklist). "
            "Impossible de reconstituer une date exacte a posteriori. "
            "Aucun recours à created_at / updated_at du dossier."
        ),
        "with_sent_at": len(recoverable),
        "missing_sent_at": len(missing),
        "missing": missing,
        "with_date_sample": recoverable[:50],
    }


async def scan_all_clients_for_relances(db, *, user_id: Optional[str] = None) -> dict:
    """Parcourt les clients et crée/résout les rappels de relance."""
    query: dict = {}
    if user_id:
        query["user_id"] = user_id
    query["$or"] = [
        {"document_checklist": {"$exists": True}},
        {"lpp_caisse_tracking": {"$exists": True}},
    ]
    created = 0
    resolved = 0
    scanned = 0
    cursor = db.clients.find(query, {"_id": 0})
    clients = await cursor.to_list(20000)
    for client in clients:
        scanned += 1
        try:
            stats = await sync_client_relances(
                db,
                user_id=client.get("user_id"),
                client=client,
                dossier_id=client.get("dossier_id") or client.get("id"),
            )
            created += stats["created"]
            resolved += stats["resolved"]
        except Exception:
            logger.exception("Relance scan failed for client %s", client.get("id"))
    return {"scanned": scanned, "created": created, "resolved": resolved}
