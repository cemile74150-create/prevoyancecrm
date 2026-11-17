"""
Extraction structurée multi-branches pour PDF d'offres / polices.

Phase 1 : modèle générique (branche, assureur, police, preneur, objets[],
primes globales, garanties, meta trouvé/à vérifier/non trouvé).
ELVIA auto multi-véhicules = premier golden test ; architecture non limitée
à une compagnie.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from offre_extract import (
    NON_INDIQUE,
    _compact_money_token,
    _find_compagnie,
    _find_offre_numero,
    _is_plausible_person_name,
    _norm,
    _normalize_date,
    _parse_axa_inline_preneur,
    _parse_axa_nom_prenom_near_dob,
    _parse_zurich_personne_assuree_line,
    _split_identity_parts,
    _strip_identity_noise,
)

STATUS_FOUND = "found"
STATUS_TO_VERIFY = "to_verify"
STATUS_NOT_FOUND = "not_found"

# Contacts typiques des centres sinistre / service assureur (à ignorer).
_INSURER_PHONE_BLOCKLIST = (
    "0800 666 222",
    "0800 055 088",
    "+41 43 311 99 90",
    "043 311 99 90",
)
_INSURER_EMAIL_BLOCKLIST = (
    "contact@elvia.ch",
    "sinistre@",
)
_INSURER_CITY_HINTS = (
    "zurich",
    "zürich",
    "wallisellen",
    "basel",
    "genève",
    "geneve",
)


def _field(
    value: Any = None,
    *,
    page: Optional[int] = None,
    confidence: float = 0.0,
    status: str = STATUS_NOT_FOUND,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    if value in (None, "", NON_INDIQUE):
        return {
            "value": None,
            "page": page,
            "confidence": 0.0,
            "status": STATUS_NOT_FOUND,
            "source": source,
        }
    return {
        "value": value,
        "page": page,
        "confidence": max(0.0, min(1.0, confidence)),
        "status": status,
        "source": source,
    }


def _value_or_none(field: Optional[Dict[str, Any]]) -> Any:
    if not isinstance(field, dict):
        return None
    if field.get("status") == STATUS_TO_VERIFY:
        # Incertitude : ne pas écrire la valeur dans le payload de préremplissage.
        return None
    if field.get("status") != STATUS_FOUND:
        return None
    return field.get("value")


def empty_structured_extraction() -> Dict[str, Any]:
    return {
        "branche": _field(),
        "marque": _field(),  # marque commerciale (ELVIA, …)
        "assureur": _field(),  # porteur du risque (Allianz, …)
        "police": {
            "numero": _field(),
            "numero_client": _field(),
            "date_debut": _field(),
            "date_fin": _field(),
            "motif": _field(),
        },
        "preneur": {
            "civilite": _field(),
            "prenom": _field(),
            "nom": _field(),
            "adresse": _field(),
            "npa": _field(),
            "ville": _field(),
            "pays": _field(),
            "date_naissance": _field(),
            "nationalite": _field(),
            "permis_sejour": _field(),
            "telephone": _field(),
            "email": _field(),
            "date_permis_conduire": _field(),
        },
        "objets": [],
        "primes": {
            "annuelle_brute": _field(),
            "annuelle_avec_taxes": _field(),
            "globale": _field(),  # une seule prime à préremplir
            "periodicite": _field(),
            "detail_risques": [],
        },
        "garanties": [],
        "meta": {
            "pages": None,
            "page_refs": [],
            "filename": "",
            "form_type_suggere": None,
            "form_type_candidates": [],
            "form_type_needs_confirm": False,
            "gf_subtype_suggere": None,
            "document_type": None,
            "document_type_status": STATUS_NOT_FOUND,
            "ocr_used": False,
            "visual_tables_limited": False,
            "notes": [],
        },
        "audit": {
            "fields": [],
            "raw_text_len": 0,
        },
    }


def _page_of(text: str, pos: int) -> Optional[int]:
    if pos < 0:
        return None
    head = text[:pos]
    pages = re.findall(r"Page\s+(\d+)\s+sur\s+(\d+)", head, re.I)
    if pages:
        return int(pages[-1][0])
    return None


def _pilier3_signals(text: str, filename: str = "") -> bool:
    """Signaux 3e pilier / prévoyance (texte + nom de fichier)."""
    hay = _norm(f"{filename}\n{text}")
    return bool(
        re.search(
            r"\b3\s*[ab]\b|"
            r"\b3[pab]\b|"
            r"pilier\s*3|"
            r"3e?\s*pilier|"
            r"pr[ée]voyance(?:\s+li[ée]e)?|"
            r"säule\s*3|"
            r"serenity\s+benefit|"
            r"dynamix\s*3|"
            r"cocontractant|"
            r"versements?\s+r[ée]guliers?\s+garantis|"
            r"police\s+de\s+pr[ée]voyance|"
            r"prime\s+unique|"
            r"feuille\s+des\s+prestations|"
            r"assurance\s+en\s+cas\s+de\s+vie|"
            r"somme\s+d['’]?assurance|"
            r"valeurs?\s+de\s+rachat|"
            r"capitalisation",
            hay,
        )
    )


def detect_document_type(text: str, filename: str = "") -> Dict[str, Any]:
    """
    Distingue offre | police | décompte | document valeurs de rachat.
    Ne déduit jamais une prime : le type guide seulement le préremplissage.
    """
    hay = _norm(f"{filename}\n{text}")
    fn = _norm(filename or "")
    scores: Dict[str, float] = {
        "offre": 0.0,
        "police": 0.0,
        "decompte": 0.0,
        "valeurs_rachat": 0.0,
    }
    if re.search(r"\boffre\b|proposition\s+d['’]?assurance|devis\b|simulation", hay):
        scores["offre"] += 0.85
    if re.search(r"\boffre\b", fn):
        scores["offre"] += 0.35  # nom de fichier « Offre … » prioritaire
    if re.search(
        r"feuille\s+des\s+prestations|valeurs?\s+de\s+rachat|"
        r"tableau\s+des\s+prestations|"
        r"rachat\s+partiel|valeur\s+de\s+transformation",
        hay,
    ):
        scores["valeurs_rachat"] += 0.95
    # « somme d'assurance » seul (hors offre commerciale) → indices valeurs
    if re.search(r"somme\s+d['’]?assurance|feuille\s+des\s+prestations", hay) and scores["offre"] < 0.85:
        scores["valeurs_rachat"] += 0.7
    if re.search(
        r"\bpolice\b|contrat\s+d['’]?assurance|attestation\s+d['’]?assurance|"
        r"conditions\s+particuli[eè]res|valable\s+d[eè]s\s+le",
        hay,
    ):
        scores["police"] += 0.7
    if re.search(
        r"d[ée]compte(?:\s+de\s+primes?)?|facture\s+de\s+primes?|"
        r"avis\s+d['’]?[ée]ch[ée]ance|prime\s+[àa]\s+payer",
        hay,
    ):
        scores["decompte"] += 0.9

    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])
    if best_score < 0.55:
        return _field(status=STATUS_NOT_FOUND)
    # Feuille des prestations Zurich = valeurs (pas une offre commerciale).
    status = STATUS_FOUND if best_score >= 0.8 else STATUS_TO_VERIFY
    return _field(best_type, confidence=min(0.99, best_score), status=status, source="document_type")


def _detect_branche(text: str, filename: str = "") -> Dict[str, Any]:
    """
    Détection générique de branche.
    Priorité prévoyance/3P quand les signaux sont clairs ; RC/casco seuls
    ne forcent le véhicule que hors contexte 3P (évite Serenity « RC »).
    """
    flat = _norm(text)
    pilier3 = _pilier3_signals(text, filename)

    vehicle_strong = bool(
        re.search(
            r"assurance\s+v[ée]hicules?\s+[àa]\s+moteur|"
            r"v[ée]hicules?\s+assur[ée]s|"
            r"fahrzeugversicherung|motorfahrzeug|"
            r"casco|kasko|"
            r"plaque\s+de\s+contr[ôo]le|"
            r"kennzeichen|"
            r"plaques?\s+interchangeables",
            flat,
        )
    )
    vehicle_rc_loose = bool(re.search(r"responsabilit[ée]\s+civile|haftpflicht", flat))

    if vehicle_strong or (vehicle_rc_loose and not pilier3):
        multi = bool(
            re.search(
                r"plaques?\s+interchangeables|"
                r"wechselkennzeichen|"
                r"v[ée]hicules?\s+assur[ée]s.{0,80},",
                flat,
                re.S,
            )
        ) or len(re.findall(r"v[ée]hicule\s+assur[ée]\b|fahrzeug\s+\d+", flat)) >= 2
        return _field(
            "vehicule_plaques_interchangeables" if multi else "vehicule",
            confidence=0.92 if multi else 0.85,
            status=STATUS_FOUND,
            source="keyword",
        )
    if pilier3:
        return _field("pilier3", confidence=0.85, status=STATUS_FOUND, source="keyword")
    if re.search(r"\bm[ée]nage\b|\brc\s+priv|hausrat", flat):
        return _field("menage_rc", confidence=0.65, status=STATUS_TO_VERIFY, source="keyword")
    return _field()


def _detect_marque(text: str) -> Dict[str, Any]:
    flat = _norm(text)
    for label, pattern in (
        ("ELVIA", r"\belvia\b"),
        ("Allianz", r"\ballianz\b"),
        ("Vaudoise", r"\bvaudoise\b"),
        ("Zurich", r"\bzurich\b"),
        ("Helvetia", r"\bhelvetia\b"),
        ("Mobilière", r"mobili[eè]re"),
        ("AXA", r"\baxa\b"),
        ("Generali", r"\bgenerali\b"),
        ("Baloise", r"\bbaloise\b"),
    ):
        m = re.search(pattern, flat, re.I)
        if m:
            # ELVIA apparaît comme marque ; Allianz comme porteur — priorité ELVIA si présent.
            conf = 0.95 if label == "ELVIA" else 0.8
            return _field(label, page=_page_of(text, m.start()), confidence=conf, status=STATUS_FOUND, source="brand")
    return _field()


def _set_preneur_name(
    out: Dict[str, Any],
    prenom: Optional[str],
    nom: Optional[str],
    *,
    page: Optional[int],
    confidence: float,
    source: str,
    min_confidence: float = 0.85,
) -> None:
    """N'écrit l'identité que si plausible ; sinon to_verify/vide (jamais faux)."""
    if not _is_plausible_person_name(prenom, nom):
        return
    status = STATUS_FOUND if confidence >= min_confidence else STATUS_TO_VERIFY
    if status == STATUS_TO_VERIFY:
        # Incertitude : ne pas préremplir (flat ignore to_verify).
        out["prenom"] = _field(prenom, page=page, confidence=confidence, status=STATUS_TO_VERIFY, source=source)
        out["nom"] = _field(nom, page=page, confidence=confidence, status=STATUS_TO_VERIFY, source=source)
        return
    if out["prenom"]["status"] == STATUS_FOUND and out["nom"]["status"] == STATUS_FOUND:
        return
    out["prenom"] = _field(prenom, page=page, confidence=confidence, status=STATUS_FOUND, source=source)
    out["nom"] = _field(nom, page=page, confidence=confidence, status=STATUS_FOUND, source=source)


def _extract_preneur_block(text: str) -> Dict[str, Any]:
    """Bloc preneur prioritaire (pas l'en-tête assureur)."""
    out = empty_structured_extraction()["preneur"]
    text = (text or "").split("----- OCR_TABLE_APPENDIX -----", 1)[0]

    # AXA inline (prioritaire) : « Preneur d'assurance VANESSA CHABLOZ (28.11.1967) »
    axa_p, axa_n, axa_dob = _parse_axa_inline_preneur(text)
    if axa_p and axa_n:
        _set_preneur_name(out, axa_p, axa_n, page=_page_of(text, 0), confidence=0.92, source="axa_inline")
        if axa_dob and out["date_naissance"]["status"] != STATUS_FOUND:
            out["date_naissance"] = _field(
                axa_dob, page=_page_of(text, 0), confidence=0.9, status=STATUS_FOUND, source="axa_inline_dob"
            )

    # Zurich / feuille des prestations OCR : ligne MAJUSCULES sous PERSONNE ASSUREE
    z_prenom, z_nom = _parse_zurich_personne_assuree_line(text)
    if z_prenom and z_nom:
        _set_preneur_name(out, z_prenom, z_nom, page=_page_of(text, 0), confidence=0.9, source="personne_assuree")

    axa_near = _parse_axa_nom_prenom_near_dob(text)
    if axa_near[0] and axa_near[1]:
        _set_preneur_name(
            out, axa_near[0], axa_near[1], page=_page_of(text, 0), confidence=0.88, source="axa_nom_prenom_dob"
        )

    m_dob_zurich = re.search(
        r"DATE\s+DE\s+NAISSANCE\s*[:：]\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
        text,
        re.I,
    )
    if m_dob_zurich:
        dob = _normalize_date(m_dob_zurich.group(1))
        if dob:
            out["date_naissance"] = _field(
                dob,
                page=_page_of(text, m_dob_zurich.start()),
                confidence=0.95,
                status=STATUS_FOUND,
                source="date_naissance",
            )

    # Bloc explicite PRENEUR D'ASSURANCE … (jusqu'au prochain titre majuscule long)
    m = re.search(
        r"PRENEUR\s+D['’]?ASSURANCE\s+([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][^\n]{2,80})\s+"
        r"([A-Z0-9][^\n,]{3,60}),\s*(\d{4})\s+([A-Za-zÀ-ÿ' \-]{2,40})",
        text,
        re.I,
    )
    if m:
        full_name = re.sub(r"\s+", " ", m.group(1)).strip()
        _civ, prenom_b, nom_b = _split_identity_parts(full_name)
        if prenom_b and nom_b:
            _set_preneur_name(
                out,
                prenom_b.title() if prenom_b.isupper() else prenom_b,
                nom_b.title() if nom_b.isupper() else nom_b,
                page=_page_of(text, m.start()),
                confidence=0.9,
                source="preneur_block",
            )
        addr = re.sub(r"\s+", " ", m.group(2)).strip()
        # Éviter N° de police collé
        if not re.search(r"police|client|v[ée]hicule", addr, re.I):
            out["adresse"] = _field(addr.title() if addr.isupper() else addr, page=_page_of(text, m.start()), confidence=0.88, status=STATUS_FOUND, source="preneur_block")
        out["npa"] = _field(m.group(3), page=_page_of(text, m.start()), confidence=0.9, status=STATUS_FOUND, source="preneur_block")
        ville = m.group(4).strip()
        out["ville"] = _field(ville.title() if ville.isupper() else ville, page=_page_of(text, m.start()), confidence=0.9, status=STATUS_FOUND, source="preneur_block")

    # Adresse détenteur / preneur multi-lignes
    if out["adresse"]["status"] != STATUS_FOUND:
        m2 = re.search(
            r"(?:D[ÉE]TENTEUR|CONDUCTEUR\s+PRINCIPAL|PRENEUR\s+D['’]?ASSURANCE|VERSICHERUNGSNEHMER|POLICYHOLDER)\s*\n"
            r"([A-Za-zÀ-ÿ' \-]{2,60})\s*\n"
            r"([A-Za-zÀ-ÿ0-9' \-]{3,60})\s*\n"
            r"(\d{4})\s+([A-Za-zÀ-ÿ' \-]{2,40})",
            text,
            re.I,
        )
        if m2:
            civ, prenom, nom = _split_identity_parts(m2.group(1))
            if civ and out["civilite"]["status"] != STATUS_FOUND:
                out["civilite"] = _field(civ, page=_page_of(text, m2.start()), confidence=0.85, status=STATUS_FOUND, source="detenteur")
            if prenom and nom:
                _set_preneur_name(
                    out, prenom, nom, page=_page_of(text, m2.start()), confidence=0.85, source="detenteur"
                )
            out["adresse"] = _field(m2.group(2).strip(), page=_page_of(text, m2.start()), confidence=0.86, status=STATUS_FOUND, source="detenteur")
            out["npa"] = _field(m2.group(3), page=_page_of(text, m2.start()), confidence=0.9, status=STATUS_FOUND, source="detenteur")
            out["ville"] = _field(m2.group(4).strip(), page=_page_of(text, m2.start()), confidence=0.9, status=STATUS_FOUND, source="detenteur")

    # Civilité + nom : ligne séparée OU « Madame Sophie Martin » sur une ligne
    m_civ = re.search(
        r"(?:^|\n)\s*(Monsieur|Madame|Mademoiselle|Herr|Frau|Fräulein)\s+"
        r"(?:(?:\n\s*)?([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][A-Za-zÀ-ÿ' \-]{1,40}))",
        text,
        re.M,
    )
    if m_civ:
        civ_map = {
            "herr": "Monsieur",
            "frau": "Madame",
            "fräulein": "Mademoiselle",
        }
        civ_raw = m_civ.group(1)
        civ = civ_map.get(civ_raw.casefold(), civ_raw if civ_raw in {"Monsieur", "Madame", "Mademoiselle"} else "Monsieur")
        if out["civilite"]["status"] != STATUS_FOUND:
            out["civilite"] = _field(
                civ,
                page=_page_of(text, m_civ.start()),
                confidence=0.8,
                status=STATUS_FOUND,
                source="letter",
            )
        if m_civ.group(2):
            _civ, prenom, nom = _split_identity_parts(_strip_identity_noise(m_civ.group(2)))
            # Lettre AXA : confidence 0.8 → found si plausible ; doute → to_verify
            if prenom and nom:
                _set_preneur_name(
                    out,
                    prenom,
                    nom,
                    page=_page_of(text, m_civ.start()),
                    confidence=0.86,
                    source="letter",
                    min_confidence=0.85,
                )

    # DOB : Né(e) le
    m_dob = re.search(
        r"N[ée]\(?e?\)?\s*le\s*[:：]?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
        text,
        re.I,
    )
    if m_dob:
        dob = _normalize_date(m_dob.group(1))
        if dob:
            out["date_naissance"] = _field(dob, page=_page_of(text, m_dob.start()), confidence=0.95, status=STATUS_FOUND, source="ne_e_le")

    m_nat = re.search(r"Nationalit[ée]\s*[:：]\s*([A-Za-zÀ-ÿ' \-]{2,40})", text, re.I)
    if m_nat:
        out["nationalite"] = _field(m_nat.group(1).strip(), page=_page_of(text, m_nat.start()), confidence=0.9, status=STATUS_FOUND, source="label")

    m_perm = re.search(r"Permis\s+de\s+s[ée]jour\s*[:：]\s*([A-Za-z0-9]{1,20})", text, re.I)
    if m_perm:
        out["permis_sejour"] = _field(m_perm.group(1).strip(), page=_page_of(text, m_perm.start()), confidence=0.9, status=STATUS_FOUND, source="label")

    m_permis_cond = re.search(
        r"Date\s+du\s+permis\s+de\s+conduire\s*[:：]?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
        text,
        re.I,
    )
    if m_permis_cond:
        d = _normalize_date(m_permis_cond.group(1))
        if d:
            out["date_permis_conduire"] = _field(
                d,
                page=_page_of(text, m_permis_cond.start()),
                confidence=0.95,
                status=STATUS_FOUND,
                source="label",
            )

    # Tél / email preneur uniquement — jamais service assureur
    for m_tel in re.finditer(
        r"(?:T[ée]l(?:[ée]phone)?\.?|Mobile|Natel)\s*[:：]?\s*(\+?\d[\d\s./-]{7,20})",
        text,
        re.I,
    ):
        raw = re.sub(r"\s+", " ", m_tel.group(1)).strip()
        ctx = _norm(text[max(0, m_tel.start() - 120) : m_tel.end() + 40])
        if any(b.replace(" ", "") in raw.replace(" ", "") for b in _INSURER_PHONE_BLOCKLIST):
            continue
        if re.search(r"sinistre|service\s+center|elvia\.ch|allianz|assureur", ctx):
            continue
        out["telephone"] = _field(raw, page=_page_of(text, m_tel.start()), confidence=0.7, status=STATUS_FOUND, source="label")
        break

    for m_em in re.finditer(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text):
        email = m_em.group(0)
        low = email.lower()
        if any(b in low for b in _INSURER_EMAIL_BLOCKLIST):
            continue
        if low.endswith("@elvia.ch") or "sinistre" in low:
            continue
        ctx = _norm(text[max(0, m_em.start() - 80) : m_em.end() + 40])
        if re.search(r"service\s+center|assureur|sinistre", ctx):
            continue
        out["email"] = _field(email, page=_page_of(text, m_em.start()), confidence=0.65, status=STATUS_FOUND, source="email")
        break

    return out


def _extract_police(text: str) -> Dict[str, Any]:
    police = empty_structured_extraction()["police"]
    m = re.search(
        r"(?:N[°ºo]\s*de\s*police|Police\s*no\.?|NO\s+DE\s+POLICE|POLICE\s+NO\.?)\s*[:：]?\s*"
        r"([A-Z0-9][A-Z0-9./-]{3,30})",
        text,
        re.I,
    )
    if m:
        police["numero"] = _field(m.group(1).strip(), page=_page_of(text, m.start()), confidence=0.95, status=STATUS_FOUND, source="label")
    m2 = re.search(r"(?:Num[ée]ro\s+de\s+client|NUM[ÉE]RO\s+DE\s+CLIENT)\s*[:：]?\s*([A-Z0-9]{4,30})", text, re.I)
    if m2:
        police["numero_client"] = _field(m2.group(1).strip(), page=_page_of(text, m2.start()), confidence=0.9, status=STATUS_FOUND, source="label")
    m3 = re.search(r"VALABLE\s+[ÀA]\s+PARTIR\s+DU\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})", text, re.I)
    if m3:
        d = _normalize_date(m3.group(1))
        if d:
            police["date_debut"] = _field(d, page=_page_of(text, m3.start()), confidence=0.9, status=STATUS_FOUND, source="label")
    # Zurich OCR : VALABLE DES LE / DUREE … DU … AU …
    if police["date_debut"]["status"] != STATUS_FOUND:
        m3b = re.search(
            r"VALABLE\s+D[EÈÉ]S\s+LE\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
            text,
            re.I,
        )
        if m3b:
            d = _normalize_date(m3b.group(1))
            if d:
                police["date_debut"] = _field(d, page=_page_of(text, m3b.start()), confidence=0.9, status=STATUS_FOUND, source="valable_des")
    m_duree = re.search(
        r"DU\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s+AU\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
        text,
        re.I,
    )
    if m_duree:
        d0 = _normalize_date(m_duree.group(1))
        d1 = _normalize_date(m_duree.group(2))
        if d0 and police["date_debut"]["status"] != STATUS_FOUND:
            police["date_debut"] = _field(d0, page=_page_of(text, m_duree.start()), confidence=0.88, status=STATUS_FOUND, source="duree")
        if d1:
            police["date_fin"] = _field(d1, page=_page_of(text, m_duree.start()), confidence=0.9, status=STATUS_FOUND, source="duree")
    m4 = re.search(r"EXPIRATION\s+DE\s+L['’]?ASSURANCE\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})", text, re.I)
    if m4 and police["date_fin"]["status"] != STATUS_FOUND:
        d = _normalize_date(m4.group(1))
        if d:
            police["date_fin"] = _field(d, page=_page_of(text, m4.start()), confidence=0.9, status=STATUS_FOUND, source="label")
    m5 = re.search(r"MOTIF\s+D['’]?[ÉE]TABLISSEMENT\s+([^\n\r]{3,60})", text, re.I)
    if m5:
        police["motif"] = _field(m5.group(1).strip(), page=_page_of(text, m5.start()), confidence=0.8, status=STATUS_FOUND, source="label")
    return police


def _extract_somme_assurance(text: str) -> Optional[Dict[str, Any]]:
    """
    Capital / somme d'assurance (valeurs de rachat / feuille prestations).
    Ce n'est PAS une prime — à exposer comme montant_investi uniquement.
    """
    m = re.search(
        r"SOMME\s+D['’\s]*ASSURANCE\s+(?:DE\s+)?(?:FR\.?|CHF)?\s*"
        r"([0-9][0-9\s'’\u00a0\u202f:.,]*)",
        text,
        re.I,
    )
    if not m:
        return None
    raw = m.group(1).replace(":", " ").replace(".", "")
    # « 74 931 » / « 74: 931 » OCR
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) < 3:
        return None
    try:
        value = float(digits)
    except ValueError:
        return None
    return _field(value, page=_page_of(text, m.start()), confidence=0.85, status=STATUS_FOUND, source="somme_assurance")

