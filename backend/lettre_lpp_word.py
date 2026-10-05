"""Lettre Recherche d'avoirs LPP — génération depuis le modèle Word Mendes.

Le fichier original n'est jamais modifié. Chaque génération copie le template,
injecte prénom / nom / date du jour, puis produit un nouveau PDF.
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "forms"
ORIGINAL_DOCX = TEMPLATES_DIR / "lettre_recherche_avoirs_lpp.original.docx"
TEMPLATE_DOCX = TEMPLATES_DIR / "lettre_recherche_avoirs_lpp.template.docx"
ASSETS_DIR = TEMPLATES_DIR / "lettre_lpp_assets"
LOGO_CANDIDATES = [ASSETS_DIR / "mendes_logo.jpg", ASSETS_DIR / "image1.jpg"]
FOOTER_CANDIDATES = [ASSETS_DIR / "footer_banner.png", ASSETS_DIR / "image2.png"]

PLACEHOLDER_PRENOM = "{{prenom}}"
PLACEHOLDER_NOM = "{{nom}}"
PLACEHOLDER_FULLNAME = "{{client_fullname}}"
PLACEHOLDER_DATE = "{{date_long}}"

BODY_TEMPLATE = (
    "Madame, Monsieur, Vous trouverez ci-joint le formulaire de demande de recherche, "
    "ainsi que la procuration signée par {{client_fullname}} nous permettant de faire "
    "la recherche de ses avoirs."
)
DATE_TEMPLATE = "Perly, le {{date_long}}"

# Modèle Word original : retrait gauche 9,753 cm depuis la marge (1,905 cm).
# Le bloc destinataire commence donc à 11,658 cm du bord gauche (haut droite).
RECIPIENT_LEFT_INDENT_CM = 9.753
PAGE_LEFT_MARGIN_CM = 1.905
RECIPIENT_LINES = (
    "Fonds de garantie LPP",
    "Organe de direction",
    "Case Postale 1023",
    "3000 Berne 14",
)


def _safe(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _first_existing(paths) -> Optional[Path]:
    for path in paths:
        if path.exists():
            return path
    return None


def client_fullname(values: Dict[str, str]) -> str:
    prenom = _safe(values.get("prenom"))
    nom = _safe(values.get("nom"))
    return " ".join(part for part in (prenom, nom) if part)


def placeholder_map(values: Dict[str, str]) -> Dict[str, str]:
    return {
        PLACEHOLDER_PRENOM: _safe(values.get("prenom")),
        PLACEHOLDER_NOM: _safe(values.get("nom")),
        PLACEHOLDER_FULLNAME: client_fullname(values),
        PLACEHOLDER_DATE: _safe(values.get("today_long")),
    }


def _apply_mapping(text: str, mapping: Dict[str, str]) -> str:
    for key, value in mapping.items():
        text = text.replace(key, value)
    return text


def _set_paragraph_text(paragraph, text: str) -> None:
    bold = bool(paragraph.runs[0].bold) if paragraph.runs else False
    for extra in paragraph.runs[1:]:
        extra._element.getparent().remove(extra._element)
    if paragraph.runs:
        run = paragraph.runs[0]
        run.text = text
    else:
        run = paragraph.add_run(text)
        run.bold = bold
        return
    run.bold = bold


def _apply_original_recipient_indent(doc) -> None:
    """Reprend le retrait droit du modèle Word, sans toucher au reste."""
    from docx.shared import Cm

    indent = Cm(RECIPIENT_LEFT_INDENT_CM)
    for paragraph in doc.paragraphs:
        if (paragraph.text or "").strip() in RECIPIENT_LINES:
            paragraph.paragraph_format.left_indent = indent


def fill_lettre_lpp_docx(values: Dict[str, str]) -> bytes:
    """Copie le template et injecte les valeurs — ne touche jamais à l'original."""
    from docx import Document

    source = TEMPLATE_DOCX if TEMPLATE_DOCX.exists() else None
    if source is None or not source.exists():
        raise FileNotFoundError("Modèle Word de la lettre LPP introuvable")
    mapping = placeholder_map(values)
    doc = Document(io.BytesIO(source.read_bytes()))
    for paragraph in doc.paragraphs:
        current = paragraph.text or ""
        updated = _apply_mapping(current, mapping)
        if updated != current:
            _set_paragraph_text(paragraph, updated)
    _apply_original_recipient_indent(doc)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _soffice_bin() -> Optional[str]:
    for candidate in (
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def convert_docx_to_pdf(docx_bytes: bytes) -> Optional[bytes]:
    soffice = _soffice_bin()
    if not soffice:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "lettre.docx"
        src.write_bytes(docx_bytes)
        try:
            subprocess.run(
                [soffice, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", tmp, str(src)],
                check=True,
                timeout=90,
                capture_output=True,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        pdf = Path(tmp) / "lettre.pdf"
        if pdf.exists():
            return pdf.read_bytes()
    return None


def render_lettre_lpp_pdf(values: Dict[str, str]) -> bytes:
    """Rendu PDF fidèle au modèle (logo, bandeau, structure, Calibri 11)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen.canvas import Canvas

    fullname = client_fullname(values) or "le/la preneur(se) d'assurance"
    date_long = _safe(values.get("today_long"))
    from pdf_generator import _register_reportlab_font

    font = _register_reportlab_font("Calibri", False)
    font_bold = _register_reportlab_font("Calibri", True)

    page_w, page_h = A4
    left = PAGE_LEFT_MARGIN_CM * cm
    right = page_w - PAGE_LEFT_MARGIN_CM * cm
    usable_w = right - left

    packet = io.BytesIO()
    canvas = Canvas(packet, pagesize=A4)

    logo = _first_existing(LOGO_CANDIDATES)
    if logo:
        logo_w, logo_h = 2.46 * cm, 3.36 * cm
        canvas.drawImage(
            str(logo),
            (page_w - logo_w) / 2.0,
            page_h - 1.15 * cm - logo_h,
            width=logo_w,
            height=logo_h,
            mask="auto",
            preserveAspectRatio=True,
            anchor="c",
        )

    banner = _first_existing(FOOTER_CANDIDATES)
    if banner:
        banner_h = 0.66 * cm
        canvas.drawImage(
            str(banner),
            0,
            0.35 * cm,
            width=page_w,
            height=banner_h,
            mask="auto",
            preserveAspectRatio=False,
            anchor="sw",
        )

    recipient_left = (PAGE_LEFT_MARGIN_CM + RECIPIENT_LEFT_INDENT_CM) * cm
    y = page_h - 5.55 * cm
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont(font, 11)
    for line in RECIPIENT_LINES:
        canvas.drawString(recipient_left, y, line)
        y -= 14.2

    y -= 28
    canvas.drawString(left, y, f"Perly, le {date_long}")

    y -= 42
    canvas.setFont(font_bold, 11)
    canvas.drawString(left, y, "Objet : Recherche d'avoirs de la prévoyance professionnelle")

    y -= 28
    canvas.setFont(font, 11)
    body = (
        "Madame, Monsieur, Vous trouverez ci-joint le formulaire de demande de recherche, "
        f"ainsi que la procuration signée par {fullname} nous permettant de faire "
        "la recherche de ses avoirs."
    )
    for line in simpleSplit(body, font, 11, usable_w) or [body]:
        canvas.drawString(left, y, line)
        y -= 15.4

    y -= 12
    thanks = (
        "Nous vous remercions de bien vouloir nous transmettre directement les résultats "
        "de vos recherches à cette adresse :"
    )
    for line in simpleSplit(thanks, font, 11, usable_w) or [thanks]:
        canvas.drawString(left, y, line)
        y -= 15.4

    y -= 10
    canvas.setFont(font_bold, 11)
    for line in ("Agence Mendes Sàrl", "Route de Saint-Julien 277", "1258 Perly"):
        canvas.drawString(left, y, line)
        y -= 15.4

    y -= 14
    canvas.setFont(font, 11)
    closing = (
        "Restant à votre disposition pour tout renseignement complémentaire que vous "
        "pourriez souhaiter, veuillez agréer, Madame, Monsieur, nos meilleures salutations."
    )
    for line in simpleSplit(closing, font, 11, usable_w) or [closing]:
        canvas.drawString(left, y, line)
        y -= 15.4

    y -= 18
    canvas.drawString(10 * cm, y, "Agence Mendes")

    y -= 36
    canvas.drawString(left, y, "Annexes :")
    y -= 16
    canvas.drawString(left + 12, y, "•  Procuration")
    y -= 15
    canvas.drawString(left + 12, y, "•  Courrier de la centrale du 2ème pilier")

    canvas.save()
    packet.seek(0)
    return packet.getvalue()


def generate_lettre_lpp_pdf(values: Dict[str, str]) -> bytes:
    """Nouvelle lettre à chaque appel. L'original Word n'est pas modifié."""
    if TEMPLATE_DOCX.exists():
        filled = fill_lettre_lpp_docx(values)
        converted = convert_docx_to_pdf(filled)
        if converted:
            return converted
    return render_lettre_lpp_pdf(values)
