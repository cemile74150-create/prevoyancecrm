"""Extraction d'informations structurées depuis un PDF d'offre 3e pilier.

Utilise le texte natif du PDF (et OCR si nécessaire via pdf_generator),
sans dépendre de positions fixes dans la mise en page.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("server")

# Compagnies suisses courantes + alias fréquents dans les offres
COMPAGNIE_ALIASES: List[Tuple[str, Tuple[str, ...]]] = [
    ("Vaudoise", (r"vaudoise", r"vaudoise assurances", r"vaudoise vie", r"\bvd\b")),
    ("Swiss Life", (r"swiss life", r"swisslife", r"schweizerische lebens")),
    ("Helvetia", (r"helvetia",)),
    ("AXA", (r"\baxa\b", r"axa vie", r"axa winterthur")),
    ("Zurich", (r"zurich", r"zurich vie", r"zurich life")),
    ("Generali", (r"generali",)),
    ("Baloise", (r"baloise", r"basler")),
    ("Allianz", (r"allianz",)),
    ("Mobilière", (r"mobili[eè]re", r"die mobiliar", r"mobiliar")),
    ("PAX", (r"\bpax\b", r"pax vie")),
    ("Groupe Mutuel", (r"groupe mutuel",)),
    ("Retraites Populaires", (r"retraites populaires",)),
    ("Swica", (r"swica",)),
    ("CSS", (r"\bcss\b",)),
    ("Pictet", (r"pictet",)),
    ("UBS", (r"\bubs\b",)),
    ("PostFinance", (r"postfinance", r"post finance")),
]

NON_INDIQUE = "Non indiqué"


def _norm(text: str) -> str:
    return (
        (text or "")
        .lower()
        .replace("’", "'")
        .replace("`", "'")
        .replace("´", "'")
        .replace("–", "-")
        .replace("—", "-")
    )


def _compact_money_token(raw: str) -> Optional[float]:
    """Parse un montant CHF saisi sous formes suisses / internationales."""
    if not raw:
        return None
    s = str(raw).strip()
    s = s.replace("CHF", "").replace("Fr.", "").replace("fr.", "").replace("SFr.", "")
    s = s.replace("'", "").replace("’", "").replace(" ", "").replace("\u00a0", "")
    s = s.replace(".–", "").replace(".-", "").replace("–", "").replace("—", "")
    if "," in s and "." in s:
        # 1.250,50 ou 1,250.50
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        value = float(s)
    except ValueError:
        return None
    if value <= 0 or value > 50_000_000:
        return None
    return value


def format_chf(value: Optional[float]) -> str:
    if value is None:
        return NON_INDIQUE
    # Arrondi au franc si quasi entier, sinon 2 décimales
    if abs(value - round(value)) < 0.005:
        n = int(round(value))
        formatted = f"{n:,}".replace(",", "'")
        return f"CHF {formatted}.–"
    formatted = f"{value:,.2f}".replace(",", "'")
    return f"CHF {formatted}"


def format_duree(years: Optional[int]) -> str:
    if years is None:
        return NON_INDIQUE
    return f"{years} ans"


def _find_compagnie(text: str, filename: str = "") -> Optional[str]:
    hay = _norm(f"{filename}\n{text}")
    best: Optional[Tuple[int, str]] = None
    for label, aliases in COMPAGNIE_ALIASES:
        for alias in aliases:
            # Alias déjà en regex (raw) — ne pas double-échapper
            pattern = alias
            m = re.search(pattern, hay, re.I)
            if not m:
                continue
            score = len(alias) * 10 - m.start() // 200
            if m.start() < 400:
                score += 50
            if re.search(pattern, _norm(filename), re.I):
                score += 80
            if best is None or score > best[0]:
                best = (score, label)
    return best[1] if best else None


_MONEY_RE = r"(?:CHF|Fr\.?|SFr\.?)?\s*([0-9]{1,3}(?:[ '’\u00a0.][0-9]{3})*(?:[.,][0-9]{1,2})?|[0-9]+(?:[.,][0-9]{1,2})?)"


def _amounts_near_keywords(
    text: str,
    keywords: Tuple[str, ...],
    *,
    window: int = 120,
    prefer_monthly: bool = False,
) -> List[Tuple[float, int]]:
    """Retourne (montant, score) pour les montants proches des mots-clés."""
    flat = _norm(text)
    hits: List[Tuple[float, int]] = []
    for kw in keywords:
        for m in re.finditer(re.escape(kw), flat):
            start = max(0, m.start() - 40)
            end = min(len(flat), m.end() + window)
            chunk = flat[start:end]
            for am in re.finditer(_MONEY_RE, chunk, re.I):
                val = _compact_money_token(am.group(1))
                if val is None:
                    continue
                score = 100 - abs(am.start() - (m.end() - start))
                nearby = chunk[max(0, am.start() - 30) : am.end() + 30]
                if prefer_monthly and re.search(r"(mois|/m|mensuel|monthly)", nearby):
                    score += 40
                if prefer_monthly and re.search(r"(an\b|annuel|/a\b|jährlich)", nearby):
                    # Rente annuelle → convertir en mensuelle si clairement annuelle
                    if val > 3000:
                        val = round(val / 12, 2)
                        score += 10
                if not prefer_monthly and re.search(r"(unique|invest|capital|prime|versement|einmal)", nearby):
                    score += 25
                hits.append((val, score))
    hits.sort(key=lambda x: -x[1])
    return hits


def _find_rente_mensuelle(text: str) -> Optional[float]:
    hits = _amounts_near_keywords(
        text,
        (
            "rente mensuelle garantie",
            "rente mensuelle",
            "rente garantie",
            "rente viagere",
            "rente viagère",
            "garantie mensuelle",
            "guaranteed monthly",
            "monatliche rente",
            "garantierte rente",
            "rente / mois",
            "rente/mois",
        ),
        prefer_monthly=True,
    )
    for val, score in hits:
        # Une rente mensuelle 3P est rarement < 50 ni > 50'000
        if 50 <= val <= 50000 and score >= 70:
            return val
    # Fallback : « CHF X.– par mois » / « / mois »
    flat = _norm(text)
    for m in re.finditer(
        _MONEY_RE + r"\s*(?:\.–|.-)?\s*(?:par\s+mois|/ ?mois|\/m(?:ois)?|pro\s+monat)",
        flat,
        re.I,
    ):
        val = _compact_money_token(m.group(1))
        if val is not None and 50 <= val <= 50000:
            return val
    return None


def _find_montant_investi(text: str) -> Optional[float]:
    hits = _amounts_near_keywords(
        text,
        (
            "montant investi",
            "capital investi",
            "prime unique",
            "versement unique",
            "capital initial",
            "montant du placement",
            "investissement",
            "einmalprämie",
            "einmalpraemie",
            "anlagebetrag",
            "investierter betrag",
            "single premium",
            "lump sum",
            "capital versé",
            "capital verse",
            "épargne constituée",
            "epargne constituee",
        ),
        prefer_monthly=False,
        window=140,
    )
    for val, score in hits:
        # Montant investi typique : quelques milliers à millions
        if 1000 <= val <= 20_000_000 and score >= 70:
            return val
    return None


def _find_duree_ans(text: str, filename: str = "") -> Optional[int]:
    hay = f"{filename}\n{text}"
    flat = _norm(hay)
    candidates: List[Tuple[int, int]] = []

    patterns = [
        (r"dur[ée]e(?:\s+du\s+contrat)?(?:\s*[:\-–])?\s*(\d{1,2})\s*ans?", 100),
        (r"(?:pour\s+une\s+)?dur[ée]e\s+de\s+(\d{1,2})\s*ans?", 95),
        (r"(\d{1,2})\s*ans?\s*(?:de\s+)?(?:contrat|placement|investissement|offre)", 90),
        (r"laufzeit(?:\s*[:\-–])?\s*(\d{1,2})\s*(?:jahre|jahr)", 95),
        (r"term(?:\s*[:\-–])?\s*(\d{1,2})\s*years?", 90),
        (r"\b(\d{1,2})\s*ans\b", 40),  # faible : beaucoup de faux positifs
    ]
    for pattern, base in patterns:
        for m in re.finditer(pattern, flat, re.I):
            years = int(m.group(1))
            if years < 3 or years > 50:
                continue
            score = base
            # Bonus si dans le nom de fichier (ex. « Offre 20 ans VD »)
            if re.search(rf"\b{years}\s*ans\b", _norm(filename)):
                score += 80
            # Bonus si près du mot durée / offre
            ctx = flat[max(0, m.start() - 40) : m.end() + 40]
            if re.search(r"dur[ée]e|offre|contrat|laufzeit|term", ctx):
                score += 20
            candidates.append((years, score))

    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[1])
    best_years, best_score = candidates[0]
    if best_score < 70:
        return None
    return best_years


def _find_offre_numero(text: str, filename: str = "") -> Optional[str]:
    hay = f"{filename}\n{text}"
    m = re.search(r"\b(OFF[- ]?\d{4}[- ]?\d{3,6})\b", hay, re.I)
    if not m:
        return None
    raw = re.sub(r"\s+", "", m.group(1).upper().replace(" ", ""))
    raw = raw.replace("OFF", "OFF-", 1) if raw.startswith("OFF") and not raw.startswith("OFF-") else raw
    # Normaliser OFF-2026-00452
    m2 = re.match(r"OFF-?(\d{4})-?(\d{3,6})", raw)
    if m2:
        return f"OFF-{m2.group(1)}-{m2.group(2).zfill(4)}"
    return raw


def _find_labeled_value(text: str, labels: Tuple[str, ...], *, max_len: int = 80) -> Optional[str]:
    flat = text or ""
    for label in labels:
        # Début de ligne, puis repli « Label : valeur » au milieu d'une ligne (PDF aplati).
        patterns = (
            rf"(?:^|\n)\s*{label}\s*[:\-–]?\s*([^\n\r]{{2,{max_len}}})",
            # Ne pas matcher « nom » à l'intérieur de « Prénom ».
            rf"(?<![A-Za-zÀ-ÿ]){label}\s*[:：]\s*([^\n\r]{{2,{max_len}}})",
        )
        for pat in patterns:
            m = re.search(pat, flat, re.I | re.M)
            if not m:
                continue
            val = m.group(1).strip(" \t.:;,-–")
            if val and len(val) >= 2:
                return val
    return None


def _find_date(text: str, labels: Tuple[str, ...]) -> Optional[str]:
    flat = text or ""
    for label in labels:
        pat = (
            rf"(?:^|\n)\s*{label}\s*[:\-–]?\s*"
            rf"(\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}})"
        )
        m = re.search(pat, flat, re.I | re.M)
        if not m:
            continue
        raw = m.group(1).strip()
        return _normalize_date(raw)
    # Dates isolées près de mots-clés
    return None


def _normalize_date(raw: str) -> Optional[str]:
    raw = (raw or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{2,4})$", raw)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000 if y < 70 else 1900
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _find_person_name(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Retourne (prenom, nom)."""
    # « Prénom Nom » après Assuré / Preneur / Client
    for label in (
        r"preneur\s+d['’]?assurance",
        r"assur[ée]e?\b",
        r"client\b",
        r"titulaire",
        r"nom\s+et\s+pr[ée]nom",
        r"pr[ée]nom\s+et\s+nom",
    ):
        m = re.search(
            rf"(?:^|\n)\s*{label}\s*[:\-–]?\s*([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][^\n\r]{{2,60}})",
            text or "",
            re.I | re.M,
        )
        if m:
            parts = re.sub(r"\s+", " ", m.group(1)).strip().split()
            if len(parts) >= 2:
                # Souvent NOM Prénom ou Prénom NOM
                if parts[0].isupper() and not parts[-1].isupper():
                    return parts[-1], parts[0]
                return parts[0], " ".join(parts[1:])
    nom = _find_labeled_value(text, (r"nom(?:\s+de\s+famille)?", r"name\b"), max_len=40)
    prenom = _find_labeled_value(text, (r"pr[ée]nom", r"vorname", r"first\s*name"), max_len=40)
    if nom and prenom:
        return prenom, nom
    return prenom, nom


