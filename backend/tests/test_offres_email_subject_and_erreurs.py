"""Tests objet e-mail permanent + erreurs incomplètes + modification."""
from email_service import (
    build_permanent_email_subject,
    format_demande_incomplete_email,
    format_demande_offre_email,
    format_offre_client_subject_name,
    format_offre_modifiee_email,
    format_offre_recue_email,
    format_offre_signee_email,
    resolve_email_subject,
    subject_uses_placeholder_client,
)
from demandes_offres_3p import (
    DEMANDE_ORIGINE_ATTRIBUEE,
    STATUT_OFFRE_A_MODIFIER,
    STATUT_OFFRE_MODIFIEE,
    build_field_changes,
    compute_erreur_stats,
    gestion_categorie_ids,
    normalize_erreurs_incomplete,
    normalize_statut,
)


def _doc(**kwargs):
    base = {
        "id": "d1",
        "numero": "OFF-2026-00452",
        "nom": "Dupont",
        "prenom": "Jean",
        "form_type_label": "3e pilier",
        "statut": "Demande envoyée",
        "agent_label": "Cemile",
        "compagnies": ["AXA"],
    }
    base.update(kwargs)
    return base


def test_permanent_subject_format():
    subj = build_permanent_email_subject(_doc())
    assert subj == "OFF-2026-00452-Dupont Jean -3e pilier"


def test_subject_name_order_nom_prenom():
    assert format_offre_client_subject_name(_doc()) == "Dupont Jean"
    assert format_offre_client_subject_name(_doc(nom="", prenom="")) == "Client"


def test_subject_from_form_payload_without_top_level_names():
    doc = {
        "numero": "OFF-2026-0040",
        "form_type": "protection_juridique_particulier",
        "form_type_label": "3eme pilier",
        "form_payload": {},
    }
    # Without schema fields filled, falls back to Client — ensure no crash
    assert "OFF-2026-0040" in build_permanent_email_subject(doc)


def test_resolve_rebuilds_placeholder_client_subject():
    doc = _doc(email_subject="OFF-2026-0040-Client-3eme pilier")
    assert subject_uses_placeholder_client(doc["email_subject"])
    assert resolve_email_subject(doc) == "OFF-2026-00452-Dupont Jean -3e pilier"


def test_resolve_uses_stored_subject():
    doc = _doc(email_subject="OFF-2026-00452-Dupont Jean -3e pilier")
    assert resolve_email_subject(doc) == doc["email_subject"]
    # Même si nom change, l'objet stocké gagne
    doc["nom"] = "Martin"
    assert resolve_email_subject(doc) == "OFF-2026-00452-Dupont Jean -3e pilier"


def test_all_formatters_share_same_subject():
    """Les e-mails « pipeline métier » partagent l'objet permanent (sauf reçue / récap)."""
    doc = _doc(email_subject="OFF-2026-00452-Dupont Jean -3e pilier")
    subjects = [
        format_demande_offre_email(doc)[0],
        format_demande_incomplete_email(doc, comment="Manque pièce")[0],
        format_offre_signee_email(doc, signature={"date_signature": "2026-09-17"})[0],
        format_offre_modifiee_email(doc, changes=[{"field": "montant", "old": 1, "new": 2}])[0],
    ]
    assert len(set(subjects)) == 1
    assert subjects[0] == "OFF-2026-00452-Dupont Jean -3e pilier"


def test_offre_recue_uses_simplified_subject():
    doc = _doc(email_subject="OFF-2026-00452-Dupont Jean -3e pilier", agent_prenom="Cemile")
    subject, text, _ = format_offre_recue_email(doc, {"compagnie": "AXA"})
    assert subject == "Offre reçue – Jean Dupont – OFF-2026-00452"
    assert "Vous avez reçu une offre pour Jean Dupont." in text
    assert "AXA" not in text


def test_demande_recap_conseiller_subject():
    from email_service import format_demande_offre_recap_conseiller_email

    doc = _doc(agent_prenom="Cemile")
    subject, text, _ = format_demande_offre_recap_conseiller_email(doc)
    assert subject.startswith("Récapitulatif de votre demande d’offre")
    assert "Jean Dupont" in subject
    assert "OFF-2026-00452" in subject
    assert "Bonjour Cemile," in text


def test_normalize_erreurs():
    errs = normalize_erreurs_incomplete([
        {"code": "document_manquant", "detail": "CNI"},
        {"code": "inconnu", "detail": "x"},
    ])
    assert errs[0]["code"] == "document_manquant"
    assert errs[1]["code"] == "autre"


def test_field_changes():
    changes = build_field_changes({"montant_prime": 6000}, {"montant_prime": 7000})
    assert any(c["field"] == "montant_prime" for c in changes)


def test_gestion_categories_modifiee():
    ids = gestion_categorie_ids({"statut": STATUT_OFFRE_A_MODIFIER})
    assert "a_modifier" in ids
    assert DEMANDE_ORIGINE_ATTRIBUEE
    assert normalize_statut("Demande envoyée")
    assert isinstance(compute_erreur_stats([]), dict)