"""Listes Excel des campagnes LAMal.

Chaque ligne non vide devient un contact de campagne, avec un brouillon.
Les montants viennent des primes OFSP déjà chargées. Aucun envoi SMTP.
"""
from __future__ import annotations

import html
import io
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import openpyxl

from lamal.engine import (
    ACCIDENT_WITH,
    ORDINARY_SUBGROUP,
    Catalog,
    Offer,
    _offer_allowed,
    age_class_for_birth_year,
    fold_name,
    load_catchment,
    load_localities_path,
    load_region_xlsx,
    load_tariff_names,
    money_str,
    resolve_residence,
    scan_premium_csv,
    valid_email,
)

YEAR = 2027
FRANCHISES = (300, 2500)
MODELS = (
    ("PRAXIS", "Médecin de famille"),
    ("TEL_DIG", "Télémédecine"),
    ("FLEX", "Flexible"),
)
MODEL_LABELS = dict(MODELS)
MISSING = "—"
UNAVAILABLE_CELL = "non disponible"
ACCIDENT_NOTE = (
    "Primes officielles OFSP 2027 avec couverture accidents. "
    "Le fichier Excel ne contient pas ce paramètre."
)
# À remplir par Cemile. Tant que c'est vide, l'encart n'a pas de lien.
CALENDLY_LAMAL_URL = ""
PRIMEINFO_URL_MISSING = (
    "Page Priminfo de l'assureur à partir de son numéro OFSP. "
    "Ce schéma d'URL n'est pas dans LeoSoft ni dans Praemien_CH.csv ou Tarife.csv."
)
EMAIL_SUBJECT = "Votre comparatif personnalisé des primes LAMal 2027 – Agence Mendes"
DEFAULT_INTRO = (
    "Vous trouverez ci-dessous notre comparatif des primes d'assurance-maladie de base "
    "(LAMal) pour 2027, selon les compagnies, les modèles de soins et les franchises sélectionnés."
)
DEFAULT_CLOSING = (
    "Nous restons à votre disposition pour toute question ou précision concernant ce comparatif.\n\n"
    "Belle journée !\n"
    "L'équipe Agence Mendes"
)
RESERVE_NOTE = (
    "Les primes sont indiquées en CHF par mois, avec couverture accidents, "
    "sous réserve de confirmation des tarifs et des conditions propres à chaque offre."
)
CHILD_FRANCHISE_2500 = (
    "La franchise 2’500 n’existe pas pour un enfant (plafond officiel 600 CHF)."
)
UNAVAILABLE = "Comparatif indisponible : veuillez vérifier les informations de ce contact."
MAIL_NAVY = "#1B4F72"
MAIL_TURQUOISE = "#148C9E"
MAIL_PAGE = "#F4F6F7"
MAIL_ZEBRA = "#F7F8F9"
MAIL_INK = "#333333"
MAIL_MUTED = "#6B7280"
COMPARATIF_LABELS = {
    "non_calcule": "Non calculé",
    "calcul_en_cours": "Calcul en cours",
    "calcule": "Calculé",
    "incomplet": "Incomplet",
    "erreur": "Erreur",
    "a_recalculer": "À recalculer",
}
BROUILLON_LABELS = {
    "non_genere": "Non généré",
    "brouillon": "Brouillon enregistré",
    "a_verifier": "À vérifier",
    "valide": "Validé",
}
SEND_REFUSAL = "Mode préparation : aucun e-mail de cette campagne ne peut être envoyé."

OFSP_DIR = Path(__file__).resolve().parents[1] / "data" / "ofsp"

_ALIAS_ROWS = (
    ("prenom", "prenom", 10),
    ("nom de famille", "nom", 20),
    ("nom", "nom", 10),
    ("date de naissance", "naissance", 20),
    ("date naissance", "naissance", 15),
    ("naissance", "naissance", 10),
    ("age", "age", 10),
    ("npa", "npa", 20),
    ("code postal", "npa", 20),
    ("plz", "npa", 10),
    ("lieu", "lieu", 20),
    ("commune", "lieu", 20),
    ("localite", "lieu", 15),
    ("ville", "lieu", 10),
    ("email", "email", 20),
    ("e mail", "email", 20),
    ("mail", "email", 10),
    ("courriel", "email", 15),
    ("compagnie d assurances", "assureur", 20),
    ("compagnie d assurance", "assureur", 20),
    ("caisse maladie", "assureur", 15),
    ("caisse", "assureur", 10),
    ("assureur", "assureur", 10),
    ("ligne d adresse 1", "adresse", 20),
    ("adresse", "adresse", 10),
    ("complement d adresse", "complement", 20),
    ("adresse 2", "complement", 15),
    ("ligne d adresse 2", "complement", 20),
    ("canton", "canton", 10),
    ("numero de portable", "telephone", 20),
    ("telephone", "telephone", 10),
    ("numero prive", "telephone_prive", 10),
    ("numero de police", "police", 15),
)
ALIASES = {name: (field, rank) for name, field, rank in _ALIAS_ROWS}

_CACHE: dict = {}


