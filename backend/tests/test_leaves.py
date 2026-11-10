"""Congés & absences : calcul, transitions, droits et scénarios API sur Mongo local.

Les scénarios API utilisent une base jetable « leosoft_test_conges_* » sur le Mongo local
(LEAVES_TEST_MONGO_URL, défaut mongodb://localhost:27017), supprimée en fin de test.
Ils sont ignorés si aucun Mongo local ne répond.
"""
import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest
from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import leaves as lv  # noqa: E402
from access_control import (  # noqa: E402
    PERM_LEAVES_MANAGE,
    ROLE_ADMIN,
    ROLE_CEO,
    ROLE_CONSEILLER,
    default_permissions,
    has_perm,
    permission_for_request,
    user_from_doc,
)
from leaves_routes import (  # noqa: E402
    LeaveAction,
    LeaveCancellationDecision,
    LeaveCreate,
    attach_leaves_routes,
)

MONGO_URL = os.environ.get("LEAVES_TEST_MONGO_URL", "mongodb://localhost:27017")
D = date.fromisoformat


# ---------------- Calcul de durée (règle indicative lun–ven) ----------------
def test_working_days_full_week_excludes_weekend():
    # Lundi 2 → dimanche 15 novembre 2026 : 10 jours ouvrés
    assert lv.compute_working_days(D("2026-11-02"), D("2026-11-15")) == 10


def test_working_days_single_and_half_days():
    assert lv.compute_working_days(D("2026-11-10"), D("2026-11-10")) == 1
    assert lv.compute_working_days(D("2026-11-10"), D("2026-11-10"), "morning", "morning") == 0.5
    assert lv.compute_working_days(D("2026-11-10"), D("2026-11-10"), "afternoon", "afternoon") == 0.5
    # Samedi seul : 0
    assert lv.compute_working_days(D("2026-11-14"), D("2026-11-14")) == 0


def test_working_days_multi_day_with_half_boundaries():
    # Mercredi après-midi → vendredi matin : 0,5 + 1 + 0,5
    assert lv.compute_working_days(D("2026-11-11"), D("2026-11-13"), "afternoon", "morning") == 2
    # Fin un samedi « matin » n'enlève rien (jour non ouvré)
    assert lv.compute_working_days(D("2026-11-12"), D("2026-11-14"), "full", "morning") == 2


def test_working_days_across_dst_and_year_end_have_no_timezone_shift():
    # Passage à l'heure d'été (29.03.2026) et fin d'année : dates civiles, aucune dérive
    assert lv.compute_working_days(D("2026-03-27"), D("2026-03-30")) == 2
    assert lv.compute_working_days(D("2026-12-31"), D("2027-01-04")) == 3
    fields = lv.validate_request({"leave_type": "paid", "start_date": "2026-12-31", "end_date": "2027-01-04"})
    assert (fields["start_date"], fields["end_date"]) == ("2026-12-31", "2027-01-04")


def test_validate_rejects_bad_input():
    with pytest.raises(lv.LeaveValidationError, match="postérieure"):
        lv.validate_request({"leave_type": "paid", "start_date": "2026-11-12", "end_date": "2026-11-10"})
    with pytest.raises(lv.LeaveValidationError, match="aucun jour ouvré"):
        lv.validate_request({"leave_type": "paid", "start_date": "2026-11-14", "end_date": "2026-11-15"})
    with pytest.raises(lv.LeaveValidationError, match="type"):
        lv.validate_request({"leave_type": "maladie", "start_date": "2026-11-10", "end_date": "2026-11-10"})
    with pytest.raises(lv.LeaveValidationError):
        lv.validate_request({"leave_type": "paid", "start_date": "2026-02-30", "end_date": "2026-03-01"})
    with pytest.raises(lv.LeaveValidationError, match="premier jour"):
        lv.validate_request({
            "leave_type": "paid", "start_date": "2026-11-10", "end_date": "2026-11-12", "start_day_part": "morning",
        })
    # Timestamps avec heure / fuseau : seule la date civile est retenue
    fields = lv.validate_request({"leave_type": "other", "start_date": "2026-11-10T23:30:00+01:00", "end_date": "2026-11-10"})
    assert fields["start_date"] == "2026-11-10"


