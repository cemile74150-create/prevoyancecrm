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
    _norm,
    _normalize_date,
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
        },
        "objets": [],
        "primes": {
            "annuelle_brute": _field(),
            "annuelle_avec_taxes": _field(),
            "globale": _field(),  # une seule prime à préremplir
            "detail_risques": [],
        },
        "garanties": [],
        "meta": {
            "pages": None,
            "filename": "",
            "form_type_suggere": None,
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


def _detect_branche(text: str) -> Dict[str, Any]:
    flat = _norm(text)
    if re.search(
        r"assurance\s+v[ée]hicules?\s+[àa]\s+moteur|v[ée]hicules?\s+assur[ée]s|casco|responsabilit[ée]\s+civile",
        flat,
    ):
        multi = bool(
            re.search(r"plaques?\s+interchangeables|v[ée]hicules?\s+assur[ée]s.{0,80},", flat, re.S)
        ) or len(re.findall(r"v[ée]hicule\s+assur[ée]\b", flat)) >= 2
        return _field(
            "vehicule_plaques_interchangeables" if multi else "vehicule",
            confidence=0.92 if multi else 0.85,
            status=STATUS_FOUND,
            source="keyword",
        )
    if re.search(r"\b3\s*a\b|pilier\s*3|pr[ée]voyance", flat):
        return _field("pilier3", confidence=0.7, status=STATUS_FOUND, source="keyword")
    if re.search(r"\bm[ée]nage\b|\brc\s+priv", flat):
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


def _extract_preneur_block(text: str) -> Dict[str, Any]:
    """Bloc preneur prioritaire (pas l'en-tête assureur)."""
    out = empty_structured_extraction()["preneur"]
    # Bloc explicite PRENEUR D'ASSURANCE … (jusqu'au prochain titre majuscule long)
    m = re.search(
        r"PRENEUR\s+D['’]?ASSURANCE\s+([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][^\n]{2,80})\s+"
        r"([A-Z0-9][^\n,]{3,60}),\s*(\d{4})\s+([A-Za-zÀ-ÿ' \-]{2,40})",
        text,
        re.I,
    )
    if m:
        full_name = re.sub(r"\s+", " ", m.group(1)).strip()
        parts = full_name.split()
        if len(parts) >= 2:
            # FERNANDO GASCA → prénom / nom
            out["prenom"] = _field(parts[0].title(), page=_page_of(text, m.start()), confidence=0.9, status=STATUS_FOUND, source="preneur_block")
            out["nom"] = _field(" ".join(p.title() for p in parts[1:]), page=_page_of(text, m.start()), confidence=0.9, status=STATUS_FOUND, source="preneur_block")
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
            r"(?:D[ÉE]TENTEUR|CONDUCTEUR\s+PRINCIPAL|PRENEUR\s+D['’]?ASSURANCE)\s*\n"
            r"([A-Za-zÀ-ÿ' \-]{2,40})\s*\n"
            r"([A-Za-zÀ-ÿ0-9' \-]{3,60})\s*\n"
            r"(\d{4})\s+([A-Za-zÀ-ÿ' \-]{2,40})",
            text,
            re.I,
        )
        if m2:
            name_parts = m2.group(1).split()
            if len(name_parts) >= 2 and out["prenom"]["status"] != STATUS_FOUND:
                out["prenom"] = _field(name_parts[0], page=_page_of(text, m2.start()), confidence=0.85, status=STATUS_FOUND, source="detenteur")
                out["nom"] = _field(" ".join(name_parts[1:]), page=_page_of(text, m2.start()), confidence=0.85, status=STATUS_FOUND, source="detenteur")
            out["adresse"] = _field(m2.group(2).strip(), page=_page_of(text, m2.start()), confidence=0.86, status=STATUS_FOUND, source="detenteur")
            out["npa"] = _field(m2.group(3), page=_page_of(text, m2.start()), confidence=0.9, status=STATUS_FOUND, source="detenteur")
            out["ville"] = _field(m2.group(4).strip(), page=_page_of(text, m2.start()), confidence=0.9, status=STATUS_FOUND, source="detenteur")

    # Civilité lettre
    m_civ = re.search(r"(?:^|\n)\s*(Monsieur|Madame|Mademoiselle)\s*\n\s*([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][^\n]{1,40})", text, re.M)
    if m_civ and out["prenom"]["status"] != STATUS_FOUND:
        out["civilite"] = _field(m_civ.group(1), page=_page_of(text, m_civ.start()), confidence=0.8, status=STATUS_FOUND, source="letter")
        parts = m_civ.group(2).split()
        if len(parts) >= 2:
            out["prenom"] = _field(parts[0], page=_page_of(text, m_civ.start()), confidence=0.75, status=STATUS_FOUND, source="letter")
            out["nom"] = _field(" ".join(parts[1:]), page=_page_of(text, m_civ.start()), confidence=0.75, status=STATUS_FOUND, source="letter")

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
    m = re.search(r"(?:N[°ºo]\s*de\s*police|Police\s*no\.?|NO\s+DE\s+POLICE)\s*[:：]?\s*([A-Z0-9][A-Z0-9./-]{4,30})", text, re.I)
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
    m4 = re.search(r"EXPIRATION\s+DE\s+L['’]?ASSURANCE\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})", text, re.I)
    if m4:
        d = _normalize_date(m4.group(1))
        if d:
            police["date_fin"] = _field(d, page=_page_of(text, m4.start()), confidence=0.9, status=STATUS_FOUND, source="label")
    m5 = re.search(r"MOTIF\s+D['’]?[ÉE]TABLISSEMENT\s+([^\n\r]{3,60})", text, re.I)
    if m5:
        police["motif"] = _field(m5.group(1).strip(), page=_page_of(text, m5.start()), confidence=0.8, status=STATUS_FOUND, source="label")
    return police


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

    # Une seule prime globale : taxes si dispo, sinon brute — jamais dupliquée.
    if primes["annuelle_avec_taxes"]["status"] == STATUS_FOUND:
        primes["globale"] = dict(primes["annuelle_avec_taxes"])
    elif primes["annuelle_brute"]["status"] == STATUS_FOUND:
        primes["globale"] = dict(primes["annuelle_brute"])
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
        usage = None
        m_u = re.search(r"Utilisation\s*[:：]?\s*([^\n\r]{3,40})", chunk, re.I)
        if m_u:
            usage = m_u.group(1).strip()
        typ = None
        m_t = re.search(r"(Voiture\s+de\s+tourisme|Camionnette|Motocycle)", chunk, re.I)
        if m_t:
            typ = m_t.group(1)

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
            "utilisation": _field(usage, page=page, confidence=0.8 if usage else 0.0, status=STATUS_FOUND if usage else STATUS_NOT_FOUND, source="vehicule_block"),
            "categorie": _field(typ, page=page, confidence=0.8 if typ else 0.0, status=STATUS_FOUND if typ else STATUS_NOT_FOUND, source="vehicule_block"),
        }
        objets.append(obj)

    # Garanties globales (pas par véhicule dans ce PDF)
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
        "utilisation": _field(),
        "categorie": _field(),
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
    branche = (structured.get("branche") or {}).get("value")
    objets = structured.get("objets") or []
    vehicules = [o for o in objets if o.get("type") == "vehicule"]
    if len(vehicules) >= 2 or branche == "vehicule_plaques_interchangeables":
        return "voyage"
    if len(vehicules) == 1 or branche == "vehicule":
        return "vehicule"
    if branche == "pilier3":
        return "pilier3"
    if branche == "menage_rc":
        return "menage_rc"
    return None


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
    pages = re.findall(r"Page\s+\d+\s+sur\s+(\d+)", text or "", re.I)
    if pages:
        try:
            result["meta"]["pages"] = max(int(p) for p in pages)
        except ValueError:
            result["meta"]["pages"] = None

    if not (text or "").strip():
        result["meta"]["notes"].append("Texte PDF vide — aucune invention.")
        return result

    result["branche"] = _detect_branche(text)
    result["marque"] = _detect_marque(text)
    compagnie = _find_compagnie(text, filename)
    if compagnie:
        # Si marque ELVIA, assureur porteur = Allianz souvent ; garder compagnie détectée.
        result["assureur"] = _field(compagnie, confidence=0.85, status=STATUS_FOUND, source="compagnie_aliases")
    result["police"] = _extract_police(text)
    result["preneur"] = _extract_preneur_block(text)
    result["primes"] = _extract_primes(text)

    if (result["branche"].get("value") or "").startswith("vehicule") or re.search(
        r"v[ée]hicule", _norm(text)
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

    suggested = suggest_form_type(result)
    result["meta"]["form_type_suggere"] = suggested

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
    marque = _value_or_none(structured.get("marque"))
    assureur = _value_or_none(structured.get("assureur"))

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
        "numero_offre": None,
        "objets": structured.get("objets") or [],
        "structured": structured,
        "form_type_suggere": (structured.get("meta") or {}).get("form_type_suggere"),
    }
    if flat["compagnie"]:
        flat["compagnie_label"] = flat["compagnie"]
    else:
        flat["compagnie_label"] = NON_INDIQUE
    return flat


def map_objets_to_voyage_hints(objets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Couche mapping (sans toucher aux JSON) : indices véhicule 1 / 2 pour voyage.
    Les clés restent sémantiques ; fill_form_payload_from_pdf lit encore le texte.
    """
    hints: Dict[str, Any] = {}
    for obj in objets:
        if obj.get("type") != "vehicule":
            continue
        idx = int(obj.get("index") or 0)
        prefix = f"vehicule_{idx}"
        for key in ("marque", "modele", "plaque", "no_matricule", "mise_en_circulation", "prix_catalogue", "utilisation", "categorie", "designation"):
            val = _value_or_none(obj.get(key))
            if val is not None:
                hints[f"{prefix}_{key}"] = val
    return hints