def parse_workbook(payload: bytes) -> dict:
    """Lit un classeur. Ignore les feuilles sans colonnes reconnues et les lignes vides."""
    if not payload:
        raise ValueError("Fichier vide")
    workbook = openpyxl.load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    contacts: list[dict] = []
    skipped_empty = 0
    duplicates_skipped = 0
    headers: list[str] = []
    seen: set[tuple] = set()
    matched = False
    try:
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            header_index, mapping = _find_header(rows)
            if mapping is None:
                continue
            matched = True
            if not headers:
                headers = [str(cell).strip() for cell in rows[header_index] if cell not in (None, "")]
            header_cells = rows[header_index]
            for offset, raw in enumerate(rows[header_index + 1:], start=header_index + 2):
                record = _record_from_row(raw, mapping, header_cells, offset)
                if record is None:
                    skipped_empty += 1
                    continue
                key = _person_key(record)
                if key and key in seen:
                    duplicates_skipped += 1
                    continue
                if key:
                    seen.add(key)
                contacts.append(record)
    finally:
        workbook.close()
    if not matched:
        raise ValueError(
            "Colonnes non reconnues. Attendu : prénom, nom, date de naissance, NPA, lieu, e-mail."
        )
    return {
        "contacts": contacts,
        "skipped_empty": skipped_empty,
        "duplicates_skipped": duplicates_skipped,
        "headers": headers,
    }


def load_ofsp_catalog(directory: Optional[Path] = None) -> Optional[Catalog]:
    """Charge les fichiers officiels s'ils sont tous présents. None si le tarif manque."""
    directory = Path(directory) if directory else OFSP_DIR
    paths = (
        directory / "Praemien_CH.csv",
        directory / "Praemienregionen_2027.xlsx",
        directory / "ortschaften.zip",
        directory / "Tarife.csv",
        directory / "Einzugsgebiete.csv",
    )
    if any(not path.exists() for path in paths):
        return None
    stamp = tuple(path.stat().st_mtime_ns for path in paths)
    cached = _CACHE.get(str(directory))
    if cached and cached[0] == stamp:
        return cached[1]
    report, offers = scan_premium_csv(paths[0], tariff_year=YEAR)
    if not report.ok:
        raise ValueError("Fichier de primes OFSP illisible : " + "; ".join(report.errors[:5]))
    catalog = Catalog(
        year=YEAR,
        offers=offers,
        localities=load_localities_path(paths[2]),
        regions_by_bfs=load_region_xlsx(paths[1]),
        tariff_names=load_tariff_names(paths[3]),
        catchment=load_catchment(paths[4]),
        source={"premiums": str(paths[0].name), "year": YEAR, "stamp": "-".join(str(part) for part in stamp)},
    )
    _CACHE[str(directory)] = (stamp, catalog, build_premium_index(catalog))
    return catalog


def premium_index_for(catalog: Optional[Catalog]) -> dict:
    if catalog is None:
        return {}
    cached = _CACHE.get(str(OFSP_DIR))
    if cached and len(cached) == 3 and cached[1] is catalog:
        return cached[2]
    return build_premium_index(catalog)


def build_premium_index(catalog: Catalog) -> dict[tuple, list[Offer]]:
    index: dict[tuple, list[Offer]] = {}
    allowed_models = set(MODEL_LABELS)
    for offer in catalog.offers.values():
        if offer.accident != ACCIDENT_WITH:
            continue
        if offer.tariftyp not in allowed_models:
            continue
        if offer.age_subgroup != ORDINARY_SUBGROUP.get(offer.age_class):
            continue
        if offer.franchise_chf not in FRANCHISES:
            continue
        key = (offer.canton, offer.region, offer.age_class, offer.franchise_chf, offer.tariftyp)
        index.setdefault(key, []).append(offer)
    return index


def category_code(age: Optional[int]) -> Optional[str]:
    if age is None:
        return None
    if age <= 18:
        return "enfant"
    if age <= 25:
        return "jeune_adulte"
    return "adulte"


def category_label(age: Optional[int]) -> str:
    return {
        "enfant": "Enfant 0–18",
        "jeune_adulte": "Jeune adulte 19–25",
        "adulte": "Adulte 26+",
    }.get(category_code(age) or "", "")


def applicable_franchises(age_class: Optional[str]) -> tuple[int, ...]:
    if age_class == "AKA_01_KIN":
        return (300,)
    if age_class in {"AKA_02_JUG", "AKA_03_ERW"}:
        return FRANCHISES
    return ()


