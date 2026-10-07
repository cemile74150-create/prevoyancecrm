"""Préremplissage d'une analyse depuis une fiche client LeoSoft.

Le moteur de calcul n'est pas dupliqué ici. On ne recopie que les champs
déjà présents sur AnalyseInput : identité, état civil, salaire, NPA/ville
(commune fiscale), conseiller, conjoint. L'adresse postale, le téléphone,
l'e-mail, le canton et le pays restent sur la fiche client : le modèle
d'analyse ne les stocke pas.
"""
from __future__ import annotations

import copy
import re
from typing import Optional


def to_iso_date(value) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    match = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})", raw)
    if not match:
        return ""
    day, month, year = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def civilite_from_client(client: dict) -> str:
    raw = " ".join(
        str(client.get(key) or "")
        for key in ("civilite", "sexe", "genre")
    ).lower()
    if any(token in raw for token in ("madame", "femme", "féminin", "feminin", "f")):
        if "homme" not in raw and "monsieur" not in raw:
            return "Madame"
    if raw.strip() in {"f", "femme"}:
        return "Madame"
    return "Monsieur"


def is_married(client: dict) -> bool:
    raw = str(client.get("etat_civil") or client.get("situation") or "").lower()
    return "mari" in raw or "partenariat" in raw


def _num(value) -> float:
    try:
        if value is None or value == "":
            return 0
        return float(value)
    except (TypeError, ValueError):
        return 0


def empty_analyse_input() -> dict:
    """Même forme que emptyAnalyseInput() du moteur (saisie vide)."""
    ages = [65, 64, 63, 62, 61, 60]

    def person(civilite: str) -> dict:
        return {
            "civilite": civilite,
            "nom": "",
            "prenom": "",
            "dateNaissance": "",
            "avsMensuel": 0,
            "avsAnnuel": None,
            "avsRentesAnticipees": [],
            "lpp": [{"age": age, "capital": 0, "rente": 0} for age in ages],
            "lppPctDeblocable": 100,
            "troisiemePilier": [],
            "rentePont": 0,
        }

    return {
        "villeRecherche": "",
        "taxLocationId": None,
        "taxGroupId": None,
        "etatCivil": "Personne vivant seule",
        "salaireClient1": 0,
        "salaireConjoint": 0,
        "fortune": 0,
        "autresRevenus": 0,
        "taxYear": 2025,
        "client1": person("Monsieur"),
        "conjoint": None,
        "conseillerNom": "",
        "renteVaudoise15": None,
        "renteVaudoise20": None,
        "ageRetraiteSouhaite": None,
        "ageFinActivite": None,
        "agePerceptionAvs": None,
        "ageRetraitLpp": None,
        "comparerAvecRenteLpp": False,
        "renteHypotheses": [],
        "libresPassages": [],
        "withdrawalScenarios": [],
    }


def apply_person(person: dict, client: dict) -> dict:
    person = dict(person)
    person["civilite"] = civilite_from_client(client)
    person["nom"] = (client.get("nom") or "").strip()
    person["prenom"] = (client.get("prenom") or "").strip()
    person["dateNaissance"] = to_iso_date(client.get("date_naissance"))
    return person


def _partner_from_label(client: dict, civilite: str) -> dict:
    """Nom du conjoint saisi en texte libre sur la fiche, sans 2e client."""
    base = empty_analyse_input()["client1"]
    base["civilite"] = civilite
    parts = [part for part in str(client.get("conjoint") or "").split() if part]
    if not parts:
        return base
    if len(parts) == 1:
        base["prenom"] = parts[0]
        base["nom"] = (client.get("nom") or "").strip()
        return base
    base["prenom"] = parts[0]
    base["nom"] = " ".join(parts[1:])
    return base