def _find_adresse_block(text: str) -> Dict[str, Optional[str]]:
    adresse = _find_labeled_value(
        text,
        (r"adresse", r"rue", r"domicile", r"strasse", r"address"),
        max_len=100,
    )
    npa = None
    ville = None
    m = re.search(
        r"(?:^|\n)\s*(?:NPA|CP|PLZ|Code\s*postal)\s*[:\-–]?\s*(\d{4})\b",
        text or "",
        re.I | re.M,
    )
    if m:
        npa = m.group(1)
    m2 = re.search(
        r"(?:^|\n)\s*(?:Ville|Localit[ée]|Ort|City)\s*[:\-–]?\s*([A-Za-zÀ-ÿ' \-]{2,40})",
        text or "",
        re.I | re.M,
    )
    if m2:
        ville = m2.group(1).strip()
    # Pattern « 1000 Lausanne »
    if not npa or not ville:
        m3 = re.search(r"\b(\d{4})\s+([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][A-Za-zÀ-ÿ' \-]{1,40})\b", text or "")
        if m3:
            npa = npa or m3.group(1)
            ville = ville or m3.group(2).strip()
    # Pays uniquement s'il est écrit dans le PDF (un NPA suisse ne suffit pas).
    pays = None
    pays_match = re.search(
        r"(?:^|\n)\s*Pays\s*[:：]\s*([A-Za-zÀ-ÿ' .\-]{2,40})",
        text or "",
        re.I,
    )
    if pays_match:
        pays = pays_match.group(1).strip(" \t.:;,-–") or None
    return {"adresse": adresse, "npa": npa, "ville": ville, "pays": pays}


