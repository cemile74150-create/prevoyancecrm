"""Routes admin Entreprises + import conseillers + activation comptes."""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from access_control import (
    PERM_USERS_MANAGE,
    ROLE_CONSEILLER,
    User,
    UserCreate,
    display_name,
    force_access_by_account_id_only_on_create,
    hash_password,
    permission_storage_fields,
    public_user,
    require_admin,
    require_perm,
)
from entreprises import (
    COLLECTION,
    EntrepriseCreate,
    EntrepriseUpdate,
    attach_entreprise_fields,
    ensure_agence_mendes,
    get_entreprise,
    list_entreprises_map,
    new_entreprise_doc,
    propose_mendes_attachments,
    public_entreprise,
)
from user_activation import (
    DEFAULT_TTL_HOURS,
    consume_token_and_set_password,
    create_activation_token,
    generate_provisional_password,
    lookup_valid_token,
    send_activation_email,
    user_needs_activation,
    validate_new_password,
)
from users_import import (
    build_import_template_bytes,
    build_user_docs_from_preview,
    parse_excel_rows,
    preview_import,
)

logger = logging.getLogger(__name__)


class ActivationComplete(BaseModel):
    token: str
    password: str = Field(min_length=8)


class AttachMendesRequest(BaseModel):
    user_ids: list[str]
    dry_run: bool = True


class ImportApplyRequest(BaseModel):
    rows: list[dict[str, Any]]
    send_activation_emails: bool = True
    create_unknown_entreprises: bool = False


def _public_app_url() -> str:
    return (
        os.environ.get("PUBLIC_APP_URL")
        or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or "https://app.leosoft.ch"
    ).rstrip("/")


