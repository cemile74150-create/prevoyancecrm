"""Congés & absences : règles métier (sans solde, sans compteur annuel).

Les dates sont des dates civiles « AAAA-MM-JJ » stockées en texte : aucun fuseau horaire,
aucune conversion. La durée est indicative : jours ouvrés du lundi au vendredi,
sans jours fériés ni horaires individuels.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

LEAVES_COLLECTION = "leave_requests"
EVENTS_COLLECTION = "leave_request_events"
NOTIFICATIONS_COLLECTION = "leave_notifications"

LEAVE_TYPES = {
    "paid": "Congés payés",
    "unpaid": "Congé sans solde",
    "other": "Autre absence",
}

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"
STATUS_CANCELLATION_REQUESTED = "cancellation_requested"

STATUS_LABELS = {
    STATUS_PENDING: "En attente",
    STATUS_APPROVED: "Validée",
    STATUS_REJECTED: "Refusée",
    STATUS_CANCELLED: "Annulée",
    STATUS_CANCELLATION_REQUESTED: "Annulation demandée",
}

# Une demande dans ces statuts occupe ses dates (chevauchement interdit).
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_CANCELLATION_REQUESTED)
# L'absence reste effective tant que l'annulation n'est pas acceptée.
CALENDAR_APPROVED_STATUSES = (STATUS_APPROVED, STATUS_CANCELLATION_REQUESTED)

PART_FULL = "full"
PART_MORNING = "morning"
PART_AFTERNOON = "afternoon"
DAY_PARTS = {
    PART_FULL: "Journée entière",
    PART_MORNING: "Matin",
    PART_AFTERNOON: "Après-midi",
}

# Transitions autorisées : (statut de départ, action) -> statut d'arrivée.
TRANSITIONS = {
    (STATUS_PENDING, "approve"): STATUS_APPROVED,
    (STATUS_PENDING, "reject"): STATUS_REJECTED,
    (STATUS_PENDING, "cancel"): STATUS_CANCELLED,
    (STATUS_APPROVED, "request_cancellation"): STATUS_CANCELLATION_REQUESTED,
    (STATUS_CANCELLATION_REQUESTED, "accept_cancellation"): STATUS_CANCELLED,
    (STATUS_CANCELLATION_REQUESTED, "refuse_cancellation"): STATUS_APPROVED,
}

COMMENT_MAX = 1000
REASON_MAX = 1000
MAX_SPAN_DAYS = 366

CALCULATION_NOTE = (
    "Durée indicative : jours ouvrés du lundi au vendredi, samedis et dimanches exclus. "
    "Les jours fériés et les horaires individuels ne sont pas pris en compte."
)


class LeaveValidationError(ValueError):
    """Saisie refusée : message prêt à afficher."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def parse_civil_date(raw: Any, label: str = "La date") -> date:
    text = str(raw or "").strip()[:10]
    if len(text) != 10:
        raise LeaveValidationError(f"{label} est obligatoire (format AAAA-MM-JJ).")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise LeaveValidationError(f"{label} n'est pas une date valide.") from exc


def next_transition(status: str, action: str) -> Optional[str]:
    return TRANSITIONS.get((status, action))


def normalize_parts(start: date, end: date, start_part: Any, end_part: Any) -> tuple[str, str]:
    """Une journée : full / morning / afternoon (même valeur aux deux bouts).
    Plusieurs jours : début full / afternoon, fin full / morning."""
    sp = str(start_part or PART_FULL).strip()
    ep = str(end_part or "").strip() or None
    if sp not in DAY_PARTS:
        raise LeaveValidationError("Demi-journée de début invalide.")
    if start == end:
        if ep is not None and ep != sp:
            raise LeaveValidationError("Pour une seule journée, choisissez journée entière, matin ou après-midi.")
        return sp, sp
    ep = ep or PART_FULL
    if ep not in DAY_PARTS:
        raise LeaveValidationError("Demi-journée de fin invalide.")
    if sp == PART_MORNING:
        raise LeaveValidationError("Le premier jour ne peut commencer que le matin (journée entière) ou l'après-midi.")
    if ep == PART_AFTERNOON:
        raise LeaveValidationError("Le dernier jour ne peut se terminer que le soir (journée entière) ou à midi.")
    return sp, ep


def is_working_day(d: date) -> bool:
    return d.weekday() < 5