def prefill_from_clients(client: dict, spouse: Optional[dict] = None, conseiller_nom: str = "") -> dict:
    data = empty_analyse_input()
    data["client1"] = apply_person(data["client1"], client)
    data["salaireClient1"] = _num(client.get("salaire_annuel"))
    npa = str(client.get("npa") or "").strip()
    ville = str(client.get("ville") or "").strip()
    data["villeRecherche"] = " ".join(part for part in (npa, ville) if part)
    data["conseillerNom"] = (client.get("conseiller") or conseiller_nom or "").strip()
    married = is_married(client) or spouse is not None
    if married:
        data["etatCivil"] = "Marié(e)"
        civilite = "Madame" if data["client1"]["civilite"] == "Monsieur" else "Monsieur"
        if spouse:
            base = empty_analyse_input()["client1"]
            base["civilite"] = civilite
            base = apply_person(base, spouse)
            data["salaireConjoint"] = _num(spouse.get("salaire_annuel"))
            data["conjoint"] = base
        else:
            data["conjoint"] = _partner_from_label(client, civilite)
    return data


# Séparateur des libellés de frise (TimelineService : « LPP – Prénom – Capital »).
_TIMELINE_SEP = " – "


def _clean_prenom(value) -> str:
    return str(value or "").strip()


def apply_crm_display_prenoms(
    data: Optional[dict],
    client: Optional[dict] = None,
    spouse: Optional[dict] = None,
) -> dict:
    """Prénoms affichés pris sur les fiches CRM courantes.

    Seuls ``client1.prenom`` et ``conjoint.prenom`` peuvent changer.
    Un prénom CRM vide laisse la valeur déjà portée par l'analyse
    (le moteur retombe ensuite sur « Assuré 1/2 »). Aucun conjoint
    n'est créé : un bloc absent ne doit pas modifier le foyer calculé.
    """
    if not isinstance(data, dict):
        data = {}
    out = copy.deepcopy(data)
    if isinstance(out.get("client1"), dict) and client:
        prenom = _clean_prenom(client.get("prenom"))
        if prenom:
            out["client1"]["prenom"] = prenom
    if isinstance(out.get("conjoint"), dict) and spouse:
        prenom = _clean_prenom(spouse.get("prenom"))
        if prenom:
            out["conjoint"]["prenom"] = prenom
    return out


def _display_who(person, fallback: str) -> str:
    if not isinstance(person, dict):
        return fallback
    return _clean_prenom(person.get("prenom")) or fallback


def _rewrite_timeline_label(event: dict, who_by_person: dict) -> None:
    person = event.get("person")
    label = event.get("label")
    who = who_by_person.get(person)
    if not who or not isinstance(label, str):
        return
    parts = label.split(_TIMELINE_SEP)
    if len(parts) < 2:
        return
    parts[1] = who
    event["label"] = _TIMELINE_SEP.join(parts)


def relabel_timeline_display_prenoms(results: Optional[dict], data: dict) -> Optional[dict]:
    """Aligne les libellés de frise déjà stockés sur les prénoms courants.

    Années, montants et destin LPP (Capital / Rente) restent ceux du calcul.
    """
    if not isinstance(results, dict):
        return results
    out = copy.deepcopy(results)
    timeline = out.get("timeline")
    if not isinstance(timeline, dict):
        return out
    who = {
        "client1": _display_who((data or {}).get("client1"), "Assuré 1"),
        "conjoint": _display_who((data or {}).get("conjoint"), "Assuré 2"),
    }

    def rewrite_list(events) -> None:
        if not isinstance(events, list):
            return
        for event in events:
            if isinstance(event, dict):
                _rewrite_timeline_label(event, who)

    rewrite_list(timeline.get("events"))
    by_year = timeline.get("byYear")
    if isinstance(by_year, dict):
        for events in by_year.values():
            rewrite_list(events)
    return out


def refresh_report_display_prenoms(
    record: Optional[dict],
    client: Optional[dict] = None,
    spouse: Optional[dict] = None,
) -> dict:
    """Dossier transmis au moteur : prénoms CRM, frise alignée, calcul inchangé."""
    out = copy.deepcopy(record) if isinstance(record, dict) else {}
    data = apply_crm_display_prenoms(out.get("input") or {}, client, spouse)
    out["input"] = data
    if out.get("results") is not None:
        out["results"] = relabel_timeline_display_prenoms(out.get("results"), data)
    return out
