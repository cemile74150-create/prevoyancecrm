"""Lettre Demande AVS — génération depuis le modèle Word exact.

Le fichier original n'est jamais modifié. Chaque génération copie le .docx,
remplace uniquement « NOM Prénom » et « Perly, le … », et conserve logo,
pied de page, polices et alignements.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "forms"
ORIGINAL_DOCX = TEMPLATES_DIR / "lettre_demande_avs.original.docx"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

NAME_MARKERS = (
    "NOM Prénom",
    "NOM Prenom",
    "NOM  Prénom",
)


def _safe(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def client_fullname(values: Dict[str, str]) -> str:
    prenom = _safe(values.get("prenom"))
    nom = _safe(values.get("nom"))
    return " ".join(part for part in (prenom, nom) if part)


def _run_start(xml: str, pos: int) -> int:
    a = xml.rfind("<w:r ", 0, pos)
    b = xml.rfind("<w:r>", 0, pos)
    return max(a, b)


def _replace_name_placeholder(xml: str, fullname: str) -> str:
    """Remplace le marqueur NOM Prénom, même s'il est découpé en plusieurs runs."""
    # Cas simple : texte entier dans un seul <w:t>
    for marker in NAME_MARKERS:
        if marker in xml:
            return xml.replace(marker, xml_escape(fullname), 1)

    # Cas découpé : reconstituer les w:t du paragraphe contenant « complété par »
    idx = xml.find("complété par")
    if idx < 0:
        idx = xml.find("complete par")
    if idx < 0:
        raise ValueError("Modèle AVS : emplacement « NOM Prénom » introuvable")

    p_start = xml.rfind("<w:p ", 0, idx)
    if p_start < 0:
        p_start = xml.rfind("<w:p>", 0, idx)
    p_end = xml.find("</w:p>", idx)
    if p_start < 0 or p_end < 0:
        raise ValueError("Modèle AVS : paragraphe du prénom/nom illisible")
    p_end += len("</w:p>")
    paragraph = xml[p_start:p_end]

    texts = re.findall(r"<w:t([^>]*)>(.*?)</w:t>", paragraph, flags=re.DOTALL)
    joined = "".join(t for _, t in texts)
    if "NOM" not in joined and "Prénom" not in joined and "Prenom" not in joined:
        raise ValueError("Modèle AVS : marqueur NOM/Prénom introuvable dans le paragraphe")

    # Remplacer dans le texte concaténé, puis réécrire le dernier run contenant NOM/Prénom
    new_joined = joined
    for marker in NAME_MARKERS:
        if marker in new_joined:
            new_joined = new_joined.replace(marker, fullname, 1)
            break
    else:
        new_joined = re.sub(r"NOM\s+Pr[eé]nom", fullname, new_joined, count=1)

    # Stratégie robuste : garder le pPr, remplacer tout le contenu runs après pPr
    ppr_close = paragraph.find("</w:pPr>")
    if ppr_close < 0:
        raise ValueError("Modèle AVS : style du paragraphe nom/prénom manquant")
    head = paragraph[: ppr_close + len("</w:pPr>")]

    # Conserver la police du premier run du paragraphe si possible
    rpr_m = re.search(r"<w:rPr>.*?</w:rPr>", paragraph, flags=re.DOTALL)
    rpr = rpr_m.group(0) if rpr_m else ""
    space = ' xml:space="preserve"' if new_joined[:1].isspace() or new_joined[-1:].isspace() else ""
    run = f"<w:r>{rpr}<w:t{space}>{xml_escape(new_joined)}</w:t></w:r>"
    new_paragraph = head + run + "</w:p>"
    return xml[:p_start] + new_paragraph + xml[p_end:]