def compute_working_days(start: date, end: date, start_part: str = PART_FULL, end_part: str = PART_FULL) -> float:
    """Jours ouvrés lun–ven inclus, demi-journées à 0,5. Week-end compté 0."""
    if end < start:
        return 0.0
    if start == end:
        if not is_working_day(start):
            return 0.0
        return 1.0 if start_part == PART_FULL else 0.5
    total = 0.0
    d = start
    while d <= end:
        if is_working_day(d):
            total += 1.0
        d += timedelta(days=1)
    if start_part == PART_AFTERNOON and is_working_day(start):
        total -= 0.5
    if end_part == PART_MORNING and is_working_day(end):
        total -= 0.5
    return total


def half_day_slots(start: date, end: date, start_part: str, end_part: str) -> tuple[int, int]:
    """Plage de demi-journées occupées [début, fin] (matin = 0, après-midi = 1)."""
    first = start.toordinal() * 2 + (1 if start_part == PART_AFTERNOON else 0)
    last = end.toordinal() * 2 + (0 if end_part == PART_MORNING else 1)
    return first, last


def slots_of(doc: dict) -> tuple[int, int]:
    return half_day_slots(
        date.fromisoformat(doc["start_date"]),
        date.fromisoformat(doc["end_date"]),
        doc.get("start_day_part") or PART_FULL,
        doc.get("end_day_part") or PART_FULL,
    )


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def validate_request(payload: dict) -> dict:
    """Contrôles de saisie. Retourne les champs normalisés (sans identité)."""
    leave_type = str(payload.get("leave_type") or "").strip()
    if leave_type not in LEAVE_TYPES:
        raise LeaveValidationError("Choisissez un type d'absence.")
    start = parse_civil_date(payload.get("start_date"), "La date de début")
    end = parse_civil_date(payload.get("end_date"), "La date de fin")
    if end < start:
        raise LeaveValidationError("La date de fin doit être égale ou postérieure à la date de début.")
    if (end - start).days >= MAX_SPAN_DAYS:
        raise LeaveValidationError("Une demande ne peut pas dépasser un an. Déposez plusieurs demandes.")
    start_part, end_part = normalize_parts(start, end, payload.get("start_day_part"), payload.get("end_day_part"))
    days = compute_working_days(start, end, start_part, end_part)
    if days <= 0:
        raise LeaveValidationError("La période choisie ne contient aucun jour ouvré (lundi à vendredi).")
    comment = str(payload.get("comment") or "").strip()
    if len(comment) > COMMENT_MAX:
        raise LeaveValidationError(f"Le commentaire ne doit pas dépasser {COMMENT_MAX} caractères.")
    return {
        "leave_type": leave_type,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "start_day_part": start_part,
        "end_day_part": end_part,
        "days_count": days,
        "comment": comment or None,
    }


def clean_reason(raw: Any, *, required: bool, label: str = "Le motif") -> Optional[str]:
    text = str(raw or "").strip()
    if required and not text:
        raise LeaveValidationError(f"{label} est obligatoire.")
    if len(text) > REASON_MAX:
        raise LeaveValidationError(f"{label} ne doit pas dépasser {REASON_MAX} caractères.")
    return text or None


def find_conflict(candidate: dict, existing: Iterable[dict], *, ignore_id: Optional[str] = None) -> Optional[dict]:
    span = slots_of(candidate)
    for other in existing:
        if ignore_id and other.get("id") == ignore_id:
            continue
        if other.get("status") not in ACTIVE_STATUSES:
            continue
        if overlaps(span, slots_of(other)):
            return other
    return None


def year_bounds(year: int) -> tuple[str, str]:
    return f"{year:04d}-01-01", f"{year:04d}-12-31"


