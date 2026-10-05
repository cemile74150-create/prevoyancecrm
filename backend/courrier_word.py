"""
Génération du courrier Word Agence Mendes à partir du modèle .docx.

Le fichier modèle est copié tel quel (logo, pied de page, marges, polices).
Seuls le bloc destinataire, la date, la civilité, la formule de politesse
et le montant du gain fiscal sont adaptés.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "templates" / "courrier" / "agencemendessarl-courrier.docx"
)
DOC_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TZ_GENEVA = ZoneInfo("Europe/Zurich")
MOIS_FR = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)

ADDR_RPR = (
    '<w:rPr><w:rStyle w:val="text-color"/>'
    '<w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi" w:cstheme="majorHAnsi"/>'
    '<w:color w:val="000000"/></w:rPr>'
)
DATE_RPR = (
    '<w:rPr><w:rFonts w:asciiTheme="majorHAnsi" '
    'w:hAnsiTheme="majorHAnsi" w:cstheme="majorHAnsi"/></w:rPr>'
)
GREETING_RPR = (
    '<w:rPr><w:rStyle w:val="text-color"/>'
    '<w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi" w:cstheme="majorHAnsi"/>'
    '<w:color w:val="000000"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>'
)
GAIN_RPR = (
    '<w:rPr><w:rStyle w:val="text-color"/>'
    '<w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi" w:cstheme="majorHAnsi"/>'
    '<w:b/><w:bCs/><w:color w:val="000000"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>'
)


CIV_M = "M."
CIV_F = "Mme"


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "undefined", "n/a", "na", "-"}:
        return ""
    if re.fullmatch(r"\[.+\]", text):
        return ""
    return " ".join(text.split())


def _title_from_sexe(sexe: Any) -> Optional[str]:
    """Civilité longue (appel du courrier) : Monsieur / Madame."""
    short = civility_short(sexe)
    if is_male_civ(short):
        return "Monsieur"
    if is_female_civ(short):
        return "Madame"
    return None


def is_male_civ(value: Any) -> bool:
    if value in {CIV_M, "Mr", "Monsieur"}:
        return True
    return civility_short(value) == CIV_M


def is_female_civ(value: Any) -> bool:
    if value in {CIV_F, "Madame", "Mme"}:
        return True
    return civility_short(value) == CIV_F


def address_title(civ: Optional[str]) -> Optional[str]:
    """Civilité affichée dans le bloc adresse : M. / Mme."""
    if is_male_civ(civ):
        return CIV_M
    if is_female_civ(civ):
        return CIV_F
    return None


def civility_short(value: Any) -> Optional[str]:
    """Civilité courte interne : M. / Mme."""
    raw = _clean(value)
    if not raw:
        return None
    s = raw.casefold()
    s = (
        s.replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace(".", "")
        .replace(" ", "")
    )
    if s in {"mme", "mlle", "mademoiselle", "madame", "femme", "feminin", "female", "f"}:
        return CIV_F
    if s in {"mr", "m", "monsieur", "homme", "masculin", "male", "h"}:
        return CIV_M
    if "feminin" in s or s.startswith("f"):
        return CIV_F
    if "masculin" in s or s.startswith("m"):
        return CIV_M
    return None


def _prenom_tokens(value: Any) -> list[str]:
    raw = _clean(value).casefold()
    if not raw:
        return []
    trans = str.maketrans("àáâäãåèéêëìíîïòóôöõùúûüçñýÿ", "aaaaaaeeeeiiiiooooouuuucnyy")
    tokens: list[str] = []
    for part in re.split(r"[\s\-]+", raw):
        key = part.translate(trans)
        if key:
            tokens.append(key)
    return tokens


def _fold_prenom(value: Any) -> str:
    tokens = _prenom_tokens(value)
    return tokens[0] if tokens else ""


# Prénoms fréquents du portefeuille (FR / CH / PT / ES / IT) — repli si le sexe CRM est vide.
_MALE_PRENOMS = frozenset({
    "aaron", "adam", "adrien", "alain", "alan", "albert", "alexandre", "alexis", "alfred",
    "ali", "alvaro", "amine", "andre", "andreas", "andrew", "anthony", "antoine", "anton",
    "antonio", "armand", "arnaud", "arthur", "auguste", "aurelien", "baptiste", "basile",
    "benjamin", "benoit", "bernard", "bertrand", "bruno", "carlo", "carlos", "cedric",
    "charles", "christian", "christophe", "claude", "clement", "cyril", "damien", "daniel",
    "david", "denis", "didier", "diego", "dominique", "dylan", "edouard", "edwin", "elias",
    "emile", "emmanuel", "enrico", "eric", "etienne", "fabien", "fabio", "fabrice", "fernando",
    "florian", "francis", "francisco", "franco", "francois", "frank", "fred", "frederic",
    "gabriel", "gaston", "georges", "gerard", "germain", "gilles", "giovanni", "giuseppe",
    "gregory", "guillaume", "gustave", "gilles", "hector", "henri", "henry", "herve",
    "hugo", "hugues", "ibrahim", "ivan", "jacky", "jacques", "jean", "jeremy", "jerome",
    "joao", "joel", "john", "jonathan", "jordan", "jose", "joseph", "joshua", "jules",
    "julian", "julien", "kevin", "laurent", "leo", "leon", "leonel", "lionel", "loic",
    "louis", "luc", "lucas", "lucien", "luis", "manuel", "marc", "marcel", "marco",
    "marcos", "mario", "martin", "mathias", "mathieu", "matteo", "matthew", "maurice",
    "max", "maxime", "mehdi", "michael", "michel", "miguel", "mohamed", "nabil", "nathan",
    "nicolas", "nuno", "olivier", "oscar", "pascal", "patrice", "patrick", "paul", "paulo",
    "pedro", "philippe", "pierre", "quentin", "rafael", "raphael", "raymond", "regis",
    "remi", "renaud", "rene", "ricardo", "richard", "robert", "robin", "roger", "roland",
    "romain", "rui", "samuel", "sebastien", "serge", "sergio", "simon", "stephane",
    "steve", "steven", "sylvain", "theo", "thierry", "thomas", "timothee", "tony",
    "tristan", "valentin", "victor", "vincent", "vivien", "william", "xavier", "yanis",
    "yann", "yannick", "yves", "yvess", "zacharie",
    "alessandro", "alexander", "antony", "cesar", "dat", "eddy", "engin",
    "gaetan", "gianluca", "joaquim", "lucido", "massimo", "matej", "matthieu",
    "nicholas", "quy", "tiago", "timeo",
})
_FEMALE_PRENOMS = frozenset({
    "adelaide", "adeline", "agnes", "alexandra", "alice", "alicia", "aline", "alix",
    "amandine", "amelia", "ana", "anais", "andrea", "andree", "angela", "angelique",
    "anna", "anne", "annette", "annie", "antonia", "aria", "astrid", "audrey", "aurelia",
    "aurelie", "barbara", "beatrice", "berenice", "berthe", "brigitte", "camille",
    "carine", "carla", "carole", "caroline", "catherine", "cecile", "celia", "celine",
    "cemile", "chantal", "charlotte", "chiara", "chloe", "christelle", "christine",
    "cindy", "claire", "clara", "claude", "claudia", "clemence", "clotilde", "colette",
    "constance", "coralie", "corinne", "cynthia", "dalila", "daniela", "danielle",
    "delphine", "denise", "diane", "dominique", "dora", "edwige", "elena", "eliane",
    "elisa", "elisabeth", "elise", "ellen", "elsa", "emilie", "emma", "emmanuelle",
    "estelle", "esther", "eva", "evelyne", "fabienne", "fanny", "fatima", "fernanda",
    "flavie", "flora", "florence", "francine", "francoise", "gabrielle", "genevieve",
    "georgette", "geraldine", "ghislaine", "gina", "giovanna", "giselle", "gladys",
    "helene", "helena", "henriette", "ines", "ingrid", "irene", "iris", "isabelle",
    "jacqueline", "jade", "jessica", "joana", "joanna", "jocelyne", "joelle", "josepha",
    "josette", "josiane", "judith", "julia", "julie", "juliette", "justine", "karine",
    "katia", "kelly", "laetitia", "lara", "laura", "laure", "laurence", "lea", "leila",
    "lena", "leonie", "lidia", "liliane", "linda", "lisa", "lise", "livia", "lorena",
    "louise", "lucia", "lucie", "lucienne", "lucy", "lydie", "madeleine", "magali",
    "manon", "manuela", "mara", "marcelle", "margaux", "marguerite", "maria", "marianne",
    "marie", "marielle", "marilyn", "marina", "marine", "marion", "marisa", "marthe",
    "martine", "mathilde", "maud", "melanie", "melissa", "mia", "michele", "michelle",
    "mireille", "monica", "monique", "morgane", "muriel", "myriam", "nadia", "nadine",
    "nathalie", "nicole", "nina", "noemie", "oceane", "odette", "odile", "olga", "olivia",
    "paola", "paula", "pauline", "paule", "patricia", "pierrette", "rachel", "raphaelle",
    "rebecca", "regine", "rita", "rosa", "rosalie", "rose", "sandrine", "sara", "sarah",
    "serena", "severine", "sofia", "sonia", "sophia", "sophie", "stephanie", "susan",
    "suzanne", "sylvie", "tatiana", "teresa", "therese", "valentine", "valerie", "vanessa",
    "vera", "veronique", "victoire", "victoria", "violaine", "virginie", "viviane",
    "yolande", "yvette", "yvonne", "zoe",
    "albane", "ann", "ava", "axelle", "cristina", "edith", "elimara", "erin",
    "gilberte", "giorgia", "isabel", "kateryna", "katja", "lalaina", "laurie",
    "leane", "luciana", "lucile", "maira", "mairin", "natalia", "patrizia",
    "rika", "rumana", "sabine", "shailly", "tamara", "thera", "yasmina",
    "marta", "perrine",
})
_AMBIGUOUS_PRENOMS = frozenset({"camille", "claude", "dominique", "maxime", "andrea"})


def civility_from_prenom(prenom: Any) -> Optional[str]:
    """M. / Mme d'après le prénom CRM, sans inventer une personne."""
    tokens = _prenom_tokens(prenom)
    if not tokens:
        return None
    if tokens[0] in _AMBIGUOUS_PRENOMS:
        return None
    found: list[str] = []
    for key in tokens:
        if key in _AMBIGUOUS_PRENOMS:
            continue
        if key in _FEMALE_PRENOMS:
            found.append(CIV_F)
        elif key in _MALE_PRENOMS:
            found.append(CIV_M)
    if not found:
        return None
    if CIV_M in found and CIV_F in found:
        return None
    return found[0]


