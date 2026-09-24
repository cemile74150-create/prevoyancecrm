"""Tests config mail SMTP Infomaniak + notifications offres."""
import email_service as es


def test_offres_email_to_default(monkeypatch):
    monkeypatch.delenv("OFFRES_EMAIL_TO", raising=False)
    assert es.offres_email_to() == "offres@agencemendes.ch"


def test_offres_email_to_from_env(monkeypatch):
    monkeypatch.setenv("OFFRES_EMAIL_TO", "ops@example.ch")
    assert es.offres_email_to() == "ops@example.ch"


def test_offre_notify_role_recipients():
    assert es.offre_notify_role("envoyee") == "offres_mailbox"
    assert es.offre_notify_role("envoyer") == "offres_mailbox"
    assert es.offre_notify_role(None) == "offres_mailbox"
    assert es.offre_notify_role("recue") == "createur"
    assert es.offre_notify_role("incomplete") == "createur"
    assert es.offre_notify_role("incomplète") == "createur"


def test_smtp_configured_requires_password(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.infomaniak.com")
    monkeypatch.setenv("SMTP_USER", "crm@agencemendes.ch")
    monkeypatch.setenv("SMTP_FROM", "crm@agencemendes.ch")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert es.smtp_configured() is False


def test_smtp_configured_with_infomaniak(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.infomaniak.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "crm@agencemendes.ch")
    monkeypatch.setenv("SMTP_PASSWORD", "secret-not-logged")
    monkeypatch.setenv("SMTP_FROM", "crm@agencemendes.ch")
    assert es.smtp_configured() is True


def test_offres_email_enabled_auto_when_smtp(monkeypatch):
    monkeypatch.delenv("OFFRES_EMAIL_ENABLED", raising=False)
    monkeypatch.setenv("SMTP_HOST", "mail.infomaniak.com")
    monkeypatch.setenv("SMTP_USER", "crm@agencemendes.ch")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "crm@agencemendes.ch")
    assert es.offres_email_enabled() is True


def test_offres_email_enabled_explicit_off(monkeypatch):
    monkeypatch.setenv("OFFRES_EMAIL_ENABLED", "false")
    monkeypatch.setenv("SMTP_HOST", "mail.infomaniak.com")
    monkeypatch.setenv("SMTP_USER", "crm@agencemendes.ch")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "crm@agencemendes.ch")
    assert es.offres_email_enabled() is False


def test_default_from_is_crm(monkeypatch):
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    assert es.smtp_from_address() == "crm@agencemendes.ch"


def test_mail_status_public_no_password(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "mail.infomaniak.com")
    monkeypatch.setenv("SMTP_USER", "crm@agencemendes.ch")
    monkeypatch.setenv("SMTP_PASSWORD", "super-secret-password")
    monkeypatch.setenv("SMTP_FROM", "crm@agencemendes.ch")
    status = es.mail_status_public()
    assert status["provider"] == "smtp_infomaniak"
    assert status["smtp_host"] == "mail.infomaniak.com"
    assert status["smtp_port"] == 587
    assert status["smtp_user"] == "crm@agencemendes.ch"
    assert "password" not in str(status).lower()
    assert "super-secret" not in str(status)