def test_half_day_slots_allow_morning_and_afternoon_same_day():
    am = lv.half_day_slots(D("2026-11-10"), D("2026-11-10"), "morning", "morning")
    pm = lv.half_day_slots(D("2026-11-10"), D("2026-11-10"), "afternoon", "afternoon")
    full = lv.half_day_slots(D("2026-11-10"), D("2026-11-10"), "full", "full")
    assert not lv.overlaps(am, pm)
    assert lv.overlaps(am, full) and lv.overlaps(pm, full)


# ---------------- Transitions ----------------
def test_transitions_table_is_exact():
    allowed = {
        ("pending", "approve"): "approved",
        ("pending", "reject"): "rejected",
        ("pending", "cancel"): "cancelled",
        ("approved", "request_cancellation"): "cancellation_requested",
        ("cancellation_requested", "accept_cancellation"): "cancelled",
        ("cancellation_requested", "refuse_cancellation"): "approved",
    }
    actions = {a for _, a in allowed} | {"approve", "reject"}
    for status in lv.STATUS_LABELS:
        for action in actions:
            assert lv.next_transition(status, action) == allowed.get((status, action)), (status, action)


def test_admin_sort_puts_waiting_first_then_recent():
    docs = [
        {"id": "a", "status": "approved", "created_at": "2026-11-09"},
        {"id": "b", "status": "pending", "created_at": "2026-11-01"},
        {"id": "c", "status": "cancellation_requested", "created_at": "2026-11-05"},
        {"id": "d", "status": "rejected", "created_at": "2026-11-10"},
    ]
    assert [d["id"] for d in lv.sort_for_admin(docs)] == ["c", "b", "d", "a"]


# ---------------- Droits ----------------
def _account(account_id, role=ROLE_CONSEILLER, name=None, **extra):
    name = name or account_id
    return {
        "user_id": account_id, "email": f"{account_id}@test.local", "name": name,
        "prenom": name, "nom": "", "role": role, **extra,
    }


def test_leaves_manage_defaults_to_admin_only():
    assert default_permissions(ROLE_ADMIN)[PERM_LEAVES_MANAGE] is True
    assert default_permissions(ROLE_CEO)[PERM_LEAVES_MANAGE] is False
    assert default_permissions(ROLE_CONSEILLER)[PERM_LEAVES_MANAGE] is False
    # Compte existant avec droits enregistrés avant le module : défaut du rôle
    legacy = user_from_doc(_account("u1", permissions={"clients.view": True}))
    assert has_perm(legacy, PERM_LEAVES_MANAGE) is False
    granted = user_from_doc(_account("u2", permissions={PERM_LEAVES_MANAGE: True}))
    assert has_perm(granted, PERM_LEAVES_MANAGE) is True


def test_route_permissions_protect_manager_endpoints():
    assert permission_for_request("GET", "/api/leaves/admin") == PERM_LEAVES_MANAGE
    assert permission_for_request("GET", "/api/leaves/employees") == PERM_LEAVES_MANAGE
    for action in ("approve", "reject", "resolve-cancellation"):
        assert permission_for_request("POST", f"/api/leaves/abc/{action}") == PERM_LEAVES_MANAGE
    for method, path in (
        ("POST", "/api/leaves"), ("GET", "/api/leaves/mine"), ("GET", "/api/leaves/calendar"),
        ("POST", "/api/leaves/abc/cancel"), ("POST", "/api/leaves/abc/request-cancellation"),
        ("GET", "/api/notifications/conges"),
    ):
        assert permission_for_request(method, path) is None, path


# ---------------- Scénarios API (Mongo local) ----------------
def _mongo_available() -> bool:
    try:
        from pymongo import MongoClient

        MongoClient(MONGO_URL, serverSelectionTimeoutMS=800).admin.command("ping")
        return True
    except Exception:
        return False


mongo = pytest.mark.skipif(not _mongo_available(), reason="Mongo local indisponible")