def resolve_civilities(client: dict) -> tuple[Optional[str], Optional[str]]:
    """
    Civilité de chaque personne réellement présente.
    Priorité : sexe/civilité CRM, puis prénom, puis l'opposé pour le conjoint d'un couple.
    """
    client_civ = civility_short(client.get("sexe") or client.get("civilite"))
    if not client_civ:
        client_civ = civility_from_prenom(client.get("prenom"))
    spouse_prenom, spouse_nom = parse_conjoint(client)
    has_spouse = bool(spouse_prenom or spouse_nom)
    spouse_civ = None
    if has_spouse:
        spouse_civ = civility_short(
            client.get("conjoint_sexe") or client.get("sexe_conjoint") or client.get("civilite_conjoint")
        )
        if not spouse_civ:
            spouse_civ = civility_from_prenom(spouse_prenom)
        if not spouse_civ and is_male_civ(client_civ):
            spouse_civ = CIV_F
        elif not spouse_civ and is_female_civ(client_civ):
            spouse_civ = CIV_M
        if not client_civ and is_male_civ(spouse_civ):
            client_civ = CIV_F
        elif not client_civ and is_female_civ(spouse_civ):
            client_civ = CIV_M
    return client_civ, spouse_civ if has_spouse else None


def _person_line(title: Optional[str], prenom: str, nom: str) -> str:
    name = " ".join(p for p in (prenom, nom) if p).strip()
    if not name:
        return ""
    if title:
        return f"{title} {name}"
    return name


