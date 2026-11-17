"""
Messagerie admin (Phase 1) — lecture du journal outbound `email_logs`.

Hooks futurs : `folder=inbox` (IMAP) est reconnu mais désactivé / vide.
Aucun envoi SMTP ici — lecture seule.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from email_service import (
    BODY_HTML_MAX,
    BODY_TEXT_MAX,
    MAIL_TYPE_COMPLEMENT_DEMANDE,
    MAIL_TYPE_COMPLEMENT_REPONSE,
    MAIL_TYPE_DEMANDE_OFFRE,
    MAIL_TYPE_DEMANDE_OFFRE_RECAP,
    MAIL_TYPE_DOSSIER_PRESENTE,
    MAIL_TYPE_FIL_DISCUSSION,
    MAIL_TYPE_NOTE_EXTERNE,
    MAIL_TYPE_NOTIFICATION,
    MAIL_TYPE_OFFRE_INCOMPLETE,
    MAIL_TYPE_OFFRE_MODIFIEE,
    MAIL_TYPE_OFFRE_RECUE,
    MAIL_TYPE_OFFRE_SIGNEE,
    MAIL_TYPE_OFFRES_COMPLETES,
    MAIL_TYPE_RAPPEL,
    MAIL_TYPE_RDV_SUIVI_RELANCE,
    MAIL_TYPE_RELANCE_AGENT_14J,
    MAIL_TYPE_RELANCE_AGENT_21J,
    MAIL_TYPE_TEST,
    normalize_email_status,
)

# Aligné sur user_activation.send_activation_email (mail_type literal).
MAIL_TYPE_USER_ACTIVATION = "user_activation"

LEGACY_ERROR_CUTOFF = "2026-09-10T00:00:00"

# Catégorie UI « E-mails automatiques » (+ rappels J+14 / J+21).
AUTOMATIC_MAIL_TYPES = frozenset(
    {
        MAIL_TYPE_DEMANDE_OFFRE,
        MAIL_TYPE_DEMANDE_OFFRE_RECAP,
        MAIL_TYPE_OFFRE_RECUE,
        MAIL_TYPE_OFFRES_COMPLETES,
        MAIL_TYPE_OFFRE_INCOMPLETE,
        MAIL_TYPE_OFFRE_SIGNEE,
        MAIL_TYPE_OFFRE_MODIFIEE,
        MAIL_TYPE_NOTE_EXTERNE,
        MAIL_TYPE_COMPLEMENT_DEMANDE,
        MAIL_TYPE_COMPLEMENT_REPONSE,
        MAIL_TYPE_FIL_DISCUSSION,
        MAIL_TYPE_RAPPEL,
        MAIL_TYPE_RELANCE_AGENT_14J,
        MAIL_TYPE_RELANCE_AGENT_21J,
        MAIL_TYPE_RDV_SUIVI_RELANCE,
        MAIL_TYPE_DOSSIER_PRESENTE,
        MAIL_TYPE_NOTIFICATION,
        MAIL_TYPE_USER_ACTIVATION,
        MAIL_TYPE_TEST,
    }
)

EMAIL_TYPE_LABELS = {
    MAIL_TYPE_DEMANDE_OFFRE: "Demande d'offre",
    MAIL_TYPE_DEMANDE_OFFRE_RECAP: "Récap demande d'offre",
    MAIL_TYPE_OFFRE_RECUE: "Offre reçue",
    MAIL_TYPE_OFFRES_COMPLETES: "Offres complètes",
    MAIL_TYPE_OFFRE_INCOMPLETE: "Offre incomplète",
    MAIL_TYPE_OFFRE_SIGNEE: "Offre signée",
    MAIL_TYPE_OFFRE_MODIFIEE: "Modification",
    MAIL_TYPE_NOTE_EXTERNE: "Note externe",
    MAIL_TYPE_COMPLEMENT_DEMANDE: "Complément demandé",
    MAIL_TYPE_COMPLEMENT_REPONSE: "Réponse complément",
    MAIL_TYPE_FIL_DISCUSSION: "Fil de discussion",
    MAIL_TYPE_RAPPEL: "Rappel",
    MAIL_TYPE_RELANCE_AGENT_14J: "Relance agent J+14",
    MAIL_TYPE_RELANCE_AGENT_21J: "Relance agent J+21",
    MAIL_TYPE_RDV_SUIVI_RELANCE: "Relance RDV suivi",
    MAIL_TYPE_DOSSIER_PRESENTE: "Dossier présenté",
    MAIL_TYPE_NOTIFICATION: "Notification",
    MAIL_TYPE_USER_ACTIVATION: "Activation compte",
    MAIL_TYPE_TEST: "Test SMTP",
}

# Dossiers Messagerie : outbox = journal d'envoi ; inbox réservé IMAP (Phase 2+).
FOLDER_OUTBOX = "outbox"
FOLDER_INBOX = "inbox"
SUPPORTED_FOLDERS = frozenset({FOLDER_OUTBOX, FOLDER_INBOX})

CATEGORY_ALL = "all"
CATEGORY_SENT = "sent"
CATEGORY_AUTOMATIC = "automatic"
CATEGORY_ERROR = "error"
SUPPORTED_CATEGORIES = frozenset(
    {CATEGORY_ALL, CATEGORY_SENT, CATEGORY_AUTOMATIC, CATEGORY_ERROR}
)

LIST_PROJECTION = {
    "_id": 0,
    "body_html": 0,
    "body_text": 0,
}


def email_type_label(mail_type: Optional[str]) -> str:
    key = str(mail_type or "").strip().lower()
    return EMAIL_TYPE_LABELS.get(key) or (mail_type or "E-mail")


def is_automatic_mail_type(mail_type: Optional[str]) -> bool:
    key = str(mail_type or "").strip().lower()
    if key in AUTOMATIC_MAIL_TYPES:
        return True
    # Préfixes tolérants (demande_offre*, offre_*, complement_*)
    if key.startswith("demande_offre"):
        return True
    if key.startswith("offre_"):
        return True
    if key.startswith("complement_"):
        return True
    if key.startswith("relance_"):
        return True
    return False


def detect_body_truncated(row: Optional[dict]) -> bool:
    """True si le corps stocké a été tronqué à la persistance (ou flag explicite)."""
    if not row:
        return False
    if row.get("body_truncated") is True:
        return True
    bt = str(row.get("body_text") or "")
    bh = str(row.get("body_html") or "")
    if bt.endswith("…") and len(bt) >= max(1, BODY_TEXT_MAX - 1):
        return True
    if bh.endswith("…") and len(bh) >= max(1, BODY_HTML_MAX - 1):
        return True
    return False


def _status_mongo_values(want: str) -> List[str]:
    if want == "error":
        return ["error", "failed", "fail"]
    if want == "pending":
        return ["pending", "en_cours", "in_progress", "processing"]
    if want == "sent":
        return ["sent", "ok", "success"]
    if want == "skipped":
        return ["skipped", "skip"]
    return [want]


def _escape_regex(value: str) -> str:
    return re.escape(value)


def build_email_logs_query(
    *,
    category: Optional[str] = None,
    mail_type: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    agent: Optional[str] = None,
    include_old_errors: bool = False,
) -> dict:
    """Construit un filtre Mongo pour email_logs (pagination serveur)."""
    and_parts: List[dict] = []

    cat = (category or CATEGORY_ALL).strip().lower() or CATEGORY_ALL
    if cat not in SUPPORTED_CATEGORIES:
        cat = CATEGORY_ALL

    type_filter = (mail_type or "").strip()
    if type_filter and type_filter.lower() not in {"all", "*"}:
        and_parts.append({"type": type_filter})
    elif cat == CATEGORY_AUTOMATIC:
        and_parts.append({"type": {"$in": sorted(AUTOMATIC_MAIL_TYPES)}})

    status_filter = (status or "").strip().lower()
    if cat == CATEGORY_SENT:
        status_filter = "sent"
    elif cat == CATEGORY_ERROR:
        status_filter = "error"

    if status_filter and status_filter not in {"all", "*"}:
        if status_filter in {"error", "failed", "echec", "échec"}:
            want = "error"
        elif status_filter in {"pending", "en_cours", "encours", "in_progress"}:
            want = "pending"
        elif status_filter in {"sent", "envoye", "envoyé", "ok"}:
            want = "sent"
        else:
            want = normalize_email_status(status_filter) or status_filter
        and_parts.append({"status": {"$in": _status_mongo_values(want)}})

    df = (date_from or "").strip()[:10]
    dt = (date_to or "").strip()[:10]
    if df or dt:
        # sent_at ISO ; repli created_at via $ifNull côté app — filtre large sur les deux.
        date_or = []
        for field in ("sent_at", "created_at"):
            rng: dict = {}
            if df:
                rng["$gte"] = df
            if dt:
                # Comparaison lexicographique ISO (date seule + suffixe haut)
                rng["$lte"] = dt + "\uffff"
            date_or.append({field: rng})
        and_parts.append({"$or": date_or})

    agent_needle = (agent or "").strip()
    if agent_needle:
        rx = {"$regex": _escape_regex(agent_needle), "$options": "i"}
        and_parts.append(
            {
                "$or": [
                    {"agent_label": rx},
                    {"created_by": rx},
                    {"extra.agent_label": rx},
                ]
            }
        )

    needle = (q or "").strip()
    if needle:
        rx = {"$regex": _escape_regex(needle), "$options": "i"}
        and_parts.append(
            {
                "$or": [
                    {"to": rx},
                    {"to_email": rx},
                    {"from": rx},
                    {"subject": rx},
                    {"client_label": rx},
                    {"numero": rx},
                    {"numero_dossier": rx},
                    {"agent_label": rx},
                    {"created_by": rx},
                    {"module": rx},
                    {"type": rx},
                    {"ref_id": rx},
                    {"dossier_id": rx},
                    {"client_id": rx},
                ]
            }
        )

    if not include_old_errors:
        # Exclure anciens échecs Resend (avant cutoff) sans charger toute la collection.
        and_parts.append(
            {
                "$nor": [
                    {
                        "status": {"$in": ["error", "failed", "fail"]},
                        "$or": [
                            {"sent_at": {"$lt": LEGACY_ERROR_CUTOFF}},
                            {
                                "sent_at": {"$in": [None, ""]},
                                "created_at": {"$lt": LEGACY_ERROR_CUTOFF},
                            },
                        ],
                    }
                ]
            }
        )

    if not and_parts:
        return {}
    if len(and_parts) == 1:
        return and_parts[0]
    return {"$and": and_parts}


def sort_key_sent_at(row: dict) -> str:
    return str(row.get("sent_at") or row.get("created_at") or "")


def normalize_legacy_rappel_row(row: dict) -> dict:
    out = dict(row)
    out.setdefault("type", MAIL_TYPE_RAPPEL)
    if (out.get("status") or "").strip().lower() == "failed":
        out["status"] = "error"
    out.setdefault("to", out.get("to_email"))
    out.setdefault("subject", out.get("subject") or "")
    return out


def dedupe_email_rows(rows: Sequence[dict]) -> List[dict]:
    """Déduplique id puis (to|subject|minute), en préférant sent / smtp_infomaniak / corps."""

    def _rank(r: dict) -> tuple:
        st = (r.get("status") or "").strip().lower()
        sent_rank = 0 if st in {"sent", "ok", "success"} else 1
        provider = 0 if (r.get("provider") or "") == "smtp_infomaniak" else 1
        has_body = 0 if (r.get("body_text") or r.get("body_html") or r.get("body_preview")) else 1
        return (sent_rank, provider, has_body)

    by_id: Dict[str, dict] = {}
    for r in rows:
        rid = r.get("id")
        if rid:
            prev = by_id.get(rid)
            if prev is None or _rank(r) < _rank(prev):
                by_id[rid] = r
        else:
            by_id[f"_noid_{len(by_id)}"] = r

    def _soft_key(r: dict) -> str:
        to_v = (r.get("to") or r.get("to_email") or "").strip().lower()
        subj = (r.get("subject") or "").strip().casefold()
        when = str(r.get("sent_at") or r.get("created_at") or "")[:16]
        return f"{to_v}|{subj}|{when}"

    soft: Dict[str, dict] = {}
    for r in by_id.values():
        key = _soft_key(r)
        prev = soft.get(key)
        if prev is None or _rank(r) < _rank(prev):
            soft[key] = r
    return list(soft.values())


def leosoft_link_for_email(row: dict) -> Optional[dict]:
    """Lien applicatif vers dossier / demande / client si identifiable."""
    client_id = (row.get("client_id") or "").strip() or None
    dossier_id = (row.get("dossier_id") or "").strip() or None
    ref_id = (row.get("ref_id") or "").strip() or None
    numero = (row.get("numero") or "").strip() or None
    numero_dossier = (row.get("numero_dossier") or "").strip() or None
    mail_type = str(row.get("type") or "").strip().lower()

    if ref_id and (
        mail_type.startswith("demande_offre")
        or mail_type.startswith("offre_")
        or mail_type.startswith("complement_")
        or mail_type
        in {
            MAIL_TYPE_NOTE_EXTERNE,
            MAIL_TYPE_FIL_DISCUSSION,
            MAIL_TYPE_RELANCE_AGENT_14J,
            MAIL_TYPE_RELANCE_AGENT_21J,
            MAIL_TYPE_OFFRES_COMPLETES,
        }
    ):
        return {
            "kind": "demande_offre",
            "href": f"/demandes-offres/{ref_id}",
            "label": numero or "Demande d'offre",
        }
    if dossier_id:
        return {
            "kind": "dossier",
            "href": f"/dossiers/{dossier_id}",
            "label": numero_dossier or "Dossier",
        }
    if client_id:
        return {
            "kind": "client",
            "href": f"/clients/{client_id}",
            "label": row.get("client_label") or numero_dossier or "Client",
        }
    return None


def public_email_row(row: dict, *, detail: bool = False) -> dict:
    """Projection list/détail Messagerie — statuts honnêtes (jamais « delivered »)."""
    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    status_raw = (row.get("status") or "").strip().lower()
    if status_raw in {
        "sent",
        "ok",
        "success",
        "pending",
        "en_cours",
        "in_progress",
        "processing",
        "skipped",
        "skip",
        "error",
        "failed",
        "fail",
    }:
        status = normalize_email_status(status_raw)
    else:
        status = status_raw or ""

    client_label = row.get("client_label") or extra.get("client_label") or ""
    if not client_label and row.get("rappel_count") and int(row.get("rappel_count") or 0) > 1:
        client_label = f"{row.get('rappel_count')} clients"

    out = {
        "id": row.get("id"),
        "type": row.get("type") or row.get("mail_type") or "",
        "type_label": email_type_label(row.get("type") or row.get("mail_type")),
        "to": row.get("to") or row.get("to_email") or "",
        "from": row.get("from") or row.get("from_email") or "",
        "cc": list(row.get("cc") or []),
        "bcc": list(row.get("bcc") or []),
        "subject": row.get("subject") or row.get("email_subject") or "",
        "status": status,
        "error": row.get("error"),
        "client_id": row.get("client_id"),
        "client_label": client_label,
        "numero": row.get("numero") or "",
        "numero_dossier": row.get("numero_dossier") or "",
        "ref_id": row.get("ref_id"),
        "dossier_id": row.get("dossier_id"),
        "agent_label": row.get("agent_label") or "",
        "module": row.get("module") or extra.get("module") or "",
        "sent_at": row.get("sent_at") or row.get("created_at"),
        "created_at": row.get("created_at"),
        "attachments": list(row.get("attachments") or []),
        "kind": row.get("kind") or extra.get("kind") or "",
        "rappel_count": row.get("rappel_count") or extra.get("rappel_count"),
        "message_id": row.get("message_id") or "",
        "created_by": row.get("created_by") or "",
        "automatic": is_automatic_mail_type(row.get("type") or row.get("mail_type")),
        "leosoft_link": leosoft_link_for_email(row),
    }
    if detail:
        out["body_preview"] = row.get("body_preview") or ""
        out["body_text"] = row.get("body_text") or row.get("body_preview") or ""
        out["body_html"] = row.get("body_html") or None
        out["body_truncated"] = detect_body_truncated(row)
        out["form_type_label"] = row.get("form_type_label") or ""
        out["event"] = row.get("event") or ""
    return out


def empty_inbox_response(*, limit: int, skip: int, category: str) -> dict:
    return {
        "items": [],
        "total": 0,
        "limit": limit,
        "skip": skip,
        "has_more": False,
        "folder": FOLDER_INBOX,
        "folder_enabled": False,
        "folder_message": "Boîte de réception IMAP non activée (Phase 2).",
        "category": category,
    }


def build_list_response(
    *,
    items: List[dict],
    total: int,
    limit: int,
    skip: int,
    folder: str,
    category: str,
) -> dict:
    return {
        "items": items,
        "total": int(total),
        "limit": int(limit),
        "skip": int(skip),
        "has_more": int(skip) + len(items) < int(total),
        "folder": folder,
        "folder_enabled": folder != FOLDER_INBOX,
        "category": category,
        "type_labels": dict(EMAIL_TYPE_LABELS),
    }


async def fetch_email_page(
    db: Any,
    *,
    limit: int = 50,
    skip: int = 0,
    category: Optional[str] = None,
    mail_type: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    agent: Optional[str] = None,
    include_old_errors: bool = False,
    folder: str = FOLDER_OUTBOX,
) -> dict:
    """
    Page Messagerie outbound depuis email_logs (+ fusion légère rappel_email_logs).

    Ne charge pas toute la collection en RAM : find + skip/limit + count_documents.
    """
    from email_service import EMAIL_LOGS_COLLECTION

    cat = (category or CATEGORY_ALL).strip().lower() or CATEGORY_ALL
    if cat not in SUPPORTED_CATEGORIES:
        cat = CATEGORY_ALL
    fold = (folder or FOLDER_OUTBOX).strip().lower() or FOLDER_OUTBOX
    if fold not in SUPPORTED_FOLDERS:
        fold = FOLDER_OUTBOX

    limit = max(1, min(int(limit or 50), 200))
    skip = max(0, int(skip or 0))

    if fold == FOLDER_INBOX:
        return empty_inbox_response(limit=limit, skip=skip, category=cat)

    query = build_email_logs_query(
        category=cat,
        mail_type=mail_type,
        status=status,
        q=q,
        date_from=date_from,
        date_to=date_to,
        agent=agent,
        include_old_errors=include_old_errors,
    )

    coll = db[EMAIL_LOGS_COLLECTION]
    try:
        total_main = await coll.count_documents(query)
    except Exception:
        total_main = 0

    rows: List[dict] = []
    try:
        cursor = (
            coll.find(query, LIST_PROJECTION)
            .sort([("sent_at", -1), ("created_at", -1)])
            .skip(skip)
            .limit(limit)
        )
        rows = await cursor.to_list(limit)
    except Exception:
        rows = []

    # Fusion legacy rappels : fenêtre plafonnée (pas de to_list massif).
    type_key = (mail_type or "").strip().lower()
    include_legacy = type_key in {"", "all", "rappel"} and cat in {
        CATEGORY_ALL,
        CATEGORY_AUTOMATIC,
        CATEGORY_SENT,
        CATEGORY_ERROR,
    }
    legacy_extra_total = 0
    if include_legacy:
        legacy_status = status
        if cat == CATEGORY_SENT:
            legacy_status = "sent"
        elif cat == CATEGORY_ERROR:
            legacy_status = "error"
        legacy_query = build_email_logs_query(
            category=CATEGORY_ALL,
            mail_type=None,
            status=legacy_status,
            q=q,
            date_from=date_from,
            date_to=date_to,
            agent=agent,
            include_old_errors=include_old_errors,
        )
        try:
            legacy_count_raw = await db.rappel_email_logs.count_documents(legacy_query)
        except Exception:
            legacy_count_raw = 0
        legacy_window = min(100, max(limit, skip + limit))
        try:
            legacy_rows = await (
                db.rappel_email_logs.find(legacy_query, LIST_PROJECTION)
                .sort([("sent_at", -1), ("created_at", -1)])
                .limit(legacy_window)
                .to_list(legacy_window)
            )
        except Exception:
            legacy_rows = []
        legacy_norm = [normalize_legacy_rappel_row(r) for r in legacy_rows]
        legacy_ids = [r.get("id") for r in legacy_norm if r.get("id")]
        existing_ids: set = set()
        if legacy_ids:
            try:
                found = await coll.find(
                    {"id": {"$in": legacy_ids}},
                    {"_id": 0, "id": 1},
                ).to_list(len(legacy_ids))
                existing_ids = {r.get("id") for r in found if r.get("id")}
            except Exception:
                existing_ids = set()
        legacy_only = [r for r in legacy_norm if r.get("id") not in existing_ids]
        # Approximation : ids déjà unifiés dans la fenêtre retirés du compte legacy.
        legacy_extra_total = max(0, int(legacy_count_raw) - len(existing_ids))
        if skip == 0 and legacy_only:
            merged = dedupe_email_rows(list(rows) + legacy_only)
            merged.sort(key=sort_key_sent_at, reverse=True)
            rows = merged[:limit]

    total = int(total_main) + (int(legacy_extra_total) if skip == 0 else 0)
    if skip > 0:
        total = int(total_main)

    items = [public_email_row(r) for r in rows]
    return build_list_response(
        items=items,
        total=total,
        limit=limit,
        skip=skip,
        folder=fold,
        category=cat,
    )