def _extract_primes(text: str) -> Dict[str, Any]:
    primes = empty_structured_extraction()["primes"]
    detail: List[Dict[str, Any]] = []
    for label, pattern in (
        ("Responsabilité civile", r"Responsabilit[ée]\s+civile\s+([0-9][0-9'’\u00a0\u202f.,]*)"),
        ("Casco partielle", r"Casco\s+partielle\s+([0-9][0-9'’\u00a0\u202f.,]*)"),
        ("Collision (Casco complète)", r"Collision\s*\(Casco\s+compl[eè]te\)\s+([0-9][0-9'’\u00a0\u202f.,]*)"),
        ("Assistance", r"Assistance\s+([0-9][0-9'’\u00a0\u202f.,]*)"),
    ):
        m = re.search(pattern, text, re.I)
        if not m:
            continue
        val = _compact_money_token(m.group(1))
        if val is None:
            continue
        detail.append(
            {
                "label": label,
                "montant": _field(val, page=_page_of(text, m.start()), confidence=0.85, status=STATUS_FOUND, source="primes_table"),
            }
        )
    primes["detail_risques"] = detail

    m_brute = re.search(
        r"PRIME\s+ANNUELLE(?!\s+AVEC)\s+([0-9][0-9'’\u00a0\u202f.,]*)",
        text,
        re.I,
    )
    if m_brute:
        val = _compact_money_token(m_brute.group(1))
        if val is not None:
            primes["annuelle_brute"] = _field(val, page=_page_of(text, m_brute.start()), confidence=0.9, status=STATUS_FOUND, source="prime_annuelle")

    m_tax = re.search(
        r"PRIME\s+ANNUELLE\s+AVEC\s+REDEVANCES[^0-9\n]{0,80}([0-9][0-9'’\u00a0\u202f.,]*)",
        text,
        re.I,
    )
    if m_tax:
        val = _compact_money_token(m_tax.group(1))
        if val is not None:
            primes["annuelle_avec_taxes"] = _field(val, page=_page_of(text, m_tax.start()), confidence=0.95, status=STATUS_FOUND, source="prime_avec_taxes")

    # Synonymes multi-compagnies (DE/EN/FR) si libellés ELVIA absents.
    if primes["annuelle_avec_taxes"]["status"] != STATUS_FOUND and primes["annuelle_brute"]["status"] != STATUS_FOUND:
        for pattern, conf, source in (
            (r"Jahrespr[aä]mie(?:\s+inkl\.?\s*(?:Steuern|Abgaben))?[^0-9\n]{0,40}([0-9][0-9'’\u00a0\u202f.,]*)", 0.9, "jahrespraemie"),
            (r"(?:Prime|Cotisation)\s+totale(?:\s+annuelle)?[^0-9\n]{0,40}([0-9][0-9'’\u00a0\u202f.,]*)", 0.85, "prime_totale"),
            (r"Annual\s+premium[^0-9\n]{0,40}([0-9][0-9'’\u00a0\u202f.,]*)", 0.85, "annual_premium"),
            (r"Montant\s+de\s+la\s+prime[^0-9\n]{0,40}([0-9][0-9'’\u00a0\u202f.,]*)", 0.8, "montant_prime_label"),
            (r"Prime\s*/\s*an[^0-9\n]{0,20}([0-9][0-9'’\u00a0\u202f.,]*)", 0.8, "prime_slash_an"),
        ):
            m_syn = re.search(pattern, text, re.I)
            if not m_syn:
                continue
            val = _compact_money_token(m_syn.group(1))
            if val is None or not (20 <= float(val) <= 500_000):
                continue
            primes["annuelle_brute"] = _field(
                val, page=_page_of(text, m_syn.start()), confidence=conf, status=STATUS_FOUND, source=source
            )
            break

    # Une seule prime globale : taxes si dispo, sinon brute — jamais dupliquée.
    if primes["annuelle_avec_taxes"]["status"] == STATUS_FOUND:
        primes["globale"] = dict(primes["annuelle_avec_taxes"])
    elif primes["annuelle_brute"]["status"] == STATUS_FOUND:
        primes["globale"] = dict(primes["annuelle_brute"])

    m_per = re.search(
        r"Mode\s+de\s+paiement\s+(annuel|semestriel|trimestriel|mensuel)|"
        r"P[ée]riodicit[ée]\s*(?:de\s+(?:paiement|la\s+prime))?\s*[:：]?\s*"
        r"(Annuel|Semestriel|Trimestriel|Mensuel|annuel|semestriel|trimestriel|mensuel)",
        text,
        re.I,
    )
    if m_per:
        raw_per = (m_per.group(1) or m_per.group(2) or "").strip()
        if raw_per:
            primes["periodicite"] = _field(
                raw_per[:1].upper() + raw_per[1:].lower(),
                page=_page_of(text, m_per.start()),
                confidence=0.9,
                status=STATUS_FOUND,
                source="paiement",
            )
    return primes