def _find_police_number(text: str) -> Optional[str]:
    return _find_labeled_value(
        text,
        (
            r"n[°oº]\s*(?:de\s+)?police",
            r"num[ée]ro\s*(?:de\s+)?police",
            r"police\s*n[°oº]?",
            r"contrat\s*n[°oº]?",
            r"policenummer",
            r"policy\s*(?:no|number)",
        ),
        max_len=40,
    )


def _find_prime_annuelle(text: str) -> Optional[float]:
    hits = _amounts_near_keywords(
        text,
        (
            "prime annuelle",
            "prime / an",
            "prime par an",
            "cotisation annuelle",
            "jahresprämie",
            "jahrespraemie",
            "annual premium",
            "montant de la prime",
            "prime totale",
        ),
        prefer_monthly=False,
        window=100,
    )
    for val, score in hits:
        if 100 <= val <= 500_000 and score >= 60:
            return val
    # Mensuelle * 12 si on a une prime mensuelle
    hits_m = _amounts_near_keywords(
        text,
        ("prime mensuelle", "prime / mois", "Monatsprämie", "monthly premium"),
        prefer_monthly=True,
        window=80,
    )
    for val, score in hits_m:
        if 20 <= val <= 20_000 and score >= 70:
            return round(val * 12, 2)
    return None


