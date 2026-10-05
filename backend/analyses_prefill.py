"""Préremplissage d'une analyse depuis une fiche client LeoSoft.

Le moteur de calcul n'est pas dupliqué ici. On ne recopie que les champs
déjà présents sur AnalyseInput : identité, état civil, salaire, NPA/ville
(commune fiscale), conseiller, conjoint. L'adresse postale, le téléphone,
l'e-mail, le canton et le pays restent sur la fiche client : le modèle
d'analyse ne les stocke pas.
"""
from __future__ import annotations

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
