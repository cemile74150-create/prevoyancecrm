"""Routes du module Congés & absences.

Tout compte connecté dépose et suit ses propres demandes.
Les décisions (valider, refuser, traiter une annulation) exigent leaves.manage :
contrôle dans access_control._ROUTE_PERMISSIONS et de nouveau ici.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from access_control import PERM_LEAVES_MANAGE, TENANT_USER_ID, User, has_perm
import leaves as lv

logger = logging.getLogger(__name__)


class LeaveCreate(BaseModel):
    leave_type: str
    start_date: str
    end_date: str
    start_day_part: Optional[str] = lv.PART_FULL
    end_day_part: Optional[str] = None
    comment: Optional[str] = None
    client_request_id: Optional[str] = None


class LeaveAction(BaseModel):
    reason: Optional[str] = None
    expected_version: Optional[int] = None


class LeaveCancellationDecision(BaseModel):
    decision: str
    reason: Optional[str] = None
    expected_version: Optional[int] = None


def can_manage_leaves(user: User) -> bool:
    return has_perm(user, PERM_LEAVES_MANAGE)


def _bad_request(exc: lv.LeaveValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _fr_date(iso: Optional[str]) -> str:
    if not iso or len(iso) < 10:
        return "—"
    return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}"


def _period_label(doc: dict) -> str:
    start, end = doc.get("start_date"), doc.get("end_date")
    if start == end:
        part = doc.get("start_day_part") or lv.PART_FULL
        suffix = "" if part == lv.PART_FULL else f" ({lv.DAY_PARTS[part].lower()})"
        return f"le {_fr_date(start)}{suffix}"
    return f"du {_fr_date(start)} au {_fr_date(end)}"


def attach_leaves_routes(api_router, *, db, get_current_user: Callable):
    leaves_coll = db[lv.LEAVES_COLLECTION]
    events_coll = db[lv.EVENTS_COLLECTION]
    notif_coll = db[lv.NOTIFICATIONS_COLLECTION]

    def _require_manager(user: User) -> None:
        if not can_manage_leaves(user):
            raise HTTPException(status_code=403, detail="Réservé aux personnes autorisées à gérer les congés")

    async def _event(doc: dict, event: str, actor: User, from_status: Optional[str], reason: Optional[str] = None):
        await events_coll.insert_one({
            "id": lv.new_id(),
            "user_id": TENANT_USER_ID,
            "leave_request_id": doc["id"],
            "employee_id": doc.get("employee_id"),
            "event": event,
            "from_status": from_status,
            "to_status": doc.get("status"),
            "actor_id": actor.account_id,
            "actor_name": actor.name,
            "reason": reason,
            "created_at": lv.now_iso(),
        })

    async def _notify(doc: dict, event: str, title: str, message: str, *, audience: str) -> None:
        """audience « managers » : comptes leaves.manage ; « employee » : le demandeur."""
        try:
            await notif_coll.insert_one({
                "id": lv.new_id(),
                "user_id": TENANT_USER_ID,
                "type": "conge",
                "event": event,
                "leave_request_id": doc["id"],
                "title": title,
                "message": message,
                "audience": audience,
                "account_ids": [doc["employee_id"]] if audience == "employee" else [],
                "exclude_account_ids": [doc["employee_id"]] if audience == "managers" else [],
                "read_by": [],
                "created_at": lv.now_iso(),
            })
        except Exception:
            logger.exception("Notification congés non enregistrée event=%s", event)

    async def _get_or_404(leave_id: str) -> dict:
        doc = await leaves_coll.find_one({"id": leave_id, "user_id": TENANT_USER_ID}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Demande introuvable")
        return doc

    async def _get_visible(leave_id: str, user: User) -> dict:
        doc = await _get_or_404(leave_id)
        if doc.get("employee_id") != user.account_id and not can_manage_leaves(user):
            raise HTTPException(status_code=404, detail="Demande introuvable")
        return doc

    async def _active_overlapping(employee_id: str, start: str, end: str) -> list[dict]:
        query = {
            "user_id": TENANT_USER_ID,
            "employee_id": employee_id,
            "status": {"$in": list(lv.ACTIVE_STATUSES)},
            **lv.overlap_query(start, end),
        }
        return await leaves_coll.find(query, {"_id": 0}).to_list(500)

    async def _transition(
        doc: dict,
        action: str,
        actor: User,
        *,
        event: str,
        extra: Optional[dict] = None,
        reason: Optional[str] = None,
        expected_version: Optional[int] = None,
    ) -> dict:
        current = doc.get("status")
        target = lv.next_transition(current, action)
        if not target:
            label = lv.STATUS_LABELS.get(current, current)
            raise HTTPException(status_code=409, detail=f"Action impossible : la demande est « {label} ».")
        guard = {"id": doc["id"], "user_id": TENANT_USER_ID, "status": current}
        if expected_version is not None:
            guard["version"] = expected_version
        now = lv.now_iso()
        updated = await leaves_coll.find_one_and_update(
            guard,
            {"$set": {**(extra or {}), "status": target, "updated_at": now}, "$inc": {"version": 1}},
            projection={"_id": 0},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise HTTPException(
                status_code=409,
                detail="La demande a été modifiée entre-temps. Rechargez la page pour voir son état actuel.",
            )
        await _event(updated, event, actor, current, reason)
        return updated

    def _forbid_own_decision(doc: dict, user: User) -> None:
        if doc.get("employee_id") == user.account_id:
            raise HTTPException(
                status_code=403,
                detail="Vous ne pouvez pas décider de votre propre demande. Une autre personne RH doit la traiter.",
            )

    # ---------------- Collaborateur ----------------
    @api_router.get("/leaves/meta")
    async def leaves_meta(user: User = Depends(get_current_user)):
        return {
            "employee": {"id": user.account_id, "name": user.name, "email": user.email},
            "can_manage": can_manage_leaves(user),
            "leave_types": [{"id": k, "label": v} for k, v in lv.LEAVE_TYPES.items()],
            "statuses": [{"id": k, "label": v} for k, v in lv.STATUS_LABELS.items()],
            "day_parts": [{"id": k, "label": v} for k, v in lv.DAY_PARTS.items()],
            "calculation_note": lv.CALCULATION_NOTE,
        }

    @api_router.post("/leaves/preview")
    async def preview_leave(payload: LeaveCreate, user: User = Depends(get_current_user)):
        try:
            fields = lv.validate_request(payload.model_dump())
        except lv.LeaveValidationError as exc:
            raise _bad_request(exc) from exc
        conflict = lv.find_conflict(
            fields, await _active_overlapping(user.account_id, fields["start_date"], fields["end_date"])
        )
        return {
            "days_count": fields["days_count"],
            "start_day_part": fields["start_day_part"],
            "end_day_part": fields["end_day_part"],
            "conflict": lv.public_request(conflict) if conflict else None,
            "calculation_note": lv.CALCULATION_NOTE,
        }

    @api_router.post("/leaves", status_code=201)
    async def create_leave(payload: LeaveCreate, user: User = Depends(get_current_user)):
        try:
            fields = lv.validate_request(payload.model_dump())
        except lv.LeaveValidationError as exc:
            raise _bad_request(exc) from exc

        client_request_id = (payload.client_request_id or "").strip()[:80] or None
        if client_request_id:
            already = await leaves_coll.find_one(
                {"employee_id": user.account_id, "client_request_id": client_request_id}, {"_id": 0}
            )
            if already:
                return {**lv.public_request(already), "duplicate": True}

        def _conflict_error(other: dict) -> HTTPException:
            label = lv.STATUS_LABELS.get(other.get("status"), other.get("status"))
            return HTTPException(
                status_code=409,
                detail=f"Cette période chevauche une demande existante ({label}, {_period_label(other)}).",
            )

        existing = await _active_overlapping(user.account_id, fields["start_date"], fields["end_date"])
        conflict = lv.find_conflict(fields, existing)
        if conflict:
            raise _conflict_error(conflict)

        now = lv.now_iso()
        doc = {
            "id": lv.new_id(),
            "user_id": TENANT_USER_ID,
            "employee_id": user.account_id,
            "employee_name": user.name,
            "employee_email": user.email,
            **fields,
            "status": lv.STATUS_PENDING,
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "reviewed_by": None,
            "reviewed_by_name": None,
            "reviewed_at": None,
            "rejection_reason": None,
            "calculation_note": lv.CALCULATION_NOTE,
        }
        if client_request_id:
            doc["client_request_id"] = client_request_id
        try:
            await leaves_coll.insert_one(dict(doc))
        except DuplicateKeyError:
            already = await leaves_coll.find_one(
                {"employee_id": user.account_id, "client_request_id": client_request_id}, {"_id": 0}
            )
            if already:
                return {**lv.public_request(already), "duplicate": True}
            raise HTTPException(status_code=409, detail="Demande déjà enregistrée") from None

        # Deux envois simultanés peuvent passer le contrôle : la plus ancienne demande est conservée.
        rivals = await _active_overlapping(user.account_id, fields["start_date"], fields["end_date"])
        mine = (doc["created_at"], doc["id"])
        for other in rivals:
            if other["id"] == doc["id"] or not lv.overlaps(lv.slots_of(doc), lv.slots_of(other)):
                continue
            if (other.get("created_at") or "", other["id"]) < mine:
                await leaves_coll.delete_one({"id": doc["id"], "status": lv.STATUS_PENDING})
                raise _conflict_error(other)

        await _event(doc, "created", user, None)
        await _notify(
            doc,
            "created",
            "Nouvelle demande de congé",
            f"{user.name} : {lv.LEAVE_TYPES[doc['leave_type']]} {_period_label(doc)} ({doc['days_count']:g} j).",
            audience="managers",
        )
        return lv.public_request(doc)

    @api_router.get("/leaves/mine")
    async def list_my_leaves(
        year: Optional[int] = Query(None, ge=2000, le=2100),
        status: Optional[str] = None,
        user: User = Depends(get_current_user),
    ):
        base = {"user_id": TENANT_USER_ID, "employee_id": user.account_id}
        all_mine = await leaves_coll.find(base, {"_id": 0}).sort("created_at", -1).to_list(2000)
        years = sorted({int(d["start_date"][:4]) for d in all_mine if d.get("start_date")}, reverse=True)
        scoped = all_mine
        if year:
            y_start, y_end = lv.year_bounds(year)
            scoped = [d for d in all_mine if d["start_date"] <= y_end and d["end_date"] >= y_start]
        counts = lv.status_counts(scoped)
        items = [d for d in scoped if not status or d.get("status") == status]
        return {
            "items": [lv.public_request(d) for d in items],
            "total": len(items),
            "years": years,
            "kpis": {
                "pending": counts[lv.STATUS_PENDING],
                "approved": counts[lv.STATUS_APPROVED] + counts[lv.STATUS_CANCELLATION_REQUESTED],
                "rejected": counts[lv.STATUS_REJECTED],
                "cancellation_requested": counts[lv.STATUS_CANCELLATION_REQUESTED],
            },
        }

    # ---------------- RH ----------------
    @api_router.get("/leaves/employees")
    async def list_leave_employees(user: User = Depends(get_current_user)):
        _require_manager(user)
        rows = await db.users.find(
            {"active": {"$ne": False}}, {"_id": 0, "user_id": 1, "name": 1, "prenom": 1, "nom": 1, "email": 1}
        ).to_list(1000)
        people = [
            {
                "id": r["user_id"],
                "name": r.get("name") or f"{r.get('prenom') or ''} {r.get('nom') or ''}".strip() or r.get("email"),
                "email": r.get("email"),
            }
            for r in rows
            if r.get("user_id")
        ]
        people.sort(key=lambda p: (p["name"] or "").casefold())
        return {"items": people}

    @api_router.get("/leaves/admin")
    async def list_admin_leaves(
        employee_id: Optional[str] = None,
        status: Optional[str] = None,
        year: Optional[int] = Query(None, ge=2000, le=2100),
        period_from: Optional[str] = None,
        period_to: Optional[str] = None,
        submitted_from: Optional[str] = None,
        submitted_to: Optional[str] = None,
        user: User = Depends(get_current_user),
    ):
        _require_manager(user)
        query: dict = {"user_id": TENANT_USER_ID}
        if employee_id:
            query["employee_id"] = employee_id
        ands: list[dict] = []
        try:
            if year:
                ands.append(lv.overlap_query(*lv.year_bounds(year)))
            if period_from or period_to:
                p_from = lv.parse_civil_date(period_from, "Début de période").isoformat() if period_from else "0000-01-01"
                p_to = lv.parse_civil_date(period_to, "Fin de période").isoformat() if period_to else "9999-12-31"
                ands.append(lv.overlap_query(p_from, p_to))
            if submitted_from:
                ands.append({"created_at": {"$gte": lv.parse_civil_date(submitted_from, "Soumise depuis").isoformat()}})
            if submitted_to:
                # created_at est un horodatage UTC ISO : borne exclusive au lendemain.
                day = lv.parse_civil_date(submitted_to, "Soumise jusqu'au")
                ands.append({"created_at": {"$lt": (day + timedelta(days=1)).isoformat()}})
        except lv.LeaveValidationError as exc:
            raise _bad_request(exc) from exc
        if ands:
            query["$and"] = ands
        rows = await leaves_coll.find(query, {"_id": 0}).to_list(5000)
        counts = lv.status_counts(rows)
        items = lv.sort_for_admin([d for d in rows if not status or d.get("status") == status])
        all_years = await leaves_coll.distinct("start_date", {"user_id": TENANT_USER_ID})
        return {
            "items": [lv.public_request(d) for d in items],
            "total": len(items),
            "years": sorted({int(s[:4]) for s in all_years if s}, reverse=True),
            "kpis": {
                "pending": counts[lv.STATUS_PENDING],
                "approved": counts[lv.STATUS_APPROVED],
                "rejected": counts[lv.STATUS_REJECTED],
                "cancellation_requested": counts[lv.STATUS_CANCELLATION_REQUESTED],
            },
        }

    # ---------------- Calendrier ----------------
    @api_router.get("/leaves/calendar")
    async def leaves_calendar(
        month: str = Query(..., description="AAAA-MM"),
        include_pending: bool = False,
        employee_id: Optional[str] = None,
        leave_type: Optional[str] = None,
        user: User = Depends(get_current_user),
    ):
        manager = can_manage_leaves(user)
        try:
            m_start, m_end = lv.month_bounds(month)
        except lv.LeaveValidationError as exc:
            raise _bad_request(exc) from exc
        statuses = list(lv.CALENDAR_APPROVED_STATUSES)
        if manager and include_pending:
            statuses.append(lv.STATUS_PENDING)
        query = {"user_id": TENANT_USER_ID, "status": {"$in": statuses}, **lv.overlap_query(m_start, m_end)}
        if employee_id:
            query["employee_id"] = employee_id
        if manager and leave_type:
            query["leave_type"] = leave_type
        rows = await leaves_coll.find(query, {"_id": 0}).sort("start_date", 1).to_list(5000)
        return {
            "month": month,
            "start": m_start,
            "end": m_end,
            "manager_view": manager,
            "items": [lv.calendar_entry(d, manager=manager, viewer_id=user.account_id) for d in rows],
        }

    # ---------------- Détail et transitions ----------------
    @api_router.get("/leaves/{leave_id}")
    async def get_leave(leave_id: str, user: User = Depends(get_current_user)):
        doc = await _get_visible(leave_id, user)
        events = await events_coll.find({"leave_request_id": leave_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
        manager = can_manage_leaves(user)
        mine = doc.get("employee_id") == user.account_id
        status = doc.get("status")
        return {
            **lv.public_request(doc),
            "calculation_note": doc.get("calculation_note") or lv.CALCULATION_NOTE,
            "events": [lv.public_event(e) for e in events],
            "can_cancel": mine and status == lv.STATUS_PENDING,
            "can_request_cancellation": mine and status == lv.STATUS_APPROVED,
            "can_decide": manager and not mine and status == lv.STATUS_PENDING,
            "can_resolve_cancellation": manager and not mine and status == lv.STATUS_CANCELLATION_REQUESTED,
        }

    @api_router.post("/leaves/{leave_id}/cancel")
    async def cancel_leave(leave_id: str, payload: Optional[LeaveAction] = None, user: User = Depends(get_current_user)):
        payload = payload or LeaveAction()
        doc = await _get_visible(leave_id, user)
        if doc.get("employee_id") != user.account_id:
            raise HTTPException(status_code=403, detail="Seul l'auteur de la demande peut l'annuler")
        if doc.get("status") == lv.STATUS_APPROVED:
            raise HTTPException(status_code=409, detail="Demande validée : utilisez « Demander l'annulation ».")
        try:
            reason = lv.clean_reason(payload.reason, required=False, label="Le commentaire")
        except lv.LeaveValidationError as exc:
            raise _bad_request(exc) from exc
        updated = await _transition(
            doc, "cancel", user, event="cancelled", reason=reason, expected_version=payload.expected_version,
            extra={"cancelled_at": lv.now_iso(), "cancelled_by": user.account_id, "cancellation_reason": reason},
        )
        await _notify(
            updated, "cancelled", "Demande de congé retirée",
            f"{updated['employee_name']} a annulé sa demande {_period_label(updated)}.", audience="managers",
        )
        return lv.public_request(updated)

    @api_router.post("/leaves/{leave_id}/request-cancellation")
    async def request_leave_cancellation(leave_id: str, payload: LeaveAction, user: User = Depends(get_current_user)):
        doc = await _get_visible(leave_id, user)
        if doc.get("employee_id") != user.account_id:
            raise HTTPException(status_code=403, detail="Seul l'auteur de la demande peut demander son annulation")
        try:
            reason = lv.clean_reason(payload.reason, required=False, label="Le commentaire")
        except lv.LeaveValidationError as exc:
            raise _bad_request(exc) from exc
        updated = await _transition(
            doc, "request_cancellation", user, event="cancellation_requested", reason=reason,
            expected_version=payload.expected_version,
            extra={"cancellation_requested_at": lv.now_iso(), "cancellation_reason": reason},
        )
        await _notify(
            updated, "cancellation_requested", "Demande d'annulation de congé",
            f"{updated['employee_name']} demande l'annulation de son congé validé {_period_label(updated)}.",
            audience="managers",
        )
        return lv.public_request(updated)

    @api_router.post("/leaves/{leave_id}/approve")
    async def approve_leave(leave_id: str, payload: Optional[LeaveAction] = None, user: User = Depends(get_current_user)):
        _require_manager(user)
        payload = payload or LeaveAction()
        doc = await _get_or_404(leave_id)
        _forbid_own_decision(doc, user)
        now = lv.now_iso()
        updated = await _transition(
            doc, "approve", user, event="approved", expected_version=payload.expected_version,
            extra={"reviewed_by": user.account_id, "reviewed_by_name": user.name, "reviewed_at": now},
        )
        await _notify(
            updated, "approved", "Congé validé",
            f"Votre demande {_period_label(updated)} a été validée par {user.name}.", audience="employee",
        )
        return lv.public_request(updated)

    @api_router.post("/leaves/{leave_id}/reject")
    async def reject_leave(leave_id: str, payload: LeaveAction, user: User = Depends(get_current_user)):
        _require_manager(user)
        try:
            reason = lv.clean_reason(payload.reason, required=True, label="Le motif du refus")
        except lv.LeaveValidationError as exc:
            raise _bad_request(exc) from exc
        doc = await _get_or_404(leave_id)
        _forbid_own_decision(doc, user)
        now = lv.now_iso()
        updated = await _transition(
            doc, "reject", user, event="rejected", reason=reason, expected_version=payload.expected_version,
            extra={
                "reviewed_by": user.account_id, "reviewed_by_name": user.name, "reviewed_at": now,
                "rejection_reason": reason,
            },
        )
        await _notify(
            updated, "rejected", "Congé refusé",
            f"Votre demande {_period_label(updated)} a été refusée. Motif : {reason}", audience="employee",
        )
        return lv.public_request(updated)

    @api_router.post("/leaves/{leave_id}/resolve-cancellation")
    async def resolve_leave_cancellation(
        leave_id: str, payload: LeaveCancellationDecision, user: User = Depends(get_current_user)
    ):
        _require_manager(user)
        decision = (payload.decision or "").strip()
        if decision not in ("accept", "refuse"):
            raise HTTPException(status_code=400, detail="Décision attendue : accept ou refuse")
        try:
            reason = lv.clean_reason(payload.reason, required=decision == "refuse", label="Le motif du refus d'annulation")
        except lv.LeaveValidationError as exc:
            raise _bad_request(exc) from exc
        doc = await _get_or_404(leave_id)
        _forbid_own_decision(doc, user)
        now = lv.now_iso()
        if decision == "accept":
            updated = await _transition(
                doc, "accept_cancellation", user, event="cancellation_accepted", reason=reason,
                expected_version=payload.expected_version,
                extra={
                    "cancelled_at": now, "cancelled_by": user.account_id,
                    "cancellation_decided_by": user.account_id, "cancellation_decided_by_name": user.name,
                    "cancellation_decided_at": now, "cancellation_decision_reason": reason,
                },
            )
            title, msg = "Annulation acceptée", f"L'annulation de votre congé {_period_label(updated)} a été acceptée."
        else:
            updated = await _transition(
                doc, "refuse_cancellation", user, event="cancellation_refused", reason=reason,
                expected_version=payload.expected_version,
                extra={
                    "cancellation_decided_by": user.account_id, "cancellation_decided_by_name": user.name,
                    "cancellation_decided_at": now, "cancellation_decision_reason": reason,
                },
            )
            title = "Annulation refusée"
            msg = f"L'annulation de votre congé {_period_label(updated)} a été refusée : le congé reste validé. Motif : {reason}"
        await _notify(updated, f"cancellation_{decision}", title, msg, audience="employee")
        return lv.public_request(updated)

    # ---------------- Notifications internes ----------------
    @api_router.get("/notifications/conges")
    async def list_leave_notifications(limit: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user)):
        ors: list[dict] = [{"audience": "employee", "account_ids": user.account_id}]
        if can_manage_leaves(user):
            ors.append({"audience": "managers", "exclude_account_ids": {"$ne": user.account_id}})
        rows = await notif_coll.find(
            {"user_id": TENANT_USER_ID, "$or": ors}, {"_id": 0}
        ).sort("created_at", -1).to_list(limit)
        for row in rows:
            row["read"] = user.account_id in (row.get("read_by") or [])
            row.pop("read_by", None)
            row.pop("exclude_account_ids", None)
        return {"items": rows, "count": sum(1 for r in rows if not r["read"]), "total": len(rows)}

    @api_router.post("/notifications/conges/{notif_id}/read")
    async def mark_leave_notification_read(notif_id: str, user: User = Depends(get_current_user)):
        await notif_coll.update_one(
            {"id": notif_id, "user_id": TENANT_USER_ID}, {"$addToSet": {"read_by": user.account_id}}
        )
        return {"ok": True}
