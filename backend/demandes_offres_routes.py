"""FastAPI routes for the third-pillar offer-request workflow."""
from __future__ import annotations

import inspect
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from starlette.datastructures import UploadFile as StarletteUploadFile

from access_control import (
    User,
    TENANT_USER_ID,
    can_process_offres,
    can_view_all_offres,
    enforce_route_permission,
    is_global_viewer,
    require_admin,
    require_perm,
    resolve_session_user,
    PERM_DEMANDES_OFFRES_EDIT,
    PERM_DEMANDES_OFFRES_PROCESS,
)
from demandes_offres_3p import *

try:
    from access_control import get_current_user as _shared_get_current_user
except ImportError:
    _shared_get_current_user = None


logger = logging.getLogger(__name__)


def _coerce_to_list(value: Any) -> Optional[list]:
    """Pydantic/JSON : une valeur seule ne doit pas faire échouer un champ list."""
    if value is None:
        return None
    if isinstance(value, list):
        return value
    return [value]


async def collect_multipart_uploads(
    request: Request,
    *,
    single_file: Optional[UploadFile] = None,
    field_names: tuple[str, ...] = ("files", "documents", "file"),
) -> list[UploadFile]:
    """
    Collecte 1..N fichiers depuis un multipart.

    Ne pas typer `files: Optional[list[UploadFile]] = File(None)` : avec un seul
    fichier, FastAPI/Pydantic v2 reçoit un UploadFile scalaire et répond
    « Input should be a valid list ».
    """
    form = await request.form()
    out: list[UploadFile] = []
    seen: set[tuple[str, Optional[int]]] = set()

    def _add(item: Any) -> None:
        if item is None:
            return
        if not isinstance(item, (UploadFile, StarletteUploadFile)):
            return
        name = (getattr(item, "filename", None) or "").strip()
        if not name:
            return
        size = getattr(item, "size", None)
        key = (name, size if isinstance(size, int) else None)
        if key in seen:
            return
        seen.add(key)
        out.append(item)

    for field in field_names:
        for item in form.getlist(field):
            _add(item)
    _add(single_file)
    return out


class DemandeOffreUpdate(BaseModel):
    agent_prenom: Optional[str] = None
    agent_nom: Optional[str] = None
    agent_email: Optional[str] = None
    agent_finma: Optional[str] = None
    civilite: Optional[str] = None
    nom: Optional[str] = None
    prenom: Optional[str] = None
    sexe: Optional[str] = None
    date_naissance: Optional[str] = None
    nationalite: Optional[str] = None
    permis: Optional[str] = None
    adresse: Optional[str] = None
    ville: Optional[str] = None
    npa: Optional[str] = None
    pays: Optional[str] = None
    statut_professionnel: Optional[str] = None
    profession: Optional[str] = None
    travail_bureau_80: Optional[str] = None
    affilie_lpp: Optional[str] = None
    fumeur: Optional[str] = None
    situation: Optional[str] = None
    activites_risque: Optional[bool] = None
    activites_risque_liste: Optional[list[str]] = None
    type_pilier: Optional[str] = None
    date_debut: Optional[str] = None
    periodicite_prime: Optional[str] = None
    montant_prime: Optional[float | str] = None
    deja_piliers_pax: Optional[str] = None
    type_paiement: Optional[str] = None
    duree_contrat: Optional[str] = None
    age_terme: Optional[str] = None
    exoneration_primes: Optional[str] = None
    rente_invalidite: Optional[str] = None
    diplome: Optional[str] = None
    adaptation_auto_primes: Optional[str] = None
    risque_pur: Optional[str] = None
    taille: Optional[str] = None
    poids: Optional[str] = None
    renseignements_complementaires: Optional[str] = None
    compagnies: Optional[list[str]] = None
    commentaires: Optional[str] = None
    inclure_cga: Optional[bool] = None
    date_prochain_rdv: Optional[str] = None
    langue_offre: Optional[str] = None
    mandat_gestion: Optional[bool] = None
    form_type: Optional[str] = None
    form_payload: Optional[dict[str, Any]] = None
    client_id: Optional[str] = None
    type_client: Optional[str] = None
    demande_origine: Optional[str] = None
    note_service_offre: Optional[str] = None


class CreateDemandeOffreRequest(BaseModel):
    form_type: Optional[str] = "pilier3_legacy"
    form_type_label: Optional[str] = None
    client_id: Optional[str] = None
    type_client: Optional[str] = None
    demande_origine: Optional[str] = None
    assigned_to_account_id: Optional[str] = None
    assigned_to_name: Optional[str] = None
    agent_prenom: Optional[str] = None
    agent_nom: Optional[str] = None
    agent_email: Optional[str] = None


class IncompleteErreurItem(BaseModel):
    code: str = "autre"
    detail: Optional[str] = None
    label: Optional[str] = None


class IncompleteRequest(BaseModel):
    comment: str = Field(min_length=1)
    documents_manquants: Optional[str] = None
    erreurs: Optional[list[IncompleteErreurItem]] = None
    compagnie: Optional[str] = None

    @field_validator("erreurs", mode="before")
    @classmethod
    def _erreurs_as_list(cls, value: Any) -> Any:
        return _coerce_to_list(value)


class CompleteOfferRequest(BaseModel):
    commentaire: Optional[str] = None
    message_conseiller: Optional[str] = None


class InternalNoteRequest(BaseModel):
    note: str = Field(min_length=1)


class SignatureRequest(BaseModel):
    signee: bool
    date_signature: Optional[str] = None
    commentaire: Optional[str] = None
    date_relance: Optional[str] = None


class AnnulationRequest(BaseModel):
    commentaire: Optional[str] = None


class ModificationRequest(BaseModel):
    form_payload: Optional[dict[str, Any]] = None
    fields: Optional[dict[str, Any]] = None
    note_service_offre: Optional[str] = None
    changes: Optional[list[dict[str, Any]]] = None

    @field_validator("changes", mode="before")
    @classmethod
    def _changes_as_list(cls, value: Any) -> Any:
        return _coerce_to_list(value)


class MarkCompanyIncompleteRequest(BaseModel):
    compagnie: str = Field(min_length=1)
    comment: Optional[str] = None


class ChooseOffreRequest(BaseModel):
    offre_id: str


class ConclusionRequest(BaseModel):
    commentaire: Optional[str] = None
    date_conclusion: Optional[str] = None


