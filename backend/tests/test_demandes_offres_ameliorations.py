from demandes_offres_ameliorations import (
    count_urgences_agent,
    enregistrer_suivi,
    etape_affichee,
    etapes_visibles,
    fiche_stats_agent,
    filter_rdv_a_venir,
    grant_agent_bonus,
    quota_block_message,
    should_send_offres_completes_email,
    sort_demandes,
    validate_urgence_for_send,
)
from demandes_offres_3p import (
    STATUT_BROUILLON,
    STATUT_ENVOYEE,
    STATUT_OFFRE_ENVOYEE_CLIENT,
    STATUT_OFFRE_RECUE,
    STATUT_OFFRE_REFUSEE,
    STATUT_OFFRE_SIGNEE,
)


def test_urgence_exige_un_motif():
    assert validate_urgence_for_send({"urgente": False}) is None
    assert validate_urgence_for_send({"urgente": True, "urgence_motif": "  "})
    assert validate_urgence_for_send({"urgente": True, "urgence_motif": "RDV demain"}) is None


def test_quota_desactive_par_defaut_et_message_si_atteint():
    assert quota_block_message({"quota_actif": False, "max_par_agent": 1}, 9) is None
    msg = quota_block_message({"quota_actif": True, "max_par_agent": 2, "periode": "mois"}, 2)
    assert msg and "Quota" in msg
    assert quota_block_message({"quota_actif": True, "max_par_agent": 2, "periode": "mois"}, 1) is None


def test_urgences_excluent_brouillon_et_compter_la_periode():
    rows = [
        {"agent_label": "Jean Dupont", "urgente": True, "statut": STATUT_ENVOYEE, "urgence_at": "2026-11-02T10:00:00"},
        {"agent_label": "Jean Dupont", "urgente": True, "statut": STATUT_BROUILLON, "urgence_at": "2026-11-03T10:00:00"},
        {"agent_label": "Jean Dupont", "urgente": True, "statut": "Demande annulée", "urgence_at": "2026-11-03T10:00:00"},
        {"agent_label": "Jean Dupont", "urgente": True, "statut": STATUT_ENVOYEE, "urgence_at": "2026-10-01T10:00:00"},
        {"agent_label": "Autre", "urgente": True, "statut": STATUT_ENVOYEE, "urgence_at": "2026-11-02T10:00:00"},
    ]
    assert count_urgences_agent(rows, "Jean Dupont", since_iso="2026-11-01T00:00:00") == 1


def test_tri_rdv_place_les_dates_vides_a_la_fin():
    rows = [
        {"id": "b", "date_prochain_rdv": "2026-12-01", "created_at": "2026-01-01"},
        {"id": "a", "date_prochain_rdv": "", "created_at": "2026-01-02"},
        {"id": "c", "date_prochain_rdv": "2026-11-10", "heure_rdv": "09:00", "created_at": "2026-01-03"},
    ]
    ordered = [r["id"] for r in sort_demandes(rows, "rdv_asc")]
    assert ordered == ["c", "b", "a"]
    desc = [r["id"] for r in sort_demandes(rows, "rdv_desc")]
    assert desc[0] == "b" and desc[-1] == "a"
    upcoming = filter_rdv_a_venir(rows, True, today="2026-11-15")
    assert [r["id"] for r in upcoming] == ["b"]


def test_stats_fiche_reprennent_les_compteurs_agent():
    rows = [
        {"agent_label": "Jean Dupont", "statut": STATUT_ENVOYEE, "created_at": "2026-01-01"},
        {"agent_label": "Jean Dupont", "statut": STATUT_BROUILLON, "created_at": "2026-01-02"},
        {"agent_label": "Jean Dupont", "statut": "Demande annulée", "created_at": "2026-01-03"},
        {"agent_label": "Jean Dupont", "statut": STATUT_OFFRE_ENVOYEE_CLIENT, "created_at": "2026-01-04"},
        {"agent_label": "Jean Dupont", "statut": STATUT_OFFRE_SIGNEE, "created_at": "2026-01-05"},
        {"agent_label": "Jean Dupont", "statut": STATUT_OFFRE_SIGNEE, "created_at": "2026-01-06"},
        {"agent_label": "Jean Dupont", "statut": STATUT_OFFRE_REFUSEE, "created_at": "2026-01-07"},
    ]
    stats = fiche_stats_agent(rows, "Jean Dupont")
    assert stats["nb_demandes"] == 5
    assert stats["nb_brouillons"] == 1
    assert stats["offres_signees"] == 2
    assert stats["offres_envoyees"] == 4
    assert stats["taux_signature"] == round(2 / 4 * 100, 1)
    assert stats["taux_signature_denominateur"] == "offres_envoyees"
    assert "transmis au client" in stats["taux_signature_definition"]


