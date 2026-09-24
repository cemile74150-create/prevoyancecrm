"""Hub clients centralisé : une seule identité personne (collection `clients`).

Les modules (Offres, Suivi 3P, …) stockent un `client_id` vers ce hub
et dénormalisent l'identité pour le workflow.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from access_control import TENANT_USER_ID
from suivi_3p import normalize_person_name, person_match_key

# Réexport pour les tests / callers
__all__ = (
    "find_hub_client",
    "get_hub_client",
    "upsert_hub_client_from_person",
    "apply_hub_to_offre",
    "apply_hub_to_suivi",
    "person_dict_from_any",
    "person_match_key",
    "propagate_hub_identity",
    "push_person_to_hub",
    "client_modules_activity",
    "link_existing_module_records",
)

logger = logging.getLogger(__name__)

# Champs identité / adresse / famille / pro partagés entre hub et modules
IDENTITY_FIELDS = (
    "civilite",
    "prenom",
    "nom",
    "sexe",
    "date_naissance",
    "nationalite",
    "pays_residence",
    "pays",
    "frontalier",
    "avs_number",
    "email",
    "telephone",
    "adresse",
    "adresse_complement",
    "npa",
    "ville",
    "etat_civil",
    "nombre_enfants",
    "conjoint",
    "conjoint_prenom",
    "conjoint_nom",
    "conjoint_date_naissance",
    "employeur",
    "profession",
    "taux_activite",
    "salaire_annuel",
    "conseiller",
)

# Mapping hub → demande d'offre
HUB_TO_OFFRE = {
    "civilite": "civilite",
    "nom": "nom",
    "prenom": "prenom",
    "sexe": "sexe",
    "date_naissance": "date_naissance",
    "nationalite": "nationalite",
    "adresse": "adresse",
    "adresse_complement": "adresse_complement",
    "npa": "npa",
    "ville": "ville",
    "pays_residence": "pays",
    "pays": "pays",
    "etat_civil": "situation",
    "profession": "profession",
    "employeur": "employeur",
    "email": "email",
    "telephone": "telephone",
}

HUB_TO_SUIVI = {
    "prenom": "prenom",
    "nom": "nom",
    "date_naissance": "date_naissance",
    "etat_civil": "etat_civil",
    "nombre_enfants": "nombre_enfants",
    "conseiller": "conseiller",
    "conjoint": "conjoint",
    "conjoint_prenom": "conjoint_prenom",
    "conjoint_nom": "conjoint_nom",
    "conjoint_date_naissance": "conjoint_date_naissance",
    "email": "email",
    "telephone": "telephone",
    "adresse": "adresse",
    "adresse_complement": "adresse_complement",
    "npa": "npa",
    "ville": "ville",
    "pays_residence": "pays",
    "pays": "pays",
    "sexe": "sexe",
    "civilite": "civilite",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(v: Any) -> str:
    return str(v or "").strip()


def _dob(v: Any) -> Optional[str]:
    if not v:
        return None
    s = str(v).strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    return s[:10] or None


def _decrypt(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    try:
        from field_crypto import decrypt_client_fields
        from data_crypto_keys import EncryptionNotConfigured

        return decrypt_client_fields(doc)
    except Exception:
        return doc


def _encrypt(doc: dict) -> dict:
    try:
        from field_crypto import encrypt_client_fields
        from data_crypto_keys import encryption_configured

        if not encryption_configured():
            return doc
        return encrypt_client_fields(doc)
    except Exception:
        return doc


def _encrypt_patch(updates: dict) -> dict:
    try:
        from field_crypto import patch_encrypt_sensitive
        from data_crypto_keys import encryption_configured

        if not encryption_configured():
            return updates
        return patch_encrypt_sensitive(updates)
    except Exception:
        return updates


def person_dict_from_any(source: dict) -> dict:
    """Extrait un dict identité normalisé depuis hub / offre / suivi."""
    out = {}
    for k in IDENTITY_FIELDS:
        if k in source and source.get(k) not in (None, ""):
            out[k] = source.get(k)
    if "date_naissance" in out:
        out["date_naissance"] = _dob(out["date_naissance"])
    if "conjoint_date_naissance" in out:
        out["conjoint_date_naissance"] = _dob(out["conjoint_date_naissance"])
    # Alias pays
    if not out.get("pays_residence") and out.get("pays"):
        out["pays_residence"] = out["pays"]
    if not out.get("pays") and out.get("pays_residence"):
        out["pays"] = out["pays_residence"]
    if not out.get("civilite") and out.get("sexe"):
        out["civilite"] = out["sexe"]
    return out


def apply_hub_to_offre(hub: dict, target: Optional[dict] = None) -> dict:
    target = dict(target or {})
    hub = _decrypt(hub) or hub
    for src, dst in HUB_TO_OFFRE.items():
        val = hub.get(src)
        if val in (None, ""):
            continue
        if dst == "date_naissance":
            val = _dob(val) or ""
        target[dst] = val
    return target


def apply_hub_to_suivi(hub: dict, target: Optional[dict] = None) -> dict:
    target = dict(target or {})
    hub = _decrypt(hub) or hub
    for src, dst in HUB_TO_SUIVI.items():
        val = hub.get(src)
        if val in (None, ""):
            continue
        if "date_naissance" in dst:
            val = _dob(val)
        target[dst] = val
    return target


async def _next_dossier_number(db, user_id: str) -> str:
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": {"$ifNull": ["$dossier_id", "$id"]}}},
        {"$count": "n"},
    ]
    rows = await db.clients.aggregate(pipeline).to_list(1)
    count = rows[0]["n"] if rows else 0
    return f"DOS-{count + 1:04d}"


async def find_hub_client(
    db,
    *,
    nom: str,
    prenom: str,
    date_naissance: Optional[str] = None,
    user_id: str = TENANT_USER_ID,
) -> Optional[dict]:
    """Trouve un client hub par identité. Match fort : nom+prénom (+ DOB si fourni)."""
    key = person_match_key(nom, prenom)
    if not key or key == "|":
        return None
    want_dob = _dob(date_naissance)
    candidates = await db.clients.find(
        {
            "user_id": user_id,
            "source_import": {"$ne": "suivi_3p_excel"},
            "is_deleted": {"$ne": True},
        },
        {"_id": 0},
    ).to_list(10000)

    matches: List[dict] = []
    for raw in candidates:
        c = _decrypt(raw) or raw
        k1 = person_match_key(c.get("nom"), c.get("prenom"))
        k2 = person_match_key(c.get("prenom"), c.get("nom"))
        if key not in {k1, k2}:
            continue
        # DOB fournie → match strict (évite les homonymes / doublons)
        if want_dob:
            got = _dob(c.get("date_naissance"))
            if got != want_dob:
                continue
        matches.append(c)

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Ambigu : préférer match DOB exact
    if want_dob:
        exact = [m for m in matches if _dob(m.get("date_naissance")) == want_dob]
        if len(exact) == 1:
            return exact[0]
        if exact:
            return exact[0]
    return matches[0]


async def get_hub_client(db, client_id: str, *, user_id: str = TENANT_USER_ID) -> Optional[dict]:
    if not client_id:
        return None
    doc = await db.clients.find_one(
        {"id": client_id, "user_id": user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    return _decrypt(doc) if doc else None


def _merge_source_modules(existing: Any, module: Optional[str]) -> List[str]:
    mods = []
    if isinstance(existing, list):
        mods = [str(x) for x in existing if x]
    elif existing:
        mods = [str(existing)]
    if module and module not in mods:
        mods.append(module)
    return mods


async def upsert_hub_client_from_person(
    db,
    person: dict,
    *,
    user_id: str = TENANT_USER_ID,
    module: Optional[str] = None,
    conseiller: Optional[str] = None,
    create_if_missing: bool = True,
) -> Tuple[Optional[dict], str]:
    """
    Crée ou met à jour le client hub.
    Retourne (hub_doc_decrypted, action) avec action in created|linked|updated|skipped.
    """
    person = person_dict_from_any(person or {})
    prenom = _safe(person.get("prenom"))
    nom = _safe(person.get("nom"))
    if not prenom or not nom:
        return None, "skipped"

    existing = await find_hub_client(
        db,
        nom=nom,
        prenom=prenom,
        date_naissance=person.get("date_naissance"),
        user_id=user_id,
    )

    now = _now_iso()
    if existing:
        updates: Dict[str, Any] = {"updated_at": now}
        # Compléter les champs vides uniquement (ne pas écraser la fiche principale)
        for k in IDENTITY_FIELDS:
            new_v = person.get(k)
            if new_v in (None, ""):
                continue
            old_v = existing.get(k)
            if old_v in (None, ""):
                updates[k] = _dob(new_v) if "date_naissance" in k else new_v
        updates["source_modules"] = _merge_source_modules(existing.get("source_modules"), module)
        if conseiller and not existing.get("conseiller"):
            updates["conseiller"] = conseiller
        patch = _encrypt_patch({k: v for k, v in updates.items() if k != "updated_at" and k != "source_modules"})
        patch["updated_at"] = now
        patch["source_modules"] = updates["source_modules"]
        await db.clients.update_one({"id": existing["id"], "user_id": user_id}, {"$set": patch})
        refreshed = await get_hub_client(db, existing["id"], user_id=user_id)
        return refreshed, "linked" if len(updates) <= 2 else "updated"

    if not create_if_missing:
        return None, "skipped"

    # Garde-fou course : re-check juste avant insert (double onglet / API parallèle)
    from client_identity import identity_fields_for_storage

    existing_again = await find_hub_client(
        db,
        nom=nom,
        prenom=prenom,
        date_naissance=person.get("date_naissance"),
        user_id=user_id,
    )
    if existing_again:
        return existing_again, "linked"

    dossier_id = str(uuid.uuid4())
    numero = await _next_dossier_number(db, user_id)
    identity = identity_fields_for_storage(prenom, nom, person.get("date_naissance"))
    doc = {
        "id": dossier_id,
        "user_id": user_id,
        "prenom": prenom,
        "nom": nom,
        "date_naissance": _dob(person.get("date_naissance")),
        "sexe": person.get("sexe") or person.get("civilite") or "",
        "civilite": person.get("civilite") or person.get("sexe") or "",
        "nationalite": person.get("nationalite") or "",
        "pays_residence": person.get("pays_residence") or person.get("pays") or "",
        "frontalier": person.get("frontalier") or "non",
        "avs_number": person.get("avs_number") or "",
        "email": person.get("email") or "",
        "telephone": person.get("telephone") or "",
        "adresse": person.get("adresse") or "",
        "adresse_complement": person.get("adresse_complement") or "",
        "npa": person.get("npa") or "",
        "ville": person.get("ville") or "",
        "etat_civil": person.get("etat_civil") or "",
        "nombre_enfants": person.get("nombre_enfants") or 0,
        "conjoint": person.get("conjoint") or "",
        "conjoint_prenom": person.get("conjoint_prenom") or "",
        "conjoint_nom": person.get("conjoint_nom") or "",
        "conjoint_date_naissance": _dob(person.get("conjoint_date_naissance")),
        "employeur": person.get("employeur") or "",
        "profession": person.get("profession") or "",
        "taux_activite": person.get("taux_activite") or "",
        "salaire_annuel": person.get("salaire_annuel") or "",
        "conseiller": conseiller or person.get("conseiller") or None,
        "statut": "Nouveau",
        "priorite": "normale",
        "numero_dossier": numero,
        "dossier_id": dossier_id,
        "dossier_label": f"{prenom} {nom}".strip(),
        "source_modules": [module] if module else [],
        "linked_from": module,
        # Fiches créées depuis Offres / Fiscalité : visibles dans Clients, pas dans Dossiers
        "in_dossiers": False,
        "document_checklist": {},
        "created_at": now,
        "updated_at": now,
        **identity,
    }
    # Ne JAMAIS utiliser source_import=suivi_3p_excel (exclu de l'onglet Clients)
    to_store = _encrypt(doc)
    try:
        await db.clients.insert_one(to_store)
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "unique" in err or "e11000" in err:
            raced = await find_hub_client(
                db,
                nom=nom,
                prenom=prenom,
                date_naissance=person.get("date_naissance"),
                user_id=user_id,
            )
            if raced:
                return raced, "linked"
        raise
    return _decrypt(doc), "created"


async def propagate_hub_identity(db, hub_client_id: str, *, user_id: str = TENANT_USER_ID) -> dict:
    """Propage l'identité hub vers offres + suivi 3P liés (pas les statuts métier)."""
    hub = await get_hub_client(db, hub_client_id, user_id=user_id)
    if not hub:
        return {"offres": 0, "suivi_3p": 0}

    offre_patch = apply_hub_to_offre(hub)
    offre_patch["updated_at"] = _now_iso()
    from demandes_offres_3p import COLLECTION as OFFRES_COL

    r1 = await db[OFFRES_COL].update_many(
        {"user_id": user_id, "client_id": hub_client_id, "is_deleted": {"$ne": True}},
        {"$set": offre_patch},
    )

    suivi_patch = apply_hub_to_suivi(hub)
    suivi_patch["updated_at"] = _now_iso()
    from suivi_3p import COLLECTION_CLIENTS as SUIVI_COL

    encrypted_suivi = _encrypt_patch(suivi_patch)
    r2 = await db[SUIVI_COL].update_many(
        {"user_id": user_id, "client_id": hub_client_id},
        {"$set": encrypted_suivi},
    )
    return {
        "offres": int(getattr(r1, "modified_count", 0) or 0),
        "suivi_3p": int(getattr(r2, "modified_count", 0) or 0),
    }


