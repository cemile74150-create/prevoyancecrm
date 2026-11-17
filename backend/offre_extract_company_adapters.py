"""
Phase 4 — adaptateurs multi-compagnies / multi-formats PDF.

Architecture :
  1. Détection marque / assureur (synonymes FR/DE)
  2. Normalisation des libellés section (synonymes → clés canoniques)
  3. Extraction structurée générique (offre_extract_structured) + hints adaptateur
  4. Mapping formulaire inchangé (offre_pdf_form_map) — indépendant de la compagnie

Les adaptateurs n'écrivent jamais dans les JSON GF ; ils enrichissent le texte
normalisé / les indices avant le pipeline commun. Golden ELVIA reste la référence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Synonymes de sections / libellés (formats PDF variables)
# ---------------------------------------------------------------------------

SECTION_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "preneur": (
        "preneur d'assurance",
        "preneur dassurance",
        "versicherungsnehmer",
        "contratant",
        "cocontractant",
        "policyholder",
        "titulaire de la police",
        "personne assurée",
    ),
    "prime_unique": (
        "prime unique",
        "einmalprämie",
        "einmalpraemie",
        "single premium",
        "versement unique",
    ),
    "rente_mensuelle": (
        "rente mensuelle garantie",
        "rente mensuelle",
        "fraction mensuelle",
        "versement annuel, payable par fraction mensuelle",
        "monatliche rente",
    ),
    "detenteur": (
        "détenteur",
        "detenteur",
        "fahrzeughalter",
        "halter",
        "propriétaire du véhicule",
    ),
    "vehicule": (
        "véhicule assuré",
        "vehicule assure",
        "fahrzeug",
        "objet assuré",
        "véhicule",
    ),
    "prime_annuelle": (
        "prime annuelle",
        "jahresprämie",
        "prime annuelle avec redevances",
        "prime totale",
        "prämie total",
        "montant de la prime",
    ),
    "police": (
        "police no",
        "police n°",
        "n° de police",
        "policenr",
        "vertragsnummer",
        "numéro de contrat",
    ),
    "plaque": (
        "plaque de contrôle",
        "numéro de plaque",
        "kennzeichen",
        "immatriculation",
    ),
    "garage": (
        "place de garage à disposition",
        "garage",
        "einstellplatz",
        "stationnement",
    ),
    "casco": (
        "casco complète",
        "casco collision",
        "vollkasko",
        "casco intégrale",
    ),
    "rc": (
        "responsabilité civile",
        "haftpflicht",
        "rc véhicule",
    ),
}

COMPANY_ALIASES: Dict[str, Tuple[str, ...]] = {
    "ELVIA": ("elvia",),
    "Allianz": ("allianz", "allianz suisse"),
    "Vaudoise": ("vaudoise", "vaudoise assurances"),
    "Zurich": ("zurich", "zurich assurance", "zurich versicherungen"),
    "Mobilière": ("mobilière", "mobiliere", "die mobiliar", "la mobilière"),
    "AXA": ("axa", "axa switzerland", "axa winterthur"),
    "Helvetia": ("helvetia",),
    "Generali": ("generali",),
    "Baloise": ("baloise", "basler"),
}


@dataclass
class CompanyAdapter:
    """Adaptateur léger : détection + normalisation de libellés."""

    company_id: str
    aliases: Tuple[str, ...]
    label_rewrites: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def matches(self, text: str, filename: str = "") -> float:
        blob = f"{filename}\n{text}".casefold()
        score = 0.0
        for alias in self.aliases:
            if alias.casefold() in blob:
                score = max(score, 0.85 if alias.casefold() == self.company_id.casefold() else 0.7)
        return score

    def normalize_text(self, text: str) -> str:
        """Réécrit les synonymes locaux vers des libellés reconnus par le parseur générique."""
        out = text or ""
        for src, dst in self.label_rewrites.items():
            out = re.sub(re.escape(src), dst, out, flags=re.I)
        return out


# Adaptateurs concrets (formats types CH) — extensibles sans toucher au mapping GF.
ADAPTERS: List[CompanyAdapter] = [
    CompanyAdapter(
        company_id="ELVIA",
        aliases=COMPANY_ALIASES["ELVIA"] + COMPANY_ALIASES["Allianz"],
        label_rewrites={
            "PRIME ANNUELLE AVEC REDEVANCES LÉGALES ET SUPPLÉMENTS": "PRIME ANNUELLE AVEC REDEVANCES LÉGALES ET SUPPLÉMENTS",
        },
        notes=["Golden test : multi-véhicules plaques interchangeables"],
    ),
    CompanyAdapter(
        company_id="Mobilière",
        aliases=COMPANY_ALIASES["Mobilière"],
        label_rewrites={
            "Numéro de contrat": "Police no.",
            "Preneur / titulaire": "PRENEUR D'ASSURANCE",
            "Kennzeichen": "Plaque",
            "Jahresprämie total": "PRIME ANNUELLE",
            "Einstellplatz vorhanden: Ja": "Place de garage à disposition: Oui",
            "Einstellplatz vorhanden: Nein": "Place de garage à disposition: Non",
        },
    ),
    CompanyAdapter(
        company_id="Vaudoise",
        aliases=COMPANY_ALIASES["Vaudoise"],
        label_rewrites={
            "N° de police": "Police no.",
            "Assuré principal": "PRENEUR D'ASSURANCE",
            "Cocontractant": "PRENEUR D'ASSURANCE",
            "Prénom, nom": "Prénom et nom",
            "Immatriculation": "Plaque",
            "Prime totale annuelle": "PRIME ANNUELLE",
            "Garage / parking: oui": "Place de garage à disposition: Oui",
            "payable par fraction mensuelle de": "rente mensuelle garantie",
        },
        notes=["Auto + prévoyance Serenity (prime unique / fraction mensuelle)"],
    ),
    CompanyAdapter(
        company_id="AXA",
        aliases=COMPANY_ALIASES["AXA"],
        label_rewrites={
            "Vertragsnummer": "Police no.",
            "Versicherungsnehmer": "PRENEUR D'ASSURANCE",
            "Preneur dassurance": "PRENEUR D'ASSURANCE",
            "Fahrzeug": "Véhicule assuré",
            "Kontrollschild": "Plaque",
            "Jahresprämie": "PRIME ANNUELLE",
            "Garagenplatz: Ja": "Place de garage à disposition: Oui",
            "Geburtsdatum": "Date de naissance",
            "Police de prévoyance": "Police de prévoyance",
            "Prévoyance liée 3a": "Prévoyance liée 3a",
        },
        notes=["Auto + polices / valeurs 3a Dynamix"],
    ),
    CompanyAdapter(
        company_id="Zurich",
        aliases=COMPANY_ALIASES["Zurich"],
        label_rewrites={
            "Policy number": "Police no.",
            "Policyholder": "PRENEUR D'ASSURANCE",
            "Registration plate": "Plaque",
            "Annual premium": "PRIME ANNUELLE",
            "Garage available: Yes": "Place de garage à disposition: Oui",
            "3rd pillar": "pilier 3",
            "pillar 3a": "pilier 3a",
            "pillar 3b": "pilier 3b",
        },
        notes=["Auto + 3P ; PDF scannés sans OCR → champs vides"],
    ),
]


def detect_company_adapter(text: str, filename: str = "") -> Optional[CompanyAdapter]:
    best: Optional[CompanyAdapter] = None
    best_score = 0.0
    for adapter in ADAPTERS:
        score = adapter.matches(text, filename)
        # ELVIA prioritaire si présent (marque commerciale vs porteur Allianz)
        if "elvia" in f"{filename}\n{text}".casefold() and adapter.company_id == "ELVIA":
            score = max(score, 0.95)
        if score > best_score:
            best_score = score
            best = adapter
    return best if best_score >= 0.55 else None


def prepare_text_for_extraction(text: str, filename: str = "") -> Tuple[str, Optional[str], List[str]]:
    """
    Point d'entrée Phase 4 : normalise le texte selon la compagnie détectée.
    Retourne (texte_normalisé, company_id, notes).
    """
    adapter = detect_company_adapter(text, filename)
    if not adapter:
        return text or "", None, ["Aucun adaptateur compagnie — pipeline générique seul."]
    normalized = adapter.normalize_text(text or "")
    notes = list(adapter.notes) + [f"Adaptateur {adapter.company_id}"]
    return normalized, adapter.company_id, notes


def expand_section_pattern(canonical_key: str) -> str:
    """Construit un motif regex OR à partir des synonymes d'une section."""
    syns = SECTION_SYNONYMS.get(canonical_key) or (canonical_key,)
    parts = [re.escape(s) for s in syns]
    return "(?:" + "|".join(parts) + ")"


def score_extraction_coverage(
    extracted: Dict[str, Any],
    *,
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Mesure filled / missing / incorrect pour un jeu de champs attendus (Phase 4).
    expected: {clé_plate: valeur_attendue}
    """
    ok: List[str] = []
    missing: List[str] = []
    incorrect: List[str] = []

    def _norm(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.4g}"
        return re.sub(r"\s+", " ", str(v)).strip().casefold()

    for key, exp in (expected or {}).items():
        got = extracted.get(key)
        if got in (None, "", []):
            # Chercher dans form_payload si préfixe input_
            missing.append(key)
            continue
        if _norm(got) == _norm(exp) or (_norm(exp) and _norm(exp) in _norm(got)):
            ok.append(key)
        else:
            incorrect.append(key)
    total = len(expected) or 1
    return {
        "ok": ok,
        "missing": missing,
        "incorrect": incorrect,
        "filled_ratio": round(len(ok) / total, 3),
        "counts": {"ok": len(ok), "missing": len(missing), "incorrect": len(incorrect)},
    }
