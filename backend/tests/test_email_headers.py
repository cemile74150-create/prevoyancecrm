"""Headers / config expéditeur e-mails CRM (SMTP Infomaniak — sans envoi réel)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email.header import decode_header, make_header

from email_service import smtp_from_header, smtp_reply_to  # noqa: E402


def test_from_uses_smtp_from_and_display_name(monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "crm@agencemendes.ch")
    monkeypatch.delenv("SMTP_FROM_NAME", raising=False)
    header = smtp_from_header()
    assert "crm@agencemendes.ch" in header
    decoded = str(make_header(decode_header(header)))
    assert "LeoSoft" in decoded


def test_reply_to_defaults_to_smtp_from_not_noreply(monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "crm@agencemendes.ch")
    monkeypatch.delenv("SMTP_REPLY_TO", raising=False)
    assert smtp_reply_to() == "crm@agencemendes.ch"
    assert "no-reply" not in smtp_reply_to().lower()


def test_reply_to_honors_env_only_when_set(monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "crm@agencemendes.ch")
    monkeypatch.setenv("SMTP_REPLY_TO", "crm@agencemendes.ch")
    assert smtp_reply_to() == "crm@agencemendes.ch"