def _extract_vehicules(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Retourne (objets, garanties liées). Sépare les blocs véhicule sans mélanger."""
    objets: List[Dict[str, Any]] = []
    garanties: List[Dict[str, Any]] = []

    # Résumé « VÉHICULES ASSURÉS A, B »
    resume = re.search(
        r"V[ÉE]HICULES?\s+ASSUR[ÉE]S\s+(.+?)(?:\nVALABLE|\nEXPIRATION|\nMOTIF|\nAPER[ÇC]U)",
        text,
        re.I | re.S,
    )
    resume_items: List[str] = []
    if resume:
        blob = re.sub(r"\s+", " ", resume.group(1)).strip()
        # Toyota …, GR xxx PORSCHE …, GR xxx
        parts = re.split(r"(?=\b(?:TOYOTA|PORSCHE|BMW|AUDI|MERCEDES|VW|VOLKSWAGEN|FORD|HONDA|TESLA|SKODA|SEAT|FIAT|RENAULT|PEUGEOT|OPEL|VOLVO|SUBARU|MAZDA|NISSAN|HYUNDAI|KIA|CUPRA|JEEP|LAND\s+ROVER|MINI)\b)", blob, flags=re.I)
        resume_items = [p.strip(" ,;") for p in parts if p.strip(" ,;")]

    # Blocs détaillés « VÉHICULE ASSURÉ »
    blocks = list(re.finditer(r"V[ÉE]HICULE\s+ASSUR[ÉE]\s*\n(.+?)(?=\nV[ÉE]HICULE\s+ASSUR[ÉE]\b|\nNO\s+DE\s+POLICE\b|\nAPER[ÇC]U\s+DES\s+PRIMES\b|\Z)", text, re.I | re.S))
    if not blocks and resume_items:
        for i, item in enumerate(resume_items):
            objets.append(_vehicule_from_resume_line(item, index=i + 1, page=_page_of(text, resume.start() if resume else 0)))
        return objets, garanties

    for i, blk in enumerate(blocks):
        chunk = blk.group(1)
        page = _page_of(text, blk.start())
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        designation = lines[0] if lines else ""
        marque, modele = _split_marque_modele(designation)
        plaque = None
        # Plaque souvent dans le résumé, pas toujours dans le bloc détaillé
        if i < len(resume_items):
            pm = re.search(r"\b([A-Z]{1,2}\s*\d{1,6})\b", resume_items[i], re.I)
            if pm:
                plaque = re.sub(r"\s+", " ", pm.group(1)).upper()
        if not plaque:
            pm_chunk = re.search(
                r"(?:Plaque(?:\s+de\s+contr[ôo]le)?|Kennzeichen|Kontrollschild|Immatriculation|Registration\s+plate)\s*[:：]?\s*([A-Z]{1,2}\s*\d{1,6})",
                chunk,
                re.I,
            )
            if pm_chunk:
                plaque = re.sub(r"\s+", " ", pm_chunk.group(1)).upper()
        if not plaque:
            # « pour GR 96299 » global
            pm2 = re.search(r"\b([A-Z]{1,2})\s*(\d{4,6})\b", text)
            if pm2:
                plaque = f"{pm2.group(1).upper()} {pm2.group(2)}"
                # Même plaque pour plusieurs véhicules (plaques interchangeables) → to_verify si partagée
        immat = None
        m_mat = re.search(r"No\s+de\s+matricule\s*[:：]?\s*([0-9.]+)", chunk, re.I)
        if m_mat:
            immat = m_mat.group(1).strip()
        mise = None
        m_mise = re.search(r"1re\s+mise\s+en\s+circulation\s*[:：]?\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})", chunk, re.I)
        if m_mise:
            mise = _normalize_date(m_mise.group(1))
        prix = None
        m_prix = re.search(r"Prix\s+catalogue\s*[:：]?\s*([0-9][0-9'’\u00a0\u202f ]*)", chunk, re.I)
        if m_prix:
            prix = _compact_money_token(m_prix.group(1))
        prix_options = None
        m_opt = re.search(
            r"(?:[ÉE]quipements?\s+et\s+accessoires|Prix\s+des\s+options)\s*[:：]?\s*([0-9][0-9'’\u00a0\u202f ]*)",
            chunk,
            re.I,
        )
        if m_opt:
            prix_options = _compact_money_token(m_opt.group(1))
        km_annuel = None
        m_km = re.search(r"Kilom[ée]trage\s+annuel\s*[:：]?\s*([0-9][0-9'’\u00a0\u202f ]*)", chunk, re.I)
        if m_km:
            km_annuel = _compact_money_token(m_km.group(1))
            if km_annuel is not None:
                km_annuel = int(km_annuel) if abs(km_annuel - round(km_annuel)) < 0.001 else km_annuel
        usage = None
        m_u = re.search(r"Utilisation\s*[:：]?\s*([^\n\r]{3,40})", chunk, re.I)
        if m_u:
            usage = m_u.group(1).strip()
        typ = None
        m_t = re.search(r"(Voiture\s+de\s+tourisme|Camionnette|Motocycle)", chunk, re.I)
        if m_t:
            typ = m_t.group(1)
        leasing = None
        if re.search(r"\bSans\s+leasing\b", chunk, re.I):
            leasing = "Non"
        elif re.search(r"(?:^|\n)\s*Leasing\s*(?:\n|$)", chunk, re.I) or re.search(
            r"\bAvec\s+leasing\b|\bEn\s+leasing\b", chunk, re.I
        ):
            leasing = "Oui"
        garage_dispo = None
        m_g = re.search(r"Place\s+de\s+garage\s+[àa]\s+disposition\s*[:：]?\s*(Oui|Non)", chunk, re.I)
        if m_g:
            garage_dispo = m_g.group(1).title()

        cov = _extract_vehicule_couvertures(chunk, page=page)

        plaque_status = STATUS_FOUND if plaque else STATUS_NOT_FOUND
        plaque_conf = 0.85 if plaque else 0.0
        # Si même plaque sur 2+ objets → toujours found mais note plaques interchangeables
        obj = {
            "type": "vehicule",
            "index": i + 1,
            "designation": _field(designation or None, page=page, confidence=0.9 if designation else 0.0, status=STATUS_FOUND if designation else STATUS_NOT_FOUND, source="vehicule_block"),
            "marque": _field(marque, page=page, confidence=0.9 if marque else 0.0, status=STATUS_FOUND if marque else STATUS_NOT_FOUND, source="vehicule_block"),
            "modele": _field(modele, page=page, confidence=0.85 if modele else 0.0, status=STATUS_FOUND if modele else STATUS_NOT_FOUND, source="vehicule_block"),
            "plaque": _field(plaque, page=page, confidence=plaque_conf, status=plaque_status, source="resume_or_global"),
            "no_matricule": _field(immat, page=page, confidence=0.9 if immat else 0.0, status=STATUS_FOUND if immat else STATUS_NOT_FOUND, source="vehicule_block"),
            "mise_en_circulation": _field(mise, page=page, confidence=0.9 if mise else 0.0, status=STATUS_FOUND if mise else STATUS_NOT_FOUND, source="vehicule_block"),
            "prix_catalogue": _field(prix, page=page, confidence=0.85 if prix else 0.0, status=STATUS_FOUND if prix else STATUS_NOT_FOUND, source="vehicule_block"),
            "prix_options": _field(prix_options, page=page, confidence=0.85 if prix_options else 0.0, status=STATUS_FOUND if prix_options else STATUS_NOT_FOUND, source="vehicule_block"),
            "km_annuel": _field(km_annuel, page=page, confidence=0.9 if km_annuel else 0.0, status=STATUS_FOUND if km_annuel else STATUS_NOT_FOUND, source="vehicule_block"),
            "utilisation": _field(usage, page=page, confidence=0.8 if usage else 0.0, status=STATUS_FOUND if usage else STATUS_NOT_FOUND, source="vehicule_block"),
            "categorie": _field(typ, page=page, confidence=0.8 if typ else 0.0, status=STATUS_FOUND if typ else STATUS_NOT_FOUND, source="vehicule_block"),
            "leasing": _field(leasing, page=page, confidence=0.9 if leasing else 0.0, status=STATUS_FOUND if leasing else STATUS_NOT_FOUND, source="vehicule_block"),
            "garage_disponibilite": _field(
                garage_dispo,
                page=page,
                confidence=0.85 if garage_dispo else 0.0,
                status=STATUS_FOUND if garage_dispo else STATUS_NOT_FOUND,
                source="vehicule_block",
            ),
            "couvertures": cov,
        }
        objets.append(obj)
        for g in cov.get("garanties_list") or []:
            garanties.append({**g, "objet_index": i + 1})

    if not garanties:
        for label in ("Responsabilité civile", "Casco partielle", "Collision (Casco complète)", "Assistance"):
            if re.search(re.escape(label.split("(")[0].strip()), text, re.I):
                garanties.append(
                    {
                        "label": label,
                        "scope": "police",
                        "status": STATUS_FOUND,
                        "confidence": 0.8,
                    }
                )
    return objets, garanties


def _extract_vehicule_couvertures(chunk: str, *, page: Optional[int] = None) -> Dict[str, Any]:
    """Garanties / franchises dans le bloc véhicule (adaptateur générique, golden ELVIA)."""
    flat = _norm(chunk)
    has_detail = bool(re.search(r"votre\s+assurance\s+en\s+d[ée]tail|risques\s+assur[ée]s", flat))

    def yn(present: bool, *, conf: float = 0.85) -> Dict[str, Any]:
        # Preuve textuelle claire → found ; sinon not_found (vide), pas de faux to_verify « Non ».
        if not has_detail or not present:
            return _field()
        return _field(
            "Oui",
            page=page,
            confidence=conf,
            status=STATUS_FOUND,
            source="couverture_bloc",
        )

    rc = bool(re.search(r"\brc\b|responsabilit[ée]\s+civile", flat))
    casco_part = bool(re.search(r"casco\s+partielle", flat))
    casco_coll = bool(re.search(r"casco\s+collision|collision\s*\(casco|casco\s+compl[eè]te", flat))
    assistance = bool(re.search(r"\bassistance\b", flat))
    bonus_rc = bool(re.search(r"protection\s+du\s+bonus", flat)) and rc
    bonus_coll = bool(re.search(r"casco\s+collision[\s\S]{0,400}protection\s+du\s+bonus", flat))

    franchise = None
    m_fr = re.search(
        r"Casco\s+collision[\s\S]{0,500}?Conducteurs?\s+d[eè]s\s+26\s+ans\s*[:：]?\s*([0-9][0-9'’\u00a0\u202f ]*)",
        chunk,
        re.I,
    )
    if not m_fr:
        m_fr = re.search(
            r"franchise\s+collision\s*[:：]?\s*([0-9][0-9'’\u00a0\u202f ]*)",
            chunk,
            re.I,
        )
    if m_fr:
        franchise = _compact_money_token(m_fr.group(1))
        if franchise is not None and abs(franchise - round(franchise)) < 0.001:
            franchise = int(franchise)

    garanties_list = []
    for label, present in (
        ("Responsabilité civile", rc),
        ("Casco partielle", casco_part),
        ("Collision (Casco complète)", casco_coll),
        ("Assistance", assistance),
    ):
        if present:
            garanties_list.append(
                {"label": label, "scope": "vehicule", "status": STATUS_FOUND, "confidence": 0.85}
            )

    return {
        "rc": yn(rc),
        "rc_protection_bonus": yn(bonus_rc, conf=0.8),
        "casco_integrale": yn(casco_coll),
        "casco_partielle": yn(casco_part),
        "assistance": yn(assistance),
        "protection_bonus_collision": yn(bonus_coll, conf=0.8),
        "franchise_collision": _field(
            franchise,
            page=page,
            confidence=0.9 if franchise is not None else 0.0,
            status=STATUS_FOUND if franchise is not None else STATUS_NOT_FOUND,
            source="couverture_bloc",
        ),
        "garanties_list": garanties_list,
    }


def _vehicule_from_resume_line(item: str, *, index: int, page: Optional[int]) -> Dict[str, Any]:
    plaque = None
    pm = re.search(r",?\s*([A-Z]{1,2}\s*\d{1,6})\s*$", item, re.I)
    designation = item
    if pm:
        plaque = re.sub(r"\s+", " ", pm.group(1)).upper()
        designation = item[: pm.start()].strip(" ,")
    marque, modele = _split_marque_modele(designation)
    return {
        "type": "vehicule",
        "index": index,
        "designation": _field(designation, page=page, confidence=0.8, status=STATUS_FOUND, source="resume"),
        "marque": _field(marque, page=page, confidence=0.8 if marque else 0.0, status=STATUS_FOUND if marque else STATUS_NOT_FOUND, source="resume"),
        "modele": _field(modele, page=page, confidence=0.75 if modele else 0.0, status=STATUS_FOUND if modele else STATUS_NOT_FOUND, source="resume"),
        "plaque": _field(plaque, page=page, confidence=0.85 if plaque else 0.0, status=STATUS_FOUND if plaque else STATUS_NOT_FOUND, source="resume"),
        "no_matricule": _field(),
        "mise_en_circulation": _field(),
        "prix_catalogue": _field(),
        "prix_options": _field(),
        "km_annuel": _field(),
        "utilisation": _field(),
        "categorie": _field(),
        "leasing": _field(),
        "garage_disponibilite": _field(),
        "couvertures": {},
    }


def _split_marque_modele(designation: str) -> Tuple[Optional[str], Optional[str]]:
    text = re.sub(r"\s+", " ", designation or "").strip()
    if not text:
        return None, None
    parts = text.split(" ", 1)
    marque = parts[0].title() if parts else None
    modele = parts[1].strip() if len(parts) > 1 else None
    return marque, modele


def suggest_form_type(structured: Dict[str, Any]) -> Optional[str]:
    """
    Suggestion non forcée : voyage = plaques interchangeables (2+ véhicules),
    vehicule = un seul. Id historique « voyage » = auto multi-plaques.
    """
    info = suggest_form_type_with_candidates(structured)
    return info.get("form_type_suggere")


def suggest_form_type_with_candidates(
    structured: Dict[str, Any],
    *,
    text: str = "",
) -> Dict[str, Any]:
    """
    Propose le formulaire LeoSoft (+ sous-type GF) et liste les candidats
    si plusieurs sont plausibles → confirmation UI requise.
    """
    branche = (structured.get("branche") or {}).get("value")
    meta = structured.get("meta") or {}
    raw_doc = meta.get("document_type")
    if isinstance(raw_doc, dict):
        doc_type = raw_doc.get("value")
    else:
        doc_type = raw_doc
    objets = structured.get("objets") or []
    vehicules = [o for o in objets if o.get("type") == "vehicule"]
    flat = _norm(text or "")

    candidates: List[Dict[str, Any]] = []
    gf_subtype: Optional[str] = None

    if len(vehicules) >= 2 or branche == "vehicule_plaques_interchangeables":
        candidates.append({"form_type": "voyage", "label": "Véhicule plaques interchangeables", "confidence": 0.95})
    elif len(vehicules) == 1 or branche == "vehicule":
        candidates.append({"form_type": "vehicule", "label": "Véhicule", "confidence": 0.9})
        if re.search(r"motocycle|moto\b|scooter", flat):
            candidates.append({"form_type": "motocycle", "label": "Motocycles", "confidence": 0.7})

    if branche == "pilier3" or _pilier3_signals(text):
        conf = 0.9 if branche == "pilier3" else 0.75
        candidates.append({"form_type": "pilier3", "label": "3ème pilier", "confidence": conf})
        if re.search(r"risque\s+pur|d[ée]c[eè]s\s+seul|temporaire\s+en\s+cas\s+de\s+d[ée]c[eè]s", flat):
            candidates.append(
                {"form_type": "pilier3_risque_pur", "label": "3ème pilier risque pur", "confidence": 0.8}
            )
            gf_subtype = "risque_pur"
        elif re.search(r"parent[\s-]?enfant", flat):
            candidates.append(
                {"form_type": "pilier3_parent_enfant", "label": "3ème pilier parent-enfant", "confidence": 0.78}
            )
            gf_subtype = "parent_enfant"
        elif doc_type in {"valeurs_rachat", "police", "decompte"}:
            gf_subtype = "vie_capitalisation"

    if branche == "menage_rc":
        candidates.append({"form_type": "menage_rc", "label": "RC seule", "confidence": 0.7})

    # Dédupliquer en gardant la meilleure confiance
    by_id: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        fid = c["form_type"]
        if fid not in by_id or float(c.get("confidence") or 0) > float(by_id[fid].get("confidence") or 0):
            by_id[fid] = c
    ordered = sorted(by_id.values(), key=lambda c: -float(c.get("confidence") or 0))

    needs_confirm = len(ordered) > 1 and (
        float(ordered[0].get("confidence") or 0) < 0.92
        or abs(float(ordered[0].get("confidence") or 0) - float(ordered[1].get("confidence") or 0)) < 0.15
    )
    # Toujours confirmer si le top n'est pas le même « genre » que le 2e (ex. voyage vs pilier3)
    if len(ordered) > 1:
        top, second = ordered[0]["form_type"], ordered[1]["form_type"]
        if top.split("_")[0] != second.split("_")[0] and not (
            top.startswith("pilier3") and second.startswith("pilier3")
        ):
            needs_confirm = True

    return {
        "form_type_suggere": ordered[0]["form_type"] if ordered else None,
        "form_type_candidates": ordered,
        "form_type_needs_confirm": needs_confirm,
        "gf_subtype_suggere": gf_subtype,
    }


def _apply_form_suggestions(result: Dict[str, Any], text: str = "") -> None:
    info = suggest_form_type_with_candidates(result, text=text)
    meta = result.setdefault("meta", {})
    meta["form_type_suggere"] = info.get("form_type_suggere")
    meta["form_type_candidates"] = info.get("form_type_candidates") or []
    meta["form_type_needs_confirm"] = bool(info.get("form_type_needs_confirm"))
    meta["gf_subtype_suggere"] = info.get("gf_subtype_suggere")


def extract_structured_offre(
    pdf_bytes: bytes,
    *,
    filename: str = "",
    text: Optional[str] = None,
) -> Dict[str, Any]:
    """Point d'entrée Phase 1 : extraction structurée générique."""
    if text is None:
        try:
            from pdf_generator import _extract_pdf_text

            text = _extract_pdf_text(pdf_bytes) or ""
        except Exception:
            text = ""

    result = empty_structured_extraction()
    result["meta"]["filename"] = filename or ""
    result["audit"]["raw_text_len"] = len(text or "")
    page_markers = re.findall(r"Page\s+(\d+)\s+sur\s+(\d+)", text or "", re.I)
    if page_markers:
        try:
            result["meta"]["pages"] = max(int(total) for _n, total in page_markers)
            result["meta"]["page_refs"] = sorted({int(n) for n, _t in page_markers})
        except ValueError:
            result["meta"]["pages"] = None
    # Heuristique OCR : marqueurs Page + peu/pas de texte natif dense avant OCR
    if page_markers and re.search(r"feuille\s+des\s+prestations|zurich|scann|ocr", _norm(f"{filename}\n{text[:400]}")):
        result["meta"]["ocr_used"] = True
    if "[table p" in (text or ""):
        result["meta"]["notes"].append(
            "Tableaux natifs PyMuPDF fusionnés — limité aux PDF avec couche texte (pas scans purs)."
        )
    if "[ocr-table-heuristics]" in (text or ""):
        result["meta"]["notes"].append(
            "Heuristiques lignes/colonnes OCR appliquées (scans) — qualité dépendante Tesseract fra+deu+eng."
        )
    if "[table p" not in (text or ""):
        result["meta"]["visual_tables_limited"] = True
        if not (text or "").strip() or result["meta"].get("ocr_used") or "[ocr-table-heuristics]" in (text or ""):
            result["meta"]["notes"].append(
                "Analyse visuelle tableaux limitée : scans → OCR Tesseract + heuristiques ; pas de find_tables fiable."
            )

    doc_type_field = detect_document_type(text or "", filename)
    result["meta"]["document_type"] = doc_type_field
    result["meta"]["document_type_status"] = doc_type_field.get("status") or STATUS_NOT_FOUND

    if not (text or "").strip():
        result["meta"]["notes"].append("Texte PDF vide / OCR indisponible — aucune invention de champs.")
        # Indices nom de fichier uniquement (compagnie / branche), pas de données personne.
        result["branche"] = _detect_branche("", filename)
        result["marque"] = _detect_marque(filename)
        compagnie_fn = _find_compagnie("", filename)
        if compagnie_fn:
            result["assureur"] = _field(
                compagnie_fn, confidence=0.6, status=STATUS_TO_VERIFY, source="filename"
            )
        _apply_form_suggestions(result, filename)
        return result

    result["branche"] = _detect_branche(text, filename)
    result["marque"] = _detect_marque(text)
    compagnie = _find_compagnie(text, filename)
    if compagnie:
        # Si marque ELVIA, assureur porteur = Allianz souvent ; garder compagnie détectée.
        result["assureur"] = _field(compagnie, confidence=0.85, status=STATUS_FOUND, source="compagnie_aliases")
    result["police"] = _extract_police(text)
    result["preneur"] = _extract_preneur_block(text)
    result["primes"] = _extract_primes(text)

    # Valeurs de rachat / feuille prestations : capital ≠ prime (ne jamais inventer prime).
    doc_val = doc_type_field.get("value")
    if doc_val in {"valeurs_rachat", "police", "decompte"}:
        somme = _extract_somme_assurance(text)
        if somme:
            result.setdefault("capital", {})
            result["capital"] = {"somme_assurance": somme}
            result["meta"]["notes"].append(
                "Somme d'assurance / capital détecté — non utilisé comme prime annuelle."
            )
        # Si aucune mention explicite de prime annuelle, forcer not_found (pas d'invention).
        if not re.search(r"prime\s+annuelle|jahresprämie|cotisation\s+annuelle", _norm(text)):
            for key in ("annuelle_brute", "annuelle_avec_taxes", "globale"):
                if (result["primes"].get(key) or {}).get("status") == STATUS_FOUND:
                    # Conservé seulement si libellé prime clair — sinon déjà not_found
                    pass
            if not re.search(r"\bprime\b|\bcotisation\b|\bprämie\b", _norm(text)):
                result["primes"]["globale"] = _field(status=STATUS_NOT_FOUND, source="no_prime_on_document")
                result["primes"]["annuelle_brute"] = _field(status=STATUS_NOT_FOUND, source="no_prime_on_document")
                result["primes"]["annuelle_avec_taxes"] = _field(status=STATUS_NOT_FOUND, source="no_prime_on_document")
                result["meta"]["notes"].append(
                    "Document sans prime explicite — montant_prime laissé vide."
                )

    if (result["branche"].get("value") or "").startswith("vehicule") or (
        re.search(r"v[ée]hicule", _norm(text)) and not _pilier3_signals(text, filename)
    ):
        objets, garanties = _extract_vehicules(text)
        result["objets"] = objets
        result["garanties"] = garanties
        plaques = [
            (o.get("plaque") or {}).get("value")
            for o in objets
            if (o.get("plaque") or {}).get("value")
        ]
        if len(objets) >= 2 and len(set(plaques)) == 1 and plaques:
            result["meta"]["notes"].append(
                "Plusieurs véhicules partagent la même plaque (plaques interchangeables)."
            )
            result["branche"] = _field(
                "vehicule_plaques_interchangeables",
                confidence=0.95,
                status=STATUS_FOUND,
                source="multi_vehicule_same_plate",
            )

    _apply_form_suggestions(result, text)

    # Audit flat list
    audit_fields: List[Dict[str, Any]] = []

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict) and "status" in node and "value" in node:
            audit_fields.append({"path": prefix, **node})
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if k in {"meta", "audit"}:
                    continue
                walk(f"{prefix}.{k}" if prefix else k, v)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(f"{prefix}[{i}]", item)

    walk("", {k: v for k, v in result.items() if k not in {"meta", "audit"}})
    result["audit"]["fields"] = audit_fields
    return result