def _find_periodicite(text: str) -> Optional[str]:
    """Périodicité seulement si le PDF la nomme explicitement."""
    flat = _norm(text or "")
    labeled = _find_labeled_value(
        text or "",
        (r"p[ée]riodicit[ée](?:\s+de\s+la\s+prime)?",),
        max_len=30,
    )
    if labeled:
        low = _norm(labeled)
        for token, label in (
            ("prime unique", "Prime unique"),
            ("mensuel", "Mensuel"),
            ("semestriel", "Semestriel"),
            ("trimestriel", "Trimestriel"),
            ("annuel", "Annuel"),
        ):
            if token in low:
                return label
    if "prime unique" in flat or "versement unique" in flat:
        return "Prime unique"
    if "prime mensuelle" in flat or "cotisation mensuelle" in flat:
        return "Mensuel"
    if "prime semestrielle" in flat:
        return "Semestriel"
    if "prime trimestrielle" in flat:
        return "Trimestriel"
    if "prime annuelle" in flat or "cotisation annuelle" in flat:
        return "Annuel"
    return None


def _find_type_pilier(text: str) -> Optional[str]:
    """3a / 3b seulement si les deux ne sont pas cités ensemble."""
    flat = _norm(text or "")
    has_a = bool(re.search(r"pilier\s*(?:li[ée]\s*)?3\s*a|pr[ée]voyance\s+3\s*a|\b3e?\s*pilier\s+a\b|\b3a\b", flat))
    has_b = bool(re.search(r"pilier\s*(?:libre\s*)?3\s*b|pr[ée]voyance\s+3\s*b|\b3e?\s*pilier\s+b\b|\b3b\b", flat))
    if has_a and not has_b:
        return "3a"
    if has_b and not has_a:
        return "3b"
    return None


def _find_email(text: str) -> Optional[str]:
    raw = _find_labeled_value(text, (r"e-?mail", r"courriel"), max_len=80)
    if not raw:
        return None
    m = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", raw)
    return m.group(0) if m else None


def _find_telephone(text: str) -> Optional[str]:
    return _find_labeled_value(
        text,
        (r"t[ée]l[ée]phone", r"mobile", r"natel", r"t[ée]l\."),
        max_len=30,
    )


