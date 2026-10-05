"""Tests template e-mail dossier présenté (analyse de prévoyance)."""
import os

import email_service as es


def test_format_client_prenom_nom():
    assert es.format_client_prenom_nom({"prenom": "Jean", "nom": "Dupont"}) == "Jean DUPONT"
    assert es.format_client_prenom_nom({"prenom": "Marie", "nom": "martin"}) == "Marie MARTIN"
    assert es.format_client_prenom_nom({"dossier_label": "Famille X"}) == "Famille X"


def test_format_dossier_presente_email_content(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.com")
    subject, text, html_body = es.format_dossier_presente_email(
        {"id": "cli-ada", "prenom": "Ada", "nom": "Lovelace"}
    )
    assert subject == "Dossier prêt à être présenté – Ada LOVELACE"
    assert "Bonjour," in text
    assert "Le dossier de Ada LOVELACE est prêt à être présenté." in text
    assert "vient d’être présenté" not in text
    assert "L’analyse de prévoyance est disponible dans son dossier sur Leosoft." in text
    assert "Bonne journée," in text
    assert "Leosoft" in text
    assert "Ada LOVELACE" in html_body
    assert "est prêt à être présenté" in html_body
    assert es.MAIL_TYPE_DOSSIER_PRESENTE == "dossier_presente"

    expected_url = "https://crm.example.com/clients/cli-ada?tab=analyse-prevoyance"
    assert expected_url in text
    assert "👉 Ouvrir l’analyse de prévoyance" in text
    assert expected_url in html_body
    assert "Ouvrir l’analyse de prévoyance" in html_body
    assert 'href="https://crm.example.com/clients/cli-ada?tab=analyse-prevoyance"' in html_body


def test_format_dossier_presente_email_without_public_url(monkeypatch):
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    _, text, html_body = es.format_dossier_presente_email(
        {"id": "cli-ada", "prenom": "Ada", "nom": "Lovelace"}
    )
    assert "?tab=analyse-prevoyance" not in text
    assert "href=" not in html_body
    assert "est prêt à être présenté" in text


def test_analyse_prevoyance_url(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.test/")
    assert es._analyse_prevoyance_url("abc-123") == (
        "https://app.test/clients/abc-123?tab=analyse-prevoyance"
    )
    assert es._analyse_prevoyance_url(None) is None
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    assert es._analyse_prevoyance_url("abc-123") is None
