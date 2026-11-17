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
    """Parse un montant CHF saisi sous formes suisses / internationales.

    Gère 1178.50, 1'243.90, 1 243.90, espaces insécables (\\u00a0, \\u202f),
    et ne tronque pas 1178.50 en 117.
    """
    if not raw:
        return None
    s = str(raw).strip()
    s = s.replace("CHF", "").replace("Fr.", "").replace("fr.", "").replace("SFr.", "")
    # Apostrophes / espaces milliers (y compris fine / no-break)
    for ch in ("'", "’", "`", "´", " ", "\u00a0", "\u202f", "\u2009", "\u2007"):
        s = s.replace(ch, "")
    s = s.replace(".–", "").replace(".-", "").replace("–", "").replace("—", "")
    if not s or not re.search(r"\d", s):
        return None
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
        # 1.178.50 (milliers + décimales) → garder la dernière partie décimale
        head, _, dec = s.rpartition(".")
        if len(dec) <= 2 and dec.isdigit():
            s = head.replace(".", "") + "." + dec
        else:
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


# Priorité : (1) milliers suisses avec au moins un groupe, (2) entier/décimal complet.
# Évite de matcher « 117 » dans « 1178.50 ».
_MONEY_RE = (
    r"(?:CHF|Fr\.?|SFr\.?)?\s*"
    r"("
    r"[0-9]{1,3}(?:[ '’\u00a0\u202f\u2009.][0-9]{3})+(?:[.,][0-9]{1,2})?"
    r"|[0-9]+(?:[.,][0-9]{1,2})?"
    r")"
)


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
            "fraction mensuelle",
            "payable par fraction mensuelle",
            "versement annuel, payable par fraction mensuelle",
            "versements reguliers garantis",
            "versements réguliers garantis",
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
    # Vaudoise Serenity : « payable par fraction mensuelle de CHF 4'482.90 »
    m_frac = re.search(
        r"fraction\s+mensuelle\s+de\s+" + _MONEY_RE,
        flat,
        re.I,
    )
    if m_frac:
        val = _compact_money_token(m_frac.group(1))
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


def _find_labeled_value(
    text: str,
    labels: Tuple[str, ...],
    *,
    max_len: int = 80,
    min_len: int = 1,
) -> Optional[str]:
    flat = text or ""
    for label in labels:
        # Début de ligne, puis repli « Label : valeur » au milieu d'une ligne (PDF aplati).
        patterns = (
            rf"(?:^|\n)\s*{label}\s*[:\-–]?\s*([^\n\r]{{{min_len},{max_len}}})",
            # Ne pas matcher « nom » à l'intérieur de « Prénom ».
            rf"(?<![A-Za-zÀ-ÿ]){label}\s*[:：]\s*([^\n\r]{{{min_len},{max_len}}})",
        )
        for pat in patterns:
            m = re.search(pat, flat, re.I | re.M)
            if not m:
                continue
            val = m.group(1).strip(" \t.:;,-–")
            if val and len(val) >= min_len:
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
            # Repli milieu de ligne (PDF aplati, ex. « Né(e) le: 04.07.1967 »)
            pat2 = (
                rf"(?<![A-Za-zÀ-ÿ]){label}\s*[:：]\s*"
                rf"(\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}})"
            )
            m = re.search(pat2, flat, re.I)
        if not m:
            continue
        raw = m.group(1).strip()
        return _normalize_date(raw)
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


_IDENTITY_HEADER_BLOCKLIST = {
    "personne",
    "assurée",
    "assuree",
    "assuré",
    "assure",
    "preneur",
    "cocontractant",
    "broker",
    "service",
    "center",
    "prestations",
    "nos",
    "votre",
    "police",
    "dynamix",
    "financement",
}