def structured_to_flat_extracted(structured: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aplatit vers le dict attendu par map_extract_to_form / fill_form_payload_from_pdf.
    Les champs to_verify / not_found ne sont pas écrits (pas d'invention).
    """
    preneur = structured.get("preneur") or {}
    police = structured.get("police") or {}
    primes = structured.get("primes") or {}
    capital = structured.get("capital") or {}
    meta = structured.get("meta") or {}
    marque = _value_or_none(structured.get("marque"))
    assureur = _value_or_none(structured.get("assureur"))
    doc_raw = meta.get("document_type")
    document_type = doc_raw.get("value") if isinstance(doc_raw, dict) else doc_raw

    flat: Dict[str, Any] = {
        "compagnie": marque or assureur,
        "prenom": _value_or_none(preneur.get("prenom")),
        "nom": _value_or_none(preneur.get("nom")),
        "civilite": _value_or_none(preneur.get("civilite")),
        "adresse": _value_or_none(preneur.get("adresse")),
        "npa": _value_or_none(preneur.get("npa")),
        "ville": _value_or_none(preneur.get("ville")),
        "pays": _value_or_none(preneur.get("pays")),
        "date_naissance": _value_or_none(preneur.get("date_naissance")),
        "nationalite": _value_or_none(preneur.get("nationalite")),
        "permis": _value_or_none(preneur.get("permis_sejour")),
        "telephone": _value_or_none(preneur.get("telephone")),
        "email": _value_or_none(preneur.get("email")),
        "reference_police": _value_or_none(police.get("numero")),
        "date_debut": _value_or_none(police.get("date_debut")),
        "date_fin": _value_or_none(police.get("date_fin")),
        "montant_prime": _value_or_none(primes.get("globale")),
        "montant_investi": _value_or_none(capital.get("somme_assurance")),
        "periodicite": _value_or_none(primes.get("periodicite")),
        "date_permis_conduire": _value_or_none(preneur.get("date_permis_conduire")),
        "numero_offre": None,
        "objets": structured.get("objets") or [],
        "structured": structured,
        "form_type_suggere": meta.get("form_type_suggere"),
        "form_type_candidates": meta.get("form_type_candidates") or [],
        "form_type_needs_confirm": bool(meta.get("form_type_needs_confirm")),
        "gf_subtype_suggere": meta.get("gf_subtype_suggere"),
        "document_type": document_type,
        "document_type_status": meta.get("document_type_status"),
        "page_refs": meta.get("page_refs") or [],
    }
    if flat["compagnie"]:
        flat["compagnie_label"] = flat["compagnie"]
    else:
        flat["compagnie_label"] = NON_INDIQUE
    return flat


def map_objets_to_voyage_hints(objets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Couche mapping (sans toucher aux JSON) : indices véhicule 1 / 2 pour voyage.
    Clés sémantiques consommées par offre_pdf_form_map.
    """
    hints: Dict[str, Any] = {}
    for obj in objets:
        if obj.get("type") != "vehicule":
            continue
        idx = int(obj.get("index") or 0)
        prefix = f"vehicule_{idx}"
        for key in (
            "marque",
            "modele",
            "plaque",
            "no_matricule",
            "mise_en_circulation",
            "prix_catalogue",
            "prix_options",
            "km_annuel",
            "utilisation",
            "categorie",
            "designation",
            "leasing",
            "garage_disponibilite",
        ):
            val = _value_or_none(obj.get(key))
            if val is not None:
                hints[f"{prefix}_{key}"] = val
        cov = obj.get("couvertures") or {}
        for ckey in (
            "rc",
            "rc_protection_bonus",
            "casco_integrale",
            "casco_partielle",
            "assistance",
            "protection_bonus_collision",
            "franchise_collision",
        ):
            val = _value_or_none(cov.get(ckey))
            if val is not None:
                hints[f"{prefix}_{ckey}"] = val
    return hints