class Env:
    def __init__(self, db):
        self.db = db
        router = APIRouter(prefix="/api")

        async def _no_auth():  # les tests passent l'utilisateur explicitement
            raise AssertionError

        attach_leaves_routes(router, db=db, get_current_user=_no_auth)
        self.endpoints = {(m, r.path): r.endpoint for r in router.routes for m in r.methods}
        self.alice = user_from_doc(_account("alice", name="Alice Martin"))
        self.bob = user_from_doc(_account("bob", name="Bob Favre"))
        self.rh = user_from_doc(_account("rh", role=ROLE_ADMIN, name="Rita RH"))
        self.rh2 = user_from_doc(_account("rh2", role=ROLE_CEO, name="Hugo RH", permissions={PERM_LEAVES_MANAGE: True}))

    async def call(self, method, path, **kwargs):
        return await self.endpoints[(method, "/api" + path)](**kwargs)

    async def create(self, user, start, end=None, **kw):
        payload = LeaveCreate(leave_type=kw.pop("leave_type", "paid"), start_date=start, end_date=end or start, **kw)
        return await self.call("POST", "/leaves", payload=payload, user=user)

    async def approve(self, user, leave_id, **kw):
        return await self.call("POST", "/leaves/{leave_id}/approve", leave_id=leave_id, payload=LeaveAction(**kw), user=user)

    async def reject(self, user, leave_id, reason=None):
        return await self.call(
            "POST", "/leaves/{leave_id}/reject", leave_id=leave_id, payload=LeaveAction(reason=reason), user=user
        )

    async def detail(self, user, leave_id):
        return await self.call("GET", "/leaves/{leave_id}", leave_id=leave_id, user=user)

    async def mine(self, user, year=None, status=None):
        return await self.call("GET", "/leaves/mine", year=year, status=status, user=user)

    async def admin(self, user, **filters):
        params = {k: None for k in (
            "employee_id", "status", "year", "period_from", "period_to", "submitted_from", "submitted_to",
        )}
        params.update(filters)
        return await self.call("GET", "/leaves/admin", user=user, **params)

    async def calendar(self, user, month, include_pending=False, employee_id=None, leave_type=None):
        return await self.call(
            "GET", "/leaves/calendar", month=month, include_pending=include_pending,
            employee_id=employee_id, leave_type=leave_type, user=user,
        )

    async def notifs(self, user):
        return await self.call("GET", "/notifications/conges", limit=50, user=user)


def run_scenario(scenario):
    async def main():
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=2000)
        name = f"leosoft_test_conges_{uuid.uuid4().hex[:10]}"
        db = client[name]
        try:
            await lv.ensure_indexes(db)
            await scenario(Env(db))
        finally:
            await client.drop_database(name)
            client.close()

    asyncio.run(main())


async def _expect(status, coro):
    with pytest.raises(HTTPException) as exc:
        await coro
    assert exc.value.status_code == status, exc.value.detail
    return exc.value.detail


@mongo
def test_s01_create_request_pending_with_account_identity():
    async def s(env):
        created = await env.create(env.alice, "2026-11-16", "2026-11-20", comment="Vacances")
        assert created["status"] == "pending"
        assert created["employee_id"] == "alice"
        assert created["employee_name"] == "Alice Martin"
        assert created["employee_email"] == "alice@test.local"
        assert created["days_count"] == 5
        stored = await env.db.leave_requests.find_one({"id": created["id"]})
        assert stored["start_date"] == "2026-11-16" and isinstance(stored["start_date"], str)
        events = await env.db.leave_request_events.find({"leave_request_id": created["id"]}).to_list(10)
        assert [e["event"] for e in events] == ["created"]
    run_scenario(s)


@mongo
def test_s02_identity_cannot_be_overridden_by_payload():
    async def s(env):
        payload = LeaveCreate.model_validate({
            "leave_type": "paid", "start_date": "2026-11-16", "end_date": "2026-11-16",
            "employee_id": "bob", "employee_name": "Pirate",
        })
        created = await env.call("POST", "/leaves", payload=payload, user=env.alice)
        assert created["employee_id"] == "alice" and created["employee_name"] == "Alice Martin"
    run_scenario(s)


@mongo
def test_s03_end_before_start_and_weekend_only_rejected():
    async def s(env):
        await _expect(400, env.create(env.alice, "2026-11-20", "2026-11-16"))
        await _expect(400, env.create(env.alice, "2026-11-21", "2026-11-22"))
        assert await env.db.leave_requests.count_documents({}) == 0
    run_scenario(s)