def comparatif_for_contact(
    contact: dict,
    catalog: Optional[Catalog],
    index: Optional[dict] = None,
    *,
    cheapest_only: bool = True,
) -> dict:
    """Primes officielles pour les franchises applicables. Rien n'est inventé."""
    motifs: list[str] = []
    birth = _as_date(contact.get("naissance"))
    age_class = None
    if not str(contact.get("naissance") or "").strip():
        motifs.append("naissance manquante")
    elif birth is None:
        motifs.append("naissance invalide")
    else:
        try:
            age_class = age_class_for_birth_year(birth.year, YEAR)
        except ValueError:
            motifs.append("naissance invalide")
    npa_digits = "".join(character for character in str(contact.get("npa") or "") if character.isdigit())
    if not npa_digits:
        motifs.append("NPA absent")
    elif len(npa_digits) != 4:
        motifs.append("NPA invalide")
    email = str(contact.get("email") or "").strip()
    if not email:
        motifs.append("e-mail manquant")
    elif not valid_email(email):
        motifs.append("e-mail incorrect")
    residence = {"ok": False, "reason": "residence_incomplete", "messages": []}
    if catalog is None:
        motifs.append("tarif absent")
    elif npa_digits and len(npa_digits) == 4:
        residence = resolve_residence(
            catalog,
            plz=npa_digits,
            commune=str(contact.get("lieu") or ""),
        )
        if not residence.get("ok"):
            motifs.append("région introuvable")
    franchise_notes: dict[int, str] = {}
    if age_class == "AKA_01_KIN":
        franchise_notes[2500] = CHILD_FRANCHISE_2500
    table = {franchise: {code: [] for code, _label in MODELS} for franchise in FRANCHISES}
    can_price = catalog is not None and residence.get("ok") and age_class and "région introuvable" not in motifs
    if can_price:
        index = index if index is not None else premium_index_for(catalog)
        for franchise in applicable_franchises(age_class):
            for code, _label in MODELS:
                key = (residence["canton"], residence["region"], age_class, franchise, code)
                rows = []
                seen = set()
                for offer in index.get(key, []):
                    if offer.age_class != age_class:
                        continue
                    if not _offer_allowed(catalog, offer, residence.get("bfs")):
                        continue
                    label = offer_label(catalog, offer)
                    premium = money_str(offer.premium_month)
                    marker = (label, premium, offer.insurer_id, offer.tarif_id)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    rows.append({
                        "label": label,
                        "premium": premium,
                        "tariftyp": code,
                        "insurer_id": offer.insurer_id,
                        "tarif_id": offer.tarif_id,
                        "url": primeinfo_url(offer.insurer_id),
                    })
                rows.sort(key=lambda item: (Decimal(item["premium"]), item["label"]))
                table[franchise][code] = rows[:1] if cheapest_only else rows
    applicable_missing = False
    if age_class and "naissance manquante" not in motifs and "naissance invalide" not in motifs:
        for franchise in applicable_franchises(age_class):
            for code, _label in MODELS:
                if not table[franchise][code]:
                    applicable_missing = True
    if applicable_missing and "tarif absent" not in motifs and can_price:
        motifs.append("tarif absent")
    if age_class == "AKA_01_KIN":
        motifs.append("franchise incompatible")
    blockers = {
        "naissance manquante",
        "naissance invalide",
        "NPA absent",
        "NPA invalide",
        "région introuvable",
        "tarif absent",
    }
    blocked = any(item in blockers for item in motifs) or applicable_missing or not age_class
    if age_class == "AKA_01_KIN" and not applicable_missing and not any(item in blockers for item in motifs):
        blocked = False
    found = sum(1 for franchise in applicable_franchises(age_class) for rows in (table.get(franchise) or {}).values() if rows)
    return {
        "residence": residence,
        "age_class": age_class,
        "birth_year": birth.year if birth else None,
        "age": (YEAR - birth.year) if birth and age_class else None,
        "categorie": category_code(YEAR - birth.year) if birth and age_class else None,
        "table": table,
        "premiums_found": found,
        "accident": "avec",
        "motifs": motifs,
        "franchise_notes": franchise_notes,
        "blocked": blocked,
        "canton_fiable": bool(residence.get("ok") and residence.get("canton")),
    }


def primeinfo_url(insurer_id: str) -> Optional[str]:
    """Le numéro OFSP seul ne désigne aucune page Priminfo documentée."""
    _ = insurer_id
    return None


def age_in_2027(naissance) -> Optional[int]:
    birth = _as_date(naissance)
    if not birth:
        return None
    try:
        age_class_for_birth_year(birth.year, YEAR)
    except ValueError:
        return None
    return YEAR - birth.year


def render_comparatif_email(
    table: dict,
    *,
    prenom: str = "",
    age_class: Optional[str] = None,
    franchise_notes: Optional[dict] = None,
    intro: Optional[str] = None,
    closing: Optional[str] = None,
    subject: Optional[str] = None,
) -> dict:
    """Mail HTML 2027. Une ligne par modèle : la compagnie la moins chère."""
    body = _mail_html(
        table,
        prenom=prenom,
        age_class=age_class,
        franchise_notes=franchise_notes or {},
        intro=intro,
        closing=closing,
    )
    if "À compléter" in body or "A completer" in body or "[Compagnie]" in body:
        raise RuntimeError("Le brouillon ne doit pas contenir de mention à compléter")
    return {
        "subject": subject or EMAIL_SUBJECT,
        "body": body,
        "intro": intro if intro is not None else DEFAULT_INTRO,
        "closing": closing if closing is not None else DEFAULT_CLOSING,
        "kind": "comparatif_modeles",
        "savings_claimed": False,
    }


def render_contact_email(contact: dict, catalog: Optional[Catalog], index: Optional[dict] = None) -> dict:
    calculated = comparatif_for_contact(contact, catalog, index)
    prenom = str(contact.get("prenom") or "").strip()
    message = render_comparatif_email(
        calculated["table"],
        prenom=prenom,
        age_class=calculated.get("age_class"),
        franchise_notes=calculated.get("franchise_notes"),
    )
    message["recipient_name"] = " ".join(part for part in (prenom, contact.get("nom")) if part).strip()
    message["calculated"] = calculated
    message["comparatif_statut"], message["brouillon_statut"] = statuts_from_calculated(calculated)
    return message


def statuts_from_calculated(calculated: dict) -> tuple[str, str]:
    motifs = calculated.get("motifs") or []
    email_issue = any(item.startswith("e-mail") for item in motifs)
    if calculated.get("blocked"):
        comparative = "incomplet"
    else:
        comparative = "calcule"
    if comparative != "calcule" or email_issue:
        draft = "a_verifier"
    else:
        draft = "brouillon"
    return comparative, draft