def extract_offre_fields(
    pdf_bytes: bytes,
    *,
    filename: str = "",
) -> Dict[str, Any]:
    """
    Analyse un PDF d'offre et retourne des champs structurés.
    Valeurs absentes / peu sûres → None (affichage « Non indiqué »).
    """
    text = ""
    try:
        from pdf_generator import _extract_pdf_text

        text = _extract_pdf_text(pdf_bytes) or ""
    except Exception:
        logger.exception("Lecture texte offre PDF échouée")
        text = ""

    compagnie = _find_compagnie(text, filename)
    rente = _find_rente_mensuelle(text)
    montant = _find_montant_investi(text)
    duree = _find_duree_ans(text, filename)
    prenom, nom = _find_person_name(text)
    addr = _find_adresse_block(text)
    date_naissance = _find_date(
        text,
        (r"date\s+de\s+naissance", r"n[ée]e?\s+le", r"geburtsdatum", r"date\s+of\s+birth"),
    )
    date_debut = _find_date(
        text,
        (r"date\s+de\s+d[ée]but", r"entr[ée]e\s+en\s+vigueur", r"d[ée]but\s+(?:du\s+)?contrat", r"beginn", r"start\s+date"),
    )
    date_fin = _find_date(
        text,
        (r"date\s+de\s+fin", r"[ée]ch[ée]ance", r"fin\s+(?:du\s+)?contrat", r"ablauf", r"end\s+date", r"terme"),
    )
    civilite = _find_labeled_value(text, (r"civilit[ée]", r"anrede", r"title"), max_len=20)
    if civilite:
        c = civilite.casefold()
        if "madame" in c or "frau" in c or c.startswith("mme"):
            civilite = "Madame"
        elif "monsieur" in c or "herr" in c or c.startswith("m."):
            civilite = "Monsieur"

    if not text.strip():
        compagnie = compagnie or _find_compagnie("", filename)
        duree = duree or _find_duree_ans("", filename)

    return {
        "compagnie": compagnie,
        "rente_mensuelle_garantie": rente,
        "montant_investi": montant,
        "duree": duree,
        "compagnie_label": compagnie or NON_INDIQUE,
        "rente_mensuelle_garantie_label": format_chf(rente),
        "montant_investi_label": format_chf(montant),
        "duree_label": format_duree(duree),
        # Champs formulaire CRM
        "numero_offre": _find_offre_numero(text, filename),
        "prenom": prenom,
        "nom": nom,
        "civilite": civilite,
        "date_naissance": date_naissance,
        "adresse": addr.get("adresse"),
        "npa": addr.get("npa"),
        "ville": addr.get("ville"),
        "pays": addr.get("pays"),
        "reference_police": _find_police_number(text),
        "montant_prime": _find_prime_annuelle(text),
        "date_debut": date_debut,
        "date_fin": date_fin,
        "nationalite": _find_labeled_value(text, (r"nationalit[ée]", r"staatsangehörigkeit"), max_len=30),
        "profession": _find_labeled_value(text, (r"profession", r"beruf", r"activit[ée]\s+professionnelle"), max_len=80),
        "email": _find_email(text),
        "telephone": _find_telephone(text),
        "permis": _find_labeled_value(text, (r"permis(?:\s+de\s+s[ée]jour)?",), max_len=40),
        "sexe": _find_labeled_value(text, (r"sexe", r"geschlecht"), max_len=20),
        "statut_professionnel": _find_labeled_value(text, (r"statut\s+professionnel",), max_len=40),
        "fumeur": _find_labeled_value(text, (r"fumeur",), max_len=20),
        "periodicite": _find_periodicite(text),
        "type_pilier": _find_type_pilier(text),
        "_text": text or "",
        "_raw_text_len": len(text or ""),
    }