def attach_entreprises_routes(api_router: APIRouter, db, get_current_user):
    async def enrich_user(doc: Optional[dict]) -> Optional[dict]:
        if not doc:
            return None
        ent = None
        eid = (doc.get("entreprise_id") or "").strip()
        if eid:
            ent = await get_entreprise(db, eid)
        attached = attach_entreprise_fields(doc, ent)
        pub = public_user(attached)
        pub["entreprise_id"] = attached.get("entreprise_id")
        pub["entreprise_nom"] = attached.get("entreprise_nom")
        pub["entreprise_finma"] = attached.get("entreprise_finma")
        pub["must_set_password"] = bool(attached.get("must_set_password"))
        pub["activation_pending"] = user_needs_activation(attached)
        return pub

    # ---------- Entreprises ----------
    @api_router.get("/entreprises")
    async def list_entreprises(user: User = Depends(get_current_user)):
        require_perm(user, PERM_USERS_MANAGE)
        rows = await db[COLLECTION].find({}, {"_id": 0}).to_list(500)
        rows.sort(key=lambda e: (e.get("nom") or "").casefold())
        return [public_entreprise(r) for r in rows]

    @api_router.post("/entreprises")
    async def create_entreprise(payload: EntrepriseCreate, user: User = Depends(get_current_user)):
        require_admin(user)
        nom = (payload.nom or "").strip()
        finma = (payload.finma_number or "").strip()
        if not nom or not finma:
            raise HTTPException(status_code=400, detail="Nom et numéro FINMA obligatoires")
        dup = await db[COLLECTION].find_one(
            {"nom": {"$regex": f"^{re_escape(nom)}$", "$options": "i"}},
            {"_id": 0},
        )
        if dup:
            raise HTTPException(status_code=400, detail="Une entreprise porte déjà ce nom")
        doc = new_entreprise_doc(
            nom=nom,
            finma_number=finma,
            email_domains=payload.email_domains,
            active=payload.active,
        )
        await db[COLLECTION].insert_one(doc)
        return public_entreprise(doc)

    @api_router.put("/entreprises/{entreprise_id}")
    async def update_entreprise(
        entreprise_id: str,
        payload: EntrepriseUpdate,
        user: User = Depends(get_current_user),
    ):
        require_admin(user)
        doc = await db[COLLECTION].find_one({"id": entreprise_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Entreprise introuvable")
        updates: dict[str, Any] = {}
        if payload.nom is not None:
            nom = payload.nom.strip()
            if not nom:
                raise HTTPException(status_code=400, detail="Nom invalide")
            other = await db[COLLECTION].find_one(
                {
                    "id": {"$ne": entreprise_id},
                    "nom": {"$regex": f"^{re_escape(nom)}$", "$options": "i"},
                },
                {"_id": 0},
            )
            if other:
                raise HTTPException(status_code=400, detail="Une entreprise porte déjà ce nom")
            updates["nom"] = nom
        if payload.finma_number is not None:
            finma = payload.finma_number.strip()
            if not finma:
                raise HTTPException(status_code=400, detail="FINMA invalide")
            updates["finma_number"] = finma
        if payload.email_domains is not None:
            from entreprises import normalize_domains

            updates["email_domains"] = normalize_domains(payload.email_domains)
        if payload.active is not None:
            updates["active"] = bool(payload.active)
        if updates:
            from datetime import datetime, timezone

            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db[COLLECTION].update_one({"id": entreprise_id}, {"$set": updates})
        fresh = await db[COLLECTION].find_one({"id": entreprise_id}, {"_id": 0})
        return public_entreprise(fresh)

    @api_router.post("/entreprises/ensure-agence-mendes")
    async def api_ensure_mendes(user: User = Depends(get_current_user)):
        """Crée/complète Agence Mendes (sans rattacher les utilisateurs)."""
        require_admin(user)
        doc = await ensure_agence_mendes(db)
        return public_entreprise(doc)

    @api_router.get("/entreprises/mendes-attachment-preview")
    async def mendes_attachment_preview(user: User = Depends(get_current_user)):
        """Aperçu des comptes @agencemendes.ch à rattacher (lecture seule)."""
        require_admin(user)
        # Pas d'écriture ici : créer Mendes via POST /entreprises/ensure-agence-mendes.
        mendes = await db[COLLECTION].find_one(
            {"nom": {"$regex": r"^Agence\s+Mendes$", "$options": "i"}},
            {"_id": 0},
        )
        if not mendes:
            return {
                "entreprise": None,
                "count": 0,
                "proposals": [],
                "missing_entreprise": True,
                "hint": "Appelez POST /entreprises/ensure-agence-mendes avant le rattachement.",
            }
        users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(2000)
        proposals = propose_mendes_attachments(users, mendes)
        return {
            "entreprise": public_entreprise(mendes),
            "count": len(proposals),
            "proposals": proposals,
            "missing_entreprise": False,
        }

    @api_router.post("/entreprises/mendes-attachment-apply")
    async def mendes_attachment_apply(
        payload: AttachMendesRequest,
        user: User = Depends(get_current_user),
    ):
        """Rattache les user_ids listés à Agence Mendes. dry_run=true par défaut."""
        require_admin(user)
        mendes = await ensure_agence_mendes(db)
        wanted = {str(x).strip() for x in (payload.user_ids or []) if str(x).strip()}
        users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(2000)
        proposals = [
            p for p in propose_mendes_attachments(users, mendes) if p["user_id"] in wanted
        ]
        if payload.dry_run:
            return {"dry_run": True, "would_update": len(proposals), "proposals": proposals}
        ids = [p["user_id"] for p in proposals]
        if ids:
            await db.users.update_many(
                {"user_id": {"$in": ids}},
                {"$set": {"entreprise_id": mendes["id"]}},
            )
        return {"dry_run": False, "updated": len(ids), "user_ids": ids}

    # ---------- Import ----------
    # Chemins hors /users/{id} pour éviter la capture par account_id.
    @api_router.get("/users-import/template.xlsx")
    async def download_import_template(user: User = Depends(get_current_user)):
        require_perm(user, PERM_USERS_MANAGE)
        data = build_import_template_bytes()
        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="modele_import_conseillers_leosoft.xlsx"'
            },
        )

    @api_router.post("/users-import/preview")
    async def import_preview(
        file: UploadFile = File(...),
        user: User = Depends(get_current_user),
    ):
        require_admin(user)
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Fichier vide")
        rows, err = parse_excel_rows(raw)
        if err:
            raise HTTPException(status_code=400, detail=err)
        existing = {
            str(u.get("email") or "").strip().lower()
            for u in await db.users.find({}, {"email": 1, "_id": 0}).to_list(5000)
        }
        entreprises = await db[COLLECTION].find({}, {"_id": 0}).to_list(500)
        return preview_import(rows, existing_emails=existing, entreprises=entreprises)

    @api_router.post("/users-import/apply")
    async def import_apply(payload: ImportApplyRequest, user: User = Depends(get_current_user)):
        """Applique uniquement les lignes status=ok. Aucun mot de passe dans la réponse."""
        require_admin(user)
        entreprises = await db[COLLECTION].find({}, {"_id": 0}).to_list(500)
        existing = {
            str(u.get("email") or "").strip().lower()
            for u in await db.users.find({}, {"email": 1, "_id": 0}).to_list(5000)
        }
        # Revalide côté serveur
        repreview = preview_import(
            [
                {
                    "ligne": r.get("ligne"),
                    "prenom": r.get("prenom"),
                    "nom": r.get("nom"),
                    "email": r.get("email"),
                    "entreprise": r.get("entreprise"),
                }
                for r in (payload.rows or [])
            ],
            existing_emails=existing,
            entreprises=entreprises,
        )
        ok_rows = [r for r in repreview["rows"] if r.get("status") == "ok"]
        if not ok_rows:
            return {
                "created": 0,
                "ignored": len(repreview["rows"]),
                "errors": len(repreview["rows"]),
                "activations_emailed": 0,
                "activations_pending_admin_link": 0,
                "preview_counts": repreview["counts"],
                "created_users": [],
            }

        docs = build_user_docs_from_preview(ok_rows)
        if docs:
            await db.users.insert_many(docs)

        created_users = []
        emailed = 0
        pending_links = 0
        public_url = _public_app_url()
        if not public_url.startswith("http"):
            public_url = f"https://{public_url}"

        for doc in docs:
            raw_token, _meta = await create_activation_token(
                db,
                user_id=doc["user_id"],
                purpose="activate",
                created_by=user.account_id,
            )
            link_for_admin = None
            email_ok = False
            if payload.send_activation_emails:
                email_ok, _err, link = await send_activation_email(
                    db,
                    user=doc,
                    raw_token=raw_token,
                    public_app_url=public_url,
                )
                if email_ok:
                    emailed += 1
                else:
                    pending_links += 1
                    link_for_admin = link
            else:
                pending_links += 1
                from user_activation import build_activation_link

                link_for_admin = build_activation_link(public_url, raw_token)

            created_users.append(
                {
                    "user_id": doc["user_id"],
                    "email": doc["email"],
                    "name": doc["name"],
                    "entreprise_id": doc.get("entreprise_id"),
                    "activation_email_sent": email_ok,
                    # Lien uniquement si e-mail non envoyé — à copier par l'admin, pas exporté en masse Excel
                    "activation_link": link_for_admin if not email_ok else None,
                }
            )

        return {
            "created": len(docs),
            "ignored": len(repreview["rows"]) - len(ok_rows),
            "errors": 0,
            "activations_emailed": emailed,
            "activations_pending_admin_link": pending_links,
            "preview_counts": repreview["counts"],
            "created_users": created_users,
        }

    # ---------- Activation publique ----------
    @api_router.get("/auth/activation/status")
    async def activation_status(token: str):
        tok = await lookup_valid_token(db, token)
        if not tok:
            return {"ok": False, "error": "invalid_or_expired"}
        u = await db.users.find_one({"user_id": tok["user_id"]}, {"_id": 0, "password_hash": 0})
        if not u or u.get("active") is False:
            return {"ok": False, "error": "user_inactive"}
        return {
            "ok": True,
            "email": u.get("email"),
            "prenom": u.get("prenom"),
            "nom": u.get("nom"),
            "purpose": tok.get("purpose"),
            "expires_at": tok.get("expires_at"),
        }

    @api_router.post("/auth/activation/complete")
    async def activation_complete(payload: ActivationComplete):
        fresh, err = await consume_token_and_set_password(
            db, raw_token=payload.token, new_password=payload.password
        )
        if err:
            raise HTTPException(
                status_code=400,
                detail={
                    "invalid_or_expired": "Lien invalide ou expiré",
                    "weak_password": validate_new_password(payload.password)
                    or "Mot de passe trop faible",
                    "user_inactive": "Compte désactivé",
                }.get(err, err),
            )
        return {"ok": True, "email": (fresh or {}).get("email")}

    @api_router.post("/users/{account_id}/send-activation")
    async def send_user_activation(account_id: str, user: User = Depends(get_current_user)):
        require_admin(user)
        doc = await db.users.find_one({"user_id": account_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        raw_token, meta = await create_activation_token(
            db,
            user_id=account_id,
            purpose="activate" if user_needs_activation(doc) else "reset",
            created_by=user.account_id,
        )
        await db.users.update_one(
            {"user_id": account_id},
            {"$set": {"must_set_password": True, "activation_pending": True}},
        )
        public_url = _public_app_url()
        if not public_url.startswith("http"):
            public_url = f"https://{public_url}"
        email_ok, err, link = await send_activation_email(
            db, user=doc, raw_token=raw_token, public_app_url=public_url
        )
        return {
            "ok": True,
            "email_sent": email_ok,
            "smtp_error": err,
            "expires_at": meta.get("expires_at"),
            # Lien remis à l'admin seulement si e-mail échoue
            "activation_link": None if email_ok else link,
        }

    @api_router.post("/users/{account_id}/provisional-password")
    async def set_provisional_password(account_id: str, user: User = Depends(get_current_user)):
        """Alternative sans e-mail : MDP provisoire unique, changement obligatoire."""
        require_admin(user)
        doc = await db.users.find_one({"user_id": account_id}, {"_id": 0})
        if not doc:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        provisional = generate_provisional_password()
        await db.users.update_one(
            {"user_id": account_id},
            {
                "$set": {
                    "password_hash": hash_password(provisional),
                    "must_set_password": True,
                    "activation_pending": True,
                }
            },
        )
        await db.user_sessions.delete_many({"user_id": account_id})
        # Retourné une seule fois à l'admin — ne pas logger
        return {
            "ok": True,
            "user_id": account_id,
            "email": doc.get("email"),
            "provisional_password": provisional,
            "must_set_password": True,
        }

    return enrich_user


def re_escape(s: str) -> str:
    import re

    return re.escape(s)