def attach_demandes_offres_routes(
    api_router,
    *,
    db,
    put_object,
    local_storage_fallback,
    file_response_headers,
    mime_types,
    app_name,
    root_dir,
    load_storage_bytes,
    resolve_download_filename=None,
):
    """Register all Demandes d'offres 3P endpoints on ``api_router``."""

    root_path = Path(root_dir)
    locked_statuses = {STATUT_OFFRE_SIGNEE, STATUT_ANNULEE}

    def download_name(record: dict, fallback: str = "document") -> str:
        if resolve_download_filename:
            return resolve_download_filename(record, fallback=fallback)
        return (record or {}).get("original_filename") or fallback

    async def _injected_get_current_user(
        request: Request,
        authorization: Optional[str] = Header(None),
    ) -> User:
        user = await resolve_session_user(db, request, authorization)
        enforce_route_permission(user, request.method, request.url.path)
        return user

    current_user_dependency = _shared_get_current_user or _injected_get_current_user

    def actor_name(user: User) -> str:
        return (user.name or f"{user.prenom} {user.nom}").strip()

    def public_doc(doc: dict) -> dict:
        return {
            key: value
            for key, value in doc.items()
            if key not in {"_id", "storage_path", "storage_path_legacy"}
        }

    async def maybe_await(value):
        return await value if inspect.isawaitable(value) else value

    async def next_numero() -> str:
        from pymongo import ReturnDocument

        year = now_iso()[:4]
        counter = await db[COLLECTION_COUNTERS].find_one_and_update(
            {"id": f"offres-{year}", "user_id": TENANT_USER_ID},
            {
                "$inc": {"value": 1},
                "$set": {"updated_at": now_iso()},
                "$setOnInsert": {
                    "id": f"offres-{year}",
                    "user_id": TENANT_USER_ID,
                    "year": int(year),
                    "created_at": now_iso(),
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        sequence = int((counter or {}).get("value") or 1)
        return f"OFF-{year}-{sequence:04d}"

    async def require_demande(demande_id: str, user: User) -> dict:
        doc = await db[COLLECTION].find_one(
            {
                "id": demande_id,
                "user_id": TENANT_USER_ID,
                "is_deleted": {"$ne": True},
            },
            {"_id": 0},
        )
        if not doc or not can_access_demande(user, doc):
            raise HTTPException(status_code=404, detail="Demande d'offre introuvable")
        return doc

    async def docs_for(demande_id: str) -> list[dict]:
        rows = await db[COLLECTION_DOCS].find(
            {
                "demande_id": demande_id,
                "user_id": TENANT_USER_ID,
                "is_deleted": {"$ne": True},
            },
            {"_id": 0, "storage_path": 0, "storage_path_legacy": 0},
        ).sort("created_at", -1).to_list(200)
        return [public_doc(row) for row in rows]

    async def store_doc(
        demande_id: str,
        upload: UploadFile,
        user: User,
        *,
        category: str,
    ) -> dict:
        data = await upload.read()
        if not data:
            raise HTTPException(status_code=400, detail="Fichier vide")

        original_filename = Path(upload.filename or "document").name
        suffix = Path(original_filename).suffix.lower()
        extension = suffix[1:] if suffix.startswith(".") else suffix
        extension = extension or "bin"
        content_type = (
            upload.content_type
            or mime_types.get(extension)
            or "application/octet-stream"
        )
        storage_key = (
            f"{app_name}/demandes-offres/{TENANT_USER_ID}/"
            f"{demande_id}/{uuid.uuid4()}.{extension}"
        )
        try:
            result = await maybe_await(put_object(storage_key, data, content_type))
            storage_path = result["path"]
            size = int(result.get("size", len(data)))
        except Exception as exc:
            logger.warning("Offer-request object upload failed, using fallback: %s", exc)
            local_name = f"{uuid.uuid4()}.{extension}"
            try:
                storage_path = await maybe_await(
                    local_storage_fallback(
                        root_path / "uploads" / "demandes-offres" / demande_id,
                        local_name,
                        data,
                    )
                )
            except Exception as fallback_exc:
                logger.exception("Offer-request document storage failed")
                raise HTTPException(
                    status_code=503,
                    detail="Le stockage du document est indisponible",
                ) from fallback_exc
            size = len(data)

        record = {
            "id": str(uuid.uuid4()),
            "user_id": TENANT_USER_ID,
            "demande_id": demande_id,
            "storage_path": storage_path,
            "original_filename": original_filename,
            "content_type": content_type,
            "size": size,
            "category": category,
            "is_deleted": False,
            "created_at": now_iso(),
            "uploaded_by": user.account_id,
            "uploaded_by_name": actor_name(user),
        }
        await db[COLLECTION_DOCS].insert_one(record)
        return public_doc(record)

    def history(
        action: str,
        user: User,
        detail: str = "",
        *,
        statut: Optional[str] = None,
        document_id: Optional[str] = None,
        email_log_id: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> dict:
        return history_entry(
            action,
            by_name=actor_name(user),
            by_id=user.account_id,
            detail=detail,
            statut=statut,
            document_id=document_id,
            email_log_id=email_log_id,
            meta=meta,
        )

    async def save_status(
        demande_id: str,
        user: User,
        *,
        statut: str,
        action: str,
        detail: str = "",
        extra: Optional[dict] = None,
        document_id: Optional[str] = None,
        email_log_id: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> dict:
        current = await db[COLLECTION].find_one(
            {"id": demande_id, "user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}}
        )
        hist = collapse_demande_historique((current or {}).get("historique") or [])
        hist.append(
            history(
                action,
                user,
                detail,
                statut=statut,
                document_id=document_id,
                email_log_id=email_log_id,
                meta=meta,
            )
        )
        updates = {
            "statut": statut,
            "updated_at": now_iso(),
            "historique": hist,
            **(extra or {}),
        }
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {"$set": updates},
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    async def ensure_permanent_subject(doc: dict) -> str:
        """Fige email_subject au premier envoi ; ne change jamais ensuite (sauf placeholder Client)."""
        from email_service import (
            build_permanent_email_subject,
            resolve_offre_client_identity,
            subject_uses_placeholder_client,
        )

        existing = (doc.get("email_subject") or "").strip()
        if existing and not subject_uses_placeholder_client(existing):
            return existing

        # Enrichir nom/prénom depuis le dossier client hub si manquants
        nom, prenom = resolve_offre_client_identity(doc)
        if (not nom and not prenom) and (doc.get("client_id") or "").strip():
            try:
                from client_hub import get_hub_client

                hub = await get_hub_client(
                    db,
                    str(doc.get("client_id")).strip(),
                    user_id=getattr(user, "user_id", None) or doc.get("user_id"),
                )
                if hub:
                    if not nom:
                        nom = (hub.get("nom") or "").strip()
                        if nom:
                            doc["nom"] = nom
                    if not prenom:
                        prenom = (hub.get("prenom") or "").strip()
                        if prenom:
                            doc["prenom"] = prenom
            except Exception:
                logger.exception("enrich subject from hub client failed")

        # Re-sync depuis form_payload si toujours vide
        if not nom and not prenom:
            form_type_id = (doc.get("form_type") or "").strip()
            if form_type_id and form_type_id != "pilier3_legacy" and isinstance(doc.get("form_payload"), dict):
                try:
                    from offre_form_types import sync_crm_fields_from_payload

                    sync_crm_fields_from_payload(doc, form_type_id, doc.get("form_payload") or {})
                except Exception:
                    logger.exception("sync_crm_fields for email subject failed")

        subject = build_permanent_email_subject(doc)
        demande_id = doc.get("id")
        if demande_id:
            patch = {
                "email_subject": subject,
                "updated_at": now_iso(),
            }
            # Persister aussi nom/prénom résolus pour les prochains envois / l'UI
            resolved_nom, resolved_prenom = resolve_offre_client_identity(doc)
            if resolved_nom and not (doc.get("nom") or "").strip():
                patch["nom"] = resolved_nom
                doc["nom"] = resolved_nom
            if resolved_prenom and not (doc.get("prenom") or "").strip():
                patch["prenom"] = resolved_prenom
                doc["prenom"] = resolved_prenom
            await db[COLLECTION].update_one(
                {"id": demande_id, "user_id": TENANT_USER_ID},
                {"$set": patch},
            )
            doc["email_subject"] = subject
        return subject

    async def try_send_email(
        doc: dict,
        *,
        event: str = "envoyee",
        offer: Optional[dict] = None,
        comment: Optional[str] = None,
        signature: Optional[dict] = None,
        changes: Optional[list] = None,
        note: Optional[str] = None,
        to_override: Optional[str] = None,
        cc: Optional[list] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Envoie une notification offre via SMTP.
        L'objet (email_subject) est permanent pour toute la vie de l'offre
        (sauf récap conseiller / offre reçue simplifiée).
        À l'envoi (envoyee) : offres@ + copie récapitulatif au conseiller créateur.
        """
        try:
            from email_service import (
                MAIL_TYPE_DEMANDE_OFFRE,
                MAIL_TYPE_DEMANDE_OFFRE_RECAP,
                MAIL_TYPE_OFFRE_INCOMPLETE,
                MAIL_TYPE_OFFRE_MODIFIEE,
                MAIL_TYPE_OFFRE_RECUE,
                MAIL_TYPE_OFFRES_COMPLETES,
                MAIL_TYPE_OFFRE_SIGNEE,
                format_demande_incomplete_email,
                format_demande_offre_email,
                format_demande_offre_recap_conseiller_email,
                format_offre_modifiee_email,
                format_offre_recue_email,
                format_offres_completes_email,
                format_offre_signee_email,
                office_email_to,
                offre_notify_role,
                offres_email_enabled,
                offres_email_to,
                send_email_async,
            )
        except Exception as exc:
            logger.warning("Email service unavailable: %s", exc)
            return False, "Service e-mail indisponible"

        if not offres_email_enabled():
            return False, "Envoi e-mail désactivé"
        # SMTP manquant : laisser send_email_async journaliser le statut error

        await ensure_permanent_subject(doc)
        event_key = (event or "envoyee").strip().lower()
        cc_list = list(cc or [])
        send_conseiller_recap = False

        if event_key in {"recue", "reçue", "offre_recue", "received"}:
            mail_type = MAIL_TYPE_OFFRE_RECUE
            subject, body_text, body_html = format_offre_recue_email(doc, offer)
            to_addr = to_override or await resolve_demande_creator_email(doc)
            if not to_addr:
                return False, "E-mail du créateur introuvable sur la demande"
        elif event_key in {
            "complete",
            "completes",
            "offres_completes",
            "offres_complètes",
            "offre_complete",
            "offre_complète",
        }:
            mail_type = MAIL_TYPE_OFFRES_COMPLETES
            subject, body_text, body_html = format_offres_completes_email(doc)
            to_addr = to_override or await resolve_demande_creator_email(doc)
            if not to_addr:
                return False, "E-mail du créateur introuvable sur la demande"
        elif event_key in {"incomplete", "incomplet", "incompletee", "incomplète"}:
            mail_type = MAIL_TYPE_OFFRE_INCOMPLETE
            subject, body_text, body_html = format_demande_incomplete_email(doc, comment=comment)
            to_addr = to_override or await resolve_demande_creator_email(doc)
            if not to_addr:
                return False, "E-mail du créateur introuvable sur la demande"
        elif event_key in {"signee", "signée", "signed"}:
            mail_type = MAIL_TYPE_OFFRE_SIGNEE
            subject, body_text, body_html = format_offre_signee_email(doc, signature=signature)
            to_addr = to_override or office_email_to()
            offres_box = offres_email_to()
            if offres_box and offres_box.lower() != (to_addr or "").lower():
                cc_list.append(offres_box)
        elif event_key in {"modifiee", "modification", "a_modifier"}:
            mail_type = MAIL_TYPE_OFFRE_MODIFIEE
            subject, body_text, body_html = format_offre_modifiee_email(
                doc, changes=changes, note=note
            )
            to_addr = to_override or offres_email_to()
        else:
            mail_type = MAIL_TYPE_DEMANDE_OFFRE
            subject, body_text, body_html = format_demande_offre_email(doc)
            to_addr = to_override or offres_email_to()
            send_conseiller_recap = True

        sent = False
        error = None
        client_label = (
            f"{(doc.get('prenom') or '').strip()} {(doc.get('nom') or '').strip()}".strip()
            or doc.get("client_label")
            or None
        )

        async def _dispatch(
            *,
            dest: str,
            subj: str,
            text: str,
            html_body: str,
            mtype: str,
            meta_event: str,
            meta_role: str,
            dest_cc: Optional[list] = None,
        ) -> tuple[bool, Optional[str]]:
            log_meta = {
                "client_id": doc.get("client_id"),
                "ref_id": doc.get("id"),
                "user_id": doc.get("user_id") or TENANT_USER_ID,
                "created_by": doc.get("created_by") or doc.get("created_by_account_id"),
                "numero": doc.get("numero"),
                "form_type": doc.get("form_type"),
                "form_type_label": doc.get("form_type_label"),
                "event": meta_event,
                "notify_role": meta_role,
                "agent_label": doc.get("agent_label"),
                "client_label": client_label,
                "module": "demandes_offres",
                "email_subject": subj,
            }
            try:
                result = await maybe_await(
                    send_email_async(
                        dest,
                        subj,
                        text,
                        body_html=html_body,
                        cc=dest_cc or None,
                        mail_type=mtype,
                        log_meta=log_meta,
                    )
                )
                if isinstance(result, tuple):
                    return bool(result[0]), result[1]
                return bool(result), (None if result else "Échec de l'envoi")
            except TypeError:
                try:
                    from email_service import send_email as send_email_sync

                    result = await maybe_await(
                        send_email_sync(
                            dest,
                            subj,
                            text,
                            body_html=html_body,
                            cc=dest_cc or None,
                            mail_type=mtype,
                            log_meta=log_meta,
                        )
                    )
                    if isinstance(result, tuple):
                        return bool(result[0]), result[1]
                    return bool(result), (None if result else "Échec de l'envoi")
                except Exception as exc:
                    logger.exception("Offer email failed event=%s", meta_event)
                    return False, str(exc)[:500]
            except Exception as exc:
                logger.exception("Offer email failed event=%s", meta_event)
                return False, str(exc)[:500]

        sent, error = await _dispatch(
            dest=to_addr,
            subj=subject,
            text=body_text,
            html_body=body_html,
            mtype=mail_type,
            meta_event=event_key,
            meta_role=offre_notify_role(event_key),
            dest_cc=cc_list or None,
        )

        # Copie récapitulatif au conseiller (envoi / renvoi / compléter-renvoyer)
        if send_conseiller_recap:
            try:
                conseiller_to = await resolve_demande_creator_email(doc)
            except Exception:
                logger.exception("Resolve conseiller email for recap failed")
                conseiller_to = None
            if conseiller_to and conseiller_to.strip().lower() != (to_addr or "").strip().lower():
                recap_subj, recap_text, recap_html = format_demande_offre_recap_conseiller_email(doc)
                recap_sent, recap_err = await _dispatch(
                    dest=conseiller_to,
                    subj=recap_subj,
                    text=recap_text,
                    html_body=recap_html,
                    mtype=MAIL_TYPE_DEMANDE_OFFRE_RECAP,
                    meta_event="envoyee_recap",
                    meta_role="createur",
                    dest_cc=None,
                )
                if not recap_sent:
                    logger.warning(
                        "Conseiller recap email failed demande=%s err=%s",
                        doc.get("id"),
                        recap_err,
                    )
                    # Ne pas faire échouer l'envoi offres@ si la copie échoue
                    if sent and recap_err:
                        error = (error + " ; " if error else "") + f"Récap conseiller : {recap_err}"

        return sent, error

    async def write_offre_notification(
        *,
        doc: dict,
        event: str,
        title: str,
        message: str,
        audience: str,
        account_ids: Optional[list] = None,
    ) -> None:
        """Historique notifications CRM (cloche / audit offres)."""
        try:
            row = {
                "id": str(uuid.uuid4()),
                "user_id": TENANT_USER_ID,
                "type": "demande_offre",
                "event": event,
                "demande_id": doc.get("id"),
                "numero": doc.get("numero"),
                "title": title,
                "message": message,
                "audience": audience,  # conseiller | gestionnaires | all
                "account_ids": account_ids or [],
                "read_by": [],
                "created_at": now_iso(),
            }
            await db.offre_notifications.insert_one(row)
        except Exception:
            logger.exception("Failed to write offre_notifications event=%s", event)

    async def manager_account_ids() -> list[str]:
        """Comptes ayant le droit de traiter les offres."""
        users = await db.users.find(
            {"active": {"$ne": False}},
            {"_id": 0, "user_id": 1, "role": 1, "permissions": 1},
        ).to_list(500)
        ids = []
        for u in users:
            role = u.get("role") or "conseiller"
            perms = u.get("permissions") if isinstance(u.get("permissions"), dict) else {}
            if PERM_DEMANDES_OFFRES_PROCESS in perms:
                if perms[PERM_DEMANDES_OFFRES_PROCESS]:
                    ids.append(u.get("user_id"))
                continue
            if role in {"admin", "ceo", "gestionnaire_offres"}:
                ids.append(u.get("user_id"))
        return [i for i in ids if i]

    async def resolve_conseiller_notify_email(doc: dict) -> Optional[str]:
        """
        E-mail du conseiller / propriétaire métier de la demande.
        Ordre : agent_email → utilisateur créateur → recherche par agent_label.
        """
        direct = pick_conseiller_email_from_demande(doc)
        if direct:
            return direct

        account_id = (doc.get("created_by_account_id") or "").strip()
        if account_id:
            u = await db.users.find_one(
                {"$or": [{"user_id": account_id}, {"account_id": account_id}], "active": {"$ne": False}},
                {"_id": 0, "email": 1},
            )
            email = ((u or {}).get("email") or "").strip()
            if "@" in email:
                return email

        # Ancien champ éventuel
        created_by = (doc.get("created_by") or "").strip()
        if created_by:
            u = await db.users.find_one(
                {
                    "$or": [{"account_id": created_by}, {"user_id": created_by}],
                    "active": {"$ne": False},
                },
                {"_id": 0, "email": 1},
            )
            email = ((u or {}).get("email") or "").strip()
            if "@" in email:
                return email

        label = (doc.get("agent_label") or "").strip()
        if label:
            u = await db.users.find_one(
                {
                    "active": {"$ne": False},
                    "$or": [
                        {"conseiller": label},
                        {"name": label},
                    ],
                },
                {"_id": 0, "email": 1},
            )
            email = ((u or {}).get("email") or "").strip()
            if "@" in email:
                return email
            # Prénom + nom séparés
            parts = label.split(None, 1)
            if len(parts) == 2:
                u = await db.users.find_one(
                    {
                        "active": {"$ne": False},
                        "prenom": {"$regex": f"^{re.escape(parts[0])}$", "$options": "i"},
                        "nom": {"$regex": f"^{re.escape(parts[1])}$", "$options": "i"},
                    },
                    {"_id": 0, "email": 1},
                )
                email = ((u or {}).get("email") or "").strip()
                if "@" in email:
                    return email
        return None

    async def resolve_demande_creator_email(doc: dict) -> Optional[str]:
        """
        E-mail du créateur de la demande d'offre (notifs « reçue » / « incomplète »).
        Ordre : created_by_account_id → created_by → fallback conseiller.
        """
        for key in ("created_by_account_id", "created_by"):
            account_id = (doc.get(key) or "").strip()
            if not account_id:
                continue
            u = await db.users.find_one(
                {
                    "$or": [{"user_id": account_id}, {"account_id": account_id}],
                    "active": {"$ne": False},
                },
                {"_id": 0, "email": 1},
            )
            email = ((u or {}).get("email") or "").strip()
            if "@" in email:
                return email
        return await resolve_conseiller_notify_email(doc)

    @api_router.post("/demandes-offres/modifier/analyse-pdf")
    async def analyse_pdf_for_modification(
        file: UploadFile = File(...),
        form_type: str = Form("pilier3_legacy"),
        numero: Optional[str] = Form(None),
        user: User = Depends(current_user_dependency),
    ):
        """
        Analyse un PDF d'offre / police et préremplit le formulaire du type choisi.
        Lie éventuellement la demande existante via le n° OFF trouvé ou fourni
        (numéro + objet e-mail conservés à l'envoi).
        """
        require_perm(user, PERM_DEMANDES_OFFRES_EDIT, detail="Permission d'édition des demandes requise")
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Fichier vide")
        filename = file.filename or "offre.pdf"
        form_type = (form_type or "pilier3_legacy").strip() or "pilier3_legacy"

        from offre_extract import extract_offre_fields, map_extract_to_form

        raw = extract_offre_fields(data, filename=filename)
        mapped = map_extract_to_form(raw, form_type=form_type)
        fields = mapped.get("fields") or {}
        form_payload = mapped.get("form_payload") or {}
        numero_detecte = (numero or "").strip() or (mapped.get("numero_offre") or raw.get("numero_offre") or "")
        numero_detecte = numero_detecte.strip().upper() if numero_detecte else ""

        matched = None
        if numero_detecte:
            # Normaliser OFF-YYYY-NNNN
            m = re.match(r"OFF-?(\d{4})-?(\d{3,6})", numero_detecte.replace(" ", ""))
            if m:
                numero_detecte = f"OFF-{m.group(1)}-{m.group(2).zfill(4)}"
            doc = await db[COLLECTION].find_one(
                {
                    "user_id": TENANT_USER_ID,
                    "is_deleted": {"$ne": True},
                    "numero": {"$regex": f"^{re.escape(numero_detecte)}$", "$options": "i"},
                },
                {"_id": 0},
            )
            if doc and can_access_demande(user, doc):
                await ensure_permanent_subject(doc)
                matched = {
                    "id": doc.get("id"),
                    "numero": doc.get("numero"),
                    "email_subject": doc.get("email_subject") or "",
                    "statut": doc.get("statut"),
                    "form_type": doc.get("form_type"),
                    "form_type_label": doc.get("form_type_label"),
                    "prenom": doc.get("prenom"),
                    "nom": doc.get("nom"),
                }
                # Compléter les trous avec les données déjà en base (PDF prioritaire)
                for k, v in list(fields.items()):
                    if v in (None, ""):
                        if doc.get(k) not in (None, ""):
                            fields[k] = doc.get(k)
                if not form_payload and isinstance(doc.get("form_payload"), dict):
                    form_payload = dict(doc.get("form_payload") or {})
                elif isinstance(doc.get("form_payload"), dict):
                    merged_fp = dict(doc.get("form_payload") or {})
                    merged_fp.update({k: v for k, v in form_payload.items() if v not in (None, "")})
                    form_payload = merged_fp

        # Labels utiles pour l'UI
        labels = {
            "compagnie": raw.get("compagnie_label"),
            "rente_mensuelle_garantie": raw.get("rente_mensuelle_garantie_label"),
            "montant_investi": raw.get("montant_investi_label"),
            "duree": raw.get("duree_label"),
            "reference_police": raw.get("reference_police"),
            "montant_prime": raw.get("montant_prime"),
            "prenom": raw.get("prenom"),
            "nom": raw.get("nom"),
            "date_naissance": raw.get("date_naissance"),
            "adresse": raw.get("adresse"),
            "npa": raw.get("npa"),
            "ville": raw.get("ville"),
            "date_debut": raw.get("date_debut"),
            "date_fin": raw.get("date_fin"),
        }
        extracted_ui = {k: v for k, v in labels.items() if v not in (None, "", "Non indiqué")}

        return {
            "form_type": form_type,
            "filename": filename,
            "numero": matched["numero"] if matched else (numero_detecte or None),
            "numero_detecte": numero_detecte or None,
            "demande": matched,
            "fields": fields,
            "form_payload": form_payload,
            "extracted": extracted_ui,
            "reference_police": mapped.get("reference_police") or raw.get("reference_police"),
            "hint": "Formulaire prérempli depuis le PDF. Modifiez uniquement les champs nécessaires, puis envoyez.",
        }

    @api_router.get("/demandes-offres/meta")
    async def demandes_offres_meta(user: User = Depends(current_user_dependency)):
        from offre_form_types import list_form_types, load_form_menu

        try:
            from email_service import mail_status_public, smtp_configured

            status = mail_status_public()
            smtp_ready = bool(status.get("smtp_configured") or smtp_configured())
        except Exception:
            status = {}
            smtp_ready = False
        return {
            "statuts": STATUTS,
            "kanban_columns": KANBAN_COLUMNS,
            "compagnies": COMPAGNIES_DEFAUT,
            "activites": ACTIVITES_RISQUE,
            "activites_risque": ACTIVITES_RISQUE,
            "civilites": CIVILITES,
            "sexes": SEXES,
            "statuts_professionnels": STATUTS_PRO,
            "situations": SITUATIONS,
            "types_pilier": TYPES_PILIER,
            "periodicites": PERIODICITES,
            "types_paiement": TYPES_PAIEMENT,
            "exonerations": EXONERATIONS,
            "langues": LANGUES,
            "email_configured": bool(status.get("email_ready") if status else False),
            "email_enabled": bool(status.get("offres_email_enabled") if status else False),
            "email_to": (status.get("offres_email_to") if status else None) or _offres_email_to(),
            "smtp_configured": smtp_ready,
            "smtp_from": status.get("smtp_from") if status else None,
            "form_types": list_form_types(active_only=True),
            "form_menu": load_form_menu(),
            "can_process": can_process_offres(user),
            "can_view_all": can_view_all_offres(user),
            "demande_origines": DEMANDE_ORIGINES,
            "types_client": TYPES_CLIENT,
            "erreurs_incomplete_catalog": ERREURS_INCOMPLETE_CATALOG,
            "gestion_categories": {
                cid: {
                    "label": conf["label"],
                    "statuts": list(conf["statuts"] or []),
                }
                for cid, conf in GESTION_CATEGORIES.items()
            },
            "gestion_kanban": GESTION_KANBAN_COLUMNS,
            "delai_surveiller_jours": OFFRES_DELAI_SURVEILLER_JOURS,
            "delai_urgent_jours": OFFRES_DELAI_URGENT_JOURS,
        }

    @api_router.get("/demandes-offres/form-types/{form_type_id}")
    async def get_demande_form_schema(
        form_type_id: str,
        user: User = Depends(current_user_dependency),
    ):
        del user
        from offre_form_types import load_form_schema

        schema = load_form_schema(form_type_id)
        if not schema:
            raise HTTPException(status_code=404, detail="Type de formulaire inconnu")
        return schema

    @api_router.get("/demandes-offres/stats")
    async def demandes_offres_stats(
        conseiller: Optional[str] = Query(None),
        periode: Optional[str] = Query("all"),
        date_de: Optional[str] = Query(None),
        date_a: Optional[str] = Query(None),
        user: User = Depends(current_user_dependency),
    ):
        query = demandes_offres_base_query(user, conseiller)
        rows = await db[COLLECTION].find(query, {"_id": 0}).to_list(10000)
        rows, period_meta = filter_rows_by_period(
            rows, periode=periode, date_de=date_de, date_a=date_a
        )
        return compute_stats(rows, period_meta=period_meta)

    @api_router.get("/demandes-offres/stats/erreurs")
    async def demandes_offres_stats_erreurs(
        conseiller: Optional[str] = Query(None),
        periode: Optional[str] = Query("all"),
        date_de: Optional[str] = Query(None),
        date_a: Optional[str] = Query(None),
        user: User = Depends(current_user_dependency),
    ):
        """Scoring incomplètes : global pour gestionnaires, personnel pour conseillers."""
        if can_process_offres(user) or can_view_all_offres(user):
            query = demandes_offres_base_query(user, conseiller)
        else:
            query = demandes_offres_base_query(user, None)
        rows = await db[COLLECTION].find(query, {"_id": 0}).to_list(10000)
        rows, period_meta = filter_rows_by_period(
            rows, periode=periode, date_de=date_de, date_a=date_a
        )
        stats = compute_erreur_stats(rows)
        if not (can_process_offres(user) or can_view_all_offres(user)):
            from conseiller_identity import normalize_conseiller_key

            labels = set()
            try:
                from access_control import conseiller_identity_labels
                labels = {normalize_conseiller_key(l) for l in conseiller_identity_labels(user)}
            except Exception:
                labels = {normalize_conseiller_key(user.conseiller or user.name or "")}
            labels.discard("")
            stats["by_agent"] = [
                a for a in stats["by_agent"]
                if normalize_conseiller_key(a.get("agent")) in labels
            ]
            stats["scoped"] = True
        else:
            stats["scoped"] = False
        stats["periode"] = period_meta
        return stats

    @api_router.get("/demandes-offres")
    async def list_demandes_offres(
        q: Optional[str] = Query(None),
        statut: Optional[str] = Query(None),
        conseiller: Optional[str] = Query(None),
        type_pilier: Optional[str] = Query(None),
        form_type: Optional[str] = Query(None),
        compagnie: Optional[str] = Query(None),
        periode: Optional[str] = Query("all"),
        date_de: Optional[str] = Query(None),
        date_a: Optional[str] = Query(None),
        categorie: Optional[str] = Query(None),
        priorite: Optional[str] = Query(None),
        en_retard: Optional[bool] = Query(None),
        demande_origine: Optional[str] = Query(None),
        limit: int = Query(200, ge=1, le=1000),
        user: User = Depends(current_user_dependency),
    ):
        query = demandes_offres_base_query(user, conseiller)
        clauses: list[dict] = []
        cat = (categorie or "").strip()
        if cat == "attribuees":
            clauses.append({"demande_origine": DEMANDE_ORIGINE_ATTRIBUEE})
        elif cat == "en_retard":
            pass  # filtré après
        elif cat and cat in GESTION_CATEGORIES and GESTION_CATEGORIES[cat].get("statuts"):
            clauses.append({"statut": {"$in": list(GESTION_CATEGORIES[cat]["statuts"])}})
        elif statut and statut != "all":
            clauses.append({"statut": statut})
        origine = (demande_origine or "").strip().lower()
        if origine in {DEMANDE_ORIGINE_CONSEILLER, DEMANDE_ORIGINE_ATTRIBUEE}:
            clauses.append({"demande_origine": origine})
        if type_pilier and type_pilier != "all":
            clauses.append({"type_pilier": type_pilier})
        if form_type and form_type != "all":
            clauses.append({"form_type": form_type})
        if compagnie and compagnie != "all":
            clauses.append(
                {
                    "$or": [
                        {"compagnies": compagnie},
                        {"offre.compagnie": compagnie},
                        {"offres.compagnie": compagnie},
                    ]
                }
            )
        if q and q.strip():
            pattern = re.escape(q.strip())
            clauses.append(
                {
                    "$or": [
                        {"numero": {"$regex": pattern, "$options": "i"}},
                        {"nom": {"$regex": pattern, "$options": "i"}},
                        {"prenom": {"$regex": pattern, "$options": "i"}},
                        {"agent_label": {"$regex": pattern, "$options": "i"}},
                        {"agent_email": {"$regex": pattern, "$options": "i"}},
                        {"form_type_label": {"$regex": pattern, "$options": "i"}},
                    ]
                }
            )
        if clauses:
            query = {"$and": [query, *clauses]}
        rows = await db[COLLECTION].find(query, {"_id": 0}).sort(
            "updated_at", -1
        ).to_list(limit * 5)
        rows, _ = filter_rows_by_period(
            rows, periode=periode, date_de=date_de, date_a=date_a
        )
        # Filtres priorité / retard (calculés, pas stockés)
        want_prio = (priorite or "").strip().lower()
        want_retard = en_retard is True or cat == "en_retard"
        if want_prio or want_retard:
            filtered = []
            for row in rows:
                prio = compute_priorite(row)
                if want_retard and not prio.get("en_retard"):
                    continue
                if want_prio and want_prio not in {"all", ""} and prio.get("niveau") != want_prio:
                    continue
                filtered.append(row)
            rows = filtered
        rows = rows[:limit]
        return [serialize_demande(row, viewer=user) for row in rows]

    @api_router.post("/demandes-offres")
    async def create_demande_offre(
        payload: Optional[CreateDemandeOffreRequest] = None,
        user: User = Depends(current_user_dependency),
    ):
        from offre_form_types import (
            empty_form_payload,
            filter_form_payload_to_schema,
            get_form_type,
            prefill_form_payload_from_crm,
        )

        created_at = now_iso()
        form_type_id = "pilier3_legacy"
        client_id = None
        if payload is not None:
            form_type_id = (payload.form_type or form_type_id).strip() or form_type_id
            client_id = (payload.client_id or "").strip() or None

        meta = get_form_type(form_type_id) or get_form_type("pilier3_legacy")
        form_type_id = (meta or {}).get("id") or "pilier3_legacy"
        # Defaults isolés : pas de type_pilier / périodicité / exonération hors legacy 3P
        doc = empty_form_defaults(user, form_type=form_type_id)
        custom_label = None
        if payload is not None and (payload.form_type_label or "").strip():
            custom_label = payload.form_type_label.strip()

        if client_id:
            from client_hub import apply_hub_to_offre, get_hub_client

            client = await get_hub_client(db, client_id, user_id=user.user_id)
            if client:
                doc = apply_hub_to_offre(client, doc)
                doc["client_id"] = client_id
                # Identité AGENT DEMANDEUR = profil session uniquement (pas le conseiller client)

        from offre_agent_identity import (
            agent_identity_from_user,
            apply_agent_identity_to_doc,
            apply_agent_identity_to_payload,
        )

        identity = agent_identity_from_user(user)
        apply_agent_identity_to_doc(doc, identity, overwrite_payload=False)

        agent_label = identity.get("label") or user.conseiller or actor_name(user)

        form_payload = empty_form_payload(form_type_id) if form_type_id != "pilier3_legacy" else {}
        # Préremplir agent (session) + identité client CRM
        if isinstance(form_payload, dict) and form_payload:
            form_payload = apply_agent_identity_to_payload(
                form_type_id, form_payload, identity, overwrite=True
            )
            # Identité + adresse client → champs schéma (éditables ensuite)
            form_payload = prefill_form_payload_from_crm(form_type_id, form_payload, doc)
            form_payload = filter_form_payload_to_schema(form_type_id, form_payload)
            # Re-forcer agent après prefill CRM (labels ambigus)
            form_payload = apply_agent_identity_to_payload(
                form_type_id, form_payload, identity, overwrite=True
            )

        if form_type_id != "pilier3_legacy":
            clear_legacy_3p_crm_fields(doc)

        doc.update(
            {
                "id": str(uuid.uuid4()),
                "user_id": TENANT_USER_ID,
                "numero": await next_numero(),
                "statut": STATUT_BROUILLON,
                "agent_label": agent_label,
                "agent_prenom": identity.get("prenom") or "",
                "agent_nom": identity.get("nom") or "",
                "agent_email": identity.get("email") or (getattr(user, "email", None) or ""),
                "agent_finma": identity.get("finma") or "",
                "form_type": form_type_id,
                "form_type_label": custom_label or (meta or {}).get("label") or form_type_id,
                "form_category": (meta or {}).get("category") or "",
                "form_payload": form_payload,
                "offres": [],
                "offre_choisie_id": None,
                "client_id": client_id or doc.get("client_id"),
                "demande_origine": normalize_demande_origine(
                    (payload.demande_origine if payload else None)
                    or (
                        DEMANDE_ORIGINE_ATTRIBUEE
                        if can_process_offres(user) and (payload and payload.assigned_to_account_id)
                        else DEMANDE_ORIGINE_CONSEILLER
                    )
                ),
                "type_client": normalize_type_client(
                    (payload.type_client if payload else None),
                    client_id=client_id or doc.get("client_id"),
                ),
                "assigned_to_account_id": (payload.assigned_to_account_id if payload else None) or None,
                "assigned_to_name": (payload.assigned_to_name if payload else None) or "",
                "created_by_account_id": user.account_id,
                "created_by_name": actor_name(user),
                "created_at": created_at,
                "updated_at": created_at,
                "is_deleted": False,
                "historique": [
                    history(
                        ACTION_CREEE,
                        user,
                        detail=(meta or {}).get("label") or form_type_id,
                    )
                ],
            }
        )
        await db[COLLECTION].insert_one(doc)
        # Demande attribuée → notifier le conseiller
        if doc.get("demande_origine") == DEMANDE_ORIGINE_ATTRIBUEE and doc.get("assigned_to_account_id"):
            await write_offre_notification(
                doc=doc,
                event="attribuee",
                title=f"Demande d'offre attribuée — {doc.get('numero') or ''}".strip(),
                message="Le service Offre vous a attribué une demande à compléter.",
                audience="conseiller",
                account_ids=[doc["assigned_to_account_id"]],
            )
        return serialize_demande(doc, docs=[], viewer=user)

    @api_router.get("/demandes-offres/{demande_id}")
    async def get_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        # Backfill objet permanent pour offres déjà envoyées
        if not (doc.get("email_subject") or "").strip() and (doc.get("date_envoi") or doc.get("numero")):
            try:
                await ensure_permanent_subject(doc)
            except Exception:
                logger.exception("email_subject backfill failed")
        return serialize_demande(doc, docs=await docs_for(demande_id), viewer=user)

    @api_router.put("/demandes-offres/{demande_id}")
    async def update_demande_offre(
        demande_id: str,
        payload: DemandeOffreUpdate,
        user: User = Depends(current_user_dependency),
    ):
        current = await require_demande(demande_id, user)
        if current.get("statut") in locked_statuses and not (is_global_viewer(user) or can_process_offres(user)):
            raise HTTPException(
                status_code=409,
                detail="Cette demande est verrouillée dans son statut actuel",
            )
        raw_updates = payload.model_dump(exclude_unset=True)
        # Ignorer toute tentative client de spoof agent_* (source = session)
        for spoof_key in ("agent_prenom", "agent_nom", "agent_email", "agent_finma", "agent_label"):
            raw_updates.pop(spoof_key, None)

        normalized = dict(current)
        apply_form_fields(normalized, raw_updates)

        from offre_agent_identity import agent_identity_from_user, apply_agent_identity_to_doc

        identity = agent_identity_from_user(user)
        apply_agent_identity_to_doc(normalized, identity, overwrite_payload=True)

        updates: dict[str, Any] = {
            key: normalized.get(key) for key in raw_updates
        }
        # Toujours persister l'identité agent session (anti-spoof)
        updates["agent_prenom"] = normalized.get("agent_prenom")
        updates["agent_nom"] = normalized.get("agent_nom")
        updates["agent_email"] = normalized.get("agent_email")
        updates["agent_finma"] = normalized.get("agent_finma")
        updates["agent_label"] = normalized.get("agent_label")
        if "form_payload" in raw_updates or isinstance(normalized.get("form_payload"), dict):
            updates["form_payload"] = normalized.get("form_payload")
        updates["updated_at"] = now_iso()

        # Lier / créer le client hub + synchroniser l'identité
        try:
            from client_hub import (
                apply_hub_to_offre,
                get_hub_client,
                push_person_to_hub,
                upsert_hub_client_from_person,
            )

            cid = (normalized.get("client_id") or current.get("client_id") or "").strip() or None
            if cid and "client_id" in raw_updates:
                hub = await get_hub_client(db, cid, user_id=user.user_id)
                if hub:
                    filled = apply_hub_to_offre(hub)
                    for k, v in filled.items():
                        if v not in (None, ""):
                            # Autofill uniquement si le champ n'est pas explicitement envoyé vide
                            if k not in raw_updates or raw_updates.get(k) in (None, ""):
                                updates[k] = v
                                normalized[k] = v
                    updates["client_id"] = cid
            elif (normalized.get("prenom") or "").strip() and (normalized.get("nom") or "").strip():
                hub, _action = await upsert_hub_client_from_person(
                    db,
                    normalized,
                    user_id=user.user_id,
                    module="offres",
                    conseiller=normalized.get("agent_label") or user.conseiller,
                )
                if hub:
                    updates["client_id"] = hub["id"]
                    cid = hub["id"]

            if cid and (normalized.get("prenom") or current.get("prenom")):
                await push_person_to_hub(
                    db,
                    cid,
                    {**current, **normalized, **updates},
                    user_id=user.user_id,
                    module="offres",
                )
        except Exception:
            logger.exception("Hub client sync offres échoué demande=%s", demande_id)

        # Historique : pas de ligne à chaque Enregistrer.
        # « Demande modifiée » une seule fois depuis le dernier envoi/validation (brouillon = silencieux).
        hist = collapse_demande_historique(current.get("historique") or [])
        merged_for_diff = {**current, **updates}
        substantive = build_field_changes(current, merged_for_diff)
        if should_track_demande_modification(current) and substantive:
            hist = apply_modification_to_historique(
                hist,
                history(ACTION_MODIFIEE, user),
            )
        updates["historique"] = hist

        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {"$set": updates},
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    @api_router.post("/demandes-offres/{demande_id}/validate")
    async def validate_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        from offre_agent_identity import agent_identity_from_user, apply_agent_identity_to_doc

        identity = agent_identity_from_user(user)
        apply_agent_identity_to_doc(doc, identity, overwrite_payload=True)
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {"$set": {
                "agent_prenom": doc.get("agent_prenom"),
                "agent_nom": doc.get("agent_nom"),
                "agent_email": doc.get("agent_email"),
                "agent_finma": doc.get("agent_finma"),
                "agent_label": doc.get("agent_label"),
                "form_payload": doc.get("form_payload") or {},
            }},
        )
        missing = missing_required(doc)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"message": "Champs obligatoires manquants", "missing": missing},
            )
        # Assurer le lien hub avant validation
        try:
            from client_hub import upsert_hub_client_from_person

            if (doc.get("prenom") or "").strip() and (doc.get("nom") or "").strip():
                hub, _ = await upsert_hub_client_from_person(
                    db, doc, user_id=user.user_id, module="offres",
                    conseiller=doc.get("agent_label") or user.conseiller,
                )
                if hub and hub.get("id") != doc.get("client_id"):
                    await db[COLLECTION].update_one(
                        {"id": demande_id},
                        {"$set": {"client_id": hub["id"]}},
                    )
        except Exception:
            logger.exception("Hub link on validate failed")
        return await save_status(
            demande_id,
            user,
            statut=STATUT_VALIDEE,
            action=ACTION_VALIDEE,
        )

    @api_router.post("/demandes-offres/{demande_id}/envoyer")
    async def send_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        from offre_agent_identity import agent_identity_from_user, apply_agent_identity_to_doc

        identity = agent_identity_from_user(user)
        apply_agent_identity_to_doc(doc, identity, overwrite_payload=True)
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {"$set": {
                "agent_prenom": doc.get("agent_prenom"),
                "agent_nom": doc.get("agent_nom"),
                "agent_email": doc.get("agent_email"),
                "agent_finma": doc.get("agent_finma"),
                "agent_label": doc.get("agent_label"),
                "form_payload": doc.get("form_payload") or {},
            }},
        )
        missing = missing_required(doc)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"message": "Champs obligatoires manquants", "missing": missing},
            )
        sent, email_error = await try_send_email(doc, event="envoyee")
        detail = DETAIL_EMAIL_ENVOYE if sent else (email_error or "E-mail non envoyé")
        already_sent = demande_was_already_sent(doc)
        action = ACTION_RENVOYEE if already_sent else ACTION_ENVOYEE
        result = await save_status(
            demande_id,
            user,
            statut=STATUT_ENVOYEE,
            action=action,
            detail=detail,
            extra={
                "date_envoi": now_iso(),
                "email_sent": sent,
                "email_error": email_error,
                "incomplete_comment": None,
                "incomplete_at": None,
                "incomplete_by": None,
                "incomplete_email_sent": False,
                "incomplete_email_sent_at": None,
                "incomplete_email_error": None,
            },
        )
        await write_offre_notification(
            doc=doc,
            event="envoyee",
            title=f"Nouvelle demande d'offre {doc.get('numero') or ''}".strip(),
            message=f"{actor_name(user)} a envoyé une demande d'offre à traiter.",
            audience="gestionnaires",
            account_ids=await manager_account_ids(),
        )
        return result

    @api_router.post("/demandes-offres/{demande_id}/renvoyer")
    async def admin_resend_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        """
        Admin uniquement : renvoie l'e-mail offres@ avec le form_payload déjà enregistré.
        Ne crée pas de nouvelle demande (même id / même numéro).
        N'écrase pas l'identité agent sauvegardée — l'admin apparaît seulement dans l'historique.
        """
        require_admin(user)
        doc = await require_demande(demande_id, user)
        statut = (doc.get("statut") or "").strip()
        if statut != STATUT_ENVOYEE:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Le renvoi n'est possible que pour le statut « {STATUT_ENVOYEE} » "
                    f"(statut actuel : {statut or '—'})."
                ),
            )
        # Renvoi admin : pas de validation des champs obligatoires —
        # on réutilise le form_payload déjà enregistré tel quel (même si incomplet).
        # Pipeline d'envoi existant → offres@agencemendes.ch (via offres_email_to)
        sent, email_error = await try_send_email(doc, event="envoyee")
        detail = DETAIL_EMAIL_ENVOYE if sent else (email_error or "E-mail non envoyé")
        result = await save_status(
            demande_id,
            user,
            statut=STATUT_ENVOYEE,
            action=ACTION_RENVOYEE,
            detail=detail,
            extra={
                "date_envoi": now_iso(),
                "email_sent": sent,
                "email_error": email_error,
            },
        )
        await write_offre_notification(
            doc=doc,
            event="renvoyee_admin",
            title=f"Offre renvoyée — {doc.get('numero') or ''}".strip(),
            message=(
                f"{actor_name(user)} a renvoyé la demande d'offre "
                f"{doc.get('numero') or ''} (données enregistrées)."
            ).strip(),
            audience="gestionnaires",
            account_ids=await manager_account_ids(),
        )
        return result

    @api_router.post("/demandes-offres/{demande_id}/incomplete")
    async def mark_demande_incomplete(
        demande_id: str,
        payload: IncompleteRequest,
        user: User = Depends(current_user_dependency),
    ):
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        comment = payload.comment.strip()
        if not comment:
            raise HTTPException(status_code=422, detail="Le commentaire est obligatoire")
        at = now_iso()
        by_name = actor_name(user)
        docs_manq = (payload.documents_manquants or "").strip() or None
        raw_erreurs = [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in (payload.erreurs or [])]
        for e in raw_erreurs:
            e["by_name"] = by_name
            e["by_id"] = user.account_id
            e["at"] = at
        erreurs = normalize_erreurs_incomplete(raw_erreurs)
        detail = comment
        if docs_manq:
            detail = f"{comment}\nDocuments manquants : {docs_manq}"
        if erreurs:
            detail = detail + "\n" + "\n".join(
                f"- {(e.get('label') or e.get('code'))}: {(e.get('detail') or '')}".strip()
                for e in erreurs
            )
        prev_statut = (doc.get("statut") or "").strip()
        prev_comment = (doc.get("incomplete_comment") or "").strip()
        compagnie_cible = (payload.compagnie or "").strip() or None
        # Anti-doublon : même signalement déjà notifié (pas de rechargement / re-clic identique)
        already_notified = (
            prev_statut == STATUT_INCOMPLETE
            and prev_comment == comment
            and bool(doc.get("incomplete_email_sent"))
            and (not compagnie_cible or company_key(doc.get("incomplete_compagnie")) == company_key(compagnie_cible))
        )

        extra = {
            "incomplete_comment": comment,
            "documents_manquants": docs_manq,
            "erreurs_incomplete": erreurs,
            "incomplete_at": at,
            "incomplete_by": by_name,
            "message_conseiller": detail,
            "incomplete_compagnie": compagnie_cible,
        }
        if compagnie_cible:
            offres = normalize_offres_list(doc)
            target = find_offre_for_compagnie(offres, compagnie_cible)
            if not target:
                # Créer une fiche incomplète sans offre reçue
                target = {
                    "id": str(uuid.uuid4()),
                    "compagnie": compagnie_cible,
                    "statut": STATUT_COMPAGNIE_INCOMPLETE,
                    "documents": [],
                    "retenue": False,
                    "incomplete_comment": comment,
                    "incomplete_at": at,
                    "received_at": None,
                    "date_reception": None,
                }
            else:
                target = dict(target)
                target["statut"] = STATUT_COMPAGNIE_INCOMPLETE
                target["incomplete_comment"] = comment
                target["incomplete_at"] = at
            offres = upsert_company_offre(offres, target)
            extra["offres"] = offres
            extra["offre"] = target

        result = await save_status(
            demande_id,
            user,
            statut=STATUT_INCOMPLETE,
            action="Offre compagnie incomplète" if compagnie_cible else "Demande déclarée incomplète",
            detail=f"{compagnie_cible} — {detail}" if compagnie_cible else detail,
            extra=extra,
            meta={"erreurs": erreurs, "compagnie": compagnie_cible},
        )

        sent = False
        email_error = None
        if already_notified:
            email_error = "Notification déjà envoyée pour ce signalement"
            logger.info(
                "Offre incomplète: e-mail ignoré (doublon) demande=%s",
                doc.get("numero") or demande_id,
            )
        else:
            mail_doc = {
                **doc,
                "id": doc.get("id") or demande_id,
                "numero": doc.get("numero"),
                "prenom": doc.get("prenom") or (result or {}).get("prenom"),
                "nom": doc.get("nom") or (result or {}).get("nom"),
                "client_id": doc.get("client_id"),
                "statut": STATUT_INCOMPLETE,
                "incomplete_comment": comment,
                "incomplete_at": at,
                "incomplete_by": by_name,
                "erreurs_incomplete": erreurs,
                "email_subject": doc.get("email_subject"),
            }
            sent, email_error = await try_send_email(
                mail_doc, event="incomplete", comment=detail
            )
            try:
                await db[COLLECTION].update_one(
                    {"id": demande_id, "user_id": TENANT_USER_ID},
                    {
                        "$set": {
                            "incomplete_email_sent": bool(sent),
                            "incomplete_email_sent_at": at if sent else None,
                            "incomplete_email_error": email_error,
                            "updated_at": now_iso(),
                        }
                    },
                )
            except Exception:
                logger.exception("Failed to persist incomplete_email_sent flag")

        if isinstance(result, dict):
            result["email_sent"] = sent
            result["email_error"] = email_error
            result["incomplete_email_sent"] = bool(sent) or already_notified
        if not already_notified:
            await write_offre_notification(
                doc=doc,
                event="incomplete",
                title=f"Offre incomplète — {doc.get('numero') or ''}".strip(),
                message=detail,
                audience="conseiller",
                account_ids=[doc.get("created_by_account_id")] if doc.get("created_by_account_id") else [],
            )
        return result

    @api_router.post("/demandes-offres/{demande_id}/compagnie-incomplete")
    async def mark_company_incomplete_status(
        demande_id: str,
        payload: MarkCompanyIncompleteRequest,
        user: User = Depends(current_user_dependency),
    ):
        """Passe une compagnie en statut Incomplète (sans e-mail). La notification se fait via /incomplete."""
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        compagnie = payload.compagnie.strip()
        if not compagnie:
            raise HTTPException(status_code=422, detail="Compagnie obligatoire")
        offres = normalize_offres_list(doc)
        target = find_offre_for_compagnie(offres, compagnie)
        at = now_iso()
        comment = (payload.comment or "").strip() or None
        if not target:
            target = {
                "id": str(uuid.uuid4()),
                "compagnie": compagnie,
                "documents": [],
                "retenue": False,
            }
        target = dict(target)
        target["statut"] = STATUT_COMPAGNIE_INCOMPLETE
        target["incomplete_comment"] = comment
        target["incomplete_at"] = at
        offres = upsert_company_offre(offres, target)
        return await save_status(
            demande_id,
            user,
            statut=normalize_statut(doc.get("statut")),
            action="Compagnie marquée incomplète",
            detail=compagnie + (f" — {comment}" if comment else ""),
            extra={"offres": offres, "offre": target},
            meta={"compagnie": compagnie},
        )

    @api_router.post("/demandes-offres/{demande_id}/completer-renvoyer")
    async def complete_and_resend_demande(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        missing = missing_required(doc)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"message": "Champs obligatoires manquants", "missing": missing},
            )
        sent, email_error = await try_send_email(doc, event="envoyee")
        detail = DETAIL_EMAIL_ENVOYE if sent else (email_error or "E-mail non envoyé")
        result = await save_status(
            demande_id,
            user,
            statut=STATUT_ENVOYEE,
            action=ACTION_RENVOYEE,
            detail=detail,
            extra={
                "date_envoi": now_iso(),
                "email_sent": sent,
                "email_error": email_error,
                "incomplete_comment": None,
                "documents_manquants": None,
                "incomplete_at": None,
                "incomplete_by": None,
                "incomplete_status": None,
                "incomplete_email_sent": False,
                "incomplete_email_sent_at": None,
                "incomplete_email_error": None,
                "message_conseiller": None,
            },
        )
        await write_offre_notification(
            doc=doc,
            event="completee_renvoyee",
            title=f"Éléments complétés — {doc.get('numero') or ''}".strip(),
            message=f"{actor_name(user)} a renvoyé les éléments demandés.",
            audience="gestionnaires",
            account_ids=await manager_account_ids(),
        )
        return result

    @api_router.post("/demandes-offres/{demande_id}/offre")
    async def receive_company_offer(
        request: Request,
        demande_id: str,
        compagnie: str = Form(...),
        date_reception: str = Form(...),
        reference: Optional[str] = Form(None),
        montant_prime: Optional[str] = Form(None),
        type_contrat: Optional[str] = Form(None),
        garanties: Optional[str] = Form(None),
        duree: Optional[str] = Form(None),
        commentaires: Optional[str] = Form(None),
        file: Optional[UploadFile] = File(None),
        user: User = Depends(current_user_dependency),
    ):
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        uploads = await collect_multipart_uploads(request, single_file=file)

        stored_docs = []
        for upload in uploads:
            stored_docs.append(
                await store_doc(demande_id, upload, user, category="Offre compagnie")
            )

        existing = normalize_offres_list(doc)
        prev = find_offre_for_compagnie(existing, compagnie.strip())
        base = {
            "id": (prev or {}).get("id") or str(uuid.uuid4()),
            "compagnie": compagnie.strip(),
            "date_reception": date_reception.strip(),
            "reference": (reference or "").strip() or ((prev or {}).get("reference")),
            "montant_prime": parse_float(montant_prime)
            if montant_prime not in (None, "")
            else (prev or {}).get("montant_prime"),
            "type_contrat": (type_contrat or "").strip() or ((prev or {}).get("type_contrat")),
            "garanties": (garanties or "").strip() or ((prev or {}).get("garanties")),
            "duree": (duree or "").strip() or ((prev or {}).get("duree")),
            "commentaires": (commentaires or "").strip() or ((prev or {}).get("commentaires")),
            "documents": list((prev or {}).get("documents") or []),
            "document_id": (prev or {}).get("document_id"),
            "retenue": False,
            "statut": STATUT_COMPAGNIE_RECUE,
            "received_at": now_iso(),
            "received_by": actor_name(user),
            "incomplete_comment": None,
            "incomplete_at": None,
        }
        offer = append_documents_to_offre(base, stored_docs)
        existing = upsert_company_offre(existing, offer)
        # Récupérer la version fusionnée (documents cumulés)
        offer = find_offre_for_compagnie(existing, compagnie.strip()) or offer
        new_statut = resolve_statut_apres_reception_offre(doc, existing)
        hist_detail = compagnie.strip()
        if stored_docs:
            hist_detail = f"{compagnie.strip()} · {len(stored_docs)} document(s)"
        result = await save_status(
            demande_id,
            user,
            statut=new_statut,
            action="Offre compagnie reçue",
            detail=hist_detail,
            extra={
                "offres": existing,
                "offre": offer,  # dernière offre (compat UI)
            },
            meta={"compagnie": compagnie.strip(), "offre_id": offer.get("id")},
            document_id=(offer.get("documents") or [{}])[-1].get("id") if offer.get("documents") else None,
        )
        mail_doc = {
            **doc,
            **(result if isinstance(result, dict) else {}),
            "statut": new_statut,
            "offres": existing,
            "offre": offer,
        }
        sent, email_error = await try_send_email(mail_doc, event="recue", offer=offer)
        if isinstance(result, dict):
            result["email_sent"] = sent
            result["email_error"] = email_error
        await write_offre_notification(
            doc=doc,
            event="recue",
            title=f"Offre reçue — {doc.get('numero') or ''}".strip(),
            message=f"Offre {compagnie.strip()} disponible pour consultation.",
            audience="conseiller",
            account_ids=[doc.get("created_by_account_id")] if doc.get("created_by_account_id") else [],
        )
        return result

    @api_router.post("/demandes-offres/{demande_id}/complete")
    async def mark_offre_complete(
        request: Request,
        demande_id: str,
        compagnie: str = Form(...),
        date_reception: str = Form(...),
        reference: Optional[str] = Form(None),
        montant_prime: Optional[str] = Form(None),
        type_contrat: Optional[str] = Form(None),
        garanties: Optional[str] = Form(None),
        duree: Optional[str] = Form(None),
        commentaires: Optional[str] = Form(None),
        message_conseiller: Optional[str] = Form(None),
        file: Optional[UploadFile] = File(None),
        user: User = Depends(current_user_dependency),
    ):
        """
        Compat : « Offre complète » n'est plus un statut métier distinct.
        Enregistre comme « Offre reçue » (multi-documents) et notifie le conseiller.
        """
        # Délègue au même flux que /offre (statut compagnie = reçue)
        result = await receive_company_offer(
            request=request,
            demande_id=demande_id,
            compagnie=compagnie,
            date_reception=date_reception,
            reference=reference,
            montant_prime=montant_prime,
            type_contrat=type_contrat,
            garanties=garanties,
            duree=duree,
            commentaires=commentaires or message_conseiller,
            file=file,
            user=user,
        )
        if isinstance(result, dict) and (message_conseiller or "").strip():
            msg = (message_conseiller or "").strip()
            await db[COLLECTION].update_one(
                {"id": demande_id, "user_id": TENANT_USER_ID},
                {
                    "$set": {
                        "message_conseiller": msg,
                        "updated_at": now_iso(),
                    }
                },
            )
            result["message_conseiller"] = msg
        return result

    @api_router.post("/demandes-offres/{demande_id}/offres-completes")
    async def mark_offres_completes(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        """
        Gestionnaire : signale que toutes les offres demandées sont complètes.
        Statut → « Offres complètes » + e-mail au conseiller créateur.
        """
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        current = normalize_statut(doc.get("statut"))
        terminal = {STATUT_OFFRE_SIGNEE, STATUT_OFFRE_REFUSEE, STATUT_ANNULEE}
        if current in terminal:
            raise HTTPException(
                status_code=409,
                detail=f"Impossible de marquer « Offres complètes » depuis le statut « {current} »",
            )

        at = now_iso()
        by_name = actor_name(user)
        result = await save_status(
            demande_id,
            user,
            statut=STATUT_OFFRE_COMPLETE,
            action="Offres complètes",
            detail="Toutes les offres demandées sont reçues et complètes",
            extra={
                "offres_completes_at": at,
                "offres_completes_by": by_name,
                "offres_completes_by_id": user.account_id,
            },
        )
        mail_doc = {
            **doc,
            **(result if isinstance(result, dict) else {}),
            "statut": STATUT_OFFRE_COMPLETE,
        }
        sent, email_error = await try_send_email(mail_doc, event="offres_completes")
        if isinstance(result, dict):
            result["email_sent"] = sent
            result["email_error"] = email_error
            if sent:
                await db[COLLECTION].update_one(
                    {"id": demande_id, "user_id": TENANT_USER_ID},
                    {"$set": {"offres_completes_email_sent": True, "updated_at": now_iso()}},
                )
                result["offres_completes_email_sent"] = True
        await write_offre_notification(
            doc=doc,
            event="offres_completes",
            title=f"Offres complètes — {doc.get('numero') or ''}".strip(),
            message="Les offres sont complètes et disponibles pour le conseiller.",
            audience="conseiller",
            account_ids=[doc.get("created_by_account_id")] if doc.get("created_by_account_id") else [],
        )
        return result

    @api_router.post("/demandes-offres/{demande_id}/offres/{offre_id}/documents")
    async def add_documents_to_company_offer(
        request: Request,
        demande_id: str,
        offre_id: str,
        file: Optional[UploadFile] = File(None),
        user: User = Depends(current_user_dependency),
    ):
        """Ajoute un ou plusieurs documents à une offre compagnie (sans remplacer)."""
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        existing = normalize_offres_list(doc)
        target = None
        for o in existing:
            if str(o.get("id")) == str(offre_id):
                target = o
                break
        if not target:
            raise HTTPException(status_code=404, detail="Offre compagnie introuvable")

        uploads = await collect_multipart_uploads(request, single_file=file)
        if not uploads:
            raise HTTPException(status_code=400, detail="Aucun fichier fourni")

        stored_docs = [
            await store_doc(demande_id, upload, user, category="Offre compagnie")
            for upload in uploads
        ]
        updated = append_documents_to_offre(target, stored_docs)
        new_offres = []
        for o in existing:
            if str(o.get("id")) == str(offre_id):
                new_offres.append(updated)
            else:
                new_offres.append(o)

        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {
                    "offres": new_offres,
                    "offre": updated,
                    "updated_at": now_iso(),
                },
                "$push": {
                    "historique": history(
                        "Documents offre ajoutés",
                        user,
                        f"{updated.get('compagnie') or ''} · {len(stored_docs)} fichier(s)",
                        statut=doc.get("statut"),
                        document_id=stored_docs[-1].get("id") if stored_docs else None,
                        meta={"compagnie": updated.get("compagnie"), "offre_id": offre_id},
                    )
                },
            },
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    @api_router.delete("/demandes-offres/{demande_id}/offres/{offre_id}/documents/{doc_id}")
    async def delete_document_from_company_offer(
        demande_id: str,
        offre_id: str,
        doc_id: str,
        user: User = Depends(current_user_dependency),
    ):
        """Retire un document d'une offre compagnie (soft-delete stockage)."""
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        existing = normalize_offres_list(doc)
        target = None
        for o in existing:
            if str(o.get("id")) == str(offre_id):
                target = o
                break
        if not target:
            raise HTTPException(status_code=404, detail="Offre compagnie introuvable")

        docs = [d for d in (target.get("documents") or []) if str(d.get("id")) != str(doc_id)]
        if len(docs) == len(target.get("documents") or []):
            # Compat document_id seul
            if str(target.get("document_id")) != str(doc_id):
                raise HTTPException(status_code=404, detail="Document introuvable sur cette offre")
        target = dict(target)
        target["documents"] = docs
        target["document_id"] = docs[0]["id"] if docs else None
        new_offres = [
            normalize_offre_entry(target) if str(o.get("id")) == str(offre_id) else o
            for o in existing
        ]
        await db[COLLECTION_DOCS].update_one(
            {"id": doc_id, "user_id": TENANT_USER_ID},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now_iso(),
                    "deleted_by": user.account_id,
                }
            },
        )
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {"offres": new_offres, "updated_at": now_iso()},
                "$push": {
                    "historique": history(
                        "Document offre retiré",
                        user,
                        f"{target.get('compagnie') or ''}",
                        meta={"compagnie": target.get("compagnie"), "offre_id": offre_id, "document_id": doc_id},
                    )
                },
            },
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    @api_router.post("/demandes-offres/{demande_id}/notes-internes")
    async def add_internal_note(
        demande_id: str,
        payload: InternalNoteRequest,
        user: User = Depends(current_user_dependency),
    ):
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        note = payload.note.strip()
        entry = {
            "id": str(uuid.uuid4()),
            "at": now_iso(),
            "by_name": actor_name(user),
            "by_id": user.account_id,
            "note": note,
        }
        notes = list(doc.get("notes_internes") or [])
        notes.append(entry)
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {"notes_internes": notes, "updated_at": now_iso()},
                "$push": {"historique": history("Note interne", user, note)},
            },
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    @api_router.get("/notifications/offres")
    async def list_offre_notifications(
        user: User = Depends(current_user_dependency),
        limit: int = Query(30, ge=1, le=100),
    ):
        """Notifications CRM liées aux demandes d'offres pour l'utilisateur courant."""
        account_id = user.account_id
        or_clauses = [{"audience": "all"}]
        if can_process_offres(user):
            or_clauses.append({"audience": "gestionnaires"})
            or_clauses.append({"account_ids": account_id})
        else:
            or_clauses.append({"account_ids": account_id})
            or_clauses.append({"audience": "conseiller", "account_ids": account_id})
        rows = await db.offre_notifications.find(
            {"user_id": TENANT_USER_ID, "$or": or_clauses},
            {"_id": 0},
        ).sort("created_at", -1).to_list(limit)
        for row in rows:
            row["read"] = account_id in (row.get("read_by") or [])
        unread = sum(1 for r in rows if not r.get("read"))
        return {"items": rows, "count": unread, "total": len(rows)}

    @api_router.post("/notifications/offres/{notif_id}/read")
    async def mark_offre_notification_read(
        notif_id: str,
        user: User = Depends(current_user_dependency),
    ):
        await db.offre_notifications.update_one(
            {"id": notif_id, "user_id": TENANT_USER_ID},
            {"$addToSet": {"read_by": user.account_id}},
        )
        return {"ok": True}

    @api_router.post("/demandes-offres/{demande_id}/choisir-offre")
    async def choose_company_offer(
        demande_id: str,
        payload: ChooseOffreRequest,
        user: User = Depends(current_user_dependency),
    ):
        """Ancienne sélection « offre retenue » — désactivée (workflow retiré)."""
        _ = (demande_id, payload, user)
        raise HTTPException(
            status_code=410,
            detail="Cette action n'est plus disponible",
        )

    @api_router.post("/demandes-offres/{demande_id}/conclusion")
    async def mark_demande_conclusion(
        demande_id: str,
        payload: ConclusionRequest = ConclusionRequest(),
        user: User = Depends(current_user_dependency),
    ):
        await require_demande(demande_id, user)
        body = payload
        return await save_status(
            demande_id,
            user,
            statut=STATUT_EN_CONCLUSION,
            action="Passage en conclusion",
            detail=(body.commentaire or "").strip(),
            extra={
                "conclusion": {
                    "at": now_iso(),
                    "by": actor_name(user),
                    "commentaire": (body.commentaire or "").strip() or None,
                    "date_conclusion": (body.date_conclusion or "").strip() or None,
                }
            },
        )

    @api_router.post("/demandes-offres/{demande_id}/envoyer-client")
    async def send_offer_to_client(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        has_offer = bool(doc.get("offre") or doc.get("offre_choisie_id") or (doc.get("offres") or []))
        if not has_offer:
            raise HTTPException(status_code=409, detail="Aucune offre compagnie reçue")
        return await save_status(
            demande_id,
            user,
            statut=STATUT_OFFRE_ENVOYEE_CLIENT,
            action="Offre envoyée au client",
            extra={
                "envoi_client": {
                    "at": now_iso(),
                    "by": actor_name(user),
                    "by_id": user.account_id,
                }
            },
        )

    @api_router.post("/demandes-offres/{demande_id}/signature")
    async def record_offer_signature(
        demande_id: str,
        request: Request,
        signee: Optional[bool] = Form(None),
        date_signature: Optional[str] = Form(None),
        commentaire: Optional[str] = Form(None),
        date_relance: Optional[str] = Form(None),
        file: Optional[UploadFile] = File(None),
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        if signee is None:
            try:
                payload = SignatureRequest.model_validate(await request.json())
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail="Le champ signee est obligatoire",
                ) from exc
        else:
            payload = SignatureRequest(
                signee=signee,
                date_signature=date_signature,
                commentaire=commentaire,
                date_relance=date_relance,
            )
        stored = (
            await store_doc(demande_id, file, user, category="Offre signée")
            if file is not None
            else None
        )
        signature = {
            "signee": payload.signee,
            "date_signature": (payload.date_signature or "").strip() or None,
            "commentaire": (payload.commentaire or "").strip() or None,
            "date_relance": (payload.date_relance or "").strip() or None,
            "document_id": stored.get("id") if stored else None,
            "recorded_at": now_iso(),
            "recorded_by": actor_name(user),
        }
        statut = STATUT_OFFRE_SIGNEE if payload.signee else STATUT_OFFRE_REFUSEE
        action = "Offre signée" if payload.signee else "Offre refusée"
        result = await save_status(
            demande_id,
            user,
            statut=statut,
            action=action,
            detail=signature["commentaire"] or "",
            extra={"signature": signature},
            document_id=signature.get("document_id"),
        )
        if payload.signee:
            mail_doc = {**doc, "statut": STATUT_OFFRE_SIGNEE, "signature": signature}
            if not mail_doc.get("email_subject"):
                await ensure_permanent_subject(mail_doc)
            sent, email_error = await try_send_email(
                mail_doc, event="signee", signature=signature
            )
            if isinstance(result, dict):
                result["email_sent"] = sent
                result["email_error"] = email_error
            await write_offre_notification(
                doc=doc,
                event="signee",
                title=f"Offre signée — {doc.get('numero') or ''}".strip(),
                message="Le document signé a été déposé dans le CRM.",
                audience="gestionnaires",
                account_ids=await manager_account_ids(),
            )
        return result

    @api_router.post("/demandes-offres/{demande_id}/annuler")
    async def cancel_demande_offre(
        demande_id: str,
        payload: Optional[AnnulationRequest] = None,
        user: User = Depends(current_user_dependency),
    ):
        """
        Annule une demande : change uniquement le statut (aucune suppression de données).
        Conserve le statut précédent dans ``statut_avant_annulation`` (audit) ;
        la restauration remet toujours en brouillon.
        """
        doc = await require_demande(demande_id, user)
        statut = normalize_statut(doc.get("statut"))
        if statut == STATUT_ANNULEE:
            raise HTTPException(status_code=409, detail="Cette demande est déjà annulée")
        if statut == STATUT_OFFRE_SIGNEE:
            raise HTTPException(
                status_code=409,
                detail="Une offre signée ne peut pas être annulée",
            )
        comment = (payload.commentaire if payload else None) or ""
        return await save_status(
            demande_id,
            user,
            statut=STATUT_ANNULEE,
            action=ACTION_ANNULEE,
            detail=comment.strip(),
            extra={
                FIELD_STATUT_AVANT_ANNULATION: statut,
                "annulation": {
                    "at": now_iso(),
                    "by": actor_name(user),
                    "commentaire": comment.strip() or None,
                    "statut_avant": statut,
                },
            },
        )

    @api_router.post("/demandes-offres/{demande_id}/restaurer")
    async def restore_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        """
        Restaure une demande annulée en brouillon (statut « Brouillon »).
        Numéro, client, documents, offres et historique sont conservés ;
        seul le statut change (plus événement « Demande restaurée »).
        """
        doc = await require_demande(demande_id, user)
        statut = normalize_statut(doc.get("statut"))
        if statut != STATUT_ANNULEE:
            raise HTTPException(
                status_code=409,
                detail="Seules les demandes annulées peuvent être restaurées",
            )
        restored = resolve_statut_avant_annulation(doc)
        # Ne pas réécrire le numéro ni toucher aux données métier
        numero = doc.get("numero")
        result = await save_status(
            demande_id,
            user,
            statut=restored,
            action=ACTION_RESTAUREE,
            detail=f"Statut rétabli : {restored}",
            meta={"statut_avant_annulation": restored, "numero": numero},
            extra={
                FIELD_STATUT_AVANT_ANNULATION: None,
                "restauration": {
                    "at": now_iso(),
                    "by": actor_name(user),
                    "statut_retabli": restored,
                },
            },
        )
        # Garantir que le numéro est inchangé (save_status ne le touche pas)
        if isinstance(result, dict) and numero and result.get("numero") != numero:
            result["numero"] = numero
        return result

    @api_router.post("/demandes-offres/{demande_id}/modifier/start")
    async def start_offre_modification(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        """Prépare une modification : snapshot des valeurs actuelles (numéro inchangé)."""
        doc = await require_demande(demande_id, user)
        snapshot = {
            k: doc.get(k)
            for k in (
                "civilite", "nom", "prenom", "sexe", "date_naissance", "nationalite", "permis",
                "adresse", "ville", "npa", "pays", "statut_professionnel", "profession",
                "type_pilier", "date_debut", "duree_contrat", "montant_prime", "periodicite_prime",
                "rente_invalidite", "compagnies",
                "form_payload", "form_type", "form_type_label", "commentaires", "langue_offre",
            )
        }
        result = await save_status(
            demande_id,
            user,
            statut=STATUT_OFFRE_A_MODIFIER,
            action="Modification d'offre démarrée",
            detail="Snapshot enregistré",
            extra={
                "snapshot_original": snapshot,
                "modifications": [],
                "note_service_offre": doc.get("note_service_offre") or "",
            },
        )
        return result

    @api_router.post("/demandes-offres/{demande_id}/modifier/envoyer")
    async def send_offre_modification(
        demande_id: str,
        payload: ModificationRequest,
        user: User = Depends(current_user_dependency),
    ):
        """Envoie la demande de modification au service Offre (même numéro + même objet)."""
        doc = await require_demande(demande_id, user)
        await ensure_permanent_subject(doc)
        snapshot = doc.get("snapshot_original") or {}
        # Appliquer les champs fournis
        updates: dict = {}
        if payload.fields:
            for k, v in payload.fields.items():
                updates[k] = v
        if payload.form_payload is not None:
            updates["form_payload"] = payload.form_payload
        note = (payload.note_service_offre or "").strip() or None
        if note is not None:
            updates["note_service_offre"] = note
        merged = {**doc, **updates}
        changes = payload.changes or build_field_changes(snapshot, merged)
        if payload.form_payload is not None and snapshot.get("form_payload") != payload.form_payload:
            # Diff au niveau form_payload keys
            old_fp = snapshot.get("form_payload") or {}
            new_fp = payload.form_payload or {}
            for k in set(list(old_fp.keys()) + list(new_fp.keys())):
                if old_fp.get(k) != new_fp.get(k):
                    changes.append({
                        "field": f"form_payload.{k}",
                        "label": k,
                        "old": old_fp.get(k),
                        "new": new_fp.get(k),
                    })
        updates["modifications"] = changes
        updates["note_service_offre"] = note or doc.get("note_service_offre") or ""
        result = await save_status(
            demande_id,
            user,
            statut=STATUT_OFFRE_MODIFIEE,
            action="Offre modifiée — envoyée au service Offre",
            detail=note or f"{len(changes)} champ(s) modifié(s)",
            extra=updates,
            meta={"changes": changes, "note": note},
        )
        mail_doc = {**doc, **updates, "statut": STATUT_OFFRE_MODIFIEE, "modifications": changes}
        sent, email_error = await try_send_email(
            mail_doc, event="modification", changes=changes, note=note
        )
        if isinstance(result, dict):
            result["email_sent"] = sent
            result["email_error"] = email_error
        await write_offre_notification(
            doc=doc,
            event="modification",
            title=f"Modification d'offre — {doc.get('numero') or ''}".strip(),
            message=note or "Une demande de modification a été envoyée.",
            audience="gestionnaires",
            account_ids=await manager_account_ids(),
        )
        return result

    @api_router.post("/demandes-offres/{demande_id}/modifier/extract-pdf")
    async def extract_pdf_for_modification(
        demande_id: str,
        file: UploadFile = File(...),
        user: User = Depends(current_user_dependency),
    ):
        """
        Import PDF sur une demande connue : stocke le fichier et retourne
        les champs mappés pour préremplir le formulaire de modification.
        """
        doc = await require_demande(demande_id, user)
        data = await file.read()
        filename = file.filename or "offre.pdf"
        from io import BytesIO
        from starlette.datastructures import Headers, UploadFile as StarletteUploadFile

        bio = BytesIO(data)
        upload = StarletteUploadFile(
            file=bio,
            filename=filename,
            headers=Headers({"content-type": file.content_type or "application/pdf"}),
        )
        stored = await store_doc(demande_id, upload, user, category="Modification PDF")
        fields: dict = {}
        form_payload: dict = {}
        extracted_ui: dict = {}
        if data:
            try:
                from offre_extract import extract_offre_fields, map_extract_to_form, offre_fields_for_storage

                raw = extract_offre_fields(data, filename=filename)
                mapped = map_extract_to_form(raw, form_type=doc.get("form_type") or "pilier3_legacy")
                fields = mapped.get("fields") or {}
                form_payload = mapped.get("form_payload") or {}
                storage = offre_fields_for_storage(raw)
                oe = (storage or {}).get("offre_extract") or {}
                extracted_ui = {
                    k: v for k, v in {
                        "compagnie": oe.get("compagnie_label") or oe.get("compagnie"),
                        "rente_mensuelle_garantie": oe.get("rente_mensuelle_garantie_label"),
                        "montant_investi": oe.get("montant_investi_label"),
                        "duree": oe.get("duree_label"),
                        "prenom": oe.get("prenom"),
                        "nom": oe.get("nom"),
                        "date_naissance": oe.get("date_naissance"),
                        "adresse": oe.get("adresse"),
                        "npa": oe.get("npa"),
                        "ville": oe.get("ville"),
                        "reference_police": oe.get("reference_police"),
                        "montant_prime": oe.get("montant_prime"),
                        "date_debut": oe.get("date_debut"),
                        "date_fin": oe.get("date_fin"),
                        "numero_offre": oe.get("numero_offre"),
                    }.items()
                    if v not in (None, "", "Non indiqué")
                }
            except Exception:
                logger.exception("PDF extract for modification failed")
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {"updated_at": now_iso()},
                "$push": {
                    "historique": history(
                        "PDF importé pour modification",
                        user,
                        detail=filename,
                        document_id=stored.get("id") if stored else None,
                        meta={"extracted": extracted_ui},
                    )
                },
            },
        )
        return {
            "document": stored,
            "extracted": extracted_ui,
            "fields": fields,
            "form_payload": form_payload,
            "numero": doc.get("numero"),
            "email_subject": doc.get("email_subject") or "",
            "form_type": doc.get("form_type"),
            "hint": "Formulaire prérempli depuis le PDF. Vérifiez puis modifiez uniquement le nécessaire.",
        }

    @api_router.delete("/demandes-offres/{demande_id}")
    async def delete_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        statut = normalize_statut(doc.get("statut"))
        if statut not in {STATUT_BROUILLON, STATUT_ANNULEE}:
            raise HTTPException(
                status_code=409,
                detail="Seuls les brouillons (ou demandes annulées) peuvent être supprimés",
            )
        at = now_iso()
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": at,
                    "deleted_by": user.account_id,
                    "updated_at": at,
                },
                "$push": {"historique": history("Demande supprimée", user)},
            },
        )
        await db[COLLECTION_DOCS].update_many(
            {"demande_id": demande_id, "user_id": TENANT_USER_ID},
            {"$set": {"is_deleted": True, "deleted_at": at}},
        )
        return {"ok": True}

    @api_router.get("/demandes-offres/documents/{doc_id}/download")
    async def download_demande_document(
        doc_id: str,
        user: User = Depends(current_user_dependency),
    ):
        record = await db[COLLECTION_DOCS].find_one(
            {
                "id": doc_id,
                "user_id": TENANT_USER_ID,
                "is_deleted": {"$ne": True},
            },
            {"_id": 0},
        )
        if not record:
            raise HTTPException(status_code=404, detail="Document introuvable")
        await require_demande(record.get("demande_id") or "", user)
        try:
            data = await maybe_await(load_storage_bytes(record["storage_path"]))
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Fichier introuvable") from exc
        return Response(
            content=data,
            media_type=record.get("content_type") or "application/octet-stream",
            headers=file_response_headers(
                download_name(record, fallback="document"),
                inline=False,
            ),
        )

    @api_router.delete("/demandes-offres/documents/{doc_id}")
    async def delete_demande_document(
        doc_id: str,
        user: User = Depends(current_user_dependency),
    ):
        record = await db[COLLECTION_DOCS].find_one(
            {
                "id": doc_id,
                "user_id": TENANT_USER_ID,
                "is_deleted": {"$ne": True},
            },
            {"_id": 0},
        )
        if not record:
            raise HTTPException(status_code=404, detail="Document introuvable")
        await require_demande(record.get("demande_id") or "", user)
        await db[COLLECTION_DOCS].update_one(
            {"id": doc_id, "user_id": TENANT_USER_ID},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now_iso(),
                    "deleted_by": user.account_id,
                }
            },
        )
        return {"ok": True}

    @api_router.post("/demandes-offres/{demande_id}/documents")
    async def upload_demande_document(
        demande_id: str,
        file: UploadFile = File(...),
        category: str = Form("Pièce jointe"),
        user: User = Depends(current_user_dependency),
    ):
        await require_demande(demande_id, user)
        normalized_category = category.strip() or "Pièce jointe"
        if normalized_category.lower() not in {
            "pièce jointe",
            "piece jointe",
            "pièces jointes",
            "pieces jointes",
            "mandat",
        }:
            raise HTTPException(status_code=422, detail="Catégorie de document invalide")
        stored = await store_doc(
            demande_id,
            file,
            user,
            category="Mandat" if normalized_category.lower() == "mandat" else "Pièce jointe",
        )
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {"updated_at": now_iso()},
                "$push": {
                    "historique": history(
                        "Document ajouté",
                        user,
                        stored.get("original_filename") or "",
                    )
                },
            },
        )
        return stored