async def push_person_to_hub(
    db,
    client_id: str,
    person: dict,
    *,
    user_id: str = TENANT_USER_ID,
    module: Optional[str] = None,
) -> Optional[dict]:
    """Met à jour le hub depuis une édition module (identité)."""
    if not client_id:
        return None
    hub = await get_hub_client(db, client_id, user_id=user_id)
    if not hub:
        return None
    person = person_dict_from_any(person)
    updates = {"updated_at": _now_iso()}
    for k in IDENTITY_FIELDS:
        if k in person and person.get(k) not in (None, ""):
            updates[k] = _dob(person[k]) if "date_naissance" in k else person[k]
    updates["source_modules"] = _merge_source_modules(hub.get("source_modules"), module)
    patch = _encrypt_patch({k: v for k, v in updates.items() if k not in {"updated_at", "source_modules"}})
    patch["updated_at"] = updates["updated_at"]
    patch["source_modules"] = updates["source_modules"]
    await db.clients.update_one({"id": client_id, "user_id": user_id}, {"$set": patch})
    return await get_hub_client(db, client_id, user_id=user_id)


async def client_modules_activity(db, client_id: str, *, user_id: str = TENANT_USER_ID) -> dict:
    """Résumé des modules liés à un client hub."""
    hub = await get_hub_client(db, client_id, user_id=user_id)
    if not hub:
        return {"client_id": client_id, "found": False}

    from demandes_offres_3p import COLLECTION as OFFRES_COL
    from suivi_3p import COLLECTION_CLIENTS as SUIVI_COL

    offres = await db[OFFRES_COL].find(
        {"user_id": user_id, "client_id": client_id, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "numero": 1, "statut": 1, "form_type_label": 1, "created_at": 1},
    ).to_list(200)

    suivis = await db[SUIVI_COL].find(
        {"user_id": user_id, "client_id": client_id},
        {"_id": 0, "id": 1, "statut": 1, "statut_suivi": 1, "created_at": 1, "date_derniere_analyse": 1},
    ).to_list(50)

    mandats = await db.documents.find(
        {
            "user_id": user_id,
            "client_id": client_id,
            "is_deleted": {"$ne": True},
            "$or": [
                {"template_id": "mandat_de_gestion"},
                {"checklist_item": "Mandat de gestion"},
                {"category": "Mandat de gestion"},
            ],
        },
        {"_id": 0, "id": 1, "original_filename": 1, "created_at": 1, "template_id": 1},
    ).to_list(50)

    # Dossier prévoyance = la fiche hub elle-même (toujours)
    return {
        "client_id": client_id,
        "found": True,
        "prevoyance": {
            "client_id": client_id,
            "numero_dossier": hub.get("numero_dossier"),
            "statut": hub.get("statut"),
            "dossier_id": hub.get("dossier_id") or client_id,
        },
        "offres": {
            "count": len(offres),
            "items": offres[:20],
        },
        "suivi_3p": {
            "count": len(suivis),
            "items": [
                {
                    **s,
                    "statut_suivi": s.get("statut_suivi") or s.get("statut"),
                }
                for s in suivis[:20]
            ],
        },
        "mandats": {
            "count": len(mandats),
            "items": mandats[:20],
        },
    }


