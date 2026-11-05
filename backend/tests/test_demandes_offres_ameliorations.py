import asyncio
from datetime import datetime, timedelta, timezone

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
from demandes_offres_relance_agent import process_relances_agent_21j, relance_agent_decision
from email_service import format_relance_agent_21j_email
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
    ordered = [r["id"] for r in sort_demandes(rows, "rdv_asc", today="2026-11-01")]
    assert ordered == ["c", "b", "a"]
    desc = [r["id"] for r in sort_demandes(rows, "rdv_desc", today="2026-11-01")]
    assert desc[0] == "b" and desc[-1] == "a"
    mixed = [
        {"id": "past", "date_prochain_rdv": "2026-10-01"},
        {"id": "soon", "date_prochain_rdv": "2026-11-06"},
        {"id": "later", "date_prochain_rdv": "2026-11-20"},
        {"id": "none", "date_prochain_rdv": ""},
    ]
    assert [r["id"] for r in sort_demandes(mixed, "rdv_asc", today="2026-11-05")] == ["soon", "later", "past", "none"]
    assert [r["id"] for r in sort_demandes(mixed, "rdv_desc", today="2026-11-05")] == ["later", "soon", "past", "none"]
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


def _transmis(days_ago, **extra):
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    doc = {
        "statut": "Offre reçue",
        "suivi_etape": "offre_transmise",
        "offre_transmise_agent_at": (now - timedelta(days=days_ago)).isoformat(),
    }
    doc.update(extra)
    return doc, now


def test_relance_agent_21_jours_selon_lavancement():
    fresh, now = _transmis(10)
    assert relance_agent_decision(fresh, now) == "wait"
    due, now = _transmis(21)
    assert relance_agent_decision(due, now) == "send"
    sent_client, now = _transmis(30, statut=STATUT_OFFRE_ENVOYEE_CLIENT, suivi_etape="offre_transmise")
    assert relance_agent_decision(sent_client, now) == "skip"
    signed, now = _transmis(40, statut=STATUT_OFFRE_SIGNEE)
    assert relance_agent_decision(signed, now) == "skip"
    refused, now = _transmis(40, statut=STATUT_OFFRE_REFUSEE)
    assert relance_agent_decision(refused, now) == "skip"
    cancelled, now = _transmis(40, statut="Demande annulée")
    assert relance_agent_decision(cancelled, now) == "skip"
    already, now = _transmis(30, relance_agent_21j_sent_at="2026-11-01T08:00:00+00:00")
    assert relance_agent_decision(already, now) == "skip"
    old = {"statut": "Offre reçue", "date_envoi": "2020-01-01T00:00:00+00:00"}
    assert relance_agent_decision(old, now) == "skip"
    failed, now = _transmis(21, relance_agent_21j_last_error="SMTP")
    assert relance_agent_decision(failed, now) == "retry"
    waiting_company, now = _transmis(21, suivi_etape="attente_compagnie")
    assert relance_agent_decision(waiting_company, now) == "send"


def test_email_relance_agent_reprend_le_texte_demande():
    subject, text, html = format_relance_agent_21j_email({
        "id": "d1",
        "numero": "OFF-2026-0042",
        "prenom": "Jean",
        "nom": "Dupont",
        "agent_prenom": "Ines",
    })
    assert subject == "LeoSoft – Rappel de mise à jour du statut de votre offre OFF-2026-0042"
    assert "Bonjour Ines," in text
    assert "Jean Dupont" in text
    assert "OFF-2026-0042" in text
    assert "Offre envoyée au client" in text
    assert "Offre signée" in text
    assert "Le service des Offres" in text
    assert "Consulter la demande dans LeoSoft" in html


class _Result:
    def __init__(self, count):
        self.modified_count = count


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, limit):
        return list(self.rows)[:limit]


class _Memory:
    def __init__(self, docs):
        self.docs = {doc["id"]: doc for doc in docs}

    def find(self, query, projection=None):
        rows = [
            doc for doc in self.docs.values()
            if doc.get("offre_transmise_agent_at") and not doc.get("relance_agent_21j_sent_at")
        ]
        return _Cursor(rows)

    async def find_one(self, query, projection=None):
        return None

    async def update_one(self, filt, update):
        doc = self.docs.get(filt.get("id"))
        if not doc or doc.get("relance_agent_21j_sent_at"):
            return _Result(0)
        if "$set" in update:
            doc.update(update["$set"])
        if "$push" in update and "historique" in update["$push"]:
            doc.setdefault("historique", []).append(update["$push"]["historique"])
        return _Result(1)


class _Db:
    def __init__(self, docs):
        self.demandes = _Memory(docs)
        self.users = _Memory([])

    def __getitem__(self, name):
        return self.demandes


def test_echec_denvoi_puis_nouvel_essai_sans_doublon(monkeypatch):
    calls = {"n": 0}

    async def fake_send(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, "SMTP indisponible"
        return True, ""

    monkeypatch.setattr("email_service.offres_email_enabled", lambda: True)
    monkeypatch.setattr("email_service.send_email_async", fake_send)
    now = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
    doc = {
        "id": "d-21",
        "numero": "OFF-2026-0021",
        "statut": "Offre reçue",
        "suivi_etape": "offre_transmise",
        "agent_email": "ines.agent@example.com",
        "agent_prenom": "Ines",
        "prenom": "Nadia",
        "nom": "Blanc",
        "offre_transmise_agent_at": (now - timedelta(days=21)).isoformat(),
    }
    db = _Db([doc])
    first = asyncio.run(process_relances_agent_21j(db, now=now))
    assert first["failed"] == 1
    assert not db.demandes.docs["d-21"].get("relance_agent_21j_sent_at")
    second = asyncio.run(process_relances_agent_21j(db, now=now))
    assert second["sent"] == 1
    assert db.demandes.docs["d-21"]["relance_agent_21j_sent_at"]
    assert any("Relance automatique envoyée" in item["action"] for item in db.demandes.docs["d-21"]["historique"])
    third = asyncio.run(process_relances_agent_21j(db, now=now))
    assert third["sent"] == 0
    assert calls["n"] == 2