def offer_label(catalog: Catalog, offer: Offer) -> str:
    french = (catalog.tariff_names.get((offer.insurer_id, offer.tarif_id)) or "").strip()
    if french:
        return french
    if (offer.tarif_name_fr or "").strip():
        return offer.tarif_name_fr.strip()
    if (offer.tarif_name_de or "").strip():
        return offer.tarif_name_de.strip()
    return f"Tarif {offer.tarif_id}"


def _mail_html(
    table: dict,
    *,
    prenom: str = "",
    age_class: Optional[str] = None,
    franchise_notes: Optional[dict] = None,
    intro: Optional[str] = None,
    closing: Optional[str] = None,
) -> str:
    safe_prenom = html.escape(prenom.strip())
    greeting = f"Bonjour {safe_prenom}," if safe_prenom else "Bonjour,"
    intro_text = html.escape(intro if intro is not None else DEFAULT_INTRO, quote=False)
    closing_html = _closing_html(closing)
    notes = franchise_notes or {}
    child_2500 = age_class == "AKA_01_KIN"
    note_2500 = notes.get(2500) or (CHILD_FRANCHISE_2500 if child_2500 else "")
    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><title>Primes d'assurance-maladie pour l'année 2027</title></head>
<body style="margin:0;padding:0;background:{MAIL_PAGE};color:{MAIL_INK};font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{MAIL_PAGE};">
<tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:640px;background:#ffffff;">
<tr><td style="padding:26px 32px 18px;background:#ffffff;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="vertical-align:middle;">
<p style="margin:0;color:{MAIL_TURQUOISE};font-size:20px;font-weight:700;letter-spacing:0.14em;">AGENCE MENDES</p>
<p style="margin:6px 0 0;color:{MAIL_MUTED};font-size:11px;letter-spacing:0.16em;">ASSURANCES &amp; PRÉVOYANCE</p>
</td>
<td align="right" style="vertical-align:middle;">
<span style="display:inline-block;background:#F4F7F8;border:1px solid #E3E8EB;color:{MAIL_NAVY};padding:7px 12px;font-size:12px;letter-spacing:0.04em;">LAMal · 2027</span>
</td>
</tr></table>
</td></tr>
<tr><td style="padding:0;background:{MAIL_NAVY};height:3px;font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:28px 32px 8px;color:{MAIL_INK};">
<p style="margin:0;color:{MAIL_TURQUOISE};font-size:12px;font-weight:700;letter-spacing:0.14em;">VOTRE COMPARATIF PERSONNALISÉ</p>
<h1 style="margin:10px 0 0;color:{MAIL_NAVY};font-size:30px;line-height:1.2;font-weight:700;">Primes d'assurance-maladie<br>pour l'année 2027</h1>
<p style="margin:22px 0 0;font-size:15px;line-height:1.55;color:{MAIL_INK};">{greeting}</p>
<p style="margin:10px 0 0;font-size:15px;line-height:1.55;color:{MAIL_INK};">{intro_text}</p>
{_franchise_section(1, 300, table, notes.get(300, ""), unavailable=False)}
{_franchise_section(2, 2500, table, note_2500, unavailable=child_2500)}
<p style="margin:18px 0 0;color:{MAIL_MUTED};font-size:13px;line-height:1.5;">{html.escape(RESERVE_NOTE)}</p>
</td></tr>
<tr><td style="padding:16px 32px 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#E7F4F6;border-left:4px solid {MAIL_TURQUOISE};">
<tr><td style="padding:18px 20px;color:{MAIL_INK};">
<p style="margin:0;color:{MAIL_NAVY};font-size:16px;font-weight:700;">Et vos assurances complémentaires ?</p>
<p style="margin:8px 0 0;font-size:14px;line-height:1.55;">Nos conseillers peuvent également faire le point sur vos couvertures complémentaires et vous accompagner dans vos démarches. Contactez-les directement par téléphone pour convenir d'un rendez-vous.</p>
{_calendly_html()}
</td></tr>
</table>
{closing_html}
</td></tr>
<tr><td style="padding:22px 32px;background:{MAIL_PAGE};color:{MAIL_MUTED};font-size:12px;line-height:1.6;">
<p style="margin:0;color:{MAIL_NAVY};font-weight:700;letter-spacing:0.08em;">AGENCE MENDES</p>
<p style="margin:8px 0 0;">Route de Saint-Julien 277, 1258 Perly – Genève</p>
<p style="margin:2px 0 0;"><span style="color:{MAIL_TURQUOISE};">+41 22 339 30 10</span> · <a href="https://www.agencemendes.ch" style="color:{MAIL_TURQUOISE};text-decoration:underline;">www.agencemendes.ch</a></p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _closing_html(closing: Optional[str]) -> str:
    text = closing if closing is not None else DEFAULT_CLOSING
    html_parts = []
    for part in text.split("\n"):
        if not part:
            continue
        if part == "L'équipe Agence Mendes":
            style = f"margin:8px 0 0;font-size:15px;line-height:1.5;color:{MAIL_TURQUOISE};font-weight:700;"
        else:
            style = f"margin:16px 0 0;font-size:15px;line-height:1.5;color:{MAIL_INK};"
        html_parts.append(f'<p style="{style}">{html.escape(part, quote=False)}</p>')
    return "".join(html_parts)


