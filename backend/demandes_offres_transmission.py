"""Transmission d'une offre compagnie à l'agent.

Deux parcours alimentent la même réponse compagnie (offres[]) :
- Réponses compagnies : date de réception, N variantes, Offre / CGA /
  Autre document par variante ;
- Traitement : compagnie, date, Offre / CGA / Autre document, commentaire
  (sans nombre de variantes).

Chaque transmission est ajoutée à offres[].transmissions. Les documents
précédents ne sont jamais remplacés.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Iterable, Optional

PARCOURS_REPONSES = "reponses_compagnies"
PARCOURS_TRAITEMENT = "traitement"
PARCOURS = (PARCOURS_REPONSES, PARCOURS_TRAITEMENT)
PARCOURS_LABELS = {
    PARCOURS_REPONSES: "Réponses compagnies",
    PARCOURS_TRAITEMENT: "Traitement",
}

MAX_VARIANTES = 20
VARIANTE_PIECES = (
    ("offre", "Offre"),
    ("cga", "CGA"),
    ("autre", "Autre document"),
)
PIECES_OBLIGATOIRES = ("offre", "cga")
_VARIANTE_FIELD_RE = re.compile(r"^variante_(\d+)_(offre|cga|autre)$")
_TRAITEMENT_PIECE_IDS = {piece for piece, _ in VARIANTE_PIECES}
_TRAITEMENT_LEGACY_FIELDS = {"files", "documents", "file"}


def normalize_parcours(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in PARCOURS else PARCOURS_TRAITEMENT


def parse_nb_variantes(raw: Any) -> int:
    """Vide = 1. Entier positif uniquement, plafonné à MAX_VARIANTES."""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return 1
    if not re.fullmatch(r"\d+", text):
        raise ValueError("Le nombre de variantes doit être un entier positif.")
    value = int(text)
    if value < 1:
        raise ValueError("Le nombre de variantes doit être un entier positif.")
    if value > MAX_VARIANTES:
        raise ValueError(f"Maximum {MAX_VARIANTES} variantes par transmission.")
    return value


def variante_field(index: int, piece: str) -> str:
    return f"variante_{int(index)}_{piece}"


def parse_variante_field(name: Any) -> Optional[tuple[int, str]]:
    match = _VARIANTE_FIELD_RE.match(str(name or "").strip())
    if not match:
        return None
    return int(match.group(1)), match.group(2)


def group_variante_uploads(items: Iterable[tuple[str, Any]], nb_variantes: int) -> dict:
    """{index: {piece: [upload, ...]}} pour les champs variante_<n>_<pièce>.

    Un fichier rattaché à une variante au-delà du nombre annoncé est refusé :
    il ne doit pas être enregistré sans variante.
    """
    groups: dict[int, dict[str, list]] = {
        index: {piece: [] for piece, _ in VARIANTE_PIECES}
        for index in range(1, nb_variantes + 1)
    }
    for field, upload in items:
        parsed = parse_variante_field(field)
        if not parsed or upload is None:
            continue
        index, piece = parsed
        if index < 1 or index > nb_variantes:
            raise ValueError(f"Document rattaché à une variante inexistante ({index}).")
        groups[index][piece].append(upload)
    return groups


def missing_variante_pieces(groups: dict, nb_variantes: int) -> list[str]:
    labels = dict(VARIANTE_PIECES)
    missing = []
    for index in range(1, nb_variantes + 1):
        pieces = groups.get(index) or {}
        for piece in PIECES_OBLIGATOIRES:
            if not pieces.get(piece):
                missing.append(f"Variante {index} : {labels[piece]}")
    return missing


def group_traitement_uploads(items: Iterable[tuple[str, Any]]) -> dict:
    """{piece: [upload, ...]} pour les champs offre / cga / autre.

    Les anciens champs files / documents / file sont rattachés à « offre »
    pour ne pas casser un client qui n'envoie encore qu'un document générique.
    """
    groups: dict[str, list] = {piece: [] for piece, _ in VARIANTE_PIECES}
    for field, upload in items:
        if upload is None:
            continue
        name = str(field or "").strip().lower()
        if name in _TRAITEMENT_PIECE_IDS:
            groups[name].append(upload)
        elif name in _TRAITEMENT_LEGACY_FIELDS:
            groups["offre"].append(upload)
    return groups


def missing_traitement_pieces(groups: dict) -> list[str]:
    labels = dict(VARIANTE_PIECES)
    return [labels[piece] for piece in PIECES_OBLIGATOIRES if not (groups or {}).get(piece)]


def document_variante_extra(*, transmission_id: str, parcours: str, compagnie: str,
                            variante: Optional[int] = None, piece: Optional[str] = None) -> dict:
    """Métadonnées posées sur le document stocké (collection documents)."""
    extra = {
        "transmission_id": transmission_id,
        "transmission_parcours": parcours,
        "compagnie": compagnie,
    }
    if variante is not None:
        extra["variante"] = int(variante)
    if piece:
        extra["piece_kind"] = dict(VARIANTE_PIECES).get(piece, piece)
    return extra


def find_transmission(offres: list, token: Any) -> Optional[dict]:
    """Transmission déjà enregistrée avec ce jeton (double clic, renvoi réseau)."""
    key = str(token or "").strip()
    if not key:
        return None
    for offer in offres or []:
        for item in (offer or {}).get("transmissions") or []:
            if isinstance(item, dict) and item.get("client_token") == key:
                return item
    return None


def build_transmission(
    *,
    parcours: str,
    compagnie: str,
    date_reception: str,
    nb_variantes: int,
    stored_by_variante: dict,
    stored_simple: list,
    commentaire: str,
    by_name: str,
    by_id: str,
    at: str,
    client_token: str = "",
    transmission_id: Optional[str] = None,
) -> dict:
    variantes = []
    if parcours == PARCOURS_REPONSES:
        for index in range(1, nb_variantes + 1):
            pieces = stored_by_variante.get(index) or {}
            variantes.append({
                "index": index,
                "documents": {
                    piece: [d.get("id") for d in pieces.get(piece) or [] if d.get("id")]
                    for piece, _ in VARIANTE_PIECES
                },
            })
    document_ids = [d.get("id") for d in stored_simple if d.get("id")]
    for item in variantes:
        for ids in item["documents"].values():
            document_ids.extend(ids)
    return {
        "id": transmission_id or str(uuid.uuid4()),
        "parcours": parcours,
        "compagnie": compagnie,
        "date_reception": date_reception,
        "nb_variantes": nb_variantes if parcours == PARCOURS_REPONSES else None,
        "variantes": variantes,
        "document_ids": document_ids,
        "commentaire": (commentaire or "").strip(),
        "at": at,
        "by_name": by_name,
        "by_id": by_id,
        "client_token": str(client_token or "").strip() or None,
    }


def total_variantes(transmissions: list) -> int:
    return sum(int(t.get("nb_variantes") or 0) for t in transmissions or [] if isinstance(t, dict))


def history_detail(transmission: dict, nb_documents: int) -> str:
    parts = [transmission.get("compagnie") or "Compagnie"]
    if transmission.get("nb_variantes"):
        n = int(transmission["nb_variantes"])
        parts.append(f"{n} variante{'s' if n > 1 else ''}")
    if nb_documents:
        parts.append(f"{nb_documents} document(s)")
    parts.append(PARCOURS_LABELS.get(transmission.get("parcours"), ""))
    return " · ".join(p for p in parts if p)