@mongo
def test_s04_overlap_with_pending_or_approved_is_refused_half_days_allowed():
    async def s(env):
        first = await env.create(env.alice, "2026-11-16", "2026-11-18")
        detail = await _expect(409, env.create(env.alice, "2026-11-18", "2026-11-19"))
        assert "chevauche" in detail
        await env.approve(env.rh, first["id"])
        await _expect(409, env.create(env.alice, "2026-11-17"))
        # Autre collaborateur : pas de conflit
        await env.create(env.bob, "2026-11-17")
        # Matin puis après-midi le même jour
        await env.create(env.alice, "2026-11-24", start_day_part="morning")
        await env.create(env.alice, "2026-11-24", start_day_part="afternoon")
        await _expect(409, env.create(env.alice, "2026-11-24"))
    run_scenario(s)


@mongo
def test_s05_rejected_or_cancelled_request_frees_the_dates():
    async def s(env):
        a = await env.create(env.alice, "2026-12-01")
        await env.reject(env.rh, a["id"], reason="Effectif insuffisant")
        b = await env.create(env.alice, "2026-12-01")
        await env.call("POST", "/leaves/{leave_id}/cancel", leave_id=b["id"], payload=None, user=env.alice)
        c = await env.create(env.alice, "2026-12-01")
        assert c["status"] == "pending"
    run_scenario(s)


@mongo
def test_s06_double_submission_is_idempotent():
    async def s(env):
        key = "form-123"
        one = await env.create(env.alice, "2026-11-16", client_request_id=key)
        two = await env.create(env.alice, "2026-11-16", client_request_id=key)
        assert two["id"] == one["id"] and two.get("duplicate") is True
        both = await asyncio.gather(
            env.create(env.alice, "2026-11-23", client_request_id="form-xyz"),
            env.create(env.alice, "2026-11-23", client_request_id="form-xyz"),
        )
        assert both[0]["id"] == both[1]["id"]
        assert await env.db.leave_requests.count_documents({"employee_id": "alice"}) == 2
    run_scenario(s)


@mongo
def test_s07_concurrent_overlapping_creations_keep_only_one():
    async def s(env):
        results = await asyncio.gather(
            *[env.create(env.alice, "2026-11-30", "2026-12-02") for _ in range(4)], return_exceptions=True
        )
        ok = [r for r in results if isinstance(r, dict)]
        assert len(ok) >= 1
        active = await env.db.leave_requests.count_documents({"employee_id": "alice", "status": "pending"})
        assert active == 1
    run_scenario(s)


@mongo
def test_s08_my_leaves_only_mine_with_kpis_and_filters():
    async def s(env):
        a1 = await env.create(env.alice, "2026-11-16")
        a2 = await env.create(env.alice, "2026-11-17")
        await env.create(env.alice, "2027-01-05")
        await env.create(env.bob, "2026-11-16")
        await env.approve(env.rh, a1["id"])
        await env.reject(env.rh, a2["id"], reason="Non")
        res = await env.mine(env.alice, year=2026)
        assert {i["employee_id"] for i in res["items"]} == {"alice"}
        assert res["total"] == 2
        assert res["kpis"] == {"pending": 0, "approved": 1, "rejected": 1, "cancellation_requested": 0}
        assert res["years"] == [2027, 2026]
        assert [i["id"] for i in (await env.mine(env.alice, year=2026, status="rejected"))["items"]] == [a2["id"]]
        all_items = (await env.mine(env.alice))["items"]
        created = [i["created_at"] for i in all_items]
        assert created == sorted(created, reverse=True)
    run_scenario(s)


@mongo
def test_s09_collaborator_cannot_read_or_decide_others_requests():
    async def s(env):
        b = await env.create(env.bob, "2026-11-16", comment="Privé")
        await _expect(404, env.detail(env.alice, b["id"]))
        await _expect(403, env.admin(env.alice))
        await _expect(403, env.approve(env.alice, b["id"]))
        await _expect(403, env.reject(env.alice, b["id"], reason="x"))
        # Annulation par un tiers : la demande reste invisible
        await _expect(404, env.call("POST", "/leaves/{leave_id}/cancel", leave_id=b["id"], payload=None, user=env.alice))
        assert (await env.detail(env.bob, b["id"]))["status"] == "pending"
    run_scenario(s)


@mongo
def test_s10_collaborator_cancels_pending_but_not_approved():
    async def s(env):
        a = await env.create(env.alice, "2026-11-16")
        res = await env.call("POST", "/leaves/{leave_id}/cancel", leave_id=a["id"], payload=None, user=env.alice)
        assert res["status"] == "cancelled"
        b = await env.create(env.alice, "2026-11-18")
        await env.approve(env.rh, b["id"])
        detail = await _expect(409, env.call("POST", "/leaves/{leave_id}/cancel", leave_id=b["id"], payload=None, user=env.alice))
        assert "Demander l'annulation" in detail
    run_scenario(s)