def _calendly_html() -> str:
    url = (CALENDLY_LAMAL_URL or "").strip()
    if not url:
        return ""
    safe = html.escape(url, quote=True)
    return f'<p style="margin:12px 0 0;"><a href="{safe}" style="color:{MAIL_TURQUOISE};font-weight:700;text-decoration:underline;">Prendre rendez-vous</a></p>'


def _franchise_section(number: int, franchise: int, table: dict, note: str = "", unavailable: bool = False) -> str:
    title = "300" if franchise == 300 else "2’500"
    rows_html = []
    groups = table.get(franchise) or {}
    for index, (_code, label) in enumerate(MODELS):
        chosen = None if unavailable else (groups.get(_code) or [None])[0]
        if chosen and chosen.get("premium") and chosen.get("label"):
            company = _company_html(chosen)
            premium = (
                f'<strong style="color:{MAIL_NAVY};font-size:15px;font-weight:700;">'
                f'{html.escape(str(chosen["premium"]))} CHF</strong>'
            )
        elif unavailable:
            company = MISSING
            premium = MISSING
        else:
            company = UNAVAILABLE_CELL
            premium = UNAVAILABLE_CELL
        background = "#ffffff" if index % 2 == 0 else MAIL_ZEBRA
        rows_html.append(
            "<tr>"
            f'<td style="padding:12px 14px;background:{background};color:{MAIL_INK};border-bottom:1px solid #EEF1F3;">{company}</td>'
            f'<td style="padding:12px 14px;background:{background};color:{MAIL_INK};border-bottom:1px solid #EEF1F3;">{html.escape(label, quote=False)}</td>'
            f'<td style="padding:12px 14px;background:{background};color:{MAIL_NAVY};border-bottom:1px solid #EEF1F3;text-align:right;white-space:nowrap;">{premium}</td>'
            "</tr>"
        )
    note_html = ""
    if note:
        note_html = f'<p style="margin:0 0 10px;color:{MAIL_MUTED};font-size:13px;line-height:1.45;">{html.escape(note, quote=False)}</p>'
    body = "".join(rows_html)
    return f"""
<p style="margin:32px 0 0;color:{MAIL_NAVY};font-size:18px;font-weight:700;">0{number} / Franchise de {title} CHF</p>
<p style="margin:4px 0 10px;color:{MAIL_MUTED};font-size:13px;">Comparaison des primes mensuelles</p>
{note_html}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px;">
<thead><tr>
<th align="left" width="46%" style="background:{MAIL_NAVY};color:#ffffff;padding:11px 14px;font-weight:700;">Compagnie</th>
<th align="left" width="32%" style="background:{MAIL_NAVY};color:#ffffff;padding:11px 14px;font-weight:700;">Modèle de soins</th>
<th align="right" width="22%" style="background:{MAIL_NAVY};color:#ffffff;padding:11px 14px;font-weight:700;">Prime / mois</th>
</tr></thead>
<tbody>{body}</tbody>
</table>"""


def _company_html(row: dict) -> str:
    label = html.escape(row.get("label") or MISSING, quote=False)
    url = (row.get("url") or "").strip()
    if not url:
        return label
    return f'<a href="{html.escape(url, quote=True)}" style="color:{MAIL_TURQUOISE};text-decoration:underline;">{label}</a>'


def _find_header(rows: list) -> tuple[Optional[int], Optional[dict]]:
    for index, row in enumerate(rows[:15]):
        mapping = _map_header(row)
        fields = set(mapping.values())
        identity = fields & {"prenom", "nom", "email"}
        place = fields & {"npa", "lieu", "naissance", "age"}
        if identity and place:
            return index, mapping
    return None, None


def _map_header(row) -> dict[int, str]:
    chosen: dict[str, tuple[int, int]] = {}
    for index, cell in enumerate(row or []):
        folded = fold_name(str(cell or ""))
        alias = ALIASES.get(folded)
        if not alias:
            continue
        field, rank = alias
        current = chosen.get(field)
        if current is None or rank > current[1]:
            chosen[field] = (index, rank)
    return {index: field for field, (index, _rank) in chosen.items()}


def _record_from_row(raw, mapping: dict[int, str], header_cells=None, row_number: Optional[int] = None) -> Optional[dict]:
    values = {field: _cell(raw, index) for index, field in mapping.items()}
    if not any(values.get(key) for key in ("prenom", "nom", "email", "npa", "lieu", "naissance")):
        return None
    raw_birth = values.get("naissance")
    birth = _as_date(raw_birth)
    if birth:
        naissance = birth.isoformat()
    elif raw_birth not in ("", None):
        naissance = str(raw_birth).strip()
    else:
        naissance = ""
    extras = {}
    known = set(mapping)
    for index, cell in enumerate(header_cells or []):
        if index in known:
            continue
        label = str(cell or "").strip()
        if not label:
            continue
        value = _cell(raw, index)
        if value in ("", None):
            continue
        if isinstance(value, date):
            value = value.isoformat()
        extras[label] = str(value)[:500]
    return {
        "prenom": values.get("prenom") or "",
        "nom": values.get("nom") or "",
        "email": values.get("email") or "",
        "npa": _npa(values.get("npa")),
        "lieu": values.get("lieu") or "",
        "naissance": naissance,
        "age_fichier": values.get("age") or "",
        "assureur": values.get("assureur") or "",
        "adresse": values.get("adresse") or "",
        "complement": values.get("complement") or "",
        "canton_fichier": values.get("canton") or "",
        "telephone": values.get("telephone") or "",
        "telephone_prive": values.get("telephone_prive") or "",
        "police": values.get("police") or "",
        "extras": extras,
        "ligne": row_number,
    }