def _split_full_name(full: str) -> tuple[str, str]:
    parts = [p for p in _clean(full).split(" ") if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def parse_conjoint(client: dict) -> tuple[str, str]:
    prenom = _clean(client.get("conjoint_prenom"))
    nom = _clean(client.get("conjoint_nom"))
    if prenom or nom:
        return prenom, nom
    return _split_full_name(_clean(client.get("conjoint")))


def is_couple(client: dict) -> bool:
    prenom, nom = parse_conjoint(client)
    return bool(prenom or nom)


def greeting_for_client(client: dict) -> str:
    """Appel d'ouverture : Madame, / Monsieur, / Madame, Monsieur,"""
    if is_couple(client):
        return "Madame, Monsieur,"
    client_civ, _ = resolve_civilities(client)
    if is_male_civ(client_civ):
        return "Monsieur,"
    if is_female_civ(client_civ):
        return "Madame,"
    # 1 personne, sexe inconnu : ne pas écrire la formule couple
    return "Madame, Monsieur,"


def closing_civility_for_client(client: dict) -> str:
    """Civilité dans la formule de politesse, sans virgule finale (déjà dans le modèle)."""
    return greeting_for_client(client).rstrip(",")


def format_gain_chf(gain: Optional[float]) -> str:
    if gain is None:
        return ""
    n = int(round(float(gain)))
    grouped = f"{n:,}".replace(",", " ")
    return f"{grouped} CHF"


def normalize_country_fr(pays: Any) -> str:
    raw = _clean(pays)
    if not raw:
        return ""
    s = raw.casefold()
    s = s.replace("é", "e").replace("è", "e")
    if s in {"ch", "suisse", "switzerland", "schweiz", "svizzera", "swiss"}:
        return "Suisse"
    if s in {"fr", "france", "frankreich", "french"}:
        return "France"
    if s in {"it", "italie", "italia", "italy"}:
        return "Italie"
    if s in {"de", "allemagne", "deutschland", "germany"}:
        return "Allemagne"
    return raw


_SWISS_CITIES = {
    "geneve", "genève", "geneva", "lausanne", "zurich", "zürich", "berne", "bern",
    "bale", "bâle", "basel", "lucerne", "lugano", "sion", "sierre", "montreux",
    "nyon", "morges", "vevey", "carouge", "vernier", "lancy", "meyrin", "onex",
    "thonex", "thônex", "perly", "confignon", "bernex", "satigny", "versosix",
    "versoix", "plan-les-ouates", "chene-bougeries", "chêne-bougeries",
    "chene-bourg", "chêne-bourg", "grand-saconnex", "le grand-saconnex",
    "puplinge", "troinex", "vandoeuvres", "vandœuvres", "collonge-bellerive",
    "cologny", "bellevue", "gy", "jussy", "presinge", "meinier", "aicre",
    "neuchatel", "neuchâtel", "fribourg", "yverdon", "yverdon-les-bains",
    "aigle", "martigny", "monthey", "delemont", "delémont", "bienne", "biel",
    "winterthour", "winterthur", "st-gall", "saint-gall", "coire", "chur",
    "locarno", "bellinzone", "bellinzona", "nyon", "gland", "rolle", "coppet",
}
_FRENCH_CITIES = {
    "annecy", "paris", "lyon", "annemasse", "thonon", "thonon-les-bains",
    "gaillard", "ville-la-grand", "ambilly", "etrembieres", "étrembières",
    "st-julien-en-genevois", "saint-julien-en-genevois", "viry", "valleiry",
    "chamonix", "cluses", "sallanches", "bonneville", "la roche-sur-foron",
    "cranves-sales", "vetraz-monthoux", "vétraz-monthoux", "reignier",
    "ferney-voltaire", "prevessin-moens", "prévessin-moëns", "gex", "divonne",
    "divonne-les-bains", "crozet", "echenevex", "échenevex", "orsier",
    "orsier-sainte-foy", "bellegarde", "bellegarde-sur-valserine",
    "marseille", "lille", "toulouse", "nantes", "strasbourg", "nice",
    "grenoble", "chambery", "chambéry", "aix-les-bains",
}


def infer_country(client: dict) -> str:
    """Pays en français, sans invention : CRM, puis NPA / adresse / ville."""
    known = normalize_country_fr(client.get("pays") or client.get("pays_residence"))
    if known:
        return known

    adresse = " ".join(
        _clean(client.get(k))
        for k in ("adresse", "adresse_complement", "complement_adresse", "adresse2", "ville")
    )
    blob = adresse.casefold()
    if re.search(r"\bfrance\b", blob):
        return "France"
    if re.search(r"\b(suisse|schweiz|switzerland)\b", blob):
        return "Suisse"
    if re.search(r"\bF\s*\d{5}\b", adresse, re.I):
        return "France"

    npa_digits = re.sub(r"\D", "", _clean(client.get("npa")))
    if len(npa_digits) == 4:
        return "Suisse"
    if len(npa_digits) == 5:
        return "France"

    ville = _clean(client.get("ville")).casefold()
    ville_key = ville.replace("é", "e").replace("è", "e").replace("ê", "e")
    if ville in _SWISS_CITIES or ville_key in _SWISS_CITIES:
        return "Suisse"
    if ville in _FRENCH_CITIES or ville_key in _FRENCH_CITIES:
        return "France"
    return ""


def recipient_lines(client: dict) -> list[str]:
    prenom = _clean(client.get("prenom"))
    nom = _clean(client.get("nom"))
    client_civ, spouse_civ = resolve_civilities(client)
    spouse_prenom, spouse_nom = parse_conjoint(client)
    lines: list[str] = []

    if spouse_prenom or spouse_nom:
        named = []
        # Couple : M. puis Mme, chacun avec sa civilité.
        if is_male_civ(client_civ) and is_female_civ(spouse_civ):
            named = [
                _person_line(CIV_M, prenom, nom),
                _person_line(CIV_F, spouse_prenom, spouse_nom),
            ]
        elif is_female_civ(client_civ) and is_male_civ(spouse_civ):
            named = [
                _person_line(CIV_M, spouse_prenom, spouse_nom),
                _person_line(CIV_F, prenom, nom),
            ]
        elif is_male_civ(client_civ):
            named = [
                _person_line(CIV_M, prenom, nom),
                _person_line(address_title(spouse_civ), spouse_prenom, spouse_nom),
            ]
        elif is_female_civ(client_civ):
            named = [
                _person_line(address_title(spouse_civ), spouse_prenom, spouse_nom),
                _person_line(CIV_F, prenom, nom),
            ]
        elif is_male_civ(spouse_civ):
            named = [
                _person_line(CIV_M, spouse_prenom, spouse_nom),
                _person_line(address_title(client_civ), prenom, nom),
            ]
        elif is_female_civ(spouse_civ):
            named = [
                _person_line(address_title(client_civ), prenom, nom),
                _person_line(CIV_F, spouse_prenom, spouse_nom),
            ]
        else:
            named = [
                _person_line(address_title(client_civ), prenom, nom),
                _person_line(address_title(spouse_civ), spouse_prenom, spouse_nom),
            ]
        lines.extend([ln for ln in named if ln])
    else:
        line = _person_line(address_title(client_civ), prenom, nom)
        if line:
            lines.append(line)

    adresse = _clean(client.get("adresse"))
    complement = _clean(
        client.get("adresse_complement")
        or client.get("complement_adresse")
        or client.get("adresse2")
    )
    npa = _clean(client.get("npa"))
    ville = _clean(client.get("ville"))
    pays = infer_country(client)

    if adresse:
        lines.append(adresse)
    if complement:
        lines.append(complement)
    npa_ville = " ".join(p for p in (npa, ville) if p).strip()
    if npa_ville:
        lines.append(npa_ville)
    if pays:
        lines.append(pays)
    return lines


def format_perly_date(when: Optional[date] = None) -> str:
    d = when or datetime.now(TZ_GENEVA).date()
    return f"Perly, le {d.day} {MOIS_FR[d.month - 1]} {d.year}"


def courrier_filename(client: dict) -> str:
    nom = _clean(client.get("nom"))
    prenom = _clean(client.get("prenom"))
    parts = ["Courrier_Optimisation_Fiscale"]
    if nom:
        parts.append(nom)
    if prenom:
        parts.append(prenom)
    if is_couple(client):
        sp, sn = parse_conjoint(client)
        if sn:
            parts.append(sn)
        if sp:
            parts.append(sp)
    raw = "_".join(parts) or "Courrier_Optimisation_Fiscale"
    safe = re.sub(r'[\\/:*?"<>|]+', "_", raw)
    safe = re.sub(r"\s+", "_", safe).strip("._")
    return f"{safe}.docx"


def is_optimisation_fiscale_doc(doc: dict) -> bool:
    """PDF Analyse optimisation fiscale / Fortune — pas le courrier lui-même."""
    kind = (doc.get("kind") or "").strip().casefold()
    if kind == "courrier_optimisation_fiscale":
        return False
    label = (doc.get("display_label") or "").casefold()
    folder = (doc.get("source_folder") or "").casefold()
    name = (doc.get("original_filename") or "").casefold()
    if "optimisation fiscale" in label:
        return True
    if "fortune" in folder or "optimisation" in folder:
        return True
    if "fortune" in name or "optimisation fiscale" in name:
        return True
    return False


def optimisation_fiscale_gain(client: dict, docs: Optional[Iterable[dict]] = None) -> Optional[float]:
    """
    Gain servant au courrier : le même que la colonne « GAIN FISCAL » du Suivi 3P
    (`gain_fiscal_estime`), avec repli sur le montant extrait des PDF optimisation/fortune.
    """
    from suivi_3p import parse_gain

    client_gain = parse_gain(client.get("gain_fiscal_estime"))
    docs = list(docs or [])
    opt_gains = []
    for d in docs:
        if d.get("is_deleted") or not is_optimisation_fiscale_doc(d):
            continue
        g = parse_gain(d.get("extracted_gain_fiscal"))
        if g is not None:
            opt_gains.append(g)
    if client_gain is not None:
        return client_gain
    if opt_gains:
        return max(opt_gains)
    return None


def is_eligible_for_courrier(client: dict, docs: Optional[Iterable[dict]] = None) -> bool:
    from suivi_3p import GAIN_OPTIM_MIN_EXCLUSIVE

    gain = optimisation_fiscale_gain(client, docs)
    return gain is not None and float(gain) > GAIN_OPTIM_MIN_EXCLUSIVE


def _run_start(xml: str, pos: int) -> int:
    """Début de l'élément <w:r> (pas <w:rPr>)."""
    a = xml.rfind("<w:r ", 0, pos)
    b = xml.rfind("<w:r>", 0, pos)
    return max(a, b)


def _w_t(text: str, rpr: str = ADDR_RPR) -> str:
    escaped = xml_escape(text)
    space = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    return f"<w:r>{rpr}<w:t{space}>{escaped}</w:t></w:r>"


def _replace_recipient_paragraph(xml: str, lines: list[str]) -> str:
    marker = "<w:t>Prénom</w:t>"
    idx = xml.find(marker)
    if idx < 0:
        raise ValueError("Modèle Word : bloc destinataire introuvable ([Prénom])")
    p_start = xml.rfind("<w:p ", 0, idx)
    p_end = xml.find("</w:p>", idx)
    if p_start < 0 or p_end < 0:
        raise ValueError("Modèle Word : paragraphe destinataire illisible")
    p_end += len("</w:p>")
    p_xml = xml[p_start:p_end]
    ppr_close = p_xml.find("</w:pPr>")
    if ppr_close >= 0:
        head = p_xml[: ppr_close + len("</w:pPr>")]
    else:
        gt = p_xml.find(">")
        head = p_xml[: gt + 1]
    runs = ["<w:r><w:br/></w:r>"]  # conserve la ligne vide d'origine au-dessus du bloc
    usable = [ln for ln in lines if ln]
    if not usable:
        usable = [""]
    for i, line in enumerate(usable):
        if i:
            runs.append("<w:r><w:br/></w:r>")
        if line:
            runs.append(_w_t(line))
    return xml[:p_start] + head + "".join(runs) + "</w:p>" + xml[p_end:]


def _replace_perly_date(xml: str, date_line: str) -> str:
    token = ">Perly, le"
    start = xml.find(token)
    if start < 0:
        raise ValueError("Modèle Word : date « Perly, le … » introuvable")
    r_start = _run_start(xml, start)
    month_idx = xml.find("août ", start)
    if month_idx < 0:
        month_idx = xml.find("aout ", start)
    if month_idx < 0:
        # déjà régénéré : remplacer le w:t courant
        t_start = xml.rfind("<w:t", 0, start)
        t_end = xml.find("</w:t>", start)
        if t_start < 0 or t_end < 0:
            raise ValueError("Modèle Word : date illisible")
        open_end = xml.find(">", t_start) + 1
        return xml[:open_end] + xml_escape(date_line) + xml[t_end:]
    t_end = xml.find("</w:t>", month_idx)
    r_end = xml.find("</w:r>", t_end)
    if r_start < 0 or r_end < 0:
        raise ValueError("Modèle Word : date illisible")
    r_end += len("</w:r>")
    replacement = (
        f'<w:r w:rsidRPr="0006255B">{DATE_RPR}'
        f'<w:t xml:space="preserve">{xml_escape(date_line)}</w:t></w:r>'
    )
    return xml[:r_start] + replacement + xml[r_end:]


def _replace_opening_greeting(xml: str, greeting: str) -> str:
    """Remplace le paragraphe [Madame] [,] [Monsieur] par Madame, / Monsieur, / Madame, Monsieur,"""
    marker = "<w:t>Madame</w:t>"
    idx = 0
    p_xml = ""
    p_start = p_end = -1
    while True:
        idx = xml.find(marker, idx)
        if idx < 0:
            raise ValueError("Modèle Word : appel « Madame / Monsieur » introuvable")
        p_start = xml.rfind("<w:p ", 0, idx)
        p_end = xml.find("</w:p>", idx)
        if p_start < 0 or p_end < 0:
            raise ValueError("Modèle Word : paragraphe d'appel illisible")
        p_end += len("</w:p>")
        p_xml = xml[p_start:p_end]
        texts = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p_xml))
        if "agréer" in texts or "agreer" in texts.casefold():
            idx += len(marker)
            continue
        break
    ppr_close = p_xml.find("</w:pPr>")
    if ppr_close < 0:
        raise ValueError("Modèle Word : paragraphe d'appel sans style")
    head = p_xml[: ppr_close + len("</w:pPr>")]
    run = (
        f'<w:r w:rsidRPr="0006255B">{GREETING_RPR}'
        f"<w:t>{xml_escape(greeting)}</w:t></w:r>"
    )
    return xml[:p_start] + head + run + "</w:p>" + xml[p_end:]