def _replace_perly_date(xml: str, date_line: str) -> str:
    """Remplace la ligne / champ date « Perly, le … » sans toucher au reste."""
    token = ">Perly, le"
    start = xml.find(token)
    if start < 0:
        # Déjà une ligne complète dans un w:t
        m = re.search(r"<w:t([^>]*)>Perly, le[^<]*</w:t>", xml)
        if not m:
            raise ValueError("Modèle AVS : date « Perly, le … » introuvable")
        return (
            xml[: m.start()]
            + f'<w:t{m.group(1)}>{xml_escape(date_line)}</w:t>'
            + xml[m.end() :]
        )

    r_start = _run_start(xml, start)
    # Champ TIME : s'étend souvent jusqu'à la fin du résultat du champ
    # On remplace du début du run « Perly, le » jusqu'à la fin du run de résultat.
    # Recherche large sur mois français ou année.
    months = (
        "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
        "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
    )
    month_idx = -1
    for month in months:
        month_idx = xml.find(month, start)
        if month_idx >= 0:
            break
    if month_idx < 0:
        # Remplacement du w:t courant uniquement
        t_start = xml.rfind("<w:t", 0, start)
        t_end = xml.find("</w:t>", start)
        if t_start < 0 or t_end < 0:
            raise ValueError("Modèle AVS : date illisible")
        open_end = xml.find(">", t_start) + 1
        return xml[:open_end] + xml_escape(date_line) + xml[t_end:]

    t_end = xml.find("</w:t>", month_idx)
    r_end = xml.find("</w:r>", t_end)
    if r_start < 0 or r_end < 0:
        raise ValueError("Modèle AVS : date illisible")
    r_end += len("</w:r>")

    # Inclure le run fldChar « end » s'il suit (évite un champ TIME orphelin)
    tail = xml[r_end : r_end + 280]
    if 'w:fldCharType="end"' in tail:
        end_close = xml.find("</w:r>", r_end)
        if end_close >= 0:
            r_end = end_close + len("</w:r>")

    # Conserver le rPr du run « Perly, le » d'origine
    old_run = xml[r_start : xml.find("</w:r>", r_start) + len("</w:r>")]
    rpr_m = re.search(r"<w:rPr>.*?</w:rPr>", old_run, flags=re.DOTALL)
    rpr = rpr_m.group(0) if rpr_m else ""
    replacement = (
        f"<w:r>{rpr}"
        f'<w:t xml:space="preserve">{xml_escape(date_line)}</w:t></w:r>'
    )
    return xml[:r_start] + replacement + xml[r_end:]


def fill_lettre_avs_docx(values: Dict[str, str]) -> bytes:
    if not ORIGINAL_DOCX.exists():
        raise FileNotFoundError(
            f"Modèle Word AVS introuvable : {ORIGINAL_DOCX.name}"
        )
    fullname = client_fullname(values) or "le/la preneur(se) d'assurance"
    date_long = _safe(values.get("today_long"))
    date_line = f"Perly, le {date_long}" if date_long else "Perly, le"

    out = io.BytesIO()
    with zipfile.ZipFile(ORIGINAL_DOCX, "r") as zin, zipfile.ZipFile(
        out, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "word/document.xml":
                xml = data.decode("utf-8")
                xml = _replace_name_placeholder(xml, fullname)
                xml = _replace_perly_date(xml, date_line)
                if "NOM Prénom" in xml or "NOM Prenom" in xml:
                    raise ValueError("Le marqueur NOM Prénom n'a pas été remplacé")
                data = xml.encode("utf-8")
            zout.writestr(info, data)
    return out.getvalue()


def generate_lettre_avs_docx(values: Dict[str, str]) -> Tuple[bytes, Dict[str, str]]:
    """Retourne (bytes docx, meta partielle) — usage interne / tests."""
    data = fill_lettre_avs_docx(values)
    return data, {
        "content_type": DOCX_MEDIA_TYPE,
        "output_ext": "docx",
    }


def generate_lettre_avs_pdf_and_docx(values: Dict[str, str]) -> Tuple[bytes, bytes, Dict[str, str]]:
    """Génère le .docx exact + un PDF pour le même viewer que les formulaires PDF.

    Returns:
        (pdf_bytes, docx_bytes, meta)
    """
    from lettre_lpp_word import convert_docx_to_pdf

    docx_bytes = fill_lettre_avs_docx(values)
    pdf_bytes = convert_docx_to_pdf(docx_bytes)
    if not pdf_bytes:
        raise RuntimeError(
            "Conversion PDF de la lettre AVS impossible. "
            "LibreOffice (soffice) doit être disponible sur le serveur pour la prévisualisation."
        )
    return pdf_bytes, docx_bytes, {
        "content_type": "application/pdf",
        "output_ext": "pdf",
        "docx_bytes": docx_bytes,
        "docx_content_type": DOCX_MEDIA_TYPE,
    }