def map_extract_to_form(
    extracted: Dict[str, Any],
    *,
    form_type: str = "pilier3_legacy",
) -> Dict[str, Any]:
    """
    Mappe l'extraction PDF vers les champs CRM (legacy + form_payload générique).
    """
    form_type = (form_type or "pilier3_legacy").strip() or "pilier3_legacy"
    fields: Dict[str, Any] = {}
    for key in (
        "civilite", "prenom", "nom", "date_naissance", "adresse", "npa", "ville", "pays",
        "nationalite", "date_debut", "montant_prime",
    ):
        val = extracted.get(key)
        if val not in (None, "", NON_INDIQUE):
            fields[key] = val
    if extracted.get("duree") is not None:
        fields["duree_contrat"] = str(extracted["duree"])
    if extracted.get("compagnie"):
        fields["compagnies"] = [extracted["compagnie"]]
    if extracted.get("rente_mensuelle_garantie") is not None:
        fields["rente_invalidite"] = str(extracted["rente_mensuelle_garantie"])
    for extra in ("profession", "email", "telephone", "permis", "sexe", "statut_professionnel", "periodicite"):
        val = extracted.get(extra)
        if val not in (None, "", NON_INDIQUE):
            fields[extra] = val

    # Wizard CRM historique : aliases génériques. Les autres types reçoivent
    # le payload du schéma réel (input_*), identique à une demande classique.
    if form_type == "pilier3_legacy":
        payload = _legacy_alias_payload(extracted)
        filled_keys: List[str] = []
    else:
        from offre_pdf_form_fill import fill_form_payload_from_pdf

        filled = fill_form_payload_from_pdf(
            form_type,
            extracted,
            text=str(extracted.get("_text") or ""),
        )
        payload = filled.get("form_payload") or {}
        filled_keys = list(filled.get("filled_keys") or [])

    return {
        "fields": fields,
        "form_payload": payload,
        "filled_keys": filled_keys,
        "numero_offre": extracted.get("numero_offre"),
        "reference_police": extracted.get("reference_police"),
    }


def _legacy_alias_payload(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Ancien miroir de clés (wizard 3P). Pas utilisé pour les schémas GF."""
    payload: Dict[str, Any] = {}
    mapping_payload = {
        "prenom": ("prenom", "prénom", "vorname", "first_name"),
        "nom": ("nom", "name", "nachname", "last_name"),
        "date_naissance": ("date_naissance", "naissance", "geburtsdatum", "date_of_birth"),
        "adresse": ("adresse", "rue", "strasse", "address"),
        "npa": ("npa", "plz", "code_postal", "zip"),
        "ville": ("ville", "localite", "ort", "city"),
        "compagnie": ("compagnie", "assureur", "gesellschaft", "company"),
        "montant_prime": ("montant_prime", "prime", "premium", "jahresprämie"),
        "date_debut": ("date_debut", "debut", "beginn", "start"),
        "date_fin": ("date_fin", "fin", "ablauf", "end", "echeance"),
        "reference_police": ("numero_police", "n_police", "police", "contrat"),
        "duree": ("duree", "duree_contrat", "laufzeit"),
    }
    for src, aliases in mapping_payload.items():
        val = extracted.get(src)
        if val in (None, "", NON_INDIQUE):
            continue
        for alias in aliases:
            payload[alias] = val
        payload[src] = val
    return payload


def offre_fields_for_storage(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Champs plats à enregistrer sur le document Mongo."""
    return {
        "compagnie": extracted.get("compagnie"),
        "rente_mensuelle_garantie": extracted.get("rente_mensuelle_garantie"),
        "montant_investi": extracted.get("montant_investi"),
        "duree": extracted.get("duree"),
        "offre_extract": {
            "compagnie": extracted.get("compagnie"),
            "rente_mensuelle_garantie": extracted.get("rente_mensuelle_garantie"),
            "montant_investi": extracted.get("montant_investi"),
            "duree": extracted.get("duree"),
            "compagnie_label": extracted.get("compagnie_label") or NON_INDIQUE,
            "rente_mensuelle_garantie_label": extracted.get("rente_mensuelle_garantie_label") or NON_INDIQUE,
            "montant_investi_label": extracted.get("montant_investi_label") or NON_INDIQUE,
            "duree_label": extracted.get("duree_label") or NON_INDIQUE,
            "prenom": extracted.get("prenom"),
            "nom": extracted.get("nom"),
            "date_naissance": extracted.get("date_naissance"),
            "adresse": extracted.get("adresse"),
            "npa": extracted.get("npa"),
            "ville": extracted.get("ville"),
            "reference_police": extracted.get("reference_police"),
            "numero_offre": extracted.get("numero_offre"),
            "montant_prime": extracted.get("montant_prime"),
            "date_debut": extracted.get("date_debut"),
            "date_fin": extracted.get("date_fin"),
        },
    }
