"""Lettre « Demande de versement rachat 3a ».

Le modèle Word est copié tel quel. Seuls les textes d'exemple sont remplacés
(client, compagnie, n° de police, date). Le fichier reste un .docx éditable.
Aucun e-mail n'est envoyé.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

TEMPLATE_PATH = (
    Path(__file__).resolve().parent
    / "templates"
    / "courrier"
    / "demande-versement-rachat-3a.docx"
)
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TZ_GENEVA = ZoneInfo("Europe/Zurich")

# Paragraphes du modèle (w14:paraId), stables dans la copie du courrier type.
_P_CLIENT_NAME = "67C817DC"
_P_CLIENT_STREET = "5B332678"
_P_CLIENT_CITY = "5CCAA3E4"
_P_CLIENT_AVS = "5016C112"
_P_COMPANY_NAME = "6FC28162"
_P_COMPANY_ADDR_1 = "45340EFE"
_P_COMPANY_ADDR_2 = "77D27280"

_EXAMPLE_DATE = " 20 avril 2026"
_EXAMPLE_POLICY = "1.637.398"
_EXAMPLE_SIGN_CLIENT = "Claudia Mathey"
_EXAMPLE_SIGN_SPOUSE = "Christian Mathey"

# Textes d'exemple du modèle : ils doivent disparaître, sauf s'ils font
# partie des données réellement fournies (jamais inventées ici).
_EXAMPLE_FRAGMENTS = (
    "Mathey",
    "Adversan",
    "Villard-sur-Chamby",
    "1.637.398",
    "20 avril 2026",
    "756.7566.9954.21",
    "Case Postale",
    "8085 Zurich",
    "Zurich Compagnie d\u2019assurances sur la Vie SA",
    "Christian Mathey",
    "Claudia Mathey",
)

_COMPANY_ADDRESS_KEYS = (
    "adresse_compagnie",
    "company_address",
    "compagnie_adresse",
    "adresse_postale_compagnie",
    "company_postal_address",
    "adresse_postale",
)
_COMPANY_STREET_KEYS = ("company_street", "compagnie_rue", "rue_compagnie")
_COMPANY_NPA_KEYS = ("company_npa", "compagnie_npa", "npa_compagnie")
_COMPANY_CITY_KEYS = ("company_ville", "compagnie_ville", "ville_compagnie")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "undefined", "n/a", "na", "-"}:
        return ""
    return " ".join(text.split())


def format_date_jjmmaaaa(when: Optional[date] = None) -> str:
    """Date du jour au format des courriers : jj.mm.aaaa."""
    d = when or datetime.now(TZ_GENEVA).date()
    return d.strftime("%d.%m.%Y")


def _join_name(prenom: str, nom: str) -> str:
    return " ".join(part for part in (prenom, nom) if part)


def _header_name(prenom: str, nom: str) -> str:
    """Le modèle place le nom de famille avant le prénom."""
    return " ".join(part for part in (nom, prenom) if part)


def _spouse_name(client: dict) -> str:
    prenom = _clean(client.get("conjoint_prenom"))
    nom = _clean(client.get("conjoint_nom"))
    if prenom or nom:
        return _join_name(prenom, nom)
    return _clean(client.get("conjoint"))


def _client_street(client: dict) -> str:
    adresse = _clean(client.get("adresse"))
    complement = _clean(
        client.get("adresse_complement")
        or client.get("complement_adresse")
        or client.get("adresse2")
    )
    return ", ".join(part for part in (adresse, complement) if part)


def _client_city(client: dict) -> str:
    return " ".join(
        part for part in (_clean(client.get("npa")), _clean(client.get("ville"))) if part
    )


def _avs_line(client: dict) -> str:
    number = _clean(client.get("avs_number") or client.get("numero_avs"))
    if number:
        return f"AVS n° {number}"
    return "AVS n°"


def _lines_from_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        lines: list[str] = []
        for item in value:
            lines.extend(_lines_from_value(item))
        return lines
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "undefined", "n/a", "na", "-"}:
        return []
    parts = re.split(r"\r?\n|\s\|\s", text)
    return [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]


def _address_from_mapping(source: dict) -> list[str]:
    if not isinstance(source, dict):
        return []
    for key in _COMPANY_ADDRESS_KEYS:
        lines = _lines_from_value(source.get(key))
        if lines:
            return lines
    street = ""
    for key in _COMPANY_STREET_KEYS:
        street = _clean(source.get(key))
        if street:
            break
    npa = ""
    for key in _COMPANY_NPA_KEYS:
        npa = _clean(source.get(key))
        if npa:
            break
    ville = ""
    for key in _COMPANY_CITY_KEYS:
        ville = _clean(source.get(key))
        if ville:
            break
    npa_ville = " ".join(part for part in (npa, ville) if part)
    return [part for part in (street, npa_ville) if part]


def company_postal_lines(line: Optional[dict], document: Optional[dict] = None) -> list[str]:
    """
    Adresse postale de la compagnie seulement si elle est déjà stockée
    sur la ligne 3e pilier ou sur le document lié. Sinon, rien.
    """
    sources: list[dict] = []
    if isinstance(line, dict):
        sources.append(line)
    if isinstance(document, dict):
        sources.append(document)
        extracted = document.get("extracted_echeances_3p") or []
        if isinstance(extracted, list):
            for entry in extracted:
                if isinstance(entry, dict):
                    sources.append(entry)
    for source in sources:
        lines = _address_from_mapping(source)
        if lines:
            return lines
    return []


def _company_address_paragraphs(lines: list[str]) -> tuple[str, str]:
    if not lines:
        return "", ""
    if len(lines) == 1:
        return lines[0], ""
    return lines[0], ", ".join(lines[1:])


def lettre_rachat_filename(client: dict, policy_number: str) -> str:
    parts = ["Lettre_rachat_3a"]
    nom = _clean(client.get("nom"))
    prenom = _clean(client.get("prenom"))
    if nom:
        parts.append(nom)
    if prenom:
        parts.append(prenom)
    policy = _clean(policy_number)
    if policy:
        parts.append(policy)
    raw = "_".join(parts)
    safe = re.sub(r'[\\/:*?"<>|]+', "_", raw)
    safe = re.sub(r"\s+", "_", safe).strip("._")
    return f"{safe or 'Lettre_rachat_3a'}.docx"


def _replace_paragraph_by_id(xml: str, para_id: str, new_text: str) -> str:
    marker = f'w14:paraId="{para_id}"'
    idx = xml.find(marker)
    if idx < 0:
        raise ValueError(f"Modèle rachat 3a : paragraphe {para_id} introuvable")
    p_start = xml.rfind("<w:p ", 0, idx)
    p_end = xml.find("</w:p>", idx)
    if p_start < 0 or p_end < 0:
        raise ValueError(f"Modèle rachat 3a : paragraphe {para_id} illisible")
    p_end += len("</w:p>")
    paragraph = xml[p_start:p_end]
    ppr_close = paragraph.find("</w:pPr>")
    if ppr_close >= 0:
        head = paragraph[: ppr_close + len("</w:pPr>")]
    else:
        head = paragraph[: paragraph.find(">") + 1]
    rpr_m = re.search(r"<w:rPr>.*?</w:rPr>", paragraph, flags=re.DOTALL)
    rpr = rpr_m.group(0) if rpr_m else ""
    text = new_text or ""
    space = ' xml:space="preserve"' if (not text or text[:1].isspace() or text[-1:].isspace()) else ""
    run = f"<w:r>{rpr}<w:t{space}>{xml_escape(text)}</w:t></w:r>"
    return xml[:p_start] + head + run + "</w:p>" + xml[p_end:]


def _replace_text_node(xml: str, old: str, new: str) -> str:
    patterns = (
        f"<w:t>{old}</w:t>",
        f'<w:t xml:space="preserve">{old}</w:t>',
    )
    needs_space = (not new) or new[:1].isspace() or new[-1:].isspace() or (" " in new)
    space = ' xml:space="preserve"' if needs_space else ""
    replacement = f"<w:t{space}>{xml_escape(new)}</w:t>"
    for pattern in patterns:
        if pattern in xml:
            return xml.replace(pattern, replacement, 1)
    raise ValueError(f"Modèle rachat 3a : texte introuvable ({old.strip() or old!r})")


def _plain_text(xml: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml))


def _strip_yellow_highlight(xml: str) -> str:
    """Retire le surlignage jaune du modèle. Le texte et la mise en page restent."""

    def _drop_if_yellow(match: re.Match) -> str:
        tag = match.group(0)
        if re.search(r"""w:val=["']yellow["']""", tag, flags=re.IGNORECASE):
            return ""
        return tag

    xml = re.sub(r"<w:highlight\b[^>]*/>", _drop_if_yellow, xml)
    xml = re.sub(r"<w:highlight\b[^>]*>.*?</w:highlight>", _drop_if_yellow, xml, flags=re.DOTALL)
    return xml


def _assert_examples_replaced(xml: str, allowed: str) -> None:
    plain = _plain_text(xml)
    for fragment in _EXAMPLE_FRAGMENTS:
        if fragment in plain and fragment not in allowed:
            raise ValueError(f"Exemple du modèle encore présent : {fragment}")


def render_lettre_rachat_xml(
    xml: str,
    client: dict,
    line: dict,
    *,
    document: Optional[dict] = None,
    when: Optional[date] = None,
) -> str:
    client = client or {}
    line = line or {}
    prenom = _clean(client.get("prenom"))
    nom = _clean(client.get("nom"))
    policy = _clean(line.get("policy_number"))
    company = _clean(line.get("company"))
    addr1, addr2 = _company_address_paragraphs(company_postal_lines(line, document))
    day = format_date_jjmmaaaa(when)
    inserted = [
        _header_name(prenom, nom),
        _client_street(client),
        _client_city(client),
        _avs_line(client),
        company,
        addr1,
        addr2,
        day,
        policy,
        _join_name(prenom, nom),
        _spouse_name(client),
    ]

    xml = _replace_paragraph_by_id(xml, _P_CLIENT_NAME, _header_name(prenom, nom))
    xml = _replace_paragraph_by_id(xml, _P_CLIENT_STREET, _client_street(client))
    xml = _replace_paragraph_by_id(xml, _P_CLIENT_CITY, _client_city(client))
    xml = _replace_paragraph_by_id(xml, _P_CLIENT_AVS, _avs_line(client))
    xml = _replace_paragraph_by_id(xml, _P_COMPANY_NAME, company)
    xml = _replace_paragraph_by_id(xml, _P_COMPANY_ADDR_1, addr1)
    xml = _replace_paragraph_by_id(xml, _P_COMPANY_ADDR_2, addr2)
    xml = _replace_text_node(xml, _EXAMPLE_DATE, f" {day}")
    xml = _replace_text_node(xml, _EXAMPLE_POLICY, policy)
    xml = _replace_text_node(xml, _EXAMPLE_SIGN_CLIENT, _join_name(prenom, nom))
    xml = _replace_text_node(xml, _EXAMPLE_SIGN_SPOUSE, _spouse_name(client))
    xml = _strip_yellow_highlight(xml)
    _assert_examples_replaced(xml, "\n".join(inserted))
    if re.search(r"""<w:highlight\b[^>]*w:val=["']yellow["']""", xml, flags=re.IGNORECASE):
        raise ValueError("Le surlignage jaune n'a pas été retiré du modèle")
    return xml


def generate_lettre_rachat_docx(
    client: dict,
    line: dict,
    *,
    document: Optional[dict] = None,
    template_path: Optional[Path] = None,
    when: Optional[date] = None,
) -> tuple[bytes, str]:
    path = Path(template_path or TEMPLATE_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"Modèle Word introuvable : {path}")
    source = path.read_bytes()
    out_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source), "r") as zin, zipfile.ZipFile(out_buf, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "word/document.xml":
                xml = data.decode("utf-8")
                xml = render_lettre_rachat_xml(
                    xml, client, line, document=document, when=when
                )
                data = xml.encode("utf-8")
            zout.writestr(info, data)
    policy = _clean((line or {}).get("policy_number"))
    return out_buf.getvalue(), lettre_rachat_filename(client or {}, policy)