def _person_key(record: dict) -> Optional[tuple]:
    prenom = fold_name(record.get("prenom"))
    nom = fold_name(record.get("nom"))
    birth = record.get("naissance") or ""
    if prenom and nom and birth:
        return (prenom, nom, birth)
    return None


def _cell(raw, index: int):
    if index >= len(raw or []):
        return ""
    value = raw[index]
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value).strip()


def _npa(value) -> str:
    if value is None or value == "" or isinstance(value, date):
        return ""
    digits = "".join(character for character in str(value) if character.isdigit())
    if digits and len(digits) < 4:
        return digits.zfill(4)
    return digits


def _as_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    head = text[:10]
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    year = None
    for token in text.replace(".", " ").replace("/", " ").split():
        if len(token) == 4 and token.isdigit() and token.startswith(("19", "20")):
            year = int(token)
            break
    if year:
        return date(year, 1, 1)
    return None


def lignes_from_table(table: dict) -> list[dict]:
    lignes = []
    for franchise in FRANCHISES:
        groups = table.get(franchise) or {}
        for code, _label in MODELS:
            for item in groups.get(code) or []:
                lignes.append({
                    "franchise": franchise,
                    "modele": code,
                    "label": item.get("label") or "",
                    "premium": item.get("premium") or "",
                    "insurer_id": item.get("insurer_id") or "",
                    "tarif_id": item.get("tarif_id") or "",
                })
    return lignes


def rows_to_table(lignes: list) -> dict:
    table = {franchise: {code: [] for code, _label in MODELS} for franchise in FRANCHISES}
    for row in lignes or []:
        try:
            franchise = int(row.get("franchise"))
        except (TypeError, ValueError):
            continue
        code = row.get("modele")
        if franchise not in table or code not in table[franchise]:
            continue
        table[franchise][code].append({
            "label": row.get("label") or "",
            "premium": row.get("premium") or "",
            "tariftyp": code,
            "insurer_id": row.get("insurer_id") or "",
            "url": None,
        })
    return table


def calculation_payload(calculated: dict, stamp: str, when: str) -> dict:
    comparative, draft = statuts_from_calculated(calculated)
    residence = calculated.get("residence") or {}
    notes = [
        {"franchise": franchise, "texte": text}
        for franchise, text in (calculated.get("franchise_notes") or {}).items()
    ]
    reliable = bool(calculated.get("canton_fiable"))
    return {
        "age": calculated.get("age"),
        "categorie": calculated.get("categorie"),
        "age_class": calculated.get("age_class"),
        "canton": residence.get("canton") if reliable else None,
        "region": residence.get("region") if residence.get("ok") else None,
        "canton_fiable": reliable,
        "residence_ok": bool(residence.get("ok")),
        "premiums_found": calculated.get("premiums_found") or 0,
        "comparatif_statut": comparative,
        "comparatif_motifs": list(calculated.get("motifs") or []),
        "brouillon_statut": draft,
        "calcule_le": when,
        "comparatif": {
            "annee": YEAR,
            "accident": "avec",
            "reference": "OFSP 2027, avec accidents",
            "age_class": calculated.get("age_class"),
            "categorie": calculated.get("categorie"),
            "lignes": lignes_from_table(calculated.get("table") or {}),
            "franchise_notes": notes,
            "motifs": list(calculated.get("motifs") or []),
            "premiums_found": calculated.get("premiums_found") or 0,
            "tariff_stamp": stamp or "",
            "calcule_le": when,
        },
    }


def email_document_fields(contact: dict, message: dict, when: str) -> dict:
    return {
        "to": contact.get("email") or "",
        "subject": message["subject"],
        "body": message["body"],
        "intro": message.get("intro") or DEFAULT_INTRO,
        "closing": message.get("closing") or DEFAULT_CLOSING,
        "kind": message["kind"],
        "status": "a_valider",
        "brouillon_statut": message["brouillon_statut"],
        "manual_edit": False,
        "recipient_name": message.get("recipient_name") or "",
        "year": YEAR,
        "source": "import_liste",
        "modifie_le": when,
        "valide_le": None,
        "valide_par": None,
    }


def draft_is_protected(email: Optional[dict]) -> bool:
    if not email:
        return False
    if email.get("manual_edit"):
        return True
    return email.get("brouillon_statut") == "valide" or email.get("status") == "valide"


def plan_prepare(contact: dict, email: Optional[dict], catalog: Optional[Catalog], index: Optional[dict], stamp: str, when: str) -> dict:
    """Prépare un comparatif et un brouillon. Ne crée pas de doublon et n'envoie rien."""
    if draft_is_protected(email):
        return {"action": "kept", "warning": "Brouillon modifié ou validé conservé.", "sent": 0, "queued": 0}
    message = render_contact_email(contact, catalog, index)
    return {
        "action": "write",
        "warning": "",
        "sent": 0,
        "queued": 0,
        "comparatif_statut": message["comparatif_statut"],
        "contact_updates": calculation_payload(message["calculated"], stamp, when),
        "email_updates": email_document_fields(contact, message, when),
    }