def test_suivi_relance_ne_quitte_pas_l_attente_compagnie_et_signature_bloquee():
    doc = {"statut": STATUT_ENVOYEE, "suivi_etape": "attente_compagnie", "suivi_evenements": []}
    out = enregistrer_suivi(doc, "relance", auteur="Léa", compagnie="AXA", commentaire="Relance")
    assert out["suivi_etape"] == "attente_compagnie"
    assert out["dernier_evenement"]["etape"] == "relance"
    assert out["dernier_evenement"]["compagnie"] == "AXA"
    try:
        enregistrer_suivi(doc, "signee", auteur="Léa")
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert etape_affichee({"statut": STATUT_OFFRE_SIGNEE, "suivi_etape": "en_cours"}) == "signee"
    steps = etapes_visibles(out)
    by_id = {step["id"]: step for step in steps}
    assert [step["id"] for step in steps] == [
        "en_attente", "en_cours", "attente_compagnie", "relance",
        "offre_transmise", "envoyee_client", "signee",
    ]
    assert by_id["attente_compagnie"]["current"] is True
    assert by_id["relance"]["reached"] is True
    assert by_id["relance"]["current"] is False
    assert by_id["relance"]["kind"] == "evenement"
    assert out["dernier_evenement"]["etape_precedente"] == "attente_compagnie"
    assert out["dernier_evenement"]["etape_precedente_label"] == "En attente de la compagnie"


def test_etape_choisie_par_le_gestionnaire_reste_visible():
    assert etape_affichee({"statut": STATUT_ENVOYEE, "suivi_etape": "en_cours"}) == "en_cours"
    assert etape_affichee({"statut": STATUT_OFFRE_RECUE, "suivi_etape": "attente_compagnie"}) == "attente_compagnie"
    assert etape_affichee({"statut": STATUT_OFFRE_RECUE}) == "offre_transmise"
    assert etape_affichee({"statut": STATUT_OFFRE_ENVOYEE_CLIENT, "suivi_etape": "en_cours"}) == "envoyee_client"
    assert etape_affichee({"statut": "Offre non signée", "suivi_etape": "en_cours"}) == "non_signee"
    assert etape_affichee({"statut": STATUT_ENVOYEE, "suivi_etape": "relance"}) == "attente_compagnie"


def test_quota_exception_releve_le_plafond_de_l_agent():
    settings = {"quota_actif": True, "max_par_agent": 1, "periode": "mois", "bonus_par_agent": []}
    assert quota_block_message(settings, 1, "Jean Dupont")
    bonus = grant_agent_bonus(settings, "Jean Dupont")
    settings = {**settings, "bonus_par_agent": bonus}
    assert quota_block_message(settings, 1, "Jean Dupont") is None
    assert quota_block_message(settings, 2, "Jean Dupont")
    expired = {**settings, "bonus_par_agent": [{"agent": "Jean Dupont", "extra": 5, "periode": "2020-01"}]}
    assert quota_block_message(expired, 1, "Jean Dupont")


def test_ancien_dossier_signe_affiche_les_sept_etapes_sans_relance():
    steps = etapes_visibles({"statut": STATUT_OFFRE_SIGNEE, "historique": [{"action": "Offre signée", "at": "2024-03-01T09:15:00"}]})
    assert len(steps) == 7
    assert steps[-1]["id"] == "signee" and steps[-1]["current"] is True
    assert all(step["reached"] for step in steps if step["id"] != "relance")
    assert steps[3]["id"] == "relance" and steps[3]["reached"] is False
    assert steps[2]["id"] == "attente_compagnie" and steps[2]["reached"] is True


def test_offres_completes_ne_renvoie_pas_le_mail_deja_envoye():
    assert should_send_offres_completes_email({"offre_recue_email_sent": True}, "") is False
    assert should_send_offres_completes_email({"offre_recue_email_sent": True}, "Merci de comparer") is True
    assert should_send_offres_completes_email({}, "") is True
