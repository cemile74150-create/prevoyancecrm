"""Identité client unique : une personne = un profil hub.

Clé normalisée : prenom_norm + nom_norm + date_naissance (YYYY-MM-DD).
Réutilise la même normalisation d'accents / espaces que ``normalize_person_name``
(suivi_3p) — alignée sur le style conseiller (NFD/NFKD, casefold, collapse spaces).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from suivi_3p import normalize_person_name

DUPLICATE_MESSAGE = (
    "Ce client existe déjà dans Leosoft. "
    "La création d'un nouveau profil est impossible. "
    "Veuillez utiliser le dossier existant."
)

DUPLICATE_CODE = "CLIENT_DUPLICATE"


def normalize_client_name(value: Any) -> str:
    """Trim, collapse spaces, accents retirés, casefold."""
    return normalize_person_name(value)


def normalize_date_naissance(value: Any) -> str:
    """Normalise une date de naissance en YYYY-MM-DD (vide si absente / invalide)."""
    if not value:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if "T" in s:
        s = s.split("T", 1)[0]
    s = s[:10]
    # Accepte déjà ISO ; ignore les valeurs chiffrées (enc:v1:)
    if s.startswith("enc:"):
        return ""
    # jj.mm.aaaa → aaaa-mm-jj
    if len(s) == 10 and s[2] == "." and s[5] == ".":
        try:
            d, m, y = s.split(".")
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        except Exception:
            return ""
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s if len(s) == 10 else ""


def client_identity_parts(
    prenom: Any,
    nom: Any,
    date_naissance: Any = None,
) -> Tuple[str, str, str]:
    return (
        normalize_client_name(prenom),
        normalize_client_name(nom),
        normalize_date_naissance(date_naissance),
    )


def client_identity_key(
    prenom: Any,
    nom: Any,
    date_naissance: Any = None,
) -> str:
    """Clé stable stockable. Vide si prénom ou nom manquant.

    Sans date de naissance : clé partielle ``prenom|nom|`` (suffixe vide)
    — utile pour détecter des doublons sans DOB, mais pas pour l'index unique
    (l'index n'accepte que les clés avec DOB, via ``identity_key_complete``).
    """
    p, n, d = client_identity_parts(prenom, nom, date_naissance)
    if not p or not n:
        return ""
    return f"{p}|{n}|{d}"


def identity_key_complete(key: str) -> bool:
    """True si la clé contient prénom, nom ET date (3 segments non vides)."""
    if not key or key.count("|") != 2:
        return False
    p, n, d = key.split("|", 2)
    return bool(p and n and d)


def identity_fields_for_storage(
    prenom: Any,
    nom: Any,
    date_naissance: Any = None,
) -> Dict[str, str]:
    """Champs plaintext pour index / recherche (noms déjà en clair en base)."""
    p, n, d = client_identity_parts(prenom, nom, date_naissance)
    key = f"{p}|{n}|{d}" if p and n else ""
    out: Dict[str, str] = {
        "prenom_norm": p,
        "nom_norm": n,
        "date_naissance_norm": d,
        "identity_key": key if identity_key_complete(key) else "",
    }
    return out


def _decrypt_doc(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    try:
        from field_crypto import decrypt_client_fields

        return decrypt_client_fields(doc)
    except Exception:
        return doc


def _hub_base_query(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "source_import": {"$ne": "suivi_3p_excel"},
        "is_deleted": {"$ne": True},
    }


def existing_summary(client: dict) -> dict:
    """Payload UI pour ouvrir le dossier existant."""
    prenom = (client.get("prenom") or "").strip()
    nom = (client.get("nom") or "").strip()
    return {
        "id": client.get("id"),
        "prenom": prenom,
        "nom": nom,
        "name": f"{prenom} {nom}".strip(),
        "date_naissance": normalize_date_naissance(client.get("date_naissance")) or client.get("date_naissance"),
        "numero_dossier": client.get("numero_dossier"),
        "conseiller": client.get("conseiller"),
        "dossier_id": client.get("dossier_id") or client.get("id"),
        "statut": client.get("statut"),
    }


def duplicate_conflict_detail(existing: dict, *, matches: Optional[List[dict]] = None) -> dict:
    items = [existing_summary(m) for m in (matches or [existing])]
    primary = items[0] if items else existing_summary(existing)
    return {
        "code": DUPLICATE_CODE,
        "message": DUPLICATE_MESSAGE,
        "existing": primary,
        "matches": items,
    }


async def find_identity_matches(
    db,
    *,
    prenom: str,
    nom: str,
    date_naissance: Optional[str] = None,
    user_id: str,
    exclude_id: Optional[str] = None,
) -> List[dict]:
    """Trouve les clients hub avec la même identité normalisée.

    - Avec DOB : match strict prenom+nom+DOB (ordre prénom/nom interchangeable).
    - Sans DOB : match prenom+nom uniquement (homonymes possibles).
    """
    p, n, d = client_identity_parts(prenom, nom, date_naissance)
    if not p or not n:
        return []

    # Raccourci index si identity_key déjà backfillée
    complete_key = f"{p}|{n}|{d}" if d else ""
    alt_key = f"{n}|{p}|{d}" if d else ""  # prénom/nom inversés stockés
    if complete_key:
        keyed = await db.clients.find(
            {
                **_hub_base_query(user_id),
                "identity_key": {"$in": [complete_key, alt_key]},
            },
            {"_id": 0},
        ).to_list(50)
        if keyed:
            out = []
            for raw in keyed:
                c = _decrypt_doc(raw) or raw
                if exclude_id and c.get("id") == exclude_id:
                    continue
                out.append(c)
            if out:
                return out

    candidates = await db.clients.find(_hub_base_query(user_id), {"_id": 0}).to_list(20000)
    matches: List[dict] = []
    for raw in candidates:
        c = _decrypt_doc(raw) or raw
        if exclude_id and c.get("id") == exclude_id:
            continue
        cp = normalize_client_name(c.get("prenom"))
        cn = normalize_client_name(c.get("nom"))
        if not cp or not cn:
            continue
        name_ok = (cp == p and cn == n) or (cp == n and cn == p)
        if not name_ok:
            continue
        if d:
            cd = normalize_date_naissance(c.get("date_naissance"))
            # DOB différente connue → autre personne
            if cd and cd != d:
                continue
            # DOB absente côté existant + DOB fournie à la création → match
            # (évite de recréer quand la fiche existante est incomplète)
        matches.append(c)
    return matches


async def require_unique_identity(
    db,
    *,
    prenom: str,
    nom: str,
    date_naissance: Optional[str] = None,
    user_id: str,
    exclude_id: Optional[str] = None,
) -> None:
    """Lève HTTP 409 si un profil existe déjà pour cette identité.

    Sans date de naissance : refuse aussi s'il existe un homonyme exact
    (même prénom+nom normalisés), pour bloquer les créations en série
    sans DOB renseignée.
    """
    from fastapi import HTTPException

    matches = await find_identity_matches(
        db,
        prenom=prenom,
        nom=nom,
        date_naissance=date_naissance,
        user_id=user_id,
        exclude_id=exclude_id,
    )
    if not matches:
        return
    # Préférer le plus ancien (created_at)
    matches_sorted = sorted(
        matches,
        key=lambda c: str(c.get("created_at") or ""),
    )
    raise HTTPException(
        status_code=409,
        detail=duplicate_conflict_detail(matches_sorted[0], matches=matches_sorted),
    )


def cluster_duplicates(clients: List[dict]) -> List[dict]:
    """Regroupe les doublons par clé identité (prenom|nom|dob).

    Les clients sans DOB sont regroupés par prenom|nom uniquement
    (clé avec dob vide), séparément des clusters avec DOB.
    """
    groups: Dict[str, List[dict]] = {}
    for raw in clients:
        c = _decrypt_doc(raw) or raw
        if c.get("is_deleted") is True:
            continue
        if c.get("source_import") == "suivi_3p_excel":
            continue
        key = client_identity_key(c.get("prenom"), c.get("nom"), c.get("date_naissance"))
        if not key:
            continue
        # Normaliser ordre prénom/nom : toujours p|n|d avec p=prenom stocké
        groups.setdefault(key, []).append(c)

    # Fusionner les clés inversées (nom|prenom|dob) si l'autre existe
    # (rare ; les créations stockent prénom/nom correctement)
    clusters = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        clusters.append({
            "identity_key": key,
            "prenom": members[0].get("prenom"),
            "nom": members[0].get("nom"),
            "date_naissance": normalize_date_naissance(members[0].get("date_naissance")),
            "count": len(members),
            "dossiers": [
                {
                    "id": m.get("id"),
                    "numero_dossier": m.get("numero_dossier"),
                    "conseiller": m.get("conseiller"),
                    "created_at": m.get("created_at"),
                    "statut": m.get("statut"),
                    "prenom": m.get("prenom"),
                    "nom": m.get("nom"),
                }
                for m in sorted(members, key=lambda x: str(x.get("created_at") or ""))
            ],
        })
    clusters.sort(key=lambda g: (-g["count"], g.get("nom") or "", g.get("prenom") or ""))
    return clusters