def _split_identity_parts(raw: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """(civilite, prenom, nom) depuis une chaîne libre."""
    parts = [p for p in re.sub(r"\s+", " ", raw or "").strip().split() if p]
    civilite = None
    if parts and parts[0].casefold() in {
        "monsieur", "madame", "mademoiselle", "herr", "frau", "fräulein", "fraulein", "mr", "mrs", "ms",
    }:
        tok = parts.pop(0)
        low = tok.casefold()
        if low in {"madame", "frau", "mrs", "ms"}:
            civilite = "Madame"
        elif low in {"mademoiselle", "fräulein", "fraulein"}:
            civilite = "Mademoiselle"
        else:
            civilite = "Monsieur"
    # Retirer un « nom » parasite collé (« Prénom, nom Monsieur X »)
    if parts and parts[0].casefold() in {"nom", "name"}:
        parts = parts[1:]
    # Rejeter libellés de section capturés comme identité
    if parts and any(p.casefold().strip("()") in _IDENTITY_HEADER_BLOCKLIST for p in parts[:2]):
        return civilite, None, None
    if len(parts) >= 2:
        # « May Jean-Yves » (NOM Prénom composé) fréquent chez AXA
        if len(parts) == 2 and "-" in parts[1] and "-" not in parts[0]:
            return civilite, parts[1], parts[0]
        if parts[0].isupper() and not parts[-1].isupper() and len(parts[0]) > 1:
            return civilite, parts[-1], parts[0]
        return civilite, parts[0], " ".join(parts[1:])
    if len(parts) == 1:
        return civilite, parts[0], None
    return civilite, None, None


def _find_person_name(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Retourne (prenom, nom)."""
    flat = text or ""

    # Vaudoise Serenity : « Prénom, nom Monsieur Benoit Stempfel »
    m_combo = re.search(
        r"(?:^|\n)\s*pr[ée]nom\s*[,/]\s*nom\s*[:\-–]?\s*([^\n\r]{3,80})",
        flat,
        re.I | re.M,
    )
    if m_combo:
        _civ, prenom, nom = _split_identity_parts(m_combo.group(1))
        if prenom and nom:
            return prenom, nom

    m_combo2 = re.search(
        r"(?:^|\n)\s*pr[ée]nom\s+et\s+nom\s*[:\-–]?\s*([^\n\r]{3,80})",
        flat,
        re.I | re.M,
    )
    if m_combo2:
        _civ, prenom, nom = _split_identity_parts(m_combo2.group(1))
        if prenom and nom:
            return prenom, nom

    # « Prénom Nom » après Assuré / Preneur / Client / Cocontractant (début de ligne OU inline)
    for label in (
        r"preneur\s+d['’]?assurance",
        r"cocontractant",
        r"personne\s+assur[ée]e",
        r"assur[ée]e?\b",
        r"client\b",
        r"titulaire",
        r"nom\s+et\s+pr[ée]nom",
        r"pr[ée]nom\s+et\s+nom",
    ):
        patterns = (
            rf"(?:^|\n)\s*{label}\s*[:\-–]?\s*([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][^\n\r]{{2,60}})",
            rf"(?<![A-Za-zÀ-ÿ]){label}\s*[:\-–]?\s*([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][^\n\r]{{2,60}})",
        )
        for pat in patterns:
            m = re.search(pat, flat, re.I | re.M)
            if not m:
                continue
            raw = m.group(1).strip()
            # Couper si collé à une autre rubrique (adresse agence, etc.)
            raw = re.split(r"\s{2,}|(?<=\d)\s+(?=[A-Z])|NPA|T[ée]l[ée]phone|E-?mail", raw)[0].strip()
            _civ, prenom, nom = _split_identity_parts(raw)
            if prenom and nom:
                return prenom, nom

    nom = _find_labeled_value(
        text,
        (
            r"(?<![A-Za-zÀ-ÿ,])nom(?:\s+de\s+famille)?(?!\s*,)",
            r"(?<![A-Za-z])name\b",
        ),
        max_len=40,
    )
    prenom = _find_labeled_value(
        text,
        (
            r"pr[ée]nom(?!\s*[,/])",
            r"vorname",
            r"first\s*name",
        ),
        max_len=40,
    )
    # Éviter « nom Monsieur … » capturé comme prénom via libellé ambigu
    if prenom and re.match(r"(?i)^nom\b", prenom.strip()):
        prenom = None
    if nom and prenom:
        return prenom, nom
    return prenom, nom


_INSURER_HEADER_CITIES = {
    "zurich",
    "zürich",
    "wallisellen",
    "basel",
    "genève",
    "geneve",
    "bern",
    "berne",
}


def _looks_like_insurer_address(npa: Optional[str], ville: Optional[str], ctx: str = "") -> bool:
    flat_ville = _norm(ville or "")
    flat_ctx = _norm(ctx)
    if flat_ville in _INSURER_HEADER_CITIES and re.search(
        r"elvia|allianz|service\s+center|postfach|assureur|porteur\s+du\s+risque",
        flat_ctx,
    ):
        return True
    if npa == "8010" and "zurich" in flat_ville:
        return True
    return False


def _ctx_is_agency_contact(ctx: str) -> bool:
    """True si le contexte est le bloc Contact / agence (pas l'adresse client)."""
    flat = _norm(ctx)
    return bool(
        re.search(
            r"votre\s+conseiller|agence\s+g[ée]n[ée]rale|contact\b|"
            r"bureau\s+de\s+vente|service\s+comp[ée]tent|"
            r"place\s+de\s+milan|vaudoise\.ch|axa\.ch|winterthur|"
            r"broker\s+service",
            flat,
        )
    )


def _find_adresse_block(text: str) -> Dict[str, Optional[str]]:
    """Priorise l'adresse du preneur / détenteur ; ignore l'en-tête assureur / agence."""
    adresse = None
    npa = None
    ville = None
    raw = text or ""

    # 1) Bloc PRENEUR D'ASSURANCE « RUE, NPA VILLE »
    m_preneur = re.search(
        r"PRENEUR\s+D['’]?ASSURANCE\s+[^\n]+\s+([A-Z0-9][^\n,]{3,60}),\s*(\d{4})\s+([A-Za-zÀ-ÿ' \-]{2,40})",
        raw,
        re.I,
    )
    if m_preneur:
        adresse = re.sub(r"\s+", " ", m_preneur.group(1)).strip()
        npa = m_preneur.group(2)
        ville = m_preneur.group(3).strip()

    # 2) Détenteur / conducteur multi-lignes
    if not npa or not ville:
        m_det = re.search(
            r"(?:D[ÉE]TENTEUR|CONDUCTEUR\s+PRINCIPAL)\s*\n"
            r"[A-Za-zÀ-ÿ' \-]{2,40}\s*\n"
            r"([A-Za-zÀ-ÿ0-9' \-]{3,60})\s*\n"
            r"(\d{4})\s+([A-Za-zÀ-ÿ' \-]{2,40})",
            raw,
            re.I,
        )
        if m_det:
            adresse = adresse or m_det.group(1).strip()
            npa = npa or m_det.group(2)
            ville = ville or m_det.group(3).strip()

    # Adresse AXA / letter : ligne après le nom du preneur (ex. Route de la Croix 10 / 1948 Sarreyer)
    if not adresse or not npa:
        m_letter = re.search(
            r"(?:Monsieur|Madame|Mademoiselle)\s*\n"
            r"[A-Za-zÀ-ÿ' \-]{2,50}\s*\n"
            r"([A-Za-zÀ-ÿ0-9' \-]{3,60})\s*\n"
            r"(\d{4})\s+([A-Za-zÀ-ÿ' \-]{2,40})",
            raw,
            re.I,
        )
        if m_letter and not _ctx_is_agency_contact(raw[max(0, m_letter.start() - 80) : m_letter.end()]):
            adresse = adresse or m_letter.group(1).strip()
            npa = npa or m_letter.group(2)
            ville = ville or m_letter.group(3).strip()

    if not adresse:
        for m_addr in re.finditer(
            r"(?:^|\n)\s*(?:Adresse|Rue|Domicile|Strasse|Address)\s*[:\-–]?\s*([^\n\r]{3,100})",
            raw,
            re.I | re.M,
        ):
            ctx = raw[max(0, m_addr.start() - 120) : m_addr.end() + 40]
            if _ctx_is_agency_contact(ctx):
                continue
            adresse = m_addr.group(1).strip(" \t.:;,-–")
            break

    if not npa:
        for m in re.finditer(
            r"(?:^|\n)\s*(?:NPA|CP|PLZ|Code\s*postal|NPA\s*-\s*Localit[ée])\s*[:\-–]?\s*(\d{4})\b",
            raw,
            re.I | re.M,
        ):
            ctx = raw[max(0, m.start() - 120) : m.end() + 40]
            if _ctx_is_agency_contact(ctx):
                continue
            npa = m.group(1)
            # Ville éventuellement collée : « 1204 Genève » (pas « 1000\nVille »)
            m_ville_inline = re.search(
                rf"{re.escape(npa)}\s+([A-Za-zÀ-ÿ' \-]{{2,40}})",
                raw[m.start() : m.start() + 80],
            )
            if m_ville_inline and not ville:
                cand_v = m_ville_inline.group(1).strip()
                if cand_v.casefold() not in {
                    "ville", "localité", "localite", "ort", "city", "npa", "adresse",
                }:
                    ville = cand_v
            break
    if not ville:
        for m2 in re.finditer(
            r"(?:^|\n)\s*(?:Ville|Localit[ée]|Ort|City)\s*[:\-–]?\s*([A-Za-zÀ-ÿ' \-]{2,40})",
            raw,
            re.I | re.M,
        ):
            ctx = raw[max(0, m2.start() - 120) : m2.end() + 40]
            if _ctx_is_agency_contact(ctx):
                continue
            cand = m2.group(1).strip()
            if re.search(r"(?i)\bwww\b|\.ch\b", cand):
                continue
            ville = cand
            break

    def _plausible_swiss_npa(cand: str) -> bool:
        if not cand or not cand.isdigit() or len(cand) != 4:
            return False
        # Années (éditions / dates) ≠ NPA suisses typiques hors plage postale
        n = int(cand)
        if 1900 <= n <= 2099:
            return False
        return 1000 <= n <= 9999

    def _plausible_ville(cand: str) -> bool:
        if not cand or len(cand) < 2 or len(cand) > 40:
            return False
        if re.search(
            r"(?i)\b(www|cette|offre|tarif|valeur|édition|edition|agence|établi|"
            r"naissance|nationalit|conseiller|cocontractant|de\s+naissance)\b",
            cand,
        ):
            return False
        if len(cand.split()) > 4:
            return False
        return True

    # Pattern « 1000 Lausanne » — ignorer en-tête assureur (8010 Zürich ELVIA) et pied Vaudoise
    if not npa or not ville:
        for m3 in re.finditer(
            r"\b(\d{4})\s+([A-ZÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ][A-Za-zÀ-ÿ' \-]{1,40})\b",
            raw,
        ):
            cand_npa, cand_ville = m3.group(1), m3.group(2).strip()
            ctx = raw[max(0, m3.start() - 80) : m3.end() + 40]
            if not _plausible_swiss_npa(cand_npa) or not _plausible_ville(cand_ville):
                continue
            if _looks_like_insurer_address(cand_npa, cand_ville, ctx) or _ctx_is_agency_contact(ctx):
                continue
            npa = npa or cand_npa
            ville = ville or cand_ville
            break

    if npa and not _plausible_swiss_npa(str(npa)):
        npa = None
    if ville and not _plausible_ville(str(ville)):
        ville = None

    if npa and ville and (
        _looks_like_insurer_address(npa, ville, raw) or _ctx_is_agency_contact(f"{adresse or ''} {ville}")
    ):
        # Dernier filet : ne pas renvoyer l'adresse assureur/agence comme preneur
        if not m_preneur:
            npa, ville, adresse = None, None, None

    pays = None
    pays_match = re.search(
        r"(?:^|\n)\s*Pays\s*[:：]\s*([A-Za-zÀ-ÿ' .\-]{2,40})",
        raw,
        re.I,
    )
    if pays_match:
        pays = pays_match.group(1).strip(" \t.:;,-–") or None
    return {"adresse": adresse, "npa": npa, "ville": ville, "pays": pays}


def _find_police_number(text: str) -> Optional[str]:
    raw = text or ""
    # AXA / Zurich : « Police de prévoyance n° L50 1404842 »
    m_prev = re.search(
        r"police\s+de\s+pr[ée]voyance\s*n[°oº]?\s*([A-Z0-9][A-Z0-9./]*\s*[0-9][A-Z0-9./]*)",
        raw,
        re.I,
    )
    if m_prev:
        return re.sub(r"\s+", " ", m_prev.group(1)).strip(" \t.:;,-–") or None
    labeled = _find_labeled_value(
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
    if labeled:
        labeled = re.split(r"\s*[-–]\s*pr[ée]voyance|\s{2,}", labeled, maxsplit=1)[0].strip()
        # Écarter OCR bruité / libellés de formulaire
        if re.search(
            r"(?i)mail|internet|téléphone|telephone|preneur|agence|conseiller|cocontractant",
            labeled,
        ):
            labeled = None
        elif not re.search(r"[0-9A-Za-z]", labeled or ""):
            labeled = None
        if labeled:
            return labeled
    # Vaudoise Serenity : « N° 86510062000281065 » près de l'offre / cocontractant
    m_offre = re.search(
        r"(?:^|\n)\s*N[°oº]\s*([0-9]{10,20})\b",
        raw,
        re.I | re.M,
    )
    if m_offre:
        return m_offre.group(1).strip()
    return None


def _find_prime_annuelle(text: str) -> Optional[float]:
    flat = text or ""
    # Priorité : prime TTC / avec redevances (ex. ELVIA 1243.90), une seule fois.
    m_tax = re.search(
        r"PRIME\s+ANNUELLE\s+AVEC\s+REDEVANCES[^0-9\n]{0,80}" + _MONEY_RE,
        flat,
        re.I,
    )
    if m_tax:
        val = _compact_money_token(m_tax.group(1))
        if val is not None and 20 <= val <= 500_000:
            return val
    m_brute = re.search(
        r"PRIME\s+ANNUELLE(?!\s+AVEC)\s+" + _MONEY_RE,
        flat,
        re.I,
    )
    if m_brute:
        val = _compact_money_token(m_brute.group(1))
        if val is not None and 20 <= val <= 500_000:
            return val

    hits = _amounts_near_keywords(
        text,
        (
            "prime annuelle avec redevances",
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


_INSURER_CONTACT_BLOCKLIST = (
    "0800666222",
    "0800055088",
    "+41433119990",
    "0433119990",
    "contact@elvia.ch",
    "vaudoise.ch",
    "axa.ch",
    "zurich.ch",
    "elvia.ch",
    "allianz.ch",
    "helvetia.ch",
    "geneve@vaudoise",
    "services.el@axa",
    "prevoyance@axa",
)


def _is_insurer_contact(value: str, ctx: str = "") -> bool:
    low = (value or "").lower()
    compact = re.sub(r"[\s./-]", "", low)
    for b in _INSURER_CONTACT_BLOCKLIST:
        b_low = b.lower()
        if b_low in low or re.sub(r"[\s./-]", "", b_low) in compact:
            return True
    if _ctx_is_agency_contact(ctx):
        return True
    flat_ctx = _norm(ctx)
    if re.search(r"sinistre|service\s+center|elvia\.ch|assureur\s+et\s+porteur", flat_ctx):
        return True
    if compact.endswith("@elvia.ch") or "sinistre@" in compact:
        return True
    return False


def _find_email(text: str) -> Optional[str]:
    raw = _find_labeled_value(text, (r"e-?mail", r"courriel"), max_len=80)
    if not raw:
        return None
    m = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", raw)
    if not m:
        return None
    email = m.group(0)
    if _is_insurer_contact(email, raw):
        return None
    return email


def _find_telephone(text: str) -> Optional[str]:
    flat = text or ""
    for label in (r"t[ée]l[ée]phone", r"mobile", r"natel", r"t[ée]l\."):
        for m in re.finditer(
            rf"(?:^|\n)\s*{label}\s*[:\-–]?\s*([^\n\r]{{7,30}})",
            flat,
            re.I | re.M,
        ):
            val = m.group(1).strip(" \t.:;,-–")
            ctx = flat[max(0, m.start() - 100) : m.end() + 40]
            if not val or _is_insurer_contact(val, ctx):
                continue
            if not re.search(r"\d{2}", val):
                continue
            if re.search(r"(?i)mail|internet|lnternet|e-?mail", val):
                continue
            return val
    return None


def extract_offre_fields(
    pdf_bytes: bytes,
    *,
    filename: str = "",
) -> Dict[str, Any]:
    """
    Analyse un PDF d'offre et retourne des champs structurés.
    Valeurs absentes / peu sûres → None (affichage « Non indiqué »).
    Ne jamais inventer : en cas d'incertitude → None.
    """
    text = ""
    try:
        from pdf_generator import _extract_pdf_text

        text = _extract_pdf_text(pdf_bytes) or ""
    except Exception:
        logger.exception("Lecture texte offre PDF échouée")
        text = ""

    # Phase 4 : normalisation multi-compagnies (synonymes / formats) avant parsing.
    company_id = None
    adapter_notes: list = []
    try:
        from offre_extract_company_adapters import prepare_text_for_extraction

        text, company_id, adapter_notes = prepare_text_for_extraction(text, filename)
    except Exception:
        logger.exception("Adaptateur compagnie indisponible — texte brut")

    # Phase 1 : extraction structurée (multi-branches) puis aplatissement sûr.
    structured = None
    structured_flat: Dict[str, Any] = {}
    try:
        from offre_extract_structured import extract_structured_offre, structured_to_flat_extracted

        structured = extract_structured_offre(pdf_bytes, filename=filename, text=text)
        if isinstance(structured, dict):
            meta = structured.setdefault("meta", {})
            if company_id:
                meta["company_adapter"] = company_id
            if adapter_notes:
                meta.setdefault("notes", []).extend(adapter_notes)
        structured_flat = structured_to_flat_extracted(structured)
    except Exception:
        logger.exception("Extraction structurée indisponible — repli legacy")

    compagnie = structured_flat.get("compagnie") or _find_compagnie(text, filename)
    rente = _find_rente_mensuelle(text)
    montant = _find_montant_investi(text)
    duree = _find_duree_ans(text, filename)
    prenom, nom = _find_person_name(text)
    # Ne pas écraser un parsing 3P correct par un prénom structuré trop large
    # (ex. lettre AXA / cocontractant déjà résolus).
    if structured_flat.get("prenom") and not prenom:
        prenom = structured_flat["prenom"]
    elif structured_flat.get("prenom") and prenom:
        # Prefer structured only if legacy looks broken
        if re.match(r"(?i)^(nom|de|du|le)\b", str(prenom)) or "(" in str(prenom):
            prenom = structured_flat["prenom"]
    if structured_flat.get("nom") and not nom:
        nom = structured_flat["nom"]
    addr = _find_adresse_block(text)
    # Adresse structurée (auto) prioritaire ; sinon éviter d'écraser un nettoyage 3P
    if structured_flat.get("npa") and (structured_flat.get("form_type_suggere") or "").startswith("vehic"):
        addr["npa"] = structured_flat["npa"]
    elif structured_flat.get("npa") and not addr.get("npa"):
        addr["npa"] = structured_flat["npa"]
    if structured_flat.get("ville") and (structured_flat.get("form_type_suggere") or "").startswith("vehic"):
        addr["ville"] = structured_flat["ville"]
    elif structured_flat.get("ville") and not addr.get("ville"):
        addr["ville"] = structured_flat["ville"]
    if structured_flat.get("adresse") and (structured_flat.get("form_type_suggere") or "").startswith("vehic"):
        addr["adresse"] = structured_flat["adresse"]
    elif structured_flat.get("adresse") and not addr.get("adresse"):
        addr["adresse"] = structured_flat["adresse"]
    # Voyage / multi-véhicules : toujours prendre le bloc preneur structuré
    if (structured_flat.get("form_type_suggere") or "") == "voyage":
        for k in ("npa", "ville", "adresse"):
            if structured_flat.get(k):
                addr[k] = structured_flat[k]

    date_naissance = structured_flat.get("date_naissance") or _find_date(
        text,
        (
            r"date\s+de\s+naissance",
            r"n[ée]\(?e?\)?\s*le",
            r"n[ée]e?\s+le",
            r"geburtsdatum",
            r"date\s+of\s+birth",
        ),
    )
    date_debut = structured_flat.get("date_debut") or _find_date(
        text,
        (
            r"date\s+d['’]?effet",
            r"date\s+de\s+d[ée]but",
            r"entr[ée]e\s+en\s+vigueur",
            r"d[ée]but\s+(?:du\s+)?contrat",
            r"beginn",
            r"start\s+date",
            r"valable\s+[àa]\s+partir\s+du",
            r"nouvelle\s+couverture\s+d[eè]s\s+le",
        ),
    )
    date_fin = structured_flat.get("date_fin") or _find_date(
        text,
        (r"date\s+de\s+fin", r"[ée]ch[ée]ance", r"fin\s+(?:du\s+)?contrat", r"ablauf", r"end\s+date", r"terme", r"expiration\s+de\s+l['’]?assurance"),
    )
    # Vaudoise : « Date d'effet - Echéance 01.11.2026 - 31.10.2041 »
    if not date_debut or not date_fin:
        m_eff = re.search(
            r"date\s+d['’]?effet\s*[-–]\s*[ée]ch[ée]ance\s+"
            r"(\d{1,2}[./]\d{1,2}[./]\d{2,4})\s*[-–]\s*(\d{1,2}[./]\d{1,2}[./]\d{2,4})",
            text or "",
            re.I,
        )
        if m_eff:
            date_debut = date_debut or _normalize_date(m_eff.group(1))
            date_fin = date_fin or _normalize_date(m_eff.group(2))

    civilite = structured_flat.get("civilite") or _find_labeled_value(text, (r"civilit[ée]", r"anrede", r"title"), max_len=20)
    if not civilite:
        m_civ_line = re.search(
            r"(?:^|\n)\s*pr[ée]nom\s*(?:[,/]|et)\s*nom\s*[:\-–]?\s*(Monsieur|Madame|Mademoiselle)\b",
            text or "",
            re.I | re.M,
        )
        if m_civ_line:
            civilite = m_civ_line.group(1)
    if civilite:
        c = civilite.casefold()
        if "madame" in c or "frau" in c or c.startswith("mme"):
            civilite = "Madame"
        elif "monsieur" in c or "herr" in c or c.startswith("m."):
            civilite = "Monsieur"

    if not text.strip():
        compagnie = compagnie or _find_compagnie("", filename)
        duree = duree or _find_duree_ans("", filename)

    montant_prime = structured_flat.get("montant_prime")
    if montant_prime is None:
        montant_prime = _find_prime_annuelle(text)
    periodicite_val = structured_flat.get("periodicite") or _find_periodicite(text)
    # Produits 3P à prime unique : exposer le capital investi comme montant_prime CRM
    # si aucune cotisation annuelle n'est présente (Serenity / capitalisation).
    if montant_prime is None and montant is not None and (
        periodicite_val == "Prime unique" or "prime unique" in _norm(text)
    ):
        montant_prime = montant

    telephone = structured_flat.get("telephone")
    if telephone and _is_insurer_contact(str(telephone), text[:800] if text else ""):
        telephone = None
    if telephone is None:
        telephone = _find_telephone(text)
    email = structured_flat.get("email")
    if email and _is_insurer_contact(str(email), text[:800] if text else ""):
        email = None
    if email is None:
        email = _find_email(text)

    permis = structured_flat.get("permis")
    if permis is None:
        permis = _find_labeled_value(text, (r"permis\s+de\s+s[ée]jour", r"permis(?:\s+de\s+s[ée]jour)?"), max_len=40, min_len=1)

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
        "pays": addr.get("pays") or structured_flat.get("pays"),
        "reference_police": structured_flat.get("reference_police") or _find_police_number(text),
        "montant_prime": montant_prime,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "nationalite": structured_flat.get("nationalite")
        or _find_labeled_value(text, (r"nationalit[ée]", r"staatsangehörigkeit"), max_len=30),
        "profession": _find_labeled_value(text, (r"profession", r"beruf", r"activit[ée]\s+professionnelle"), max_len=80),
        "email": email,
        "telephone": telephone,
        "permis": permis,
        "date_permis_conduire": structured_flat.get("date_permis_conduire"),
        "sexe": _find_labeled_value(text, (r"sexe", r"geschlecht"), max_len=20),
        "statut_professionnel": _find_labeled_value(text, (r"statut\s+professionnel",), max_len=40),
        "fumeur": _find_labeled_value(text, (r"fumeur",), max_len=20),
        "periodicite": periodicite_val,
        "type_pilier": _find_type_pilier(text),
        "objets": structured_flat.get("objets") or [],
        "form_type_suggere": structured_flat.get("form_type_suggere"),
        "structured": structured,
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
    Couche mapping : n'altère pas les JSON de formulaires.
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
        fields["rente_mensuelle_garantie"] = extracted["rente_mensuelle_garantie"]
    if extracted.get("montant_investi") is not None:
        fields["montant_investi"] = extracted["montant_investi"]
    if extracted.get("type_pilier"):
        fields["type_pilier"] = extracted["type_pilier"]
    for extra in ("profession", "email", "telephone", "permis", "sexe", "statut_professionnel", "periodicite"):
        val = extracted.get(extra)
        if val not in (None, "", NON_INDIQUE):
            fields[extra] = val

    # Wizard CRM historique : aliases génériques. Les autres types reçoivent
    # le payload du schéma réel (input_*), identique à une demande classique.
    field_statuses: Dict[str, Any] = {}
    skipped_existing_keys: List[str] = []
    if form_type == "pilier3_legacy":
        payload = _legacy_alias_payload(extracted)
        filled_keys: List[str] = []
        objet_hints: Dict[str, Any] = {}
        try:
            from offre_extract_structured import map_objets_to_voyage_hints

            objet_hints = map_objets_to_voyage_hints(list(extracted.get("objets") or []))
        except Exception:
            objet_hints = {}
    else:
        from offre_pdf_form_map import map_structured_to_form_payload

        filled = map_structured_to_form_payload(
            form_type,
            extracted,
            text=str(extracted.get("_text") or ""),
        )
        payload = filled.get("form_payload") or {}
        filled_keys = list(filled.get("filled_keys") or [])
        field_statuses = filled.get("field_statuses") or {}
        objet_hints = filled.get("objet_hints") or {}
        skipped_existing_keys = list(filled.get("skipped_existing_keys") or [])

    return {
        "fields": fields,
        "form_payload": payload,
        "filled_keys": filled_keys,
        "field_statuses": field_statuses,
        "skipped_existing_keys": skipped_existing_keys,
        "numero_offre": extracted.get("numero_offre"),
        "reference_police": extracted.get("reference_police"),
        "objets": extracted.get("objets") or [],
        "objet_hints": objet_hints,
        "form_type_suggere": extracted.get("form_type_suggere"),
        "structured": extracted.get("structured"),
        "extract_audit": (extracted.get("structured") or {}).get("audit") if isinstance(extracted.get("structured"), dict) else None,
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
    """Champs plats à enregistrer sur le document Mongo (+ snapshot audit Phase 1)."""
    structured = extracted.get("structured") if isinstance(extracted.get("structured"), dict) else None
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
            "form_type_suggere": extracted.get("form_type_suggere"),
            "objets_count": len(extracted.get("objets") or []),
        },
        "offre_extract_structured": structured,
        "offre_extract_audit": (structured or {}).get("audit") if structured else None,
    }