@mongo
def test_s11_rh_approves_with_reviewer_and_notification():
    async def s(env):
        a = await env.create(env.alice, "2026-11-16")
        res = await env.approve(env.rh, a["id"])
        assert res["status"] == "approved"
        stored = await env.db.leave_requests.find_one({"id": a["id"]})
        assert stored["reviewed_by"] == "rh" and stored["reviewed_at"] and stored["version"] == 2
        notes = (await env.notifs(env.alice))["items"]
        assert notes[0]["event"] == "approved" and notes[0]["read"] is False
    run_scenario(s)


@mongo
def test_s12_reject_requires_reason():
    async def s(env):
        a = await env.create(env.alice, "2026-11-16")
        await _expect(400, env.reject(env.rh, a["id"], reason="   "))
        res = await env.reject(env.rh, a["id"], reason="Période de clôture")
        assert res["status"] == "rejected"
        detail = await env.detail(env.alice, a["id"])
        assert detail["rejection_reason"] == "Période de clôture"
        assert [e["event"] for e in detail["events"]] == ["created", "rejected"]
    run_scenario(s)


@mongo
def test_s13_no_double_decision_and_concurrent_decisions_are_atomic():
    async def s(env):
        a = await env.create(env.alice, "2026-11-16")
        await env.approve(env.rh, a["id"])
        await _expect(409, env.approve(env.rh2, a["id"]))
        await _expect(409, env.reject(env.rh2, a["id"], reason="Trop tard"))
        b = await env.create(env.alice, "2026-11-17")
        results = await asyncio.gather(
            env.approve(env.rh, b["id"]), env.reject(env.rh2, b["id"], reason="Non"), return_exceptions=True
        )
        assert sum(isinstance(r, dict) for r in results) == 1
        assert all(r.status_code == 409 for r in results if isinstance(r, HTTPException))
        events = await env.db.leave_request_events.count_documents({"leave_request_id": b["id"]})
        assert events == 2
        # Version périmée : refus explicite
        c = await env.create(env.alice, "2026-11-18")
        await _expect(409, env.approve(env.rh, c["id"], expected_version=7))
    run_scenario(s)


@mongo
def test_s14_cancellation_request_flow():
    async def s(env):
        a = await env.create(env.alice, "2026-11-16")
        await env.approve(env.rh, a["id"])
        res = await env.call(
            "POST", "/leaves/{leave_id}/request-cancellation", leave_id=a["id"],
            payload=LeaveAction(reason="Projet décalé"), user=env.alice,
        )
        assert res["status"] == "cancellation_requested"
        # Toujours absent au calendrier tant que la RH n'a pas décidé
        cal = await env.calendar(env.bob, "2026-11")
        assert len(cal["items"]) == 1
        await _expect(400, env.call(
            "POST", "/leaves/{leave_id}/resolve-cancellation", leave_id=a["id"],
            payload=LeaveCancellationDecision(decision="refuse"), user=env.rh,
        ))
        res = await env.call(
            "POST", "/leaves/{leave_id}/resolve-cancellation", leave_id=a["id"],
            payload=LeaveCancellationDecision(decision="refuse", reason="Présence requise"), user=env.rh,
        )
        assert res["status"] == "approved"
        await env.call(
            "POST", "/leaves/{leave_id}/request-cancellation", leave_id=a["id"], payload=LeaveAction(), user=env.alice,
        )
        res = await env.call(
            "POST", "/leaves/{leave_id}/resolve-cancellation", leave_id=a["id"],
            payload=LeaveCancellationDecision(decision="accept"), user=env.rh,
        )
        assert res["status"] == "cancelled"
        assert (await env.calendar(env.bob, "2026-11"))["items"] == []
        events = [e["event"] for e in (await env.detail(env.alice, a["id"]))["events"]]
        assert events == [
            "created", "approved", "cancellation_requested", "cancellation_refused",
            "cancellation_requested", "cancellation_accepted",
        ]
        # Plus aucune transition possible
        await _expect(409, env.call(
            "POST", "/leaves/{leave_id}/request-cancellation", leave_id=a["id"], payload=LeaveAction(), user=env.alice,
        ))
    run_scenario(s)


