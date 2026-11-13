"""Entreprises, import Excel, activation — tests unitaires (pas de prod)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from entreprises import (  # noqa: E402
    AGENCE_MENDES_DOMAIN,
    AGENCE_MENDES_FINMA,
    attach_entreprise_fields,
    email_domain,
    match_entreprise_by_name,
    new_entreprise_doc,
    normalize_domain,
    propose_mendes_attachments,
)
from user_activation import (  # noqa: E402
    generate_provisional_password,
    hash_token,
    validate_new_password,
)
from users_import import (  # noqa: E402
    build_import_template_bytes,
    build_user_docs_from_preview,
    parse_excel_rows,
    preview_import,
)


def test_normalize_domain_and_email():
    assert normalize_domain("@AgenceMendes.CH") == "agencemendes.ch"
    assert email_domain("a@agencemendes.ch") == "agencemendes.ch"


def test_entreprise_finma_resolved_not_copied_as_source():
    ent = new_entreprise_doc(
        nom="Agence Mendes",
        finma_number=AGENCE_MENDES_FINMA,
        email_domains=[AGENCE_MENDES_DOMAIN],
    )
    user = {"user_id": "u1", "email": "x@agencemendes.ch", "entreprise_id": ent["id"]}
    attached = attach_entreprise_fields(user, ent)
    assert attached["entreprise_finma"] == AGENCE_MENDES_FINMA
    assert "finma_number" not in attached or attached.get("finma_number") is None
    # Changement entreprise → nouvelle valeur affichée
    ent2 = {**ent, "finma_number": "F999"}
    assert attach_entreprise_fields(user, ent2)["entreprise_finma"] == "F999"


def test_propose_mendes_attachments_skips_already_linked():
    mendes = new_entreprise_doc(
        nom="Agence Mendes", finma_number=AGENCE_MENDES_FINMA, email_domains=[AGENCE_MENDES_DOMAIN]
    )
    users = [
        {"user_id": "a", "email": "a@agencemendes.ch", "name": "A", "role": "admin"},
        {
            "user_id": "b",
            "email": "b@agencemendes.ch",
            "name": "B",
            "role": "conseiller",
            "entreprise_id": mendes["id"],
        },
        {"user_id": "c", "email": "c@autre.ch", "name": "C", "role": "conseiller"},
    ]
    props = propose_mendes_attachments(users, mendes)
    assert [p["user_id"] for p in props] == ["a"]


def test_import_template_and_preview_flow(tmp_path):
    data = build_import_template_bytes()
    assert data[:2] == b"PK"
    # Écrire un fichier avec entreprise connue + doublon
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Prénom", "Nom", "Email", "Nom de l'entreprise"])
    ws.append(["Jean", "Dupont", "jean.dupont@ex.ch", "Agence Mendes"])
    ws.append(["Marie", "Martin", "marie@ex.ch", "Inconnue SA"])
    ws.append(["X", "Y", "jean.dupont@ex.ch", "Agence Mendes"])
    path = tmp_path / "imp.xlsx"
    wb.save(path)
    rows, err = parse_excel_rows(path.read_bytes())
    assert err is None
    assert len(rows) == 3
    ent = new_entreprise_doc(
        nom="Agence Mendes", finma_number=AGENCE_MENDES_FINMA, email_domains=[AGENCE_MENDES_DOMAIN]
    )
    prev = preview_import(rows, existing_emails=set(), entreprises=[ent])
    assert prev["counts"]["ok"] == 1
    assert prev["counts"]["unknown_entreprise"] == 1
    assert prev["counts"]["duplicate_email_file"] == 1
    assert prev["can_apply"] is False
    assert match_entreprise_by_name([ent], "agence mendes")["id"] == ent["id"]

    ok_only = [r for r in prev["rows"] if r["status"] == "ok"]
    docs = build_user_docs_from_preview(ok_only)
    assert len(docs) == 1
    assert docs[0]["role"] == "conseiller"
    assert docs[0]["access_by_account_id_only"] is True
    assert docs[0]["must_set_password"] is True
    assert docs[0]["entreprise_id"] == ent["id"]
    assert not docs[0].get("password_hash")


def test_activation_token_hash_and_password_rules():
    a = hash_token("secret-token")
    b = hash_token("secret-token")
    assert a == b and len(a) == 64
    assert validate_new_password("short") is not None
    assert validate_new_password("longenough") is None
    p1 = generate_provisional_password()
    p2 = generate_provisional_password()
    assert p1 != p2
    assert len(p1) >= 16


def test_activation_email_never_persists_body_with_link(monkeypatch):
    """Le lien d'activation ne doit pas atterrir dans email_logs.body_*."""
    import asyncio

    import email_service as es
    import user_activation as ua

    captured = {}

    def fake_send_email(*args, **kwargs):
        captured["persist_log"] = kwargs.get("persist_log")
        captured["body"] = args[2] if len(args) > 2 else kwargs.get("body_text")
        return True, None

    monkeypatch.setattr(es, "smtp_configured", lambda: True)
    monkeypatch.setattr(es, "send_email", fake_send_email)

    class FakeDB:
        def __init__(self):
            self.inserted = []

        @property
        def email_logs(self):
            return self

        async def insert_one(self, doc):
            self.inserted.append(doc)

    db = FakeDB()

    async def _run():
        return await ua.send_activation_email(
            db,
            user={"user_id": "u1", "email": "a@b.ch", "prenom": "A"},
            raw_token="tokensecretvalue",
            public_app_url="https://app.leosoft.ch",
        )

    ok, err, link = asyncio.run(_run())
    assert ok is True and err is None
    assert "tokensecretvalue" in link
    assert captured.get("persist_log") is False
    assert db.inserted and db.inserted[0].get("body_redacted") is True
    assert "body_text" not in db.inserted[0]
    assert "tokensecretvalue" not in str(db.inserted[0])


def test_route_permissions_cover_entreprises_and_import():
    from access_control import PERM_USERS_MANAGE, permission_for_request

    assert permission_for_request("GET", "/api/entreprises") == PERM_USERS_MANAGE
    assert permission_for_request("POST", "/api/entreprises") == PERM_USERS_MANAGE
    assert permission_for_request("GET", "/api/users-import/template.xlsx") == PERM_USERS_MANAGE
    assert permission_for_request("POST", "/api/users-import/preview") == PERM_USERS_MANAGE
    assert permission_for_request("GET", "/api/auth/activation/status") is None