def _replace_closing_civility(xml: str, civility: str) -> str:
    """Remplace [Madame] [,] [Monsieur] dans la formule de politesse, virgule du modèle conservée."""
    marker = "<w:t>[Madame] [,]</w:t>"
    idx = xml.find(marker)
    if idx < 0:
        raise ValueError("Modèle Word : formule de politesse introuvable")
    r_start = _run_start(xml, idx)
    m2 = xml.find("<w:t>[Monsieur]</w:t>", idx)
    if r_start < 0 or m2 < 0:
        raise ValueError("Modèle Word : civilité de clôture illisible")
    r_end = xml.find("</w:r>", m2)
    if r_end < 0:
        raise ValueError("Modèle Word : civilité de clôture illisible")
    r_end += len("</w:r>")
    replacement = (
        f'<w:r w:rsidR="0006255B" w:rsidRPr="0006255B">{GREETING_RPR}'
        f"<w:t>{xml_escape(civility)}</w:t></w:r>"
    )
    return xml[:r_start] + replacement + xml[r_end:]


def _replace_gain(xml: str, amount_text: str) -> str:
    marker = "<w:t>0 000 CHF</w:t>"
    idx = xml.find(marker)
    if idx < 0:
        raise ValueError("Modèle Word : montant « 0 000 CHF » introuvable")
    bracket = xml.rfind("<w:t>[</w:t>", 0, idx)
    r_start = _run_start(xml, bracket if bracket >= 0 else idx)
    close = xml.find("<w:t>]</w:t>", idx)
    if r_start < 0 or close < 0:
        raise ValueError("Modèle Word : montant fiscal illisible")
    r_end = xml.find("</w:r>", close)
    if r_end < 0:
        raise ValueError("Modèle Word : montant fiscal illisible")
    r_end += len("</w:r>")
    text = amount_text or ""
    replacement = (
        f'<w:r w:rsidRPr="004F1A93">{GAIN_RPR}'
        f"<w:t>{xml_escape(text)}</w:t></w:r>"
    )
    return xml[:r_start] + replacement + xml[r_end:]