def test_format_demande_offre_email_full_summary(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.ch")
    subject, text, html = es.format_demande_offre_email(
        {
            "id": "d1",
            "numero": "OFF-1",
            "prenom": "Jean",
            "nom": "Dupont",
            "form_type": "pilier3_legacy",
            "form_type_label": "RC-Ménage",
            "compagnies": ["Helvetia"],
            "agent_label": "Alberto Mendes",
            "client_id": "c1",
            "commentaires": "Urgent",
            "montant_prime": 1200,
            "periodicite_prime": "Mensuel",
            "form_payload": {"franchise": "1500", "vide": ""},
        }
    )
    assert subject == "OFF-1-Dupont Jean -RC-Ménage"
    assert "Jean Dupont" in text
    assert "Helvetia" in text
    assert "1200" in text
    assert "franchise" in text.lower() or "1500" in text
    assert "https://crm.example.ch/demandes-offres/d1" in text
    assert "Nouvelle offre" in subject or "envoyée" in text.lower() or "OFF-1" in subject
    assert "Ouvrir la demande" in html
    assert "Formulaire — input" not in text
    assert "input_" not in text


def test_format_demande_offre_email_entreprise_offres_schema_labels(monkeypatch):
    """Véhicule entreprise : labels schéma, jamais Type de pilier ni input_*."""
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.ch")
    subject, text, html = es.format_demande_offre_email(
        {
            "id": "d-ve",
            "numero": "OFF-2026-0045",
            "form_type": "entreprise_offres",
            "form_type_label": "Véhicule entreprise",
            "form_category": "Entreprise",
            "nom": "Garage Test SA",
            "statut": "Demande envoyée",
            "langue_offre": "Français",
            "agent_email": "agent@example.ch",
            "date_envoi": "2026-09-22",
            # Pollution legacy 3a — ne doit PAS apparaître
            "type_pilier": "Pilier lié 3a",
            "deja_piliers_pax": "Oui",
            "form_payload": {
                "input_124": "Entreprise - Assurance Véhicule",
                "input_127.3": "Cemile",
                "input_127.6": "Agent",
                "input_128": "agent@example.ch",
                "input_129": "FINMA-1",
                "input_88": "Garage Test SA",
                "input_2.1": "Rue du Test 1",
                "input_38": "Non",
                "vide": "",
            },
        }
    )
    assert "OFF-2026-0045" in subject
    assert "Véhicule entreprise" in subject or "Véhicule" in subject
    assert "Type de pilier" not in text
    assert "Pilier lié 3a" not in text
    assert "deja_piliers" not in text.lower()
    assert "Formulaire — input" not in text
    assert "input_124" not in text
    assert "input 124" not in text.lower()
    assert "input_127" not in text
    assert "Prénom de l'agent" in text
    assert "Cemile" in text
    assert "Nom de l'entreprise" in text
    assert "Garage Test SA" in text
    assert "Adresse postale" in text
    assert "Cemile" in html
    assert "Formulaire — input" not in html
    assert "input_" not in html


def test_format_demande_offre_email_schema_adresse_et_commentaires(monkeypatch):
    """E-mail schéma : adresse CRM + commentaires complémentaires, sans input_*."""
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.ch")
    _, text, html = es.format_demande_offre_email(
        {
            "id": "d-addr",
            "numero": "OFF-2026-0099",
            "form_type": "vehicule",
            "form_type_label": "Véhicule",
            "prenom": "Ali",
            "nom": "Ben",
            "adresse": "Rue du Lac 12",
            "npa": "1000",
            "ville": "Lausanne",
            "pays": "Suisse",
            "commentaires": "Client pressé — rappeler demain",
            "form_payload": {
                "input_2.1": "Rue du Lac 12",
                "input_2.3": "Lausanne",
                "input_2.5": "1000",
                "input_34": "Note schéma",
            },
        }
    )
    assert "Rue du Lac 12" in text
    assert "Lausanne" in text
    assert "Commentaires / informations complémentaires" in text
    assert "Client pressé" in text
    assert "input_" not in text
    assert "Client pressé" in html
    assert "input_" not in html


def test_format_demande_offre_email_pilier3_schema_labels(monkeypatch):
    """3ème pilier schéma : Type de pilier OK, jamais d'IDs techniques."""
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.ch")
    _, text, html = es.format_demande_offre_email(
        {
            "id": "d-p3",
            "numero": "OFF-2026-0100",
            "form_type": "pilier3",
            "form_type_label": "3ème pilier",
            "form_category": "3ème pilier",
            "prenom": "Jean",
            "nom": "Martin",
            "statut": "Demande envoyée",
            "form_payload": {
                "input_123.3": "Alberto",
                "input_123.6": "Mendes",
                "input_124": "alberto@example.ch",
                "input_46": "Jean",
                # Champ réel « Type de pilier » du schéma pilier3
                "input_29": "Pilier lié 3a",
            },
        }
    )
    assert "Formulaire — input" not in text
    assert "input_" not in text
    assert "Prénom de l'agent" in text
    assert "Alberto" in text
    # Le label schéma (pas la colonne CRM type_pilier)
    assert "Type de pilier" in text
    assert "Pilier lié 3a" in text
    assert "Formulaire — input" not in html


def test_format_demande_offre_email_menage_rc_no_tech_ids(monkeypatch):
    """RC-Ménage (GF1) : labels schéma, isolation vs pollution pilier3."""
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.ch")
    _, text, _ = es.format_demande_offre_email(
        {
            "id": "d-rc",
            "numero": "OFF-2026-0200",
            "form_type": "menage_rc",
            "form_type_label": "RC-Ménage",
            "form_category": "Particulier",
            "type_pilier": "Pilier lié 3a",  # pollution — à ignorer
            "form_payload": {
                "input_120.3": "Paul",
                "input_120.6": "Durand",
                "input_121": "paul@example.ch",
                "input_39": "Durand",
                "input_40": "Paul",
            },
        }
    )
    assert "Type de pilier" not in text
    assert "Pilier lié 3a" not in text
    assert "Formulaire — input" not in text
    assert "input_" not in text
    assert "Prénom de l'agent" in text
    assert "Paul" in text
    assert "Nom" in text

def test_format_offre_recue_email(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.ch")
    subject, text, html = es.format_offre_recue_email(
        {
            "id": "d1",
            "numero": "OFF-9",
            "prenom": "Marie",
            "nom": "Martin",
            "form_type_label": "3e pilier",
            "client_id": "c2",
            "statut": "Offre reçue",
            "agent_prenom": "Paul",
            "agent_label": "Paul Conseiller",
            "montant_prime": 9999,
            "commentaires": "ne doit pas apparaître",
        },
        {
            "compagnie": "AXA",
            "reference": "POL-44",
            "date_reception": "2026-09-09",
            "montant_prime": 250.5,
            "commentaires": "PDF reçu",
            "received_by": "Cemile",
            "statut": "Reçue",
        },
    )
    assert subject == "Offre reçue – Marie Martin – OFF-9"
    assert "Bonjour Paul," in text
    assert "Vous avez reçu une offre pour Marie Martin." in text
    assert "https://crm.example.ch/demandes-offres/d1" in text
    assert "Voir l’offre dans Leosoft" in text
    assert "Bonne journée," in text
    assert "Leosoft" in text
    # Pas de récap détaillé
    assert "AXA" not in text
    assert "POL-44" not in text
    assert "250.5" not in text
    assert "PDF reçu" not in text
    assert "Détails de l'offre" not in text
    assert "9999" not in text
    assert "ne doit pas apparaître" not in text
    assert "https://crm.example.ch/demandes-offres" in html
    assert "gestion-reponses-offres" not in text
    assert 'href="https://crm.example.ch/demandes-offres/d1"' in html


def test_format_demande_offre_recap_conseiller_email(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.leosoft.ch")
    subject, text, html = es.format_demande_offre_recap_conseiller_email(
        {
            "id": "d-recap",
            "numero": "OFF-2026-0100",
            "prenom": "Jean",
            "nom": "Dupont",
            "form_type_label": "RC",
            "statut": "Demande envoyée",
            "agent_prenom": "Alice",
            "compagnies": ["Helvetia"],
            "montant_prime": 800,
        }
    )
    assert subject == "Récapitulatif de votre demande d’offre – Jean Dupont – OFF-2026-0100"
    assert "Bonjour Alice," in text
    assert "récapitulatif" in text.lower()
    assert "Jean Dupont" in text
    assert "Helvetia" in text
    assert "800" in text
    assert "https://app.leosoft.ch/demandes-offres/d-recap" in text
    assert es.MAIL_TYPE_DEMANDE_OFFRE_RECAP == "demande_offre_recap"
    assert "Alice" in html
    assert "Ouvrir la demande" in html


def test_format_demande_incomplete_email(monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://crm.example.ch")
    subject, text, html = es.format_demande_incomplete_email(
        {
            "id": "d1",
            "numero": "OFF-2026-0028",
            "prenom": "Christine",
            "nom": "BEAUSOLEIL",
            "form_type_label": "RC",
            "civilite": "Madame",
            "incomplete_by": "Juliana Castro",
            "incomplete_at": "2026-09-09T10:00:00+00:00",
            "incomplete_notes": "Merci de renvoyer le mandat signé",
            "statut": "Demande incomplète",
        },
        comment="Manque le mandat",
    )
    assert subject == "OFF-2026-0028-BEAUSOLEIL Christine -RC"
    assert "informations complémentaires" in text.lower()
    assert "Christine BEAUSOLEIL" in text
    assert "OFF-2026-0028" in text
    assert "Demande incomplète" in text
    assert "Motif : Manque le mandat" in text
    assert "Commentaire : Merci de renvoyer le mandat signé" in text
    assert "Juliana Castro" in text
    assert "Détails de l'offre" in text
    assert "https://crm.example.ch/demandes-offres/d1" in text
    assert "Manque le mandat" in html
    assert "OFF-2026-0028" in html
    assert "Détails de l'offre" in html


def test_build_email_log_fields():
    doc = es.build_email_log(
        mail_type=es.MAIL_TYPE_DEMANDE_OFFRE,
        to_email="offres@agencemendes.ch",
        subject="Test",
        status="sent",
        body_preview="hello",
        ref_id="abc",
        bcc=["cci@example.ch"],
        message_id="<msg-1@leosoft.ch>",
    )
    assert doc["type"] == "demande_offre"
    assert doc["status"] == "sent"
    assert doc["to"] == "offres@agencemendes.ch"
    assert doc["provider"] == "smtp_infomaniak"
    assert doc["subject"] == "Test"
    assert doc["body_text"] == "hello"
    assert doc["bcc"] == ["cci@example.ch"]
    assert doc["message_id"] == "<msg-1@leosoft.ch>"


def test_normalize_email_status():
    assert es.normalize_email_status("sent") == "sent"
    assert es.normalize_email_status("ok") == "sent"
    assert es.normalize_email_status("pending") == "pending"
    assert es.normalize_email_status("en_cours") == "pending"
    assert es.normalize_email_status("error") == "error"
    assert es.normalize_email_status("failed") == "error"
    assert es.normalize_email_status("") == ""


def test_send_email_logs_even_when_smtp_missing(monkeypatch):
    captured = []

    def sink(doc):
        captured.append(doc)

    es.set_email_log_persist(sink)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setenv("SMTP_USER", "x@y.ch")
    monkeypatch.setenv("SMTP_FROM", "x@y.ch")
    ok, err = es.send_email(
        "dest@example.ch",
        "Objet important",
        "Corps",
        body_html="<p>Corps</p>",
        mail_type=es.MAIL_TYPE_DEMANDE_OFFRE,
        log_meta={"client_label": "Dupont Jean", "numero": "OFF-1", "module": "test"},
    )
    assert ok is False
    assert err
    assert len(captured) == 1
    log = captured[0]
    assert log["subject"] == "Objet important"
    assert log["to"] == "dest@example.ch"
    assert log["type"] == "demande_offre"
    assert log["status"] == "error"
    assert log["client_label"] == "Dupont Jean"
    assert log["numero"] == "OFF-1"
    assert log["body_text"] == "Corps"
    es.set_email_log_persist(None)


def test_send_email_async_logs_pending_then_sent(monkeypatch):
    import asyncio

    captured = []

    async def sink(doc):
        captured.append(dict(doc))

    es.set_email_log_persist(sink)

    def fake_deliver(*args, **kwargs):
        return True, None, "<mid-ok@leosoft.ch>"

    monkeypatch.setattr(es, "_smtp_deliver", fake_deliver)

    async def _run():
        return await es.send_email_async(
            "client@example.ch",
            "OFF-9-Martin Paul -3a",
            "Bonjour",
            body_html="<p>Bonjour</p>",
            mail_type=es.MAIL_TYPE_DEMANDE_OFFRE,
            log_meta={"client_label": "Martin Paul", "numero": "OFF-9"},
        )

    ok, err = asyncio.run(_run())
    assert ok is True
    assert err is None
    assert len(captured) == 2
    assert captured[0]["status"] == "pending"
    assert captured[1]["status"] == "sent"
    assert captured[0]["id"] == captured[1]["id"]
    assert captured[1]["subject"] == "OFF-9-Martin Paul -3a"
    assert captured[1]["client_label"] == "Martin Paul"
    assert captured[1]["to"] == "client@example.ch"
    assert captured[1]["message_id"] == "<mid-ok@leosoft.ch>"
    assert captured[1]["sent_at"]
    es.set_email_log_persist(None)


def test_send_email_async_logs_pending_then_error(monkeypatch):
    import asyncio

    captured = []

    async def sink(doc):
        captured.append(dict(doc))

    es.set_email_log_persist(sink)

    def fake_deliver(*args, **kwargs):
        return False, "SMTP refused", None

    monkeypatch.setattr(es, "_smtp_deliver", fake_deliver)

    async def _run():
        return await es.send_email_async(
            "client@example.ch",
            "Sujet",
            "Corps",
            mail_type=es.MAIL_TYPE_RAPPEL,
            log_meta={"client_label": "Dupont"},
        )

    ok, err = asyncio.run(_run())
    assert ok is False
    assert err == "SMTP refused"
    assert len(captured) == 2
    assert captured[0]["status"] == "pending"
    assert captured[1]["status"] == "error"
    assert captured[0]["id"] == captured[1]["id"]
    assert captured[1]["error"] == "SMTP refused"
    es.set_email_log_persist(None)


def test_build_message_sets_message_id_and_bcc_recipients(monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "noreply@leosoft.ch")
    monkeypatch.setenv("SMTP_FROM_NAME", "LeoSoft")
    monkeypatch.delenv("SMTP_REPLY_TO", raising=False)
    msg, cc, bcc = es._build_message(
        to_email="to@example.ch",
        subject="Hello",
        body_text="Hi",
        cc=["cc@example.ch"],
        bcc=["bcc@example.ch"],
    )
    assert msg["Message-ID"]
    assert "leosoft.ch" in msg["Message-ID"]
    assert cc == ["cc@example.ch"]
    assert bcc == ["bcc@example.ch"]
    # Bcc ne doit pas apparaître dans les en-têtes visibles
    assert msg.get("Bcc") is None