def month_bounds(month: str) -> tuple[str, str]:
    text = str(month or "").strip()
    try:
        first = date.fromisoformat(f"{text}-01")
    except ValueError as exc:
        raise LeaveValidationError("Mois invalide (format AAAA-MM).") from exc
    nxt = date(first.year + (first.month // 12), first.month % 12 + 1, 1)
    return first.isoformat(), (nxt - timedelta(days=1)).isoformat()


def overlap_query(start: str, end: str) -> dict:
    """Demandes qui touchent la plage [start, end] (comparaison texte sur dates ISO)."""
    return {"start_date": {"$lte": end}, "end_date": {"$gte": start}}


def status_counts(docs: Iterable[dict]) -> dict:
    counts = {s: 0 for s in STATUS_LABELS}
    for d in docs:
        s = d.get("status")
        if s in counts:
            counts[s] += 1
    return counts


def sort_for_admin(docs: list[dict]) -> list[dict]:
    """À traiter d'abord (annulations demandées comprises), puis du plus récent au plus ancien."""
    recent_first = sorted(docs, key=lambda d: d.get("created_at") or "", reverse=True)
    return sorted(
        recent_first,
        key=lambda d: 0 if d.get("status") in (STATUS_PENDING, STATUS_CANCELLATION_REQUESTED) else 1,
    )


def public_request(doc: dict, *, include_private: bool = True) -> dict:
    out = {
        "id": doc.get("id"),
        "employee_id": doc.get("employee_id"),
        "employee_name": doc.get("employee_name"),
        "employee_email": doc.get("employee_email"),
        "leave_type": doc.get("leave_type"),
        "leave_type_label": LEAVE_TYPES.get(doc.get("leave_type"), doc.get("leave_type")),
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "start_day_part": doc.get("start_day_part") or PART_FULL,
        "end_day_part": doc.get("end_day_part") or PART_FULL,
        "days_count": doc.get("days_count"),
        "status": doc.get("status"),
        "status_label": STATUS_LABELS.get(doc.get("status"), doc.get("status")),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "reviewed_by_name": doc.get("reviewed_by_name"),
        "reviewed_at": doc.get("reviewed_at"),
        "cancelled_at": doc.get("cancelled_at"),
        "cancellation_requested_at": doc.get("cancellation_requested_at"),
        "version": doc.get("version", 1),
    }
    if include_private:
        out.update({
            "comment": doc.get("comment"),
            "rejection_reason": doc.get("rejection_reason"),
            "cancellation_reason": doc.get("cancellation_reason"),
            "cancellation_decision_reason": doc.get("cancellation_decision_reason"),
        })
    return out


def calendar_entry(doc: dict, *, manager: bool, viewer_id: str) -> dict:
    """Collaborateur : identité + dates + « Absent ». RH : type, statut et identifiant en plus."""
    entry = {
        "employee_id": doc.get("employee_id"),
        "employee_name": doc.get("employee_name"),
        "start_date": doc.get("start_date"),
        "end_date": doc.get("end_date"),
        "start_day_part": doc.get("start_day_part") or PART_FULL,
        "end_day_part": doc.get("end_day_part") or PART_FULL,
        "label": "Absent",
    }
    if manager:
        entry.update({
            "id": doc.get("id"),
            "status": doc.get("status"),
            "status_label": STATUS_LABELS.get(doc.get("status"), doc.get("status")),
            "leave_type": doc.get("leave_type"),
            "leave_type_label": LEAVE_TYPES.get(doc.get("leave_type"), doc.get("leave_type")),
            "days_count": doc.get("days_count"),
        })
    elif doc.get("employee_id") == viewer_id:
        entry["id"] = doc.get("id")
    return entry


def public_event(doc: dict) -> dict:
    return {
        "id": doc.get("id"),
        "event": doc.get("event"),
        "from_status": doc.get("from_status"),
        "to_status": doc.get("to_status"),
        "actor_name": doc.get("actor_name"),
        "reason": doc.get("reason"),
        "created_at": doc.get("created_at"),
    }


INDEXES = (
    (LEAVES_COLLECTION, [("user_id", 1), ("employee_id", 1), ("created_at", -1)], {}),
    (LEAVES_COLLECTION, [("user_id", 1), ("status", 1), ("created_at", -1)], {}),
    (LEAVES_COLLECTION, [("user_id", 1), ("start_date", 1), ("end_date", 1)], {}),
    (LEAVES_COLLECTION, [("id", 1)], {"unique": True, "name": "uniq_leave_id"}),
    (
        LEAVES_COLLECTION,
        [("employee_id", 1), ("client_request_id", 1)],
        {
            "unique": True,
            "name": "uniq_leave_client_request",
            "partialFilterExpression": {"client_request_id": {"$type": "string"}},
        },
    ),
    (EVENTS_COLLECTION, [("leave_request_id", 1), ("created_at", 1)], {}),
    (NOTIFICATIONS_COLLECTION, [("user_id", 1), ("created_at", -1)], {}),
)


async def ensure_indexes(db) -> None:
    for coll, keys, opts in INDEXES:
        await db[coll].create_index(keys, **opts)
