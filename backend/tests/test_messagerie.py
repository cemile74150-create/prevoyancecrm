"""Messagerie Phase 1 — pagination / filtres / catégories (sans SMTP)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import messagerie as msg
from email_service import BODY_TEXT_MAX, build_email_log, normalize_email_status


class _FakeCursor:
    def __init__(self, rows: List[dict]):
        self._rows = list(rows)
        self._skip = 0
        self._limit: Optional[int] = None

    def sort(self, *_args, **_kwargs):
        self._rows.sort(
            key=lambda r: str(r.get("sent_at") or r.get("created_at") or ""),
            reverse=True,
        )
        return self

    def skip(self, n: int):
        self._skip = int(n or 0)
        return self

    def limit(self, n: int):
        self._limit = int(n)
        return self

    async def to_list(self, n: Optional[int] = None):
        end = self._skip + (self._limit if self._limit is not None else (n or len(self._rows)))
        return self._rows[self._skip : end]


class _FakeColl:
    def __init__(self, rows: Optional[List[dict]] = None):
        self.rows = list(rows or [])

    def _match(self, doc: dict, query: dict) -> bool:
        if not query:
            return True
        # Opérateurs logiques (ANDés avec le reste des clés, comme Mongo).
        if "$and" in query:
            rest = {k: v for k, v in query.items() if k != "$and"}
            return all(self._match(doc, part) for part in query["$and"]) and self._match(doc, rest)
        if "$or" in query:
            rest = {k: v for k, v in query.items() if k != "$or"}
            return any(self._match(doc, part) for part in query["$or"]) and self._match(doc, rest)
        if "$nor" in query:
            rest = {k: v for k, v in query.items() if k != "$nor"}
            return (not any(self._match(doc, part) for part in query["$nor"])) and self._match(doc, rest)
        for key, expected in query.items():
            if key.startswith("$"):
                continue
            actual = doc.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$gte" in expected and str(actual or "") < str(expected["$gte"]):
                    return False
                if "$lte" in expected and str(actual or "") > str(expected["$lte"]):
                    return False
                if "$lt" in expected and str(actual or "") >= str(expected["$lt"]):
                    return False
                if "$regex" in expected:
                    import re

                    flags = re.I if "i" in str(expected.get("$options") or "") else 0
                    if not re.search(expected["$regex"], str(actual or ""), flags):
                        return False
            elif actual != expected:
                return False
        return True

    def find(self, query: Optional[dict] = None, projection: Optional[dict] = None):
        matched = [r for r in self.rows if self._match(r, query or {})]
        if projection:
            out = []
            for r in matched:
                copy = dict(r)
                for k, v in projection.items():
                    if v == 0 and k != "_id":
                        copy.pop(k, None)
                out.append(copy)
            matched = out
        return _FakeCursor(matched)

    async def count_documents(self, query: Optional[dict] = None):
        return len([r for r in self.rows if self._match(r, query or {})])

    async def find_one(self, query: dict, projection: Optional[dict] = None):
        for r in self.rows:
            if self._match(r, query):
                return dict(r)
        return None


class _FakeDB:
    def __init__(self, email_logs: List[dict], legacy: Optional[List[dict]] = None):
        self._cols = {
            "email_logs": _FakeColl(email_logs),
            "rappel_email_logs": _FakeColl(legacy or []),
        }

    def __getitem__(self, name: str):
        return self._cols[name]

    @property
    def rappel_email_logs(self):
        return self._cols["rappel_email_logs"]

    @property
    def email_logs(self):
        return self._cols["email_logs"]


def _row(**kwargs):
    base = {
        "id": kwargs.get("id", "e1"),
        "type": kwargs.get("type", "notification"),
        "to": kwargs.get("to", "a@b.ch"),
        "subject": kwargs.get("subject", "Sujet"),
        "status": kwargs.get("status", "sent"),
        "sent_at": kwargs.get("sent_at", "2026-11-10T10:00:00+00:00"),
        "created_at": kwargs.get("created_at", "2026-11-10T10:00:00+00:00"),
        "client_label": kwargs.get("client_label", ""),
        "agent_label": kwargs.get("agent_label", ""),
        "numero": kwargs.get("numero", ""),
        "numero_dossier": kwargs.get("numero_dossier", ""),
        "client_id": kwargs.get("client_id"),
        "dossier_id": kwargs.get("dossier_id"),
        "ref_id": kwargs.get("ref_id"),
        "provider": kwargs.get("provider", "smtp_infomaniak"),
    }
    base.update({k: v for k, v in kwargs.items() if k not in base})
    return base


def test_normalize_status_never_delivered():
    assert normalize_email_status("sent") == "sent"
    assert normalize_email_status("ok") == "sent"
    assert normalize_email_status("failed") == "error"
    assert normalize_email_status("pending") == "pending"
    assert "delivered" not in {
        normalize_email_status("sent"),
        normalize_email_status("ok"),
        normalize_email_status("error"),
    }


def test_build_email_log_sets_body_truncated():
    long_body = "x" * (BODY_TEXT_MAX + 50)
    doc = build_email_log(
        mail_type="notification",
        to_email="a@b.ch",
        subject="t",
        status="sent",
        body_text=long_body,
    )
    assert doc["body_truncated"] is True
    assert doc["body_text"].endswith("…")
    assert len(doc["body_text"]) <= BODY_TEXT_MAX


def test_automatic_types_include_relances_and_activation():
    assert msg.is_automatic_mail_type("relance_agent_14j")
    assert msg.is_automatic_mail_type("relance_agent_21j")
    assert msg.is_automatic_mail_type("fil_discussion")
    assert msg.is_automatic_mail_type("complement_demande")
    assert msg.is_automatic_mail_type("user_activation")
    assert msg.email_type_label("relance_agent_14j") == "Relance agent J+14"
    assert msg.email_type_label("user_activation") == "Activation compte"


def test_leosoft_link_demande_and_client():
    link = msg.leosoft_link_for_email(
        {"type": "demande_offre", "ref_id": "do-1", "numero": "OFF-1"}
    )
    assert link["href"] == "/demandes-offres/do-1"
    link2 = msg.leosoft_link_for_email({"client_id": "c1", "client_label": "Ada"})
    assert link2["href"] == "/clients/c1"
    link3 = msg.leosoft_link_for_email({"dossier_id": "d1", "numero_dossier": "DOS-1"})
    assert link3["href"] == "/dossiers/d1"


def test_query_category_automatic_and_error():
    q_auto = msg.build_email_logs_query(category="automatic")
    parts = q_auto.get("$and") or [q_auto]
    type_part = next(p for p in parts if "type" in p)
    assert "relance_agent_14j" in type_part["type"]["$in"]
    q_err = msg.build_email_logs_query(category="error")
    err_parts = q_err.get("$and") or [q_err]
    status_err = next(p for p in err_parts if "status" in p)
    assert status_err["status"]["$in"] == ["error", "failed", "fail"]
    q_sent = msg.build_email_logs_query(category="sent")
    sent_parts = q_sent.get("$and") or [q_sent]
    status_sent = next(p for p in sent_parts if "status" in p)
    assert "sent" in status_sent["status"]["$in"]


def test_fetch_email_page_pagination_and_filters():
    rows = [
        _row(id="a", type="demande_offre", status="sent", sent_at="2026-11-12T10:00:00+00:00", to="one@x.ch"),
        _row(id="b", type="relance_agent_14j", status="sent", sent_at="2026-11-11T10:00:00+00:00", to="two@x.ch"),
        _row(id="c", type="notification", status="error", sent_at="2026-11-10T10:00:00+00:00", to="err@x.ch", error="boom"),
        _row(id="d", type="smtp_test", status="sent", sent_at="2026-11-09T10:00:00+00:00", to="test@x.ch", subject="Ping"),
        _row(id="e", type="fil_discussion", status="sent", sent_at="2026-11-08T10:00:00+00:00", agent_label="Cemile"),
    ]
    db = _FakeDB(rows)

    page1 = asyncio.run(msg.fetch_email_page(db, limit=2, skip=0, category="all"))
    assert page1["folder"] == "outbox"
    assert page1["folder_enabled"] is True
    assert len(page1["items"]) == 2
    assert page1["items"][0]["id"] == "a"
    assert page1["total"] >= 2
    assert page1["has_more"] is True

    page2 = asyncio.run(msg.fetch_email_page(db, limit=2, skip=2, category="all"))
    assert len(page2["items"]) == 2
    assert page2["items"][0]["id"] == "c"

    auto = asyncio.run(msg.fetch_email_page(db, limit=50, skip=0, category="automatic"))
    types = {r["type"] for r in auto["items"]}
    assert "relance_agent_14j" in types
    assert "fil_discussion" in types

    errors = asyncio.run(msg.fetch_email_page(db, limit=50, skip=0, category="error"))
    assert all(r["status"] == "error" for r in errors["items"])
    assert errors["items"][0]["id"] == "c"

    search = asyncio.run(msg.fetch_email_page(db, limit=50, skip=0, q="Ping"))
    assert [r["id"] for r in search["items"]] == ["d"]

    agent = asyncio.run(msg.fetch_email_page(db, limit=50, skip=0, agent="Cemile"))
    assert [r["id"] for r in agent["items"]] == ["e"]


def test_inbox_folder_stub_empty():
    db = _FakeDB([_row(id="a")])
    out = asyncio.run(msg.fetch_email_page(db, folder="inbox", limit=20, skip=0))
    assert out["items"] == []
    assert out["folder"] == "inbox"
    assert out["folder_enabled"] is False
    assert "IMAP" in (out.get("folder_message") or "")


def test_public_row_detail_marks_truncated():
    row = _row(id="t", body_text=("y" * BODY_TEXT_MAX) + "…", body_truncated=True)
    # Simulate stored truncated body at max length ending with ellipsis
    row["body_text"] = ("y" * (BODY_TEXT_MAX - 1)) + "…"
    pub = msg.public_email_row(row, detail=True)
    assert pub["body_truncated"] is True
    assert pub["status"] == "sent"
    assert "delivered" not in str(pub).lower()


def test_legacy_rappel_merge_on_first_page_only():
    main = [_row(id="m1", type="notification", sent_at="2026-11-12T12:00:00+00:00")]
    legacy = [
        {
            "id": "leg1",
            "to_email": "leg@x.ch",
            "status": "failed",
            "sent_at": "2026-11-12T13:00:00+00:00",
            "subject": "Rappel legacy",
        }
    ]
    db = _FakeDB(main, legacy)
    page0 = asyncio.run(msg.fetch_email_page(db, limit=10, skip=0, category="all"))
    ids = {r["id"] for r in page0["items"]}
    assert "leg1" in ids
    assert page0["items"][0]["status"] == "error"  # failed → error

    page1 = asyncio.run(msg.fetch_email_page(db, limit=10, skip=10, category="all"))
    # skip>0 : pas de re-fusion legacy (pagination stable sur email_logs)
    assert all(r["id"] != "leg1" for r in page1["items"])


def test_no_smtp_send_in_messagerie_module():
    assert not hasattr(msg, "send_email")
    src = open(msg.__file__, encoding="utf-8").read()
    assert "send_email(" not in src
    assert "smtplib" not in src