def render_document_xml(
    xml: str,
    client: dict,
    when: Optional[date] = None,
    *,
    gain: Optional[float] = None,
    docs: Optional[Iterable[dict]] = None,
) -> str:
    if gain is None:
        gain = optimisation_fiscale_gain(client, docs)
    xml = _replace_recipient_paragraph(xml, recipient_lines(client))
    xml = _replace_perly_date(xml, format_perly_date(when))
    xml = _replace_opening_greeting(xml, greeting_for_client(client))
    xml = _replace_closing_civility(xml, closing_civility_for_client(client))
    xml = _replace_gain(xml, format_gain_chf(gain))
    if "<w:t>Prénom</w:t>" in xml or "[Ligne adresse" in xml or "<w:t>NPA</w:t>" in xml:
        raise ValueError("Des placeholders du modèle n'ont pas été remplacés")
    if "[Madame]" in xml or "[Monsieur]" in xml or "0 000 CHF" in xml:
        raise ValueError("Civilité ou gain fiscal non remplacés dans le modèle")
    return xml


def generate_courrier_docx(
    client: dict,
    *,
    template_path: Optional[Path] = None,
    when: Optional[date] = None,
    docs: Optional[Iterable[dict]] = None,
    gain: Optional[float] = None,
) -> tuple[bytes, str]:
    path = Path(template_path or TEMPLATE_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"Modèle Word introuvable : {path}")
    source = path.read_bytes()
    in_buf = io.BytesIO(source)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "word/document.xml":
                xml = data.decode("utf-8")
                xml = render_document_xml(xml, client, when=when, gain=gain, docs=docs)
                data = xml.encode("utf-8")
            zout.writestr(info, data)
    return out_buf.getvalue(), courrier_filename(client)


def generate_courriers_zip(
    clients: Iterable[dict],
    *,
    template_path: Optional[Path] = None,
    when: Optional[date] = None,
) -> bytes:
    buf = io.BytesIO()
    used: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for client in clients:
            data, name = generate_courrier_docx(client, template_path=template_path, when=when)
            stem = name[:-5] if name.lower().endswith(".docx") else name
            n = used.get(stem, 0)
            used[stem] = n + 1
            final = name if n == 0 else f"{stem}_{n + 1}.docx"
            zf.writestr(final, data)
    return buf.getvalue()