@mongo
def test_s15_calendar_collaborator_sees_neutral_approved_only():
    async def s(env):
        b1 = await env.create(env.bob, "2026-11-16", "2026-11-17", comment="Mariage", leave_type="other")
        await env.create(env.bob, "2026-11-23")  # en attente
        b3 = await env.create(env.bob, "2026-11-25")
        await env.approve(env.rh, b1["id"])
        await env.reject(env.rh, b3["id"], reason="Motif confidentiel")
        cal = await env.calendar(env.alice, "2026-11", include_pending=True)
        assert cal["manager_view"] is False
        assert len(cal["items"]) == 1
        entry = cal["items"][0]
        assert entry["label"] == "Absent" and entry["employee_name"] == "Bob Favre"
        for hidden in ("comment", "leave_type", "status", "rejection_reason", "id", "days_count"):
            assert hidden not in entry
    run_scenario(s)


@mongo
def test_s16_calendar_manager_with_pending_filters_and_month_overlap():
    async def s(env):
        a = await env.create(env.alice, "2026-10-29", "2026-11-03")  # chevauche deux mois
        await env.approve(env.rh, a["id"])
        await env.create(env.bob, "2026-11-03")  # en attente, même jour
        cal = await env.calendar(env.rh, "2026-11")
        assert [i["employee_id"] for i in cal["items"]] == ["alice"]
        cal = await env.calendar(env.rh, "2026-11", include_pending=True)
        assert {i["employee_id"] for i in cal["items"]} == {"alice", "bob"}
        assert all("status" in i and "id" in i for i in cal["items"])
        cal = await env.calendar(env.rh, "2026-11", include_pending=True, employee_id="bob")
        assert [i["employee_id"] for i in cal["items"]] == ["bob"]
        assert len((await env.calendar(env.rh, "2026-10"))["items"]) == 1
        await _expect(400, env.calendar(env.rh, "2026-13"))
    run_scenario(s)


@mongo
def test_s17_admin_list_filters_kpis_and_order():
    async def s(env):
        a = await env.create(env.alice, "2026-11-16")
        await env.create(env.bob, "2026-11-17")
        c = await env.create(env.bob, "2026-12-07")
        await env.approve(env.rh, a["id"])
        await env.reject(env.rh, c["id"], reason="Non")
        res = await env.admin(env.rh, year=2026)
        assert res["kpis"] == {"pending": 1, "approved": 1, "rejected": 1, "cancellation_requested": 0}
        assert res["items"][0]["status"] == "pending"
        assert {i["employee_id"] for i in (await env.admin(env.rh, employee_id="bob"))["items"]} == {"bob"}
        period = await env.admin(env.rh, period_from="2026-12-01", period_to="2026-12-31")
        assert [i["id"] for i in period["items"]] == [c["id"]]
        today = date.today().isoformat()
        assert (await env.admin(env.rh, submitted_from=today, submitted_to=today))["total"] == 3
        assert (await env.admin(env.rh, submitted_to="2000-01-01"))["total"] == 0
        await _expect(400, env.admin(env.rh, period_from="n'importe"))
    run_scenario(s)


@mongo
def test_s18_self_decision_forbidden_and_notifications_scoped():
    async def s(env):
        own = await env.create(env.rh, "2026-11-16")
        await _expect(403, env.approve(env.rh, own["id"]))
        assert (await env.approve(env.rh2, own["id"]))["status"] == "approved"
        await env.create(env.alice, "2026-11-20")
        # RH : notifications « nouvelle demande », sauf pour sa propre demande
        rh_events = [(n["event"], n["leave_request_id"]) for n in (await env.notifs(env.rh))["items"]]
        assert ("created", own["id"]) not in rh_events
        assert any(e == "created" for e, _ in rh_events)
        # Collaborateur : jamais les notifications destinées aux RH
        alice = (await env.notifs(env.alice))["items"]
        assert all(n["audience"] == "employee" for n in alice)
        bob = (await env.notifs(env.bob))["items"]
        assert bob == []
        n = (await env.notifs(env.rh2))["items"][0]
        await env.call("POST", "/notifications/conges/{notif_id}/read", notif_id=n["id"], user=env.rh2)
        assert (await env.notifs(env.rh2))["items"][0]["read"] is True
        assert (await env.notifs(env.rh))["items"][0]["read"] is False
    run_scenario(s)