def apply_identity_edit(contact: dict, changes: dict) -> dict:
    updated = dict(contact)
    changed = []
    for key in ("prenom", "nom", "naissance", "adresse", "npa", "lieu", "email"):
        if key not in changes or changes[key] is None:
            continue
        if key == "npa":
            value = _npa(changes[key])
        elif key == "naissance":
            birth = _as_date(changes[key])
            value = birth.isoformat() if birth else str(changes[key] or "").strip()
        else:
            value = str(changes[key] or "").strip()
        if (updated.get(key) or "") != value:
            updated[key] = value
            changed.append(key)
    identity_break = "naissance" in changed or "npa" in changed
    if identity_break:
        updated["comparatif_statut"] = "a_recalculer"
        if updated.get("brouillon_statut") == "valide":
            updated["brouillon_statut"] = "a_verifier"
    if "email" in changed:
        updated["email_ok"] = valid_email(updated.get("email"))
    return {"contact": updated, "changed": changed, "recalculate": identity_break}


def save_draft_text(email: dict, contact: dict, *, subject: Optional[str], intro: Optional[str], closing: Optional[str]) -> dict:
    """Enregistre le texte du brouillon. Les primes restent celles du comparatif officiel."""
    updated = dict(email or {})
    updated["subject"] = (subject if subject is not None else updated.get("subject") or EMAIL_SUBJECT).strip()
    updated["intro"] = DEFAULT_INTRO if intro is None else intro
    updated["closing"] = DEFAULT_CLOSING if closing is None else closing
    updated["manual_edit"] = True
    updated["status"] = "a_valider"
    comparatif = contact.get("comparatif") if isinstance(contact.get("comparatif"), dict) else {}
    lignes = list(comparatif.get("lignes") or [])
    if lignes:
        notes = {}
        for item in comparatif.get("franchise_notes") or []:
            if item.get("franchise") is None:
                continue
            notes[int(item["franchise"])] = item.get("texte") or ""
        updated["body"] = _mail_html(
            rows_to_table(lignes),
            prenom=str(contact.get("prenom") or ""),
            age_class=contact.get("age_class"),
            franchise_notes=notes,
            intro=updated["intro"],
            closing=updated["closing"],
        )
    if updated.get("brouillon_statut") == "valide":
        updated["brouillon_statut"] = "brouillon"
        updated["valide_le"] = None
        updated["valide_par"] = None
    elif updated.get("brouillon_statut") not in BROUILLON_LABELS:
        updated["brouillon_statut"] = "brouillon"
    return updated


def regenerate_draft(email: Optional[dict], message: dict, *, confirm: bool) -> dict:
    if email and email.get("manual_edit") and not confirm:
        return {"ok": False, "needs_confirm": True, "email": email, "detail": "Ce brouillon a été modifié. Confirmez la régénération."}
    updated = dict(email or {})
    contact = {"email": (email or {}).get("to") or "", "prenom": ""}
    updated.update(email_document_fields(contact, message, updated.get("modifie_le") or ""))
    updated["to"] = (email or {}).get("to") or contact["email"]
    return {"ok": True, "needs_confirm": False, "email": updated}


def validate_draft(email: dict, contact: dict, *, when: str, actor: str) -> dict:
    comparative, _draft = derive_statuts(contact, email)
    if comparative != "calcule":
        return {"ok": False, "detail": "Comparatif incomplet : le brouillon ne peut pas être validé.", "sent": 0}
    if not valid_email((email or {}).get("to") or contact.get("email")):
        return {"ok": False, "detail": "E-mail manquant ou incorrect.", "sent": 0}
    body = (email or {}).get("body") or ""
    if "[Compagnie]" in body or "À compléter" in body:
        return {"ok": False, "detail": "Le brouillon contient une compagnie ou une mention à compléter.", "sent": 0}
    updated = dict(email or {})
    updated["brouillon_statut"] = "valide"
    updated["status"] = "a_valider"
    updated["valide_le"] = when
    updated["valide_par"] = actor
    return {"ok": True, "email": updated, "sent": 0, "queued": 0}


def refuse_campaign_delivery(campaign: Optional[dict] = None, emails: Optional[list] = None) -> dict:
    """Refuse l'envoi d'une campagne. N'altère ni les brouillons, ni une file."""
    _ = emails
    detail = SEND_REFUSAL
    if campaign is not None and (campaign.get("status") or "preparation") != "preparation":
        detail = "L'envoi des campagnes LAMal n'est pas ouvert."
    return {"ok": False, "refused": True, "sent": 0, "queued": 0, "status": "envoi_refuse", "detail": detail}


def reimport_decisions(existing: list[dict], incoming: list[dict]) -> dict:
    """Ajoute ou met à jour sans supprimer personne et sans écraser un brouillon protégé."""
    by_key = {}
    for item in existing:
        key = _person_key(item.get("contact") or {})
        if key:
            by_key[key] = item
    add = []
    update = []
    kept = []
    for source in incoming:
        key = _person_key(source)
        current = by_key.get(key) if key else None
        if current and draft_is_protected(current.get("email")):
            kept.append({"warning": "Brouillon modifié ou validé conservé."})
            continue
        if current:
            update.append(source)
        else:
            add.append(source)
    return {"add": add, "update": update, "kept": kept, "removed": []}