async def link_existing_module_records(db, *, user_id: str = TENANT_USER_ID) -> dict:
    """Migration one-shot : rattache suivi_3p + offres au hub."""
    from demandes_offres_3p import COLLECTION as OFFRES_COL
    from suivi_3p import COLLECTION_CLIENTS as SUIVI_COL

    report = {
        "suivi_3p_linked": 0,
        "suivi_3p_created": 0,
        "suivi_3p_skipped": 0,
        "offres_linked": 0,
        "offres_created": 0,
        "offres_skipped": 0,
        "ambiguous": [],
    }

    suivis = await db[SUIVI_COL].find(
        {"user_id": user_id, "$or": [{"client_id": {"$exists": False}}, {"client_id": None}, {"client_id": ""}]},
        {"_id": 0},
    ).to_list(20000)
    for raw in suivis:
        c = _decrypt(raw) or raw
        hub, action = await upsert_hub_client_from_person(
            db,
            c,
            user_id=user_id,
            module="suivi_3p",
            conseiller=c.get("conseiller"),
        )
        if not hub:
            report["suivi_3p_skipped"] += 1
            continue
        await db[SUIVI_COL].update_one(
            {"id": c["id"], "user_id": user_id},
            {"$set": {"client_id": hub["id"], "updated_at": _now_iso()}},
        )
        if action == "created":
            report["suivi_3p_created"] += 1
        else:
            report["suivi_3p_linked"] += 1

    offres = await db[OFFRES_COL].find(
        {
            "user_id": user_id,
            "is_deleted": {"$ne": True},
            "$or": [{"client_id": {"$exists": False}}, {"client_id": None}, {"client_id": ""}],
        },
        {"_id": 0},
    ).to_list(20000)
    for doc in offres:
        if not _safe(doc.get("nom")) or not _safe(doc.get("prenom")):
            report["offres_skipped"] += 1
            continue
        hub, action = await upsert_hub_client_from_person(
            db,
            doc,
            user_id=user_id,
            module="offres",
            conseiller=doc.get("agent_label"),
        )
        if not hub:
            report["offres_skipped"] += 1
            continue
        await db[OFFRES_COL].update_one(
            {"id": doc["id"], "user_id": user_id},
            {"$set": {"client_id": hub["id"], "updated_at": _now_iso()}},
        )
        if action == "created":
            report["offres_created"] += 1
        else:
            report["offres_linked"] += 1

    return report