def derive_statuts(contact: dict, email: Optional[dict] = None, current_stamp: Optional[str] = None) -> tuple[str, str]:
    comparative = contact.get("comparatif_statut")
    if comparative not in COMPARATIF_LABELS:
        if contact.get("premiums_found"):
            comparative = "calcule"
        elif "premiums_found" in contact:
            comparative = "incomplet"
        else:
            comparative = "non_calcule"
    comparatif = contact.get("comparatif") if isinstance(contact.get("comparatif"), dict) else {}
    stored = comparatif.get("tariff_stamp") or ""
    if comparative == "calcule" and stored and current_stamp and stored != current_stamp:
        comparative = "a_recalculer"
    draft = (email or {}).get("brouillon_statut") or contact.get("brouillon_statut")
    if draft not in BROUILLON_LABELS:
        if not email or not email.get("body"):
            draft = "non_genere"
        elif comparative == "calcule" and valid_email((email or {}).get("to") or contact.get("email")):
            draft = "brouillon"
        else:
            draft = "a_verifier"
    if comparative == "a_recalculer" and draft == "valide":
        draft = "a_verifier"
    return comparative, draft


def list_bucket(comparative: str, draft: str) -> str:
    if draft == "valide":
        return "valides"
    if comparative in {"incomplet", "erreur"} or draft == "a_verifier":
        return "verifier"
    if comparative == "calcule" and draft == "brouillon":
        return "prets"
    return "preparer"


def present_person(contact: dict, email: Optional[dict] = None, current_stamp: Optional[str] = None) -> dict:
    comparative, draft = derive_statuts(contact, email, current_stamp)
    comparatif = contact.get("comparatif") if isinstance(contact.get("comparatif"), dict) else {}
    age = contact.get("age")
    if age is None:
        age = age_in_2027(contact.get("naissance"))
    if contact.get("canton_fiable") or (contact.get("canton_fiable") is None and contact.get("residence_ok")):
        canton = contact.get("canton") or ""
    else:
        canton = ""
    lignes = list(comparatif.get("lignes") or [])
    afficher = comparative == "calcule" and bool(lignes)
    motifs = list(contact.get("comparatif_motifs") or comparatif.get("motifs") or [])
    if comparative == "calcule" and not lignes:
        message = "Le tableau des offres s'affiche après « Recalculer le comparatif »."
    elif afficher:
        message = None
    else:
        message = UNAVAILABLE
    return {
        "id": contact.get("id"),
        "campaign_id": contact.get("campaign_id"),
        "prenom": contact.get("prenom") or "",
        "nom": contact.get("nom") or "",
        "naissance": contact.get("naissance") or "",
        "age": age,
        "categorie": category_label(age),
        "adresse": contact.get("adresse") or "",
        "complement": contact.get("complement") or "",
        "npa": contact.get("npa") or "",
        "lieu": contact.get("lieu") or "",
        "canton": canton,
        "email": contact.get("email") or "",
        "telephone": contact.get("telephone") or contact.get("telephone_prive") or "",
        "fichier": contact.get("fichier") or "",
        "importe_le": contact.get("importe_le") or contact.get("created_at") or "",
        "ligne": contact.get("ligne"),
        "campagne": contact.get("campaign_id") or "",
        "etat_comparatif": comparative,
        "etat_comparatif_label": COMPARATIF_LABELS.get(comparative, comparative),
        "etat_email": draft,
        "etat_email_label": BROUILLON_LABELS.get(draft, draft),
        "calcule_le": contact.get("calcule_le") or "",
        "modifie_le": contact.get("modifie_le") or "",
        "extras": contact.get("extras") or {},
        "assureur": contact.get("assureur_actuel") or contact.get("assureur") or "",
        "premiums_found": contact.get("premiums_found") or 0,
        "bucket": list_bucket(comparative, draft),
        "comparatif": {
            "statut": comparative,
            "label": COMPARATIF_LABELS.get(comparative, comparative),
            "afficher": afficher,
            "message": message,
            "motifs": motifs,
            "lignes": lignes if afficher else [],
            "franchise_notes": list(comparatif.get("franchise_notes") or []),
            "accident": "avec",
            "annee": YEAR,
            "reference": "OFSP 2027, avec accidents",
        },
        "email_apercu": {
            "to": (email or {}).get("to") or contact.get("email") or "",
            "subject": (email or {}).get("subject") or "",
            "body": (email or {}).get("body") or "",
            "statut": draft,
            "statut_label": BROUILLON_LABELS.get(draft, draft),
            "manual_edit": bool((email or {}).get("manual_edit")),
            "intro": (email or {}).get("intro") or DEFAULT_INTRO,
            "closing": (email or {}).get("closing") or DEFAULT_CLOSING,
        },
    }


def summarize(people: list[dict], emails: Optional[list] = None) -> dict:
    sent = sum(1 for email in (emails or []) if email.get("status") == "envoye")
    return {
        "contacts": len(people),
        "avec_primes": sum(1 for person in people if (person.get("premiums_found") or 0) > 0),
        "sans_primes": sum(1 for person in people if not (person.get("premiums_found") or 0)),
        "comparatifs_disponibles": sum(1 for person in people if person.get("etat_comparatif") == "calcule"),
        "a_verifier": sum(1 for person in people if person.get("bucket") == "verifier"),
        "brouillons_valides": sum(1 for person in people if person.get("etat_email") == "valide"),
        "envoyes": sent,
    }
