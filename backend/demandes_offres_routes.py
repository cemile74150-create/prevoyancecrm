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
    has_perm,
    require_admin,
    require_perm,
    resolve_session_user,
    PERM_DEMANDES_OFFRES_EDIT,
    PERM_DEMANDES_OFFRES_PROCESS,
    PERM_USERS_MANAGE,
)
from complements_offres import (
    CATEGORY_COMPLEMENT,
    CATEGORY_NOTE_EXTERNE,
    MAX_NOTE_FILES,
    REPLY_ERROR_HTTP,
    creator_account_ids,
    new_complement,
    public_document_refs,
    reply_claim_filter,
    reply_document_ids,
    user_can_answer_complement,
    validate_reply,
)
from demandes_offres_3p import *

try:
    from access_control import get_current_user as _shared_get_current_user
except ImportError:
    _shared_get_current_user = None


logger = logging.getLogger(__name__)


_GESTION_WRITE_ROUTES = (
    (("POST",), re.compile(
        r"^/demandes-offres/([^/]+)/(incomplete|compagnie-incomplete|compagnie-incomplete-annuler|"
        r"complete|offres-completes|offre|notes-internes|notes-externes|erreurs|soumis-compagnie|"
        r"demande-annulee|conclusion|suivi|documents)$"
    )),
    (("POST",), re.compile(r"^/demandes-offres/([^/]+)/complements/[^/]+/cloturer$")),
    (("POST",), re.compile(r"^/demandes-offres/([^/]+)/documents/[^/]+/confirmer-retour$")),
    (("POST", "DELETE"), re.compile(r"^/demandes-offres/([^/]+)/offres/[^/]+/documents(/[^/]+)?$")),
    (("DELETE",), re.compile(r"^/demandes-offres/([^/]+)/erreurs/[^/]+$")),
)
_GESTION_WRITE_EXCLUDED_IDS = {"modifier", "documents", "parametres-urgence", "stats", "pilotage", "gestionnaires"}


def gestion_write_target(method: str, path: str) -> Optional[str]:
    """Identifiant de la demande visée par une action de traitement, sinon None."""
    from access_control import _normalize_api_path

    normalized = _normalize_api_path(path)
    verb = (method or "").upper()
    for methods, pattern in _GESTION_WRITE_ROUTES:
        if verb not in methods:
            continue
        match = pattern.match(normalized)
        if match and match.group(1) not in _GESTION_WRITE_EXCLUDED_IDS:
            return match.group(1)
    return None


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
    agent_account_id: Optional[str] = None
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
    heure_rdv: Optional[str] = None
    urgente: Optional[bool] = None
    urgence_motif: Optional[str] = None
    urgence_exception: Optional[bool] = None
    langue_offre: Optional[str] = None
    mandat_gestion: Optional[bool] = None
    mandat_debut: Optional[str] = None
    mandat_fin: Optional[str] = None
    form_type: Optional[str] = None
    form_payload: Optional[dict[str, Any]] = None
    client_id: Optional[str] = None
    type_client: Optional[str] = None
    demande_origine: Optional[str] = None
    note_service_offre: Optional[str] = None


class SuiviDemandeRequest(BaseModel):
    etape: str
    commentaire: Optional[str] = None
    compagnie: Optional[str] = None


class ReattributionRequest(BaseModel):
    gestionnaire_id: str = Field(..., min_length=1)
    motif: Optional[str] = Field(None, max_length=500)


class UrgenceSettingsRequest(BaseModel):
    quota_actif: bool = False
    max_par_agent: int = 5
    periode: str = "mois"


class UrgenceExceptionRequest(BaseModel):
    agent_label: str


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


class UrgenceRequest(BaseModel):
    urgente: bool = False
    motif: str = ""
    delai_24h: bool = False


class OffresCompletesRequest(BaseModel):
    """Note optionnelle destinée à l'agent (e-mail Offres complètes)."""
    message_conseiller: Optional[str] = None
    note: Optional[str] = None


class ErreursAgentRequest(BaseModel):
    """Multi-sélection de champs en erreur, rattachés à l'agent créateur."""
    fields: list[Any] = Field(min_length=1)
    error_type: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("fields", mode="before")
    @classmethod
    def _fields_as_list(cls, value: Any) -> Any:
        return _coerce_to_list(value) or []


class SignatureRequest(BaseModel):
    signee: bool
    date_signature: Optional[str] = None
    commentaire: Optional[str] = None
    date_relance: Optional[str] = None


class SoumisCompagnieRequest(BaseModel):
    soumis: bool = True


class DemandeAnnuleeRequest(BaseModel):
    """Case gestionnaire « Demande annulée » — distincte de l'annulation d'offre."""
    annulee: bool = True


class AnnulationRequest(BaseModel):
    commentaire: Optional[str] = None


class OffreNonSigneeRequest(BaseModel):
    """Motif obligatoire lorsque le gestionnaire marque l'offre non signée."""
    commentaire: str = ""


class ModificationRequest(BaseModel):
    form_payload: Optional[dict[str, Any]] = None
    fields: Optional[dict[str, Any]] = None
    form_type: Optional[str] = None
    form_type_label: Optional[str] = None
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
    locked_statuses = {
        STATUT_OFFRE_SIGNEE,
        STATUT_ANNULEE,
        STATUT_DEMANDE_ANNULEE_CODE,
        STATUT_OFFRE_NON_SIGNEE,
    }

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
        await guard_dossier_collegue(user, request.method, request.url.path)
        return user

    async def guard_dossier_collegue(user: User, method: str, path: str) -> None:
        """Un gestionnaire ne modifie pas le dossier attribué à un collègue."""
        from demandes_offres_pilotage import refus_ecriture_gestion

        demande_id = gestion_write_target(method, path)
        if not demande_id or not can_process_offres(user):
            return
        doc = await db[COLLECTION].find_one(
            {"id": demande_id, "user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "gestionnaire_id": 1, "gestionnaire_nom": 1,
             "created_by_account_id": 1, "agent_label": 1, "agent_email": 1},
        )
        motif = refus_ecriture_gestion(doc or {}, user)
        if motif:
            raise HTTPException(status_code=403, detail=motif)

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

    async def identity_from_account_id(account_id: Optional[str]) -> Optional[dict]:
        """Profil utilisateur (prénom, nom, e-mail, FINMA) pour un account_id."""
        from offre_agent_identity import agent_identity_from_user

        aid = (account_id or "").strip()
        if not aid:
            return None
        row = await db.users.find_one(
            {"$or": [{"user_id": aid}, {"account_id": aid}]},
            {
                "_id": 0,
                "user_id": 1,
                "account_id": 1,
                "prenom": 1,
                "nom": 1,
                "name": 1,
                "email": 1,
                "finma_number": 1,
                "conseiller": 1,
            },
        )
        if not row:
            return None
        ident = agent_identity_from_user(row)
        ident["account_id"] = str(row.get("account_id") or row.get("user_id") or aid).strip()
        return ident

    async def creator_identity_from_demande(doc: dict) -> Optional[dict]:
        """Profil du créateur, ou de l'agent déjà attribué par un admin."""
        assigned = (doc.get("agent_account_id") or "").strip()
        if assigned:
            ident = await identity_from_account_id(assigned)
            if ident:
                return ident
        return await identity_from_account_id(
            doc.get("created_by_account_id") or doc.get("created_by")
        )

    async def stamp_agent_identity(doc: dict, user: User) -> dict:
        """
        Force l'identité AGENT DEMANDEUR du créateur.
        Un admin / gestionnaire qui ouvre la fiche ne devient pas l'agent.
        """
        from offre_agent_identity import (
            apply_agent_identity_to_doc,
            resolve_agent_identity_for_write,
        )

        creator_identity = await creator_identity_from_demande(doc)
        identity = resolve_agent_identity_for_write(
            doc, user, creator_identity=creator_identity
        )
        apply_agent_identity_to_doc(doc, identity, overwrite_payload=True)
        return identity

    async def store_doc(
        demande_id: str,
        upload: UploadFile,
        user: User,
        *,
        category: str,
        extra: Optional[dict] = None,
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
        for key, value in (extra or {}).items():
            if key not in {"id", "user_id", "demande_id", "storage_path", "storage_path_legacy"}:
                record[key] = value
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
                MAIL_TYPE_NOTE_EXTERNE,
                MAIL_TYPE_COMPLEMENT_DEMANDE,
                MAIL_TYPE_COMPLEMENT_REPONSE,
                MAIL_TYPE_FIL_DISCUSSION,
                format_demande_incomplete_email,
                format_demande_offre_email,
                format_demande_offre_recap_conseiller_email,
                format_offre_modifiee_email,
                format_offre_recue_email,
                format_offres_completes_email,
                format_note_externe_email,
                format_complement_demande_email,
                format_complement_reponse_email,
                format_fil_discussion_email,
                format_offre_signee_email,
                normalize_message_id,
                office_email_to,
                offre_notify_role,
                offres_email_enabled,
                offres_email_to,
                send_email_async,
                should_remember_offres_thread_message_id,
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
            subject, body_text, body_html = format_offres_completes_email(
                doc, note=note or doc.get("message_conseiller")
            )
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
        elif event_key in {"complement_demande", "complement-demande"}:
            mail_type = MAIL_TYPE_COMPLEMENT_DEMANDE
            subject, body_text, body_html = format_complement_demande_email(
                doc,
                note=note,
                complement_type=doc.get("complement_type"),
                complement_id=doc.get("complement_id"),
            )
            to_addr = to_override or await resolve_demande_creator_email(doc)
            if not to_addr:
                return False, "E-mail du créateur introuvable sur la demande"
        elif event_key in {"complement_reponse", "complement-reponse"}:
            mail_type = MAIL_TYPE_COMPLEMENT_REPONSE
            names = doc.get("complement_document_names")
            subject, body_text, body_html = format_complement_reponse_email(
                doc,
                note=note or doc.get("complement_request_note"),
                reply_text=doc.get("complement_reply_text"),
                author=doc.get("complement_reply_author"),
                complement_type=doc.get("complement_type"),
                complement_id=doc.get("complement_id"),
                document_names=names if isinstance(names, list) else None,
            )
            to_addr = to_override or offres_email_to()
        elif event_key in {"note_externe", "note-externe", "external_note"}:
            mail_type = MAIL_TYPE_NOTE_EXTERNE
            subject, body_text, body_html = format_note_externe_email(doc, note=note)
            to_addr = to_override or await resolve_demande_creator_email(doc)
            if not to_addr:
                return False, "E-mail du créateur introuvable sur la demande"
        elif event_key in {
            "fil_discussion",
            "fil_discussion_agent",
            "fil_discussion_gestionnaire",
            "message",
            "message_agent",
            "message_gestionnaire",
        }:
            mail_type = MAIL_TYPE_FIL_DISCUSSION
            names = doc.get("fil_message_document_names")
            subject, body_text, body_html = format_fil_discussion_email(
                doc,
                note=note,
                author=doc.get("fil_message_author"),
                author_role=doc.get("fil_message_role"),
                document_names=names if isinstance(names, list) else None,
            )
            to_addr = to_override
            if not to_addr:
                return False, "Destinataire du fil introuvable"
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
            in_reply_to: Optional[str] = None,
            references: Optional[str] = None,
            result_out: Optional[dict] = None,
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
                        in_reply_to=in_reply_to,
                        references=references,
                        result_out=result_out,
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
                            in_reply_to=in_reply_to,
                            references=references,
                            result_out=result_out,
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

        thread_message_id = None
        if event_key in {"signee", "signée", "signed"}:
            thread_message_id = await resolve_offres_thread_message_id(doc)
            if not thread_message_id:
                logger.warning(
                    "Offre signée sans Message-ID du mail initial demande=%s — envoi hors fil",
                    doc.get("id"),
                )
        send_meta: dict = {}
        sent, error = await _dispatch(
            dest=to_addr,
            subj=subject,
            text=body_text,
            html_body=body_html,
            mtype=mail_type,
            meta_event=event_key,
            meta_role=offre_notify_role(event_key),
            dest_cc=cc_list or None,
            in_reply_to=thread_message_id,
            references=thread_message_id,
            result_out=send_meta,
        )
        remembered_id = normalize_message_id(send_meta.get("message_id"))
        if should_remember_offres_thread_message_id(
            doc, event=event_key, sent=sent, message_id=remembered_id
        ):
            doc["offres_thread_message_id"] = remembered_id
            demande_id = doc.get("id")
            if demande_id:
                try:
                    await db[COLLECTION].update_one(
                        {"id": demande_id, "user_id": TENANT_USER_ID},
                        {"$set": {
                            "offres_thread_message_id": remembered_id,
                            "updated_at": now_iso(),
                        }},
                    )
                except Exception:
                    logger.exception("persist offres_thread_message_id failed")

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
        complement_id: Optional[str] = None,
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
            if complement_id:
                row["complement_id"] = complement_id
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

    async def resolve_offres_thread_message_id(doc: dict) -> Optional[str]:
        """
        Message-ID du mail initial envoyé à l'équipe Offres.
        D'abord le champ mémorisé sur la demande, sinon le plus ancien journal SMTP réussi.
        """
        from email_service import (
            MAIL_TYPE_DEMANDE_OFFRE,
            normalize_message_id as _norm_mid,
            pick_initial_offres_message_id,
        )

        stored = _norm_mid((doc or {}).get("offres_thread_message_id"))
        if stored:
            return stored
        demande_id = ((doc or {}).get("id") or "").strip()
        if not demande_id:
            return None
        try:
            rows = await db.email_logs.find(
                {
                    "ref_id": demande_id,
                    "type": MAIL_TYPE_DEMANDE_OFFRE,
                    "event": "envoyee",
                    "status": "sent",
                },
                {"_id": 0},
            ).to_list(200)
        except Exception:
            logger.exception("lookup offres thread message id failed")
            return None
        return pick_initial_offres_message_id(rows)

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

    async def resolve_account_email(account_id: Optional[str]) -> Optional[str]:
        """E-mail actif d'un compte (user_id / account_id)."""
        aid = (account_id or "").strip()
        if not aid:
            return None
        u = await db.users.find_one(
            {
                "$or": [{"user_id": aid}, {"account_id": aid}],
                "active": {"$ne": False},
            },
            {"_id": 0, "email": 1},
        )
        email = ((u or {}).get("email") or "").strip()
        return email if "@" in email else None

    async def resolve_fil_discussion_email_to(
        doc: dict,
        *,
        role: str,
        sender: User,
    ) -> list[str]:
        """
        Destinataires e-mail du fil : le premier en « À », les suivants en copie.
        Jamais l'expéditeur, sans doublon.

        - Agent → boîte collective `OFFRES_EMAIL_TO` uniquement.
        - Gestionnaire → créateur / conseiller (même résolution que notes externes).

        Aucune boîte personnelle de gestionnaire (attribué ou process) n'est
        destinataire, ni en « À » ni en copie. La cloche in-app, elle, continue
        de notifier les comptes process et le gestionnaire attribué.
        """
        from email_service import offres_email_to
        from demandes_offres_messages import ROLE_AGENT

        sender_email = ((getattr(sender, "email", None) or "")).strip().lower()
        recipients: list[str] = []

        def _add(addr: Optional[str]) -> None:
            clean = (addr or "").strip()
            if not clean or "@" not in clean:
                return
            low = clean.lower()
            if sender_email and low == sender_email:
                return
            if any(low == existing.lower() for existing in recipients):
                return
            recipients.append(clean)

        if role == ROLE_AGENT:
            _add(offres_email_to())
            return recipients

        _add(await resolve_demande_creator_email(doc))
        return recipients

    @api_router.get("/demandes-offres/modifier/recherche")
    async def recherche_offres_par_nom_client(
        q: str = Query(""),
        limit: int = Query(30, ge=1, le=50),
        user: User = Depends(current_user_dependency),
    ):
        """
        Liste les demandes d'un client par nom / prénom (pas par numéro OFF).
        Lecture seule : aucune demande n'est réécrite.
        """
        require_perm(user, PERM_DEMANDES_OFFRES_EDIT, detail="Permission d'édition des demandes requise")
        query = (q or "").strip()
        if client_name_query_too_short(query):
            raise HTTPException(
                status_code=422,
                detail="Saisissez au moins 2 caractères du nom du client",
            )
        base = demandes_offres_base_query(user, None)
        rows = await db[COLLECTION].find(
            base,
            {
                "_id": 0,
                "id": 1,
                "nom": 1,
                "prenom": 1,
                "client_label": 1,
                "form_type": 1,
                "form_type_label": 1,
                "form_payload": 1,
                "created_at": 1,
                "date_envoi": 1,
                "updated_at": 1,
                "statut": 1,
                "numero": 1,
            },
        ).sort("updated_at", -1).to_list(5000)
        hits = []
        for row in rows:
            if not demande_matches_client_name(row, query):
                continue
            hits.append(modifier_client_search_hit(row))
            if len(hits) >= limit:
                break
        return hits

    @api_router.get("/demandes-offres/modifier/recherche-numero")
    async def recherche_offre_par_numero(
        numero: str = Query(""),
        user: User = Depends(current_user_dependency),
    ):
        """Ouvre une demande déjà dans LeoSoft par son numéro OFF. Lecture seule."""
        require_perm(user, PERM_DEMANDES_OFFRES_EDIT, detail="Permission d'édition des demandes requise")
        normalized = normalize_offre_numero(numero)
        if not normalized:
            raise HTTPException(status_code=422, detail="Saisissez un numéro OFF-AAAA-NNNN")
        doc = await db[COLLECTION].find_one(
            {
                "user_id": TENANT_USER_ID,
                "is_deleted": {"$ne": True},
                "numero": {"$regex": f"^{re.escape(normalized)}$", "$options": "i"},
            },
            {"_id": 0},
        )
        if not doc or not can_access_demande(user, doc):
            raise HTTPException(status_code=404, detail="Aucune demande pour ce numéro OFF")
        await ensure_permanent_subject(doc)
        hit = modifier_client_search_hit(doc)
        hit["email_subject"] = doc.get("email_subject") or ""
        hit["numero"] = doc.get("numero") or normalized
        return hit

    @api_router.post("/demandes-offres/modifier/analyse-pdf")
    async def analyse_pdf_for_modification(
        file: UploadFile = File(...),
        form_type: str = Form("pilier3_legacy"),
        numero: Optional[str] = Form(None),
        user: User = Depends(current_user_dependency),
    ):
        """
        Analyse un PDF d'offre / police et préremplit le formulaire du type choisi.
        Si un numéro OFF (saisi ou lu dans le PDF) correspond à une demande :
        rattacher cette demande, conserver le numéro et l'objet e-mail, ne pas
        en créer une autre. Sans numéro OFF : préremplissage hors LeoSoft.
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
        lu_dans_pdf = mapped.get("numero_offre") or raw.get("numero_offre") or ""
        candidate = (numero or "").strip() or lu_dans_pdf
        numero_detecte = normalize_offre_numero(lu_dans_pdf) or normalize_offre_numero(candidate)
        pool: list = []
        normalized = normalize_offre_numero(candidate)
        if normalized:
            doc = await db[COLLECTION].find_one(
                {
                    "user_id": TENANT_USER_ID,
                    "is_deleted": {"$ne": True},
                    "numero": {"$regex": f"^{re.escape(normalized)}$", "$options": "i"},
                },
                {"_id": 0},
            )
            if doc and can_access_demande(user, doc):
                await ensure_permanent_subject(doc)
                pool = [doc]
        decision = resolve_pdf_offre_target(pool, candidate)
        matched = decision.get("demande") if decision.get("action") == "rattacher" else None

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
            "profession": raw.get("profession"),
            "email": raw.get("email"),
            "telephone": raw.get("telephone"),
            "nationalite": raw.get("nationalite"),
            "periodicite": raw.get("periodicite"),
            "type_pilier": raw.get("type_pilier"),
        }
        extracted_ui = {k: v for k, v in labels.items() if v not in (None, "", "Non indiqué")}

        action = decision.get("action") or "creer"
        if action == "rattacher":
            hint = "PDF rattaché à la demande existante. Le numéro OFF et l'objet e-mail sont conservés."
        elif action == "refus":
            hint = "Ce numéro OFF ne correspond à aucune demande. Aucune nouvelle demande n'est créée."
        else:
            hint = "Formulaire prérempli depuis le PDF. Aucun numéro OFF : l'envoi crée une nouvelle demande."
        return {
            "form_type": form_type,
            "filename": filename,
            "action": action,
            "numero": (matched or {}).get("numero") if matched else (decision.get("numero") if action == "refus" else None),
            "numero_detecte": numero_detecte or None,
            "email_subject": (matched or {}).get("email_subject") or "",
            "demande": matched,
            "fields": fields,
            "form_payload": form_payload,
            "filled_keys": mapped.get("filled_keys") or [],
            "extracted": extracted_ui,
            "reference_police": mapped.get("reference_police") or raw.get("reference_police"),
            "hint": hint,
        }

    @api_router.get("/demandes-offres/meta")
    async def demandes_offres_meta(user: User = Depends(current_user_dependency)):
        from offre_form_types import list_form_types, load_form_menu, referentiel_compagnies

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
            "compagnies_referentiel": referentiel_compagnies(COMPAGNIES_DEFAUT),
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
            "erreurs_champs_catalog": ERREURS_CHAMPS_CATALOG,
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

    def perimetre_code(perimetre: Optional[str]) -> Optional[str]:
        code = (perimetre or "").strip().lower()
        return code if code in {"personnel", "equipe"} else None

    def pilotage_scope_clauses(user: User, perimetre: Optional[str], gestionnaire: Optional[str]) -> list[dict]:
        """Périmètres « personnel » (mes dossiers) et « equipe » (dossiers attribués, lecture seule).

        « equipe » est ouvert aux gestionnaires d'offres, comme « personnel » :
        il ne retient que les dossiers attribués, éventuellement à un seul
        gestionnaire. Les écritures sur le dossier d'un collègue restent
        refusées par ``refus_ecriture_gestion``.
        """
        from demandes_offres_pilotage import NON_ATTRIBUE_ID, attribuee_filter, non_attribuee_filter

        clauses: list[dict] = []
        code = perimetre_code(perimetre)
        if code:
            require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        if code == "personnel":
            clauses.append({"gestionnaire_id": str(user.account_id or "")})
        elif code == "equipe":
            clauses.append(attribuee_filter())
        wanted = (gestionnaire or "").strip()
        if wanted and wanted != "all":
            clauses.append(non_attribuee_filter() if wanted == NON_ATTRIBUE_ID else {"gestionnaire_id": wanted})
        return clauses

    def scoped_query(base: dict, clauses: list[dict]) -> dict:
        return {"$and": [base, *clauses]} if clauses else base

    async def gestionnaires_habilites() -> list[dict]:
        """Comptes actifs ayant accès à « Gestionnaire d'offres »."""
        from access_control import user_from_doc

        users = await db.users.find(
            {"active": {"$ne": False}},
            {"_id": 0, "password_hash": 0, "password": 0},
        ).to_list(500)
        out = []
        for row in users:
            try:
                account = user_from_doc(row)
            except Exception:
                continue
            if not can_process_offres(account):
                continue
            out.append({
                "id": str(account.account_id or ""),
                "nom": actor_name(account) or str(row.get("email") or ""),
                "role": getattr(account, "role", None),
            })
        return sorted([g for g in out if g["id"]], key=lambda g: g["nom"].casefold())

    @api_router.get("/demandes-offres/stats")
    async def demandes_offres_stats(
        conseiller: Optional[str] = Query(None),
        periode: Optional[str] = Query("all"),
        date_de: Optional[str] = Query(None),
        date_a: Optional[str] = Query(None),
        perimetre: Optional[str] = Query(None),
        gestionnaire: Optional[str] = Query(None),
        user: User = Depends(current_user_dependency),
    ):
        query = scoped_query(
            demandes_offres_base_query(user, conseiller),
            pilotage_scope_clauses(user, perimetre, gestionnaire),
        )
        rows = await db[COLLECTION].find(query, {"_id": 0}).to_list(10000)
        rows, period_meta = filter_rows_by_period(
            rows, periode=periode, date_de=date_de, date_a=date_a
        )
        if perimetre_code(perimetre) == "equipe":
            from demandes_offres_pilotage import dans_pilotage

            rows = [row for row in rows if dans_pilotage(row)]
        result = compute_stats(rows, period_meta=period_meta)
        result["perimetre"] = perimetre_code(perimetre) or "global"
        return result

    @api_router.get("/demandes-offres/pilotage")
    async def demandes_offres_pilotage(
        perimetre: Optional[str] = Query("global"),
        conseiller: Optional[str] = Query(None),
        gestionnaire: Optional[str] = Query(None),
        form_type: Optional[str] = Query(None),
        compagnie: Optional[str] = Query(None),
        periode: Optional[str] = Query("all"),
        date_de: Optional[str] = Query(None),
        date_a: Optional[str] = Query(None),
        user: User = Depends(current_user_dependency),
    ):
        """Indicateurs du service (global), du gestionnaire connecté (personnel)
        ou des dossiers attribués à l'équipe (equipe, filtre ``gestionnaire``).

        Même calcul (compute_pilotage) pour tous les périmètres. Un agent ne
        voit que ses propres demandes, via la requête de base habituelle.
        """
        from demandes_offres_pilotage import compute_pilotage, peut_reattribuer, peut_sattribuer

        code = perimetre_code(perimetre)
        personnel = code == "personnel"
        clauses = pilotage_scope_clauses(user, code, gestionnaire)
        if form_type and form_type != "all":
            clauses.append({"form_type": form_type})
        if compagnie and compagnie != "all":
            cie_match = {"$regex": f"^{re.escape(compagnie.strip())}$", "$options": "i"}
            clauses.append({"$or": [
                {"compagnies": cie_match},
                {"offre.compagnie": cie_match},
                {"offres.compagnie": cie_match},
            ]})
        query = scoped_query(demandes_offres_base_query(user, conseiller), clauses)
        rows = await db[COLLECTION].find(query, {"_id": 0}).to_list(10000)
        rows, period_meta = filter_rows_by_period(rows, periode=periode, date_de=date_de, date_a=date_a)
        global_view = can_view_all_offres(user)
        from access_control import ROLE_GESTIONNAIRE_OFFRES

        gestionnaires = (
            [g for g in await gestionnaires_habilites() if g.get("role") == ROLE_GESTIONNAIRE_OFFRES]
            if global_view and not personnel
            else []
        )
        result = compute_pilotage(rows, gestionnaires=gestionnaires)
        if not global_view or personnel:
            result["gestionnaires"] = []
        result["perimetre"] = code or ("global" if global_view else "agent")
        result["periode"] = period_meta
        result["viewer"] = {
            "account_id": user.account_id,
            "nom": actor_name(user),
            "can_attribuer": peut_sattribuer(user),
            "can_reattribuer": peut_reattribuer(user),
        }
        return result

    @api_router.get("/demandes-offres/pilotage/mensuel")
    async def demandes_offres_pilotage_mensuel(
        mois: int = Query(6),
        perimetre: Optional[str] = Query("global"),
        conseiller: Optional[str] = Query(None),
        gestionnaire: Optional[str] = Query(None),
        form_type: Optional[str] = Query(None),
        compagnie: Optional[str] = Query(None),
        periode: Optional[str] = Query("all"),
        date_de: Optional[str] = Query(None),
        date_a: Optional[str] = Query(None),
        user: User = Depends(current_user_dependency),
    ):
        """Offres reçues / signées / non signées par mois, sur le périmètre du pilotage.

        La période du tableau de bord borne la date de chaque événement, pas la
        date de création : une demande créée avant la période mais signée
        pendant celle-ci est comptée dans « Offres signées ».
        """
        from demandes_offres_3p import period_bounds
        from demandes_offres_pilotage import compute_stats_mensuelles

        code = perimetre_code(perimetre)
        clauses = pilotage_scope_clauses(user, code, gestionnaire)
        if form_type and form_type != "all":
            clauses.append({"form_type": form_type})
        if compagnie and compagnie != "all":
            cie_match = {"$regex": f"^{re.escape(compagnie.strip())}$", "$options": "i"}
            clauses.append({"$or": [
                {"compagnies": cie_match},
                {"offre.compagnie": cie_match},
                {"offres.compagnie": cie_match},
            ]})
        query = scoped_query(demandes_offres_base_query(user, conseiller), clauses)
        rows = await db[COLLECTION].find(query, {"_id": 0}).to_list(10000)
        try:
            debut, fin, norm = period_bounds(periode, date_de, date_a)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Dates de période invalides") from exc
        result = compute_stats_mensuelles(rows, nb_mois=mois, debut=debut, fin=fin)
        result["periode"] = {"periode": norm, "debut": debut, "fin": fin}
        result["perimetre"] = code or ("global" if can_view_all_offres(user) else "agent")
        return result

    @api_router.get("/demandes-offres/gestionnaires")
    async def list_gestionnaires_offres(user: User = Depends(current_user_dependency)):
        if not can_view_all_offres(user):
            raise HTTPException(status_code=403, detail="Réservé au service des offres")
        return await gestionnaires_habilites()

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
        demande_ids = [r.get("id") for r in rows if r.get("id")]
        error_records: list = []
        if demande_ids:
            error_records = await db[COLLECTION_ERREURS].find(
                {"user_id": TENANT_USER_ID, "demande_id": {"$in": demande_ids}},
                {"_id": 0},
            ).to_list(50000)
        stats = compute_erreur_stats(rows, error_records=error_records)
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

    @api_router.get("/demandes-offres/stats/erreurs-agent")
    async def demandes_offres_stats_erreurs_agent(
        agent_id: Optional[str] = Query(None),
        conseiller: Optional[str] = Query(None),
        periode: Optional[str] = Query("all"),
        date_de: Optional[str] = Query(None),
        date_a: Optional[str] = Query(None),
        user: User = Depends(current_user_dependency),
    ):
        """
        Comptabilisation des erreurs champ (bouton Erreurs) par agent.
        Gestionnaire : tous / filtre. Agent : uniquement ses erreurs.
        """
        query: dict = {"user_id": TENANT_USER_ID}
        if can_process_offres(user) or can_view_all_offres(user):
            if agent_id:
                query["agent_id"] = agent_id
            elif conseiller and conseiller != "all":
                import re as _re
                query["agent_label"] = {
                    "$regex": f"^{_re.escape(conseiller.strip())}$",
                    "$options": "i",
                }
        else:
            query["$or"] = [
                {"agent_id": user.account_id},
                {"created_by_account_id": user.account_id},
            ]
        rows = await db[COLLECTION_ERREURS].find(query, {"_id": 0}).to_list(20000)
        # Filtre période sur le champ date / at
        if periode and periode != "all":
            start, end, _ = period_bounds(periode=periode, date_de=date_de, date_a=date_a)
            filtered = []
            for r in rows:
                stamp = (r.get("at") or r.get("date") or "")[:19]
                if start and stamp < start[:19]:
                    continue
                if end and stamp >= end[:19]:
                    continue
                filtered.append(r)
            rows = filtered
        stats = compute_erreurs_agent_stats(rows)
        stats["periode"] = {"periode": periode, "date_de": date_de, "date_a": date_a}
        stats["scoped"] = not (can_process_offres(user) or can_view_all_offres(user))
        return stats

    @api_router.get("/demandes-offres/{demande_id}/erreurs-checklist")
    async def get_erreurs_checklist(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        return {
            "catalog": ERREURS_CHAMPS_CATALOG,
            "items": build_erreurs_checklist(doc),
        }

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
        tri: Optional[str] = Query(None),
        urgente: Optional[bool] = Query(None),
        rdv_a_venir: Optional[bool] = Query(None),
        perimetre: Optional[str] = Query(None),
        gestionnaire: Optional[str] = Query(None),
        statut_traitement: Optional[str] = Query(None),
        statut_commercial: Optional[str] = Query(None),
        indicateur: Optional[str] = Query(None),
        limit: int = Query(200, ge=1, le=1000),
        user: User = Depends(current_user_dependency),
    ):
        from demandes_offres_pilotage import filtrer_lignes

        query = demandes_offres_base_query(user, conseiller)
        clauses: list[dict] = pilotage_scope_clauses(user, perimetre, gestionnaire)
        cat = (categorie or "").strip()
        if cat == "attribuees":
            clauses.append({"demande_origine": DEMANDE_ORIGINE_ATTRIBUEE})
        elif cat == "en_retard":
            pass  # filtré après
        elif cat and cat in GESTION_CATEGORIES and GESTION_CATEGORIES[cat].get("statuts"):
            clauses.append({"statut": {"$in": list(GESTION_CATEGORIES[cat]["statuts"])}})
        elif statut and statut != "all":
            clauses.append({"statut": {"$in": statut_match_values(statut)}})
        origine = (demande_origine or "").strip().lower()
        if origine in {DEMANDE_ORIGINE_CONSEILLER, DEMANDE_ORIGINE_ATTRIBUEE}:
            clauses.append({"demande_origine": origine})
        if type_pilier and type_pilier != "all":
            clauses.append({"type_pilier": type_pilier})
        if form_type and form_type != "all":
            clauses.append({"form_type": form_type})
        if compagnie and compagnie != "all":
            cie = re.escape(compagnie.strip())
            cie_match = {"$regex": f"^{cie}$", "$options": "i"}
            clauses.append(
                {
                    "$or": [
                        {"compagnies": cie_match},
                        {"offre.compagnie": cie_match},
                        {"offres.compagnie": cie_match},
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
        from demandes_offres_ameliorations import (
            filter_rdv_a_venir,
            filter_urgente,
            sort_demandes,
            urgentes_en_tete,
        )

        if urgente is True:
            rows = filter_urgente(rows, True)
        if rdv_a_venir is True:
            rows = filter_rdv_a_venir(rows, True)
        if (gestionnaire or "").strip() not in {"", "all"} or perimetre_code(perimetre) == "equipe":
            from demandes_offres_pilotage import dans_pilotage

            rows = [row for row in rows if dans_pilotage(row)]
        rows = filtrer_lignes(
            rows,
            tag=indicateur,
            statut_traitement=statut_traitement,
            statut_commercial=statut_commercial,
        )
        rows = urgentes_en_tete(sort_demandes(rows, tri))
        rows = rows[:limit]
        return [serialize_demande(row, viewer=user) for row in rows]

    @api_router.get("/demandes-offres/parametres-urgence")
    async def get_urgence_settings(user: User = Depends(current_user_dependency)):
        require_admin(user)
        from demandes_offres_ameliorations import DEFAULT_URGENCE_SETTINGS, usages_urgences

        stored = await db["crm_settings"].find_one({"id": "offres_urgence"}, {"_id": 0}) or {}
        settings = {
            **DEFAULT_URGENCE_SETTINGS,
            "quota_actif": bool(stored.get("quota_actif", DEFAULT_URGENCE_SETTINGS["quota_actif"])),
            "max_par_agent": int(stored.get("max_par_agent", DEFAULT_URGENCE_SETTINGS["max_par_agent"])),
            "periode": stored.get("periode") if stored.get("periode") in {"mois", "annee"} else "mois",
            "bonus_par_agent": stored.get("bonus_par_agent") or [],
            "updated_at": stored.get("updated_at"),
            "updated_by": stored.get("updated_by") or "",
        }
        rows = await db[COLLECTION].find(
            {"user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}},
            {
                "_id": 0, "agent_label": 1, "urgente": 1, "statut": 1,
                "urgence_at": 1, "date_envoi": 1, "created_at": 1, "is_deleted": 1,
            },
        ).to_list(8000)
        settings["usages"] = usages_urgences(rows, settings)
        return settings

    @api_router.put("/demandes-offres/parametres-urgence")
    async def put_urgence_settings(
        payload: UrgenceSettingsRequest,
        user: User = Depends(current_user_dependency),
    ):
        require_admin(user)
        periode = payload.periode if payload.periode in {"mois", "annee"} else "mois"
        await db["crm_settings"].update_one(
            {"id": "offres_urgence"},
            {"$set": {
                "id": "offres_urgence",
                "quota_actif": bool(payload.quota_actif),
                "max_par_agent": max(0, int(payload.max_par_agent)),
                "periode": periode,
                "updated_at": now_iso(),
                "updated_by": actor_name(user),
            }},
            upsert=True,
        )
        return await get_urgence_settings(user)

    @api_router.post("/demandes-offres/parametres-urgence/exception")
    async def grant_urgence_exception(
        payload: UrgenceExceptionRequest,
        user: User = Depends(current_user_dependency),
    ):
        require_admin(user)
        from demandes_offres_ameliorations import grant_agent_bonus

        stored = await db["crm_settings"].find_one({"id": "offres_urgence"}, {"_id": 0}) or {}
        try:
            bonus = grant_agent_bonus(stored, payload.agent_label)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await db["crm_settings"].update_one(
            {"id": "offres_urgence"},
            {"$set": {
                "id": "offres_urgence",
                "bonus_par_agent": bonus,
                "updated_at": now_iso(),
                "updated_by": actor_name(user),
            }},
            upsert=True,
        )
        return await get_urgence_settings(user)

    @api_router.get("/demandes-offres/{demande_id}/stats-agent")
    async def demande_agent_stats(demande_id: str, user: User = Depends(current_user_dependency)):
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        from demandes_offres_ameliorations import fiche_stats_agent

        label = doc.get("agent_label") or ""
        rows = await db[COLLECTION].find(
            {"user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}},
            {"_id": 0, "statut": 1, "agent_label": 1, "is_deleted": 1, "compagnies": 1, "offres": 1, "form_type": 1, "form_category": 1},
        ).to_list(8000)
        same = [
            row for row in rows
            if str(row.get("agent_label") or "").strip().casefold() == str(label).strip().casefold()
        ]
        return fiche_stats_agent(same, label)

    async def persist_suivi(
        doc: dict,
        etape: str,
        user: User,
        commentaire: str = "",
        compagnie: str = "",
        auto: bool = False,
    ) -> None:
        from demandes_offres_ameliorations import ETAPE_OFFRES_PARTIELLES, enregistrer_suivi

        try:
            patch = enregistrer_suivi(
                doc,
                etape,
                auteur=actor_name(user),
                auteur_id=str(user.account_id or ""),
                commentaire=commentaire,
                compagnie=compagnie,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        event = patch["dernier_evenement"]
        previous = event.get("etape_precedente_label") or "—"
        parts = [f"{previous} → {event.get('label') or ''}"]
        suivi_set = {
            "suivi_etape": patch["suivi_etape"],
            "suivi_auto": bool(doc.get("suivi_auto")) if etape == "relance" else bool(auto),
            "updated_at": now_iso(),
        }
        if event.get("etape") in {"offre_transmise", ETAPE_OFFRES_PARTIELLES} and not (doc.get("offre_transmise_agent_at") or ""):
            suivi_set["offre_transmise_agent_at"] = event.get("at") or now_iso()
        if event.get("etape") == "offre_transmise" and not (doc.get("offres_transmises_agent_at") or ""):
            suivi_set["offres_transmises_agent_at"] = event.get("at") or now_iso()
        if event.get("compagnie"):
            parts.append(event["compagnie"])
        if event.get("commentaire"):
            parts.append(event["commentaire"])
        await db[COLLECTION].update_one(
            {"id": doc.get("id"), "user_id": TENANT_USER_ID},
            {
                "$set": suivi_set,
                "$push": {
                    "suivi_evenements": event,
                    "historique": history(
                        event["label"],
                        user,
                        " · ".join(parts),
                        statut=doc.get("statut"),
                        meta={
                            "suivi": True,
                            "etape": event.get("etape") or "",
                            "etape_precedente": event.get("etape_precedente") or "",
                            "etape_precedente_label": previous,
                            "compagnie": event.get("compagnie") or "",
                        },
                    ),
                },
            },
        )

    async def stamp_mise_a_disposition(demande_id: str) -> None:
        """Première mise à disposition des documents à l'agent : posée une fois, jamais déplacée."""
        await db[COLLECTION].update_one(
            {
                "id": demande_id,
                "user_id": TENANT_USER_ID,
                "$or": [
                    {"docs_mis_a_disposition_at": {"$exists": False}},
                    {"docs_mis_a_disposition_at": None},
                    {"docs_mis_a_disposition_at": ""},
                ],
            },
            {"$set": {"docs_mis_a_disposition_at": now_iso()}},
        )

    async def apply_transmission_suivi(doc: dict, user: User, compagnie: str) -> bool:
        """Aligne l'avancement sur les compagnies transmises. Vrai si la demande a changé.

        Une issue du workflow (envoyée au client, signée, annulée…) n'est jamais écrasée.
        """
        from demandes_offres_ameliorations import (
            ETAPE_OFFRES_PARTIELLES,
            etape_affichee,
            etape_transmission_cible,
        )

        cible = etape_transmission_cible(doc)
        if not cible:
            return False
        current = etape_affichee(doc)
        if current in {"envoyee_client", "signee", "annulee", "refusee", "non_signee"}:
            return False
        if current != cible or (doc.get("suivi_auto") and doc.get("suivi_etape") != cible):
            await persist_suivi(doc, cible, user, compagnie=compagnie, auto=True)
            return True
        if doc.get("suivi_etape") in {"offre_transmise", ETAPE_OFFRES_PARTIELLES} and not doc.get("suivi_auto"):
            await db[COLLECTION].update_one(
                {"id": doc.get("id"), "user_id": TENANT_USER_ID},
                {"$set": {"suivi_auto": True}},
            )
            return True
        return False

    @api_router.post("/demandes-offres/{demande_id}/suivi")
    async def post_suivi_demande(
        demande_id: str,
        payload: SuiviDemandeRequest,
        user: User = Depends(current_user_dependency),
    ):
        from demandes_offres_ameliorations import SUIVI_PROCESS

        doc = await require_demande(demande_id, user)
        etape = (payload.etape or "").strip()
        if etape not in SUIVI_PROCESS:
            raise HTTPException(status_code=422, detail="Étape de suivi non autorisée")
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        await persist_suivi(
            doc,
            etape,
            user,
            commentaire=payload.commentaire or "",
            compagnie=payload.compagnie or "",
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, viewer=user, docs=await docs_for(demande_id))

    async def enregistrer_attribution(
        doc: dict,
        user: User,
        *,
        cible_id: str,
        cible_nom: str,
        motif: str = "",
    ) -> bool:
        """Écrit le gestionnaire si le dossier n'a pas changé de main entre-temps.

        Le filtre porte sur le gestionnaire lu : deux prises en charge
        simultanées ne peuvent pas réussir toutes les deux.
        """
        from demandes_offres_pilotage import attribution_event, gestionnaire_info, non_attribuee_filter

        current = gestionnaire_info(doc)
        stamp = now_iso()
        par_nom = actor_name(user)
        kind = "reattribution" if current["id"] else (
            "auto_attribution" if cible_id == str(user.account_id or "") else "attribution"
        )
        event = attribution_event(
            kind=kind,
            at=stamp,
            par_id=str(user.account_id or ""),
            par_nom=par_nom,
            ancien_id=current["id"],
            ancien_nom=current["nom"],
            nouveau_id=cible_id,
            nouveau_nom=cible_nom,
            motif=motif,
        )
        filt = {"id": doc.get("id"), "user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}}
        if current["id"]:
            filt["gestionnaire_id"] = current["id"]
        else:
            filt.update(non_attribuee_filter())
        if kind == "reattribution":
            action = "Dossier réattribué"
            detail = f"{current['nom'] or '—'} → {cible_nom}"
        else:
            action = "Dossier attribué"
            detail = f"Pris en charge par {cible_nom}"
        if motif.strip():
            detail = f"{detail} · {motif.strip()}"
        result = await db[COLLECTION].update_one(
            filt,
            {
                "$set": {
                    "gestionnaire_id": cible_id,
                    "gestionnaire_nom": cible_nom,
                    "gestionnaire_attribue_at": stamp,
                    "gestionnaire_attribue_par": par_nom,
                    "updated_at": stamp,
                },
                "$push": {
                    "attributions_historique": event,
                    "historique": history(
                        action,
                        user,
                        detail,
                        statut=doc.get("statut"),
                        meta={"attribution": True, "gestionnaire_id": cible_id, "ancien_gestionnaire_id": current["id"]},
                    ),
                },
            },
        )
        return bool(getattr(result, "modified_count", 0))

    async def apres_attribution(demande_id: str, user: User) -> dict:
        from demandes_offres_pilotage import passe_en_cours_apres_attribution

        fresh = await require_demande(demande_id, user)
        if passe_en_cours_apres_attribution(fresh):
            await persist_suivi(fresh, "en_cours", user, commentaire="Prise en charge du dossier")
            fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, viewer=user, docs=await docs_for(demande_id))

    @api_router.post("/demandes-offres/{demande_id}/attribuer")
    async def attribuer_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        """« M'attribuer » : le gestionnaire connecté prend en charge une demande non attribuée."""
        from demandes_offres_pilotage import dans_pilotage, gestionnaire_info, peut_sattribuer

        if not peut_sattribuer(user):
            raise HTTPException(status_code=403, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        if not dans_pilotage(doc):
            raise HTTPException(status_code=409, detail="Seule une demande soumise peut être attribuée")
        me = str(user.account_id or "")
        current = gestionnaire_info(doc)
        if current["id"] == me:
            return serialize_demande(doc, viewer=user, docs=await docs_for(demande_id))
        if current["id"]:
            raise HTTPException(status_code=409, detail=f"Dossier déjà attribué à {current['nom'] or 'un gestionnaire'}")
        if not await enregistrer_attribution(doc, user, cible_id=me, cible_nom=actor_name(user)):
            fresh = await require_demande(demande_id, user)
            winner = gestionnaire_info(fresh)
            if winner["id"] != me:
                raise HTTPException(
                    status_code=409,
                    detail=f"Dossier déjà attribué à {winner['nom'] or 'un gestionnaire'}",
                )
        return await apres_attribution(demande_id, user)

    @api_router.post("/demandes-offres/{demande_id}/reattribuer")
    async def reattribuer_demande_offre(
        demande_id: str,
        payload: ReattributionRequest,
        user: User = Depends(current_user_dependency),
    ):
        """Transfert vers un autre gestionnaire. Administrateur ou responsable uniquement."""
        from demandes_offres_pilotage import dans_pilotage, gestionnaire_info, peut_reattribuer

        if not peut_reattribuer(user):
            raise HTTPException(status_code=403, detail="Réservé aux administrateurs et responsables")
        doc = await require_demande(demande_id, user)
        if not dans_pilotage(doc):
            raise HTTPException(status_code=409, detail="Seule une demande soumise peut être attribuée")
        target_id = payload.gestionnaire_id.strip()
        cible = next((g for g in await gestionnaires_habilites() if g["id"] == target_id), None)
        if cible is None:
            raise HTTPException(status_code=422, detail="Gestionnaire inconnu ou sans accès à Gestionnaire d'offres")
        if gestionnaire_info(doc)["id"] == target_id:
            return serialize_demande(doc, viewer=user, docs=await docs_for(demande_id))
        if not await enregistrer_attribution(
            doc, user, cible_id=target_id, cible_nom=cible["nom"], motif=payload.motif or ""
        ):
            raise HTTPException(
                status_code=409,
                detail="Le dossier vient d'être attribué par quelqu'un d'autre. Rechargez la page.",
            )
        if target_id != str(user.account_id or ""):
            await write_offre_notification(
                doc=doc,
                event="attribuee_gestionnaire",
                title=f"Dossier attribué — {doc.get('numero') or ''}".strip(),
                message=f"{actor_name(user)} vous a attribué ce dossier.",
                audience="gestionnaires",
                account_ids=[target_id],
            )
        return await apres_attribution(demande_id, user)

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
                "agent_account_id": user.account_id,
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
        from access_control import can_process_offres
        from offre_agent_identity import viewer_is_demande_creator as _viewer_is_creator

        deja_consultee = bool(str(doc.get("gestion_consultee_at") or "").strip())
        brouillon = str(doc.get("statut") or "").strip() == "Brouillon"
        if can_process_offres(user) and not _viewer_is_creator(doc, user) and not deja_consultee and not brouillon:
            stamp = now_iso()
            claimed = await db[COLLECTION].update_one(
                    {
                        "id": demande_id,
                        "user_id": TENANT_USER_ID,
                        "$or": [
                            {"gestion_consultee_at": {"$exists": False}},
                            {"gestion_consultee_at": None},
                            {"gestion_consultee_at": ""},
                        ],
                    },
                    {
                        "$set": {
                            "gestion_vue": True,
                            "gestion_consultee_at": stamp,
                            "gestion_consultee_par": actor_name(user),
                        },
                        "$push": {
                            "historique": history(
                                "Première consultation du dossier",
                                user,
                                "",
                                statut=doc.get("statut"),
                            ),
                        },
                },
            )
            if getattr(claimed, "modified_count", 0) == 1:
                doc["gestion_vue"] = True
                doc["gestion_consultee_at"] = stamp
                doc.setdefault("historique", []).append({"action": "Première consultation du dossier", "at": stamp})
        # Backfill objet permanent pour offres déjà envoyées
        if not (doc.get("email_subject") or "").strip() and (doc.get("date_envoi") or doc.get("numero")):
            try:
                await ensure_permanent_subject(doc)
            except Exception:
                logger.exception("email_subject backfill failed")
        # Overlay identité créateur : un admin qui consulte ne voit pas son nom.
        # Si un viewer a déjà écrasé l'agent (autosave), on restaure le créateur.
        from offre_agent_identity import agent_identity_from_doc, viewer_is_demande_creator

        display = dict(doc)
        fp = doc.get("form_payload")
        if isinstance(fp, dict):
            display["form_payload"] = dict(fp)
        await stamp_agent_identity(display, user)
        if not viewer_is_demande_creator(doc, user):
            from offre_agent_identity import agent_identity_from_user, identities_match

            bound = agent_identity_from_doc(doc)
            viewer_ident = agent_identity_from_user(user)
            if identities_match(bound, viewer_ident):
                await stamp_agent_identity(doc, user)
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
        return serialize_demande(display, docs=await docs_for(demande_id), viewer=user)

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
        can_set_agent = has_perm(user, PERM_USERS_MANAGE)
        assigned_id = ""
        if can_set_agent:
            assigned_id = str(raw_updates.pop("agent_account_id", None) or "").strip()
        else:
            for spoof_key in (
                "agent_prenom", "agent_nom", "agent_email", "agent_finma",
                "agent_label", "agent_account_id",
            ):
                raw_updates.pop(spoof_key, None)

        normalized = dict(current)
        apply_form_fields(normalized, raw_updates)

        from offre_agent_identity import apply_agent_identity_to_doc

        if can_set_agent and assigned_id:
            assigned = await identity_from_account_id(assigned_id)
            if not assigned or not (assigned.get("prenom") or assigned.get("nom") or assigned.get("email")):
                raise HTTPException(status_code=400, detail="Agent demandeur introuvable")
            apply_agent_identity_to_doc(normalized, assigned, overwrite_payload=True)
            normalized["agent_account_id"] = assigned.get("account_id") or assigned_id
            normalized["created_by_account_id"] = normalized["agent_account_id"]
            normalized["created_by_name"] = assigned.get("label") or assigned.get("email") or ""
        elif can_set_agent:
            ident = {
                "prenom": str(normalized.get("agent_prenom") or "").strip(),
                "nom": str(normalized.get("agent_nom") or "").strip(),
                "email": str(normalized.get("agent_email") or "").strip(),
                "finma": str(normalized.get("agent_finma") or "").strip(),
                "label": (
                    str(normalized.get("agent_label") or "").strip()
                    or f"{str(normalized.get('agent_prenom') or '').strip()} {str(normalized.get('agent_nom') or '').strip()}".strip()
                ),
            }
            apply_agent_identity_to_doc(normalized, ident, overwrite_payload=True)
        else:
            await stamp_agent_identity(normalized, user)

        updates: dict[str, Any] = {
            key: normalized.get(key) for key in raw_updates
        }
        # Identité agent : créateur, ou agent choisi par l'admin.
        updates["agent_prenom"] = normalized.get("agent_prenom")
        updates["agent_nom"] = normalized.get("agent_nom")
        updates["agent_email"] = normalized.get("agent_email")
        updates["agent_finma"] = normalized.get("agent_finma")
        updates["agent_label"] = normalized.get("agent_label")
        if can_set_agent and assigned_id:
            updates["agent_account_id"] = normalized.get("agent_account_id")
            updates["created_by_account_id"] = normalized.get("created_by_account_id")
            updates["created_by_name"] = normalized.get("created_by_name")
        elif can_set_agent:
            updates["agent_label"] = normalized.get("agent_label")
        if "form_payload" in raw_updates or isinstance(normalized.get("form_payload"), dict):
            updates["form_payload"] = normalized.get("form_payload")
        if "urgente" in raw_updates or "urgence_motif" in raw_updates or "urgence_exception" in raw_updates:
            updates["urgente"] = bool(normalized.get("urgente"))
            updates["urgence_motif"] = str(normalized.get("urgence_motif") or "").strip()
            if "urgence_exception" in raw_updates:
                if not (has_perm(user, PERM_USERS_MANAGE) or is_global_viewer(user)):
                    raise HTTPException(status_code=403, detail="Exception d'urgence réservée à un administrateur")
                updates["urgence_exception"] = bool(normalized.get("urgence_exception"))
                updates["urgence_exception_by"] = actor_name(user)
                updates["urgence_exception_at"] = now_iso()
            if updates["urgente"] and not current.get("urgente"):
                updates["urgence_at"] = now_iso()
                updates["urgence_by"] = actor_name(user)
                updates["urgence_by_id"] = user.account_id
        if "heure_rdv" in raw_updates:
            updates["heure_rdv"] = normalized.get("heure_rdv") or ""
        if "date_prochain_rdv" in raw_updates:
            updates["date_prochain_rdv"] = normalized.get("date_prochain_rdv") or ""
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
                    conseiller_account_id=(
                        normalized.get("agent_account_id")
                        or normalized.get("created_by_account_id")
                        or user.account_id
                    ),
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
        await stamp_agent_identity(doc, user)
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
        missing = missing_required(doc, docs=await docs_for(demande_id))
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
                    conseiller_account_id=(
                        doc.get("agent_account_id")
                        or doc.get("created_by_account_id")
                        or user.account_id
                    ),
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

    @api_router.post("/demandes-offres/{demande_id}/urgence")
    async def set_demande_urgence(
        demande_id: str,
        payload: UrgenceRequest,
        user: User = Depends(current_user_dependency),
    ):
        """Marque ou retire l'urgence. Le motif est obligatoire à la pose."""
        from access_control import can_process_offres
        from offre_agent_identity import viewer_is_demande_creator

        doc = await require_demande(demande_id, user)
        owner = viewer_is_demande_creator(doc, user)
        manager = can_process_offres(user)
        if not owner and not manager:
            raise HTTPException(status_code=403, detail="Accès refusé")
        from demandes_offres_ameliorations import (
            URGENCE_DELAI_24H,
            urgence_echeance_iso,
            validate_urgence_request,
        )

        want = bool(payload.urgente)
        motif = (payload.motif or "").strip()
        if want:
            refus = validate_urgence_request(want, motif, payload.delai_24h)
            if refus:
                raise HTTPException(status_code=422, detail=refus)
            if not doc.get("urgente"):
                from demandes_offres_ameliorations import (
                    count_urgences_agent,
                    period_start_iso,
                    quota_block_message,
                )

                settings = await db["crm_settings"].find_one({"id": "offres_urgence"}, {"_id": 0}) or {}
                if settings.get("quota_actif") and not doc.get("urgence_exception"):
                    since = period_start_iso(str(settings.get("periode") or "mois"))
                    peers = await db[COLLECTION].find(
                        {"user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}, "urgente": True},
                        {"_id": 0, "agent_label": 1, "urgente": 1, "statut": 1, "urgence_at": 1, "date_envoi": 1, "created_at": 1, "id": 1},
                    ).to_list(5000)
                    peers = [row for row in peers if row.get("id") != demande_id]
                    used = count_urgences_agent(peers, doc.get("agent_label") or "", since_iso=since)
                    blocked = quota_block_message(settings, used + 1, doc.get("agent_label") or "")
                    if blocked:
                        raise HTTPException(status_code=422, detail=blocked)
            stamp = now_iso()
            await db[COLLECTION].update_one(
                {"id": demande_id, "user_id": TENANT_USER_ID},
                {
                    "$set": {
                        "urgente": True,
                        "urgence_motif": motif,
                        "urgence_at": stamp,
                        "urgence_by": actor_name(user),
                        "urgence_by_id": user.account_id,
                        "urgence_delai": URGENCE_DELAI_24H,
                        "urgence_echeance_at": urgence_echeance_iso(stamp),
                        "updated_at": stamp,
                    },
                    "$push": {
                        "historique": history(
                            "Demande marquée urgente",
                            user,
                            f"À traiter en moins de 24 heures · {motif}",
                            statut=doc.get("statut"),
                        ),
                    },
                },
            )
        else:
            if not doc.get("urgente"):
                return serialize_demande(doc, docs=await docs_for(demande_id), viewer=user)
            stamp = now_iso()
            previous = (doc.get("urgence_motif") or "").strip()
            await db[COLLECTION].update_one(
                {"id": demande_id, "user_id": TENANT_USER_ID},
                {
                    "$set": {
                        "urgente": False,
                        "urgence_retiree_at": stamp,
                        "urgence_retiree_par": actor_name(user),
                        "updated_at": stamp,
                    },
                    "$push": {
                        "historique": history(
                            "Caractère urgent retiré",
                            user,
                            previous,
                            statut=doc.get("statut"),
                        ),
                    },
                },
            )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    async def require_demande_or_403(demande_id: str, user: User) -> dict:
        """Comme require_demande, mais une demande existante hors périmètre répond 403."""
        doc = await db[COLLECTION].find_one(
            {"id": demande_id, "user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}},
            {"_id": 0},
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Demande d'offre introuvable")
        if not can_access_demande(user, doc):
            raise HTTPException(status_code=403, detail="Accès refusé")
        return doc

    async def thread_payload(demande_id: str, user: User, *, mark_read: bool) -> dict:
        from demandes_offres_messages import (
            COLLECTION_MESSAGES,
            count_unread,
            public_message,
        )

        rows = await db[COLLECTION_MESSAGES].find(
            {"demande_id": demande_id, "user_id": TENANT_USER_ID},
            {"_id": 0},
        ).sort("created_at", 1).to_list(1000)
        unread = count_unread(rows, user)
        if mark_read and unread and user.account_id:
            await db[COLLECTION_MESSAGES].update_many(
                {"demande_id": demande_id, "user_id": TENANT_USER_ID, "read_by": {"$ne": user.account_id}},
                {"$addToSet": {"read_by": user.account_id}},
            )
        return {
            "demande_id": demande_id,
            "messages": [public_message(row, user) for row in rows],
            "non_lus": unread,
        }

    @api_router.get("/demandes-offres/{demande_id}/messages")
    async def list_demande_messages(
        demande_id: str,
        marquer_lu: bool = Query(True),
        user: User = Depends(current_user_dependency),
    ):
        """Fil agent / gestionnaire. Lecture : toute personne qui peut consulter la demande."""
        from demandes_offres_messages import can_read_thread, message_role

        doc = await require_demande_or_403(demande_id, user)
        if not can_read_thread(user, doc):
            raise HTTPException(status_code=403, detail="Accès refusé")
        payload = await thread_payload(demande_id, user, mark_read=bool(marquer_lu))
        payload["peut_ecrire"] = message_role(user, doc) is not None
        return payload

    async def parse_message_post(request: Request) -> tuple[str, list[UploadFile]]:
        """JSON ``{contenu}`` (rétrocompat) ou multipart ``contenu`` + fichiers."""
        content_type = (request.headers.get("content-type") or "").lower()
        uploads: list[UploadFile] = []
        if "multipart/form-data" in content_type:
            form = await request.form()
            contenu_raw = str(form.get("contenu") or "")
            for field in ("files", "documents", "file"):
                for item in form.getlist(field):
                    if not isinstance(item, (UploadFile, StarletteUploadFile)):
                        continue
                    if not (getattr(item, "filename", None) or "").strip():
                        continue
                    uploads.append(item)
            return contenu_raw, uploads
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            return str(body.get("contenu") or ""), []
        return "", []

    @api_router.post("/demandes-offres/{demande_id}/messages")
    async def post_demande_message(
        request: Request,
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        """Ajoute un message (texte et/ou pièces jointes) au fil. Ne change pas le statut."""
        from demandes_offres_messages import (
            CATEGORY_FIL_DISCUSSION,
            COLLECTION_MESSAGES,
            MAX_MESSAGE_FILES,
            ROLE_AGENT,
            build_message,
            clean_message_content,
            message_role,
            public_message_documents,
            validate_message_attachment,
        )

        doc = await require_demande_or_403(demande_id, user)
        role = message_role(user, doc)
        if role is None:
            raise HTTPException(
                status_code=403,
                detail="Seuls l'agent de la demande et les gestionnaires peuvent écrire",
            )
        contenu_raw, uploads = await parse_message_post(request)
        if len(uploads) > MAX_MESSAGE_FILES:
            raise HTTPException(
                status_code=422,
                detail=f"Maximum {MAX_MESSAGE_FILES} documents",
            )
        for upload in uploads:
            size_hint = getattr(upload, "size", None)
            try:
                validate_message_attachment(upload.filename, size_hint)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            contenu = clean_message_content(contenu_raw, has_attachments=bool(uploads))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        stored: list[dict] = []
        message_id = str(uuid.uuid4())
        try:
            for upload in uploads:
                data = await upload.read()
                if not data:
                    raise HTTPException(status_code=400, detail="Fichier vide")
                try:
                    validate_message_attachment(upload.filename, len(data))
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                # Remettre le curseur pour store_doc qui relit le fichier.
                try:
                    await upload.seek(0)
                except Exception:
                    upload.file.seek(0)
                stored.append(
                    await store_doc(
                        demande_id,
                        upload,
                        user,
                        category=CATEGORY_FIL_DISCUSSION,
                        extra={"message_id": message_id},
                    )
                )
        except HTTPException:
            await discard_complement_uploads([item.get("id") for item in stored], user)
            raise
        except Exception:
            await discard_complement_uploads([item.get("id") for item in stored], user)
            raise

        docs_public = public_message_documents(stored)
        message = build_message(
            demande_id=demande_id,
            user=user,
            role=role,
            contenu=contenu,
            at=now_iso(),
            documents=docs_public,
        )
        message["id"] = message_id
        message["user_id"] = TENANT_USER_ID
        await db[COLLECTION_MESSAGES].insert_one(dict(message))
        apercu = contenu if len(contenu) <= 120 else f"{contenu[:117]}…"
        if docs_public and apercu == contenu:
            apercu = f"{apercu} · {len(docs_public)} pièce(s)" if contenu else f"{len(docs_public)} pièce(s)"
        author = actor_name(user)
        if role == ROLE_AGENT:
            await write_offre_notification(
                doc=doc,
                event="message",
                title=f"Nouveau message — {doc.get('numero') or ''}".strip(),
                message=f"{author} : {apercu}",
                audience="gestionnaires",
                account_ids=[aid for aid in await manager_account_ids() if aid != user.account_id],
            )
            mail_event = "fil_discussion_gestionnaire"
        else:
            creator = doc.get("agent_account_id") or doc.get("created_by_account_id")
            gestionnaire = (doc.get("gestionnaire_id") or "").strip()
            bell_ids = []
            for aid in (creator, gestionnaire):
                if aid and aid != user.account_id and aid not in bell_ids:
                    bell_ids.append(aid)
            await write_offre_notification(
                doc=doc,
                event="message",
                title=f"Nouveau message — {doc.get('numero') or ''}".strip(),
                message=f"{author} : {apercu}",
                audience="conseiller",
                account_ids=bell_ids,
            )
            mail_event = "fil_discussion_agent"
        # E-mail en plus de la cloche ; un échec SMTP ne doit pas faire échouer le POST.
        # Les binaires restent sur LeoSoft ; le mail cite les noms de fichiers.
        doc_names = [
            ref.get("original_filename") for ref in docs_public if ref.get("original_filename")
        ]
        try:
            recipients = await resolve_fil_discussion_email_to(doc, role=role, sender=user)
            if recipients:
                mail_doc = {
                    **doc,
                    "fil_message_author": author,
                    "fil_message_role": role,
                    "fil_message_document_names": doc_names,
                }
                await try_send_email(
                    mail_doc,
                    event=mail_event,
                    note=contenu,
                    to_override=recipients[0],
                    cc=recipients[1:] or None,
                )
        except Exception:
            logger.exception(
                "Fil discussion e-mail failed demande=%s role=%s",
                demande_id,
                role,
            )
        return await thread_payload(demande_id, user, mark_read=False)

    @api_router.post("/demandes-offres/{demande_id}/envoyer")
    async def send_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        await stamp_agent_identity(doc, user)
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
        from demandes_offres_ameliorations import (
            count_urgences_agent,
            period_start_iso,
            quota_block_message,
            validate_urgence_for_send,
        )

        urgence_error = validate_urgence_for_send(doc)
        if urgence_error:
            raise HTTPException(status_code=422, detail=urgence_error)
        if doc.get("urgente") and not doc.get("urgence_exception"):
            settings = await db["crm_settings"].find_one({"id": "offres_urgence"}, {"_id": 0}) or {}
            if settings.get("quota_actif"):
                since = period_start_iso(str(settings.get("periode") or "mois"))
                peers = await db[COLLECTION].find(
                    {"user_id": TENANT_USER_ID, "is_deleted": {"$ne": True}, "urgente": True},
                    {
                        "_id": 0, "agent_label": 1, "urgente": 1, "statut": 1,
                        "urgence_at": 1, "date_envoi": 1, "created_at": 1, "id": 1, "is_deleted": 1,
                    },
                ).to_list(5000)
                peers = [row for row in peers if row.get("id") != demande_id]
                used = count_urgences_agent(peers, doc.get("agent_label") or "", since_iso=since)
                blocked = quota_block_message(settings, used + 1, doc.get("agent_label") or "")
                if blocked:
                    raise HTTPException(status_code=422, detail=blocked)
        missing = missing_required(doc, docs=await docs_for(demande_id))
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
                **({} if already_sent else {"gestion_vue": False}),
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
                    "documents": [],
                    "retenue": False,
                    "incomplete_comment": comment,
                    "incomplete_at": at,
                    "received_at": None,
                    "date_reception": None,
                }
            else:
                target = dict(target)
                target["incomplete_comment"] = comment
                target["incomplete_at"] = at
            capture_statut_avant_incomplet(target)
            target["statut"] = STATUT_COMPAGNIE_INCOMPLETE
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
        capture_statut_avant_incomplet(target)
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

    @api_router.post("/demandes-offres/{demande_id}/compagnie-incomplete-annuler")
    async def cancel_company_incomplete_status(
        demande_id: str,
        payload: MarkCompanyIncompleteRequest,
        user: User = Depends(current_user_dependency),
    ):
        """Rend le statut d'avant Incomplète. N'envoie pas d'e-mail et ne supprime rien."""
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        compagnie = payload.compagnie.strip()
        if not compagnie:
            raise HTTPException(status_code=422, detail="Compagnie obligatoire")
        offres = normalize_offres_list(doc)
        target = find_offre_for_compagnie(offres, compagnie)
        if not target or normalize_company_offer_statut(target.get("statut")) != STATUT_COMPAGNIE_INCOMPLETE:
            raise HTTPException(status_code=422, detail="Cette compagnie n'est pas incomplète")
        target = dict(target)
        restored = apply_restore_company_incomplete(target)
        offres = upsert_company_offre(offres, target)
        return await save_status(
            demande_id,
            user,
            statut=normalize_statut(doc.get("statut")),
            action="Statut incomplet annulé",
            detail=f"{compagnie} — {restored}",
            extra={"offres": offres, "offre": target},
            meta={"compagnie": compagnie, "statut_compagnie": restored},
        )

    @api_router.post("/demandes-offres/{demande_id}/completer-renvoyer")
    async def complete_and_resend_demande(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        missing = missing_required(doc, docs=await docs_for(demande_id))
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
        nb_variantes: Optional[str] = Form(None),
        parcours: Optional[str] = Form(None),
        client_token: Optional[str] = Form(None),
        user: User = Depends(current_user_dependency),
    ):
        """Transmet une offre compagnie à l'agent.

        parcours=reponses_compagnies : N variantes, chacune avec Offre et CGA
        (variante_<n>_offre / _cga / _autre). parcours=traitement : Offre,
        CGA et Autre document (champs offre / cga / autre), sans variantes.
        Sans parcours : ancien client, documents simples inchangés.
        """
        from demandes_offres_transmission import (
            PARCOURS_REPONSES,
            PARCOURS_TRAITEMENT,
            build_transmission,
            document_variante_extra,
            find_transmission,
            group_traitement_uploads,
            group_variante_uploads,
            history_detail,
            missing_traitement_pieces,
            missing_variante_pieces,
            normalize_parcours,
            parse_nb_variantes,
            total_variantes,
            VARIANTE_PIECES,
        )

        def form_text(value: Any) -> Optional[str]:
            return value if isinstance(value, str) else None

        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        parcours_raw = form_text(parcours)
        parcours_code = normalize_parcours(parcours_raw)
        token = (form_text(client_token) or "").strip()

        existing = normalize_offres_list(doc)
        try:
            compagnie_name = resolve_compagnie_saisie(doc, compagnie, existing)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not (date_reception or "").strip():
            raise HTTPException(status_code=422, detail="Date de réception obligatoire")

        if find_transmission(existing, token):
            fresh = await require_demande(demande_id, user)
            result = serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)
            result["transmission_deja_enregistree"] = True
            return result

        nb = None
        variante_groups: dict = {}
        traitement_pieces: dict = {}
        simple_uploads: list = []
        if parcours_code == PARCOURS_REPONSES:
            try:
                nb = parse_nb_variantes(form_text(nb_variantes))
                form = await request.form()
                items = [
                    (key, value)
                    for key, value in form.multi_items()
                    if isinstance(value, (UploadFile, StarletteUploadFile))
                    and (getattr(value, "filename", None) or "").strip()
                ]
                variante_groups = group_variante_uploads(items, nb)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            missing = missing_variante_pieces(variante_groups, nb)
            if missing:
                raise HTTPException(status_code=422, detail="Documents manquants : " + " · ".join(missing))
            pending_uploads = [
                upload
                for pieces in variante_groups.values()
                for uploads in pieces.values()
                for upload in uploads
            ]
        elif parcours_raw == PARCOURS_TRAITEMENT:
            form = await request.form()
            items = [
                (key, value)
                for key, value in form.multi_items()
                if isinstance(value, (UploadFile, StarletteUploadFile))
                and (getattr(value, "filename", None) or "").strip()
            ]
            if file is not None and (getattr(file, "filename", None) or "").strip():
                items.append(("file", file))
            traitement_pieces = group_traitement_uploads(items)
            missing = missing_traitement_pieces(traitement_pieces)
            if missing:
                raise HTTPException(status_code=422, detail="Documents manquants : " + " · ".join(missing))
            pending_uploads = [
                upload
                for piece, _label in VARIANTE_PIECES
                for upload in (traitement_pieces.get(piece) or [])
            ]
        else:
            simple_uploads = await collect_multipart_uploads(request, single_file=file)
            pending_uploads = simple_uploads
        if any(getattr(upload, "size", None) == 0 for upload in pending_uploads):
            raise HTTPException(status_code=400, detail="Fichier vide")

        transmission_id = str(uuid.uuid4())
        stored_docs = []
        stored_by_variante: dict = {}
        for index, pieces in variante_groups.items():
            stored_by_variante[index] = {}
            for piece, _label in VARIANTE_PIECES:
                stored_by_variante[index][piece] = []
                for upload in pieces.get(piece) or []:
                    stored = await store_doc(
                        demande_id, upload, user, category="Offre compagnie",
                        extra=document_variante_extra(
                            transmission_id=transmission_id, parcours=parcours_code,
                            compagnie=compagnie_name, variante=index, piece=piece,
                        ),
                    )
                    stored_by_variante[index][piece].append(stored)
                    stored_docs.append(stored)
        stored_simple = []
        for piece, _label in VARIANTE_PIECES:
            for upload in (traitement_pieces.get(piece) or []):
                stored = await store_doc(
                    demande_id, upload, user, category="Offre compagnie",
                    extra=document_variante_extra(
                        transmission_id=transmission_id, parcours=parcours_code,
                        compagnie=compagnie_name, piece=piece,
                    ),
                )
                stored_simple.append(stored)
                stored_docs.append(stored)
        for upload in simple_uploads:
            stored = await store_doc(
                demande_id, upload, user, category="Offre compagnie",
                extra=document_variante_extra(
                    transmission_id=transmission_id, parcours=parcours_code, compagnie=compagnie_name,
                ),
            )
            stored_simple.append(stored)
            stored_docs.append(stored)

        prev = find_offre_for_compagnie(existing, compagnie_name)
        transmission = build_transmission(
            parcours=parcours_code,
            compagnie=compagnie_name,
            date_reception=date_reception.strip(),
            nb_variantes=nb or 0,
            stored_by_variante=stored_by_variante,
            stored_simple=stored_simple,
            commentaire=commentaires or "",
            by_name=actor_name(user),
            by_id=str(user.account_id or ""),
            at=now_iso(),
            client_token=token,
            transmission_id=transmission_id,
        )
        transmissions = [*((prev or {}).get("transmissions") or []), transmission]
        base = {
            "id": (prev or {}).get("id") or str(uuid.uuid4()),
            "compagnie": compagnie_name,
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
            "transmissions": transmissions,
            "nb_variantes": total_variantes(transmissions) or None,
        }
        offer = append_documents_to_offre(base, stored_docs)
        existing = upsert_company_offre(existing, offer)
        # Récupérer la version fusionnée (documents cumulés)
        offer = find_offre_for_compagnie(existing, compagnie_name) or offer
        new_statut = resolve_statut_apres_reception_offre(doc, existing)
        hist_detail = history_detail(transmission, len(stored_docs)) if parcours_raw else compagnie_name
        if not parcours_raw and stored_docs:
            hist_detail = f"{compagnie_name} · {len(stored_docs)} document(s)"
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
            meta={"compagnie": compagnie_name, "offre_id": offer.get("id"), "transmission_id": transmission_id},
            document_id=(offer.get("documents") or [{}])[-1].get("id") if offer.get("documents") else None,
        )
        if stored_docs and normalize_statut(doc.get("statut")) != STATUT_BROUILLON:
            await stamp_mise_a_disposition(demande_id)
        mail_doc = {
            **doc,
            **(result if isinstance(result, dict) else {}),
            "statut": new_statut,
            "offres": existing,
            "offre": offer,
        }
        sent, email_error = await try_send_email(mail_doc, event="recue", offer=offer)
        if sent:
            await db[COLLECTION].update_one(
                {"id": demande_id, "user_id": TENANT_USER_ID},
                {"$set": {"offre_recue_email_sent": True, "updated_at": now_iso()}},
            )
        fresh_after_offer = await require_demande(demande_id, user)
        if await apply_transmission_suivi(fresh_after_offer, user, compagnie_name):
            fresh_after_offer = await require_demande(demande_id, user)
        result = serialize_demande(fresh_after_offer, docs=await docs_for(demande_id), viewer=user)
        if isinstance(result, dict):
            result["email_sent"] = sent
            result["email_error"] = email_error
            result["transmission_id"] = transmission_id
        variantes_txt = f" ({nb} variante{'s' if nb > 1 else ''})" if nb else ""
        await write_offre_notification(
            doc=doc,
            event="recue",
            title=f"Offre reçue — {doc.get('numero') or ''}".strip(),
            message=f"Offre {compagnie_name}{variantes_txt} disponible pour consultation.",
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
        payload: Optional[OffresCompletesRequest] = None,
        user: User = Depends(current_user_dependency),
    ):
        """
        Gestionnaire : signale que toutes les offres demandées sont complètes.
        Statut → « Offres complètes » + e-mail au conseiller créateur (note optionnelle).
        """
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        current = normalize_statut(doc.get("statut"))
        terminal = {
            STATUT_OFFRE_SIGNEE,
            STATUT_OFFRE_REFUSEE,
            STATUT_ANNULEE,
            STATUT_DEMANDE_ANNULEE_CODE,
            STATUT_OFFRE_NON_SIGNEE,
        }
        if current in terminal:
            raise HTTPException(
                status_code=409,
                detail=f"Impossible de marquer « Offres complètes » depuis le statut « {current} »",
            )

        body = payload or OffresCompletesRequest()
        note_agent = (
            (body.message_conseiller or body.note or "").strip() or None
        )

        at = now_iso()
        by_name = actor_name(user)
        extra = {
            "offres_completes_at": at,
            "offres_completes_by": by_name,
            "offres_completes_by_id": user.account_id,
        }
        if note_agent:
            extra["message_conseiller"] = note_agent
        detail = "Toutes les offres demandées sont reçues et complètes"
        if note_agent:
            detail = f"{detail} — note agent : {note_agent}"
        result = await save_status(
            demande_id,
            user,
            statut=STATUT_OFFRE_COMPLETE,
            action="Offres complètes",
            detail=detail,
            extra=extra,
        )
        mail_doc = {
            **doc,
            **(result if isinstance(result, dict) else {}),
            "statut": STATUT_OFFRE_COMPLETE,
            "message_conseiller": note_agent or doc.get("message_conseiller"),
        }
        from demandes_offres_ameliorations import should_send_offres_completes_email

        if should_send_offres_completes_email(doc, note_agent):
            sent, email_error = await try_send_email(
                mail_doc, event="offres_completes", note=note_agent
            )
        else:
            sent, email_error = False, None
        if isinstance(result, dict):
            result["email_sent"] = sent
            result["email_error"] = email_error
            if not sent and not should_send_offres_completes_email(doc, note_agent):
                result["email_skipped"] = "deja_notifie_par_transmission"
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

    @api_router.post("/demandes-offres/{demande_id}/erreurs")
    async def signaler_erreurs_agent(
        demande_id: str,
        payload: ErreursAgentRequest,
        user: User = Depends(current_user_dependency),
    ):
        """
        Gestionnaire : signale une ou plusieurs erreurs de champs, rattachées à l'agent créateur.
        """
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        fields = normalize_erreurs_agent_fields(payload.fields)
        if not fields:
            raise HTTPException(status_code=422, detail="Sélectionnez au moins un champ en erreur")
        already_docs = await db[COLLECTION_ERREURS].find(
            {"user_id": TENANT_USER_ID, "demande_id": demande_id},
            {"_id": 0, "field": 1, "demande_id": 1, "id": 1},
        ).to_list(2000)
        taken = active_erreur_field_keys(
            list(already_docs) + list(doc.get("erreurs_agent") or []),
            demande_id=demande_id,
        )
        fresh_fields = [f for f in fields if erreur_field_key({"field": f.get("code")}) not in taken]
        if not fresh_fields:
            labels = ", ".join(f.get("label") or erreurs_champs_label(f.get("code")) for f in fields)
            raise HTTPException(
                status_code=409,
                detail=f"Une erreur existe déjà pour : {labels}",
            )
        records = build_erreur_agent_records(
            doc,
            fresh_fields,
            by_user=user,
            error_type=payload.error_type or ERREUR_TYPE_DEFAUT,
            comment=payload.comment,
        )
        for rec in records:
            rec["user_id"] = TENANT_USER_ID
            rec["created_by_account_id"] = doc.get("created_by_account_id")
            await db[COLLECTION_ERREURS].update_one(
                {
                    "user_id": TENANT_USER_ID,
                    "demande_id": demande_id,
                    "field": rec.get("field"),
                },
                {"$setOnInsert": rec},
                upsert=True,
            )
        stored = await db[COLLECTION_ERREURS].find(
            {"user_id": TENANT_USER_ID, "demande_id": demande_id},
            {"_id": 0},
        ).to_list(2000)
        kept, _removed = dedupe_erreur_records(stored, demande_id=demande_id)
        slim = [{k: v for k, v in r.items() if k != "user_id"} for r in kept]
        labels = ", ".join(
            r.get("field_label") or erreurs_champs_label(r.get("field"))
            for r in slim
            if erreur_field_key(r) in {erreur_field_key({"field": f.get("code")}) for f in fresh_fields}
        )
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {"erreurs_agent": slim, "updated_at": now_iso()},
                "$push": {
                    "historique": history(
                        "Erreurs signalées",
                        user,
                        labels,
                        statut=doc.get("statut"),
                        meta={
                            "fields": [r.get("field") for r in slim],
                            "agent_id": slim[0].get("agent_id") if slim else None,
                        },
                    )
                },
            },
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    @api_router.delete("/demandes-offres/{demande_id}/erreurs/{erreur_ref}")
    async def retirer_erreur_signalee(
        demande_id: str,
        erreur_ref: str,
        user: User = Depends(current_user_dependency),
    ):
        """
        Retire une erreur déjà enregistrée. Le scoring ne la compte plus.
        La demande, son statut et les autres erreurs du dossier restent.
        """
        require_perm(
            user,
            (PERM_DEMANDES_OFFRES_PROCESS, PERM_USERS_MANAGE),
            detail="Réservé aux gestionnaires d'offres",
        )
        doc = await require_demande(demande_id, user)
        stored = await db[COLLECTION_ERREURS].find(
            {"user_id": TENANT_USER_ID, "demande_id": demande_id},
        ).to_list(2000)
        embedded = [e for e in (doc.get("erreurs_agent") or []) if isinstance(e, dict)]
        remaining, removed = retirer_erreur_agent(
            list(stored) + embedded,
            demande_id=demande_id,
            erreur_ref=erreur_ref,
        )
        if not removed:
            raise HTTPException(status_code=404, detail="Erreur introuvable")
        kept, _dupes = dedupe_erreur_records(remaining, demande_id=demande_id)
        slim = [{k: v for k, v in r.items() if k not in {"user_id", "_id"}} for r in kept]
        delete_filter: dict = {"user_id": TENANT_USER_ID, "demande_id": demande_id}
        clauses = []
        removed_id = str(removed.get("id") or "").strip()
        removed_field = str(removed.get("field") or "").strip()
        if removed_id:
            clauses.append({"id": removed_id})
        if removed_field:
            clauses.append({"field": removed_field})
        if clauses:
            delete_filter["$or"] = clauses
            await db[COLLECTION_ERREURS].delete_many(delete_filter)
        # Historique seulement : pas de nouveau statut, pas d'e-mail, pas de document.
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {"erreurs_agent": slim, "updated_at": now_iso()},
                "$push": {
                    "historique": history(
                        "Erreur retirée",
                        user,
                        detail_erreur_retiree(removed),
                        meta={
                            "erreur_id": removed.get("id"),
                            "field": removed.get("field"),
                            "field_label": removed.get("field_label"),
                            "demande_id": demande_id,
                        },
                    )
                },
            },
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

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

    def _form_bool(value) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    @api_router.post("/demandes-offres/{demande_id}/notes-externes")
    async def add_external_note(
        request: Request,
        demande_id: str,
        note: str = Form(...),
        attendre_reponse: str = Form("false"),
        retour_document: str = Form("false"),
        user: User = Depends(current_user_dependency),
    ):
        """
        Note destinée au conseiller créateur : historique LeoSoft + e-mail.
        Pièces jointes optionnelles (gestionnaire). Case « Attendre une réponse »
        ouvre une seule réponse conseiller (texte et/ou documents).
        """
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        doc = await require_demande(demande_id, user)
        note_text = (note or "").strip()
        if not note_text:
            raise HTTPException(status_code=422, detail="La note est obligatoire")
        attendre = _form_bool(attendre_reponse)
        retour = _form_bool(retour_document) and attendre
        uploads = await reply_uploads(request)
        if retour and not uploads:
            raise HTTPException(
                status_code=422,
                detail="Joignez le document que le conseiller doit compléter",
            )
        if len(uploads) > MAX_NOTE_FILES:
            raise HTTPException(
                status_code=422,
                detail=f"Maximum {MAX_NOTE_FILES} documents",
            )
        author = actor_name(user)
        entry_id = str(uuid.uuid4())
        stored = []
        try:
            for upload in uploads:
                stored.append(
                    await store_doc(
                        demande_id,
                        upload,
                        user,
                        category=CATEGORY_NOTE_EXTERNE,
                        extra={"note_externe_id": entry_id},
                    )
                )
        except Exception:
            await discard_complement_uploads([item.get("id") for item in stored], user)
            raise

        attachment_refs = public_document_refs(
            [
                {
                    "id": item.get("id"),
                    "original_filename": item.get("original_filename"),
                    "content_type": item.get("content_type"),
                    "size": item.get("size"),
                    "category": CATEGORY_NOTE_EXTERNE,
                    "created_at": item.get("created_at"),
                }
                for item in stored
            ]
        )
        to_addr = await resolve_demande_creator_email(doc)
        sent = False
        email_error = None
        doc_names = [ref.get("original_filename") for ref in attachment_refs if ref.get("original_filename")]
        if to_addr:
            mail_doc = {
                **doc,
                "note_externe_author": author,
                "complement_type": "reponse" if attendre else None,
                "complement_id": entry_id if attendre else None,
                "complement_document_names": doc_names,
                "note_externe_document_names": doc_names,
                "retour_document": bool(retour),
            }
            if attendre:
                sent, email_error = await try_send_email(
                    mail_doc,
                    event="complement_demande",
                    note=note_text,
                    to_override=to_addr,
                )
            else:
                sent, email_error = await try_send_email(
                    mail_doc,
                    event="note_externe",
                    note=note_text,
                    to_override=to_addr,
                )
        else:
            email_error = "E-mail du créateur introuvable sur la demande"
        at = now_iso()
        entry = {
            "id": entry_id,
            "at": at,
            "by_name": author,
            "by_id": user.account_id,
            "note": note_text,
            "email_to": to_addr,
            "email_sent": bool(sent),
            "email_error": email_error,
            "reply_expected": attendre,
            "retour_document": bool(retour),
            "documents": attachment_refs,
        }
        if attendre:
            entry["complement"] = new_complement(at=at)
        notes_field = doc.get("notes_externes")
        if notes_field is None:
            await db[COLLECTION].update_one(
                {"id": demande_id, "user_id": TENANT_USER_ID, "notes_externes": None},
                {"$set": {"notes_externes": []}},
            )
        action = "Demande de complément" if attendre else "Note externe"
        hist_detail = note_text
        if attachment_refs:
            hist_detail = f"{note_text} · {len(attachment_refs)} pièce(s)"
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$push": {
                    "notes_externes": entry,
                    "historique": history(action, user, hist_detail),
                },
                "$set": {"updated_at": now_iso()},
            },
        )
        if attendre:
            await write_offre_notification(
                doc=doc,
                event="complement_demande",
                title=f"Action requise — {doc.get('numero') or 'offre'}".strip(),
                message="Une note externe nécessite votre réponse.",
                audience="conseiller",
                account_ids=creator_account_ids(doc),
                complement_id=entry_id,
            )
        fresh = await require_demande(demande_id, user)
        result = serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)
        if isinstance(result, dict):
            result["note_email_sent"] = bool(sent)
            result["note_email_error"] = email_error
            result["notify_email"] = to_addr
        return result

    async def discard_complement_uploads(doc_ids: list[str], user: User) -> None:
        ids = [str(item) for item in doc_ids if item]
        if not ids:
            return
        await db[COLLECTION_DOCS].update_many(
            {"id": {"$in": ids}, "user_id": TENANT_USER_ID},
            {
                "$set": {
                    "is_deleted": True,
                    "deleted_at": now_iso(),
                    "deleted_by": user.account_id,
                }
            },
        )

    async def reply_uploads(request: Request) -> list[UploadFile]:
        """Garde chaque fichier nommé, y compris deux pièces au même nom."""
        form = await request.form()
        uploads: list[UploadFile] = []
        for field in ("files", "documents", "file"):
            for item in form.getlist(field):
                if not isinstance(item, (UploadFile, StarletteUploadFile)):
                    continue
                if not (getattr(item, "filename", None) or "").strip():
                    continue
                uploads.append(item)
        return uploads

    def public_reply_document(stored: dict) -> dict:
        return {
            "id": stored.get("id"),
            "original_filename": stored.get("original_filename") or "Document",
            "content_type": stored.get("content_type") or "application/octet-stream",
            "size": stored.get("size"),
            "category": stored.get("category") or CATEGORY_COMPLEMENT,
            "created_at": stored.get("created_at"),
        }

    @api_router.post("/demandes-offres/{demande_id}/complements/{complement_id}/reponse")
    async def reply_to_complement(
        request: Request,
        demande_id: str,
        complement_id: str,
        commentaire: str = Form(""),
        user: User = Depends(current_user_dependency),
    ):
        """
        Une seule réponse pour cette demande de complément.
        Le filtre Mongo refuse un second envoi, même depuis un autre onglet.
        """
        doc = await require_demande(demande_id, user)
        if not user_can_answer_complement(user, doc):
            raise HTTPException(status_code=403, detail="Accès refusé")
        note = next(
            (
                item for item in (doc.get("notes_externes") or [])
                if str(item.get("id") or "") == str(complement_id)
            ),
            None,
        )
        uploads = await reply_uploads(request)
        error_code = validate_reply(note, commentaire, len(uploads))
        if error_code:
            status, detail = REPLY_ERROR_HTTP.get(error_code, (422, "Réponse impossible"))
            raise HTTPException(status_code=status, detail=detail)

        stored = []
        try:
            for upload in uploads:
                stored.append(
                    await store_doc(
                        demande_id,
                        upload,
                        user,
                        category=CATEGORY_COMPLEMENT,
                        extra={"complement_id": complement_id},
                    )
                )
        except Exception:
            await discard_complement_uploads([item.get("id") for item in stored], user)
            raise

        reply = {
            "text": (commentaire or "").strip(),
            "at": now_iso(),
            "by_name": actor_name(user),
            "by_id": user.account_id,
            "documents": [public_reply_document(item) for item in stored],
        }
        result = await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {
                    "notes_externes.$[n].complement.status": "reponse_recue",
                    "notes_externes.$[n].complement.reply": reply,
                    "updated_at": now_iso(),
                },
                "$push": {
                    "historique": history(
                        "Réponse au complément",
                        user,
                        reply["text"],
                        meta={"complement_id": complement_id},
                    )
                },
            },
            array_filters=[reply_claim_filter(complement_id)],
        )
        if getattr(result, "matched_count", 0) != 1:
            await discard_complement_uploads([item.get("id") for item in stored], user)
            raise HTTPException(
                status_code=409,
                detail="Une réponse a déjà été transmise pour cette demande",
            )

        fresh = await require_demande(demande_id, user)
        sent = False
        email_error = None
        try:
            mail_doc = {
                **fresh,
                "complement_type": (note.get("complement") or {}).get("type"),
                "complement_id": complement_id,
                "complement_reply_text": reply["text"],
                "complement_reply_author": reply["by_name"],
                "complement_request_note": note.get("note"),
                "complement_document_names": [
                    item.get("original_filename") for item in reply["documents"]
                ],
            }
            sent, email_error = await try_send_email(
                mail_doc,
                event="complement_reponse",
                note=note.get("note"),
            )
        except Exception:
            logger.exception("Complement reply email failed demande=%s", demande_id)
            sent, email_error = False, "Notification e-mail indisponible"
        await write_offre_notification(
            doc=fresh,
            event="complement_reponse",
            title=f"Réponse reçue — {fresh.get('numero') or 'offre'}".strip(),
            message=f"{reply['by_name']} a répondu à une demande de complément.",
            audience="gestionnaires",
            account_ids=await manager_account_ids(),
            complement_id=complement_id,
        )
        payload_out = serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)
        if isinstance(payload_out, dict):
            payload_out["complement_email_sent"] = bool(sent)
            payload_out["complement_email_error"] = email_error
        return payload_out

    @api_router.post("/demandes-offres/{demande_id}/complements/{complement_id}/cloturer")
    async def close_complement(
        demande_id: str,
        complement_id: str,
        user: User = Depends(current_user_dependency),
    ):
        """Ferme un droit de réponse encore ouvert, sans enregistrer de réponse."""
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        await require_demande(demande_id, user)
        at = now_iso()
        result = await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {
                    "notes_externes.$[n].complement.status": "cloturee",
                    "notes_externes.$[n].complement.closed_at": at,
                    "notes_externes.$[n].complement.closed_by": actor_name(user),
                    "notes_externes.$[n].complement.closed_by_id": user.account_id,
                    "updated_at": at,
                },
                "$push": {
                    "historique": history(
                        "Complément clôturé",
                        user,
                        "",
                        meta={"complement_id": complement_id},
                    )
                },
            },
            array_filters=[reply_claim_filter(complement_id)],
        )
        if getattr(result, "matched_count", 0) != 1:
            raise HTTPException(
                status_code=409,
                detail="Cette demande ne peut plus être clôturée",
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
        # Réservé aux gestionnaires — le conseiller créateur n'utilise plus cette étape
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
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
        # Créateur, ou administrateur (users.manage)
        if not (can_follow_signature(user, doc) or getattr(user, "can_manage_users", False)):
            raise HTTPException(
                status_code=403,
                detail="L'envoi au client est réservé au conseiller ayant créé la demande",
            )
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
        if not (can_follow_signature(user, doc) or getattr(user, "can_manage_users", False)):
            raise HTTPException(
                status_code=403,
                detail="Le suivi signature est réservé à l'agent ayant créé la demande",
            )
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
        # Offre signée : PDF proposition signée obligatoire (ne coche PAS soumis_compagnie)
        if payload.signee:
            if file is None:
                raise HTTPException(
                    status_code=422,
                    detail="Le PDF de la proposition signée est obligatoire",
                )
            fname = (file.filename or "").strip().lower()
            ctype = (file.content_type or "").lower()
            if not (fname.endswith(".pdf") or "pdf" in ctype):
                raise HTTPException(
                    status_code=422,
                    detail="La proposition signée doit être un fichier PDF",
                )
        extra_uploads = (
            await signature_extra_uploads(request) if payload.signee and signee is not None else []
        )
        if len(extra_uploads) > MAX_SIGNATURE_FILES:
            raise HTTPException(
                status_code=422,
                detail=f"Maximum {MAX_SIGNATURE_FILES} documents complémentaires",
            )
        stored = (
            await store_doc(
                demande_id,
                file,
                user,
                category=DOC_CATEGORY_PROPOSITION_SIGNEE,
            )
            if file is not None
            else None
        )
        extra_stored = []
        try:
            for upload in extra_uploads:
                extra_stored.append(
                    await store_doc(
                        demande_id,
                        upload,
                        user,
                        category=DOC_CATEGORY_DOCUMENT_SIGNATURE,
                    )
                )
        except Exception:
            await discard_complement_uploads(
                [item.get("id") for item in [stored, *extra_stored] if item],
                user,
            )
            raise
        signature_docs = [
            signature_document_ref(item, category=DOC_CATEGORY_PROPOSITION_SIGNEE)
            for item in ([stored] if stored else [])
        ] + [
            signature_document_ref(item, category=DOC_CATEGORY_DOCUMENT_SIGNATURE)
            for item in extra_stored
        ]
        stamp = now_iso()
        signature = {
            "signee": payload.signee,
            "date_signature": (payload.date_signature or "").strip() or None,
            "commentaire": (payload.commentaire or "").strip() or None,
            "date_relance": (payload.date_relance or "").strip() or None,
            "document_id": stored.get("id") if stored else None,
            "document_category": DOC_CATEGORY_PROPOSITION_SIGNEE if stored else None,
            "documents": signature_docs,
            "complements": [],
            "recorded_at": stamp,
            "recorded_by": actor_name(user),
            "recorded_by_id": user.account_id,
            # Alias explicites pour audit / UI
            "signed_at": stamp if payload.signee else None,
            "signed_by": actor_name(user) if payload.signee else None,
            "signed_by_id": user.account_id if payload.signee else None,
        }
        statut = STATUT_OFFRE_SIGNEE if payload.signee else STATUT_OFFRE_REFUSEE
        action = "Offre signée" if payload.signee else "Offre refusée"
        result = await save_status(
            demande_id,
            user,
            statut=statut,
            action=action,
            detail=(
                signature_history_detail(signature["commentaire"], signature_docs)
                if payload.signee
                else signature["commentaire"] or (
                    (stored.get("original_filename") if stored else None) or ""
                )
            ),
            extra={"signature": signature},
            document_id=signature.get("document_id"),
            meta={"document_ids": [d["id"] for d in signature_docs]} if signature_docs else None,
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

    async def signature_extra_uploads(request: Request) -> list[UploadFile]:
        """Pièces complémentaires (champ « documents ») ; « file » reste la proposition signée."""
        form = await request.form()
        uploads: list[UploadFile] = []
        for item in form.getlist("documents"):
            if not isinstance(item, (UploadFile, StarletteUploadFile)):
                continue
            if not (getattr(item, "filename", None) or "").strip():
                continue
            uploads.append(item)
        return uploads

    @api_router.post("/demandes-offres/{demande_id}/signature/complements")
    async def add_signature_complement(
        request: Request,
        demande_id: str,
        commentaire: Optional[str] = Form(None),
        user: User = Depends(current_user_dependency),
    ):
        """Après « Offre signée » : l'agent ajoute des documents et/ou un commentaire."""
        doc = await require_demande(demande_id, user)
        if not (can_follow_signature(user, doc) or getattr(user, "can_manage_users", False)):
            raise HTTPException(
                status_code=403,
                detail="Le suivi signature est réservé à l'agent ayant créé la demande",
            )
        if doc.get("statut") != STATUT_OFFRE_SIGNEE:
            raise HTTPException(status_code=409, detail="L'offre n'est pas signée")
        text = (commentaire or "").strip()
        uploads = await signature_extra_uploads(request)
        if not text and not uploads:
            raise HTTPException(
                status_code=422,
                detail="Ajoutez au moins un document ou un commentaire",
            )
        if len(uploads) > MAX_SIGNATURE_FILES:
            raise HTTPException(
                status_code=422,
                detail=f"Maximum {MAX_SIGNATURE_FILES} documents",
            )
        stored = []
        try:
            for upload in uploads:
                stored.append(
                    await store_doc(
                        demande_id,
                        upload,
                        user,
                        category=DOC_CATEGORY_DOCUMENT_SIGNATURE,
                    )
                )
        except Exception:
            await discard_complement_uploads([item.get("id") for item in stored], user)
            raise
        refs = [
            signature_document_ref(item, category=DOC_CATEGORY_DOCUMENT_SIGNATURE)
            for item in stored
        ]
        entry = build_signature_complement(
            commentaire=text,
            documents=refs,
            by_name=actor_name(user),
            by_id=user.account_id,
            at=now_iso(),
        )
        current_signature = doc.get("signature") if isinstance(doc.get("signature"), dict) else {"signee": True}
        complements = [
            *[c for c in (current_signature.get("complements") or []) if isinstance(c, dict)],
            entry,
        ]
        hist = collapse_demande_historique(doc.get("historique") or [])
        hist.append(
            history(
                ACTION_COMPLEMENT_SIGNATURE,
                user,
                signature_history_detail(text, refs),
                document_id=refs[0]["id"] if refs else None,
                meta={"document_ids": [d["id"] for d in refs]} if refs else None,
            )
        )
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {
                    "signature": {**current_signature, "complements": complements},
                    "updated_at": entry["at"],
                    "historique": hist,
                },
            },
        )
        await write_offre_notification(
            doc=doc,
            event="signee_complement",
            title=f"Offre signée — complément {doc.get('numero') or ''}".strip(),
            message=signature_history_detail(text, refs) or "Complément ajouté par l'agent.",
            audience="gestionnaires",
            account_ids=await manager_account_ids(),
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    @api_router.post("/demandes-offres/{demande_id}/soumis-compagnie")
    async def mark_soumis_compagnie(
        demande_id: str,
        payload: SoumisCompagnieRequest,
        user: User = Depends(current_user_dependency),
    ):
        """
        Indicateur manuel « Soumis à la compagnie » — réservé gestionnaires
        (demandes_offres.process). Indépendant de « Offre signée » (jamais auto).
        """
        require_perm(
            user,
            PERM_DEMANDES_OFFRES_PROCESS,
            detail="Réservé aux gestionnaires d'offres",
        )
        doc = await require_demande(demande_id, user)
        current = normalize_soumis_compagnie(doc)
        wanted = bool(payload.soumis)
        if current.get("soumis") is wanted and wanted:
            return serialize_demande(
                doc, docs=await docs_for(demande_id), viewer=user
            )
        extras = build_soumis_compagnie_payload(
            soumis=wanted,
            by_name=actor_name(user),
            by_id=user.account_id or "",
        )
        action = ACTION_SOUMIS_COMPAGNIE if wanted else ACTION_NON_SOUMIS_COMPAGNIE
        # Conserve le statut courant — cet indicateur n'est pas un statut workflow
        statut = normalize_statut(doc.get("statut"))
        return await save_status(
            demande_id,
            user,
            statut=statut,
            action=action,
            detail="" if wanted else "Indicateur retiré",
            extra=extras,
            meta={"soumis_compagnie": wanted},
        )

    async def record_unique_field_error(doc: dict, field_code: str, field_label: str, comment: str, user: User) -> None:
        """Insère au plus une erreur par demande + champ, attribuée au conseiller."""
        demande_id = doc.get("id")
        built = build_erreur_agent_records(
            doc,
            [{"code": field_code, "label": field_label}],
            by_user=user,
            comment=comment,
        )
        rec = built[0]
        rec["user_id"] = TENANT_USER_ID
        rec["created_by_account_id"] = doc.get("created_by_account_id")
        await db[COLLECTION_ERREURS].update_one(
            {
                "user_id": TENANT_USER_ID,
                "demande_id": demande_id,
                "field": field_code,
            },
            {"$setOnInsert": rec},
            upsert=True,
        )
        stored = await db[COLLECTION_ERREURS].find(
            {"user_id": TENANT_USER_ID, "demande_id": demande_id},
            {"_id": 0},
        ).to_list(2000)
        kept, _removed = dedupe_erreur_records(stored, demande_id=demande_id)
        slim = [{k: v for k, v in r.items() if k != "user_id"} for r in kept]
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {"$set": {"erreurs_agent": slim, "updated_at": now_iso()}},
        )

    async def apply_offre_non_signee(demande_id: str, reason: str, user: User) -> dict:
        """
        Marque l'offre non signée. Ne supprime ni la demande ni ses documents.
        Le motif est conservé (audit / historique) mais n'est pas compté comme
        erreur de saisie dans les stats « Erreurs sur demandes d'offres ».
        """
        motif = (reason or "").strip()
        if not motif:
            raise HTTPException(
                status_code=422,
                detail="Le motif est obligatoire pour marquer l'offre non signée",
            )
        doc = await require_demande(demande_id, user)
        if not can_mark_offre_non_signee(user, doc):
            raise HTTPException(
                status_code=403,
                detail="Réservé au conseiller de la demande ou aux gestionnaires d'offres",
            )
        statut = normalize_statut(doc.get("statut"))
        if statut == STATUT_OFFRE_NON_SIGNEE:
            raise HTTPException(status_code=409, detail="Cette offre est déjà marquée non signée")
        if statut == STATUT_OFFRE_SIGNEE:
            raise HTTPException(
                status_code=409,
                detail="Une offre signée ne peut pas être marquée non signée",
            )
        stamp = now_iso()
        result = await save_status(
            demande_id,
            user,
            statut=STATUT_OFFRE_NON_SIGNEE,
            action=ACTION_OFFRE_NON_SIGNEE,
            detail=motif,
            extra={
                FIELD_STATUT_AVANT_ANNULATION: statut,
                FIELD_OFFRE_NON_SIGNEE: {
                    "status": STATUT_OFFRE_NON_SIGNEE,
                    "at": stamp,
                    "by": actor_name(user),
                    "by_id": user.account_id,
                    "reason": motif,
                },
            },
            meta={"status": STATUT_OFFRE_NON_SIGNEE},
        )
        await record_unique_field_error(
            doc,
            ERREUR_FIELD_ANNULATION_OFFRE,
            ERREUR_LABEL_ANNULATION_OFFRE,
            motif,
            user,
        )
        fresh = await require_demande(demande_id, user)
        return serialize_demande(fresh, docs=await docs_for(demande_id), viewer=user)

    @api_router.post("/demandes-offres/{demande_id}/offre-non-signee")
    async def mark_offre_non_signee(
        demande_id: str,
        payload: OffreNonSigneeRequest,
        user: User = Depends(current_user_dependency),
    ):
        return await apply_offre_non_signee(demande_id, payload.commentaire, user)

    @api_router.post("/demandes-offres/{demande_id}/annuler")
    async def cancel_demande_offre(
        demande_id: str,
        payload: Optional[AnnulationRequest] = None,
        user: User = Depends(current_user_dependency),
    ):
        """Ancien bouton « Annuler l'offre » : désormais « Offre non signée »."""
        comment = (payload.commentaire if payload else None) or ""
        return await apply_offre_non_signee(demande_id, comment, user)

    @api_router.post("/demandes-offres/{demande_id}/demande-annulee")
    async def mark_demande_annulee(
        demande_id: str,
        payload: DemandeAnnuleeRequest,
        user: User = Depends(current_user_dependency),
    ):
        """
        Case « Demande annulée » — annule la demande d'offre elle-même.
        Distinct de « Offre non signée ». Réservé aux gestionnaires.
        Aucune suppression de données.
        """
        require_perm(
            user,
            PERM_DEMANDES_OFFRES_PROCESS,
            detail="Réservé aux gestionnaires d'offres",
        )
        doc = await require_demande(demande_id, user)
        statut = normalize_statut(doc.get("statut"))
        if payload.annulee:
            if statut == STATUT_OFFRE_SIGNEE:
                raise HTTPException(
                    status_code=409,
                    detail="Une offre signée ne peut pas être annulée",
                )
            flag = normalize_demande_annulee(doc)
            if flag.get("annulee") and is_demande_annulee_statut(statut):
                return serialize_demande(doc, docs=await docs_for(demande_id), viewer=user)
            extra = build_demande_annulee_payload(
                annulee=True,
                by_name=actor_name(user),
                by_id=user.account_id or "",
            )
            if not is_demande_annulee_statut(statut):
                extra[FIELD_STATUT_AVANT_ANNULATION] = doc.get("statut")
            return await save_status(
                demande_id,
                user,
                statut=STATUT_DEMANDE_ANNULEE_CODE,
                action=ACTION_DEMANDE_ANNULEE,
                detail="La demande d'offre est annulée",
                extra=extra,
                meta={"status": STATUT_DEMANDE_ANNULEE_CODE},
            )
        if not normalize_demande_annulee(doc).get("annulee") and not is_demande_annulee_statut(statut):
            return serialize_demande(doc, docs=await docs_for(demande_id), viewer=user)
        extra = build_demande_annulee_payload(annulee=False)
        extra[FIELD_STATUT_AVANT_ANNULATION] = None
        offer_meta = doc.get(FIELD_OFFRE_NON_SIGNEE) if isinstance(doc.get(FIELD_OFFRE_NON_SIGNEE), dict) else None
        if offer_meta and offer_meta.get("status") == STATUT_OFFRE_NON_SIGNEE and is_offre_non_signee_statut(statut):
            return await save_status(
                demande_id,
                user,
                statut=STATUT_OFFRE_NON_SIGNEE,
                action=ACTION_DEMANDE_REACTIVEE,
                detail="Marquage « Demande annulée » retiré",
                extra=extra,
            )
        return await save_status(
            demande_id,
            user,
            statut=resolve_statut_avant_annulation(doc),
            action=ACTION_DEMANDE_REACTIVEE,
            detail="La demande n'est plus annulée",
            extra=extra,
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
        if not is_demande_annulee_statut(statut):
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
        form_type_id = (payload.form_type or doc.get("form_type") or "pilier3_legacy").strip() or "pilier3_legacy"
        is_schema = form_type_id != "pilier3_legacy"
        updates: dict = {}
        # Le wizard legacy envoie ses colonnes CRM. Un formulaire schéma envoie
        # le form_payload du type choisi ; les colonnes liste sont dérivées du schéma.
        if payload.fields and not is_schema:
            for k, v in payload.fields.items():
                updates[k] = v
        if payload.form_payload is not None:
            form_payload = payload.form_payload
            if is_schema:
                from offre_form_types import (
                    filter_form_payload_to_schema,
                    get_form_type,
                    sync_compagnies_from_payload,
                    sync_crm_fields_from_payload,
                )

                form_payload = filter_form_payload_to_schema(form_type_id, form_payload)
                synced: dict = {}
                sync_crm_fields_from_payload(synced, form_type_id, form_payload)
                sync_compagnies_from_payload(synced, form_type_id, form_payload)
                for key, value in synced.items():
                    if value not in (None, ""):
                        updates[key] = value
                meta = get_form_type(form_type_id) or {}
                updates["form_type"] = form_type_id
                updates["form_type_label"] = (
                    (payload.form_type_label or "").strip()
                    or meta.get("label")
                    or doc.get("form_type_label")
                )
            updates["form_payload"] = form_payload
        elif payload.form_type and is_schema:
            from offre_form_types import get_form_type

            meta = get_form_type(form_type_id) or {}
            updates["form_type"] = form_type_id
            updates["form_type_label"] = (
                (payload.form_type_label or "").strip() or meta.get("label") or doc.get("form_type_label")
            )
        note = (payload.note_service_offre or "").strip() or None
        if note is not None:
            updates["note_service_offre"] = note
        merged = {**doc, **updates}
        # changes explicites = éditions manuelles après préremplissage.
        # On ne réécrit pas ce diff avec chaque clé du formulaire prérempli.
        if payload.changes is not None:
            changes = list(payload.changes)
        else:
            changes = build_field_changes(snapshot, merged)
            if payload.form_payload is not None and snapshot.get("form_payload") != updates.get("form_payload"):
                old_fp = snapshot.get("form_payload") or {}
                new_fp = updates.get("form_payload") or {}
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
        # Le numéro OFF et l'objet du fil ne changent pas lors d'une modification.
        updates.pop("numero", None)
        updates.pop("email_subject", None)
        updates.pop("id", None)
        updates.pop("_id", None)
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
        form_type: Optional[str] = Form(None),
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
        filled_keys: list = []
        chosen_type = (form_type or doc.get("form_type") or "pilier3_legacy").strip() or "pilier3_legacy"
        if data:
            try:
                from offre_extract import extract_offre_fields, map_extract_to_form, offre_fields_for_storage

                raw = extract_offre_fields(data, filename=filename)
                mapped = map_extract_to_form(raw, form_type=chosen_type)
                fields = mapped.get("fields") or {}
                form_payload = mapped.get("form_payload") or {}
                filled_keys = list(mapped.get("filled_keys") or [])
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
            "filled_keys": filled_keys,
            "numero": doc.get("numero"),
            "email_subject": doc.get("email_subject") or "",
            "form_type": chosen_type,
            "hint": "Formulaire prérempli depuis le PDF. Vérifiez puis modifiez uniquement le nécessaire.",
        }

    @api_router.delete("/demandes-offres/{demande_id}")
    async def delete_demande_offre(
        demande_id: str,
        user: User = Depends(current_user_dependency),
    ):
        doc = await require_demande(demande_id, user)
        statut = normalize_statut(doc.get("statut"))
        if statut != STATUT_BROUILLON and not is_demande_annulee_statut(statut):
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
        await require_demande_or_403(record.get("demande_id") or "", user)
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
        demande = await require_demande(record.get("demande_id") or "", user)
        if str(doc_id) in reply_document_ids(demande.get("notes_externes")):
            raise HTTPException(
                status_code=409,
                detail="Ce document fait partie d'une réponse transmise et ne peut plus être supprimé",
            )
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
        piece_kind: str = Form(""),
        retour_obligatoire: str = Form(""),
        parent_document_id: str = Form(""),
        user: User = Depends(current_user_dependency),
    ):
        demande = await require_demande(demande_id, user)
        statut = normalize_statut(demande.get("statut"))
        editable = {STATUT_BROUILLON, STATUT_ATTENTE_INFOS, STATUT_INCOMPLETE}
        parent_id = parent_document_id.strip()
        parent = None
        if parent_id:
            parent = await db[COLLECTION_DOCS].find_one(
                {
                    "id": parent_id,
                    "demande_id": demande_id,
                    "user_id": TENANT_USER_ID,
                    "is_deleted": {"$ne": True},
                },
                {"_id": 0},
            )
            if not parent or not parent.get("retour_obligatoire"):
                raise HTTPException(status_code=422, detail="Ce document n'attend pas de retour")
            if parent.get("retour_confirme_at") or parent.get("retour_recu_at"):
                raise HTTPException(status_code=409, detail="Le retour de ce document est déjà confirmé")
            allowed_return = has_perm(user, PERM_DEMANDES_OFFRES_PROCESS) or (
                str(user.account_id) in creator_account_ids(demande)
            )
            if not allowed_return:
                raise HTTPException(status_code=403, detail="Seul l'agent de la demande peut déposer ce retour")
        elif statut not in editable:
            require_perm(
                user,
                PERM_DEMANDES_OFFRES_PROCESS,
                detail="Réservé aux gestionnaires d'offres",
            )
        normalized_category = category.strip() or "Pièce jointe"
        from mandat_gestion_offre import normalize_mandat_upload_category

        mandat_category = normalize_mandat_upload_category(normalized_category)
        from demandes_offres_ameliorations import normalize_piece_kind, parse_bool

        kind = normalize_piece_kind(piece_kind)
        allowed = {
            "pièce jointe",
            "piece jointe",
            "pièces jointes",
            "pieces jointes",
            "mandat",
            "mandat de gestion",
            "mandat_gestion",
            "offre",
            "cga",
            "autre document",
        }
        if normalized_category.lower() not in allowed and not kind:
            raise HTTPException(status_code=422, detail="Catégorie de document invalide")
        stored_category = kind or mandat_category or "Pièce jointe"
        extra = {}
        if kind:
            extra["piece_kind"] = kind
        if parse_bool(retour_obligatoire):
            extra["retour_obligatoire"] = True
        if parent_document_id.strip():
            extra["parent_document_id"] = parent_document_id.strip()
        stored = await store_doc(
            demande_id,
            file,
            user,
            category=stored_category,
            extra=extra or None,
        )
        hist_action = "Document ajouté"
        hist_detail = stored.get("original_filename") or ""
        if parent:
            await db[COLLECTION_DOCS].update_one(
                {"id": parent_id, "demande_id": demande_id},
                {"$set": {
                    "retour_depose_at": now_iso(),
                    "retour_document_id": stored.get("id"),
                    "retour_depose_by": actor_name(user),
                }},
            )
            hist_action = "Retour déposé"
            hist_detail = (
                f"{stored.get('original_filename') or 'document'} "
                f"en réponse à {parent.get('original_filename') or parent_id}"
            )
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {"updated_at": now_iso()},
                "$push": {
                    "historique": history(hist_action, user, hist_detail)
                },
            },
        )
        return stored

    @api_router.post("/demandes-offres/{demande_id}/documents/{doc_id}/confirmer-retour")
    async def confirmer_retour_document(
        demande_id: str,
        doc_id: str,
        user: User = Depends(current_user_dependency),
    ):
        require_perm(user, PERM_DEMANDES_OFFRES_PROCESS, detail="Réservé aux gestionnaires d'offres")
        await require_demande(demande_id, user)
        parent = await db[COLLECTION_DOCS].find_one(
            {
                "id": doc_id,
                "demande_id": demande_id,
                "user_id": TENANT_USER_ID,
                "is_deleted": {"$ne": True},
            },
            {"_id": 0},
        )
        if not parent or not parent.get("retour_obligatoire"):
            raise HTTPException(status_code=404, detail="Document à retourner introuvable")
        if not parent.get("retour_document_id"):
            raise HTTPException(status_code=422, detail="L'agent n'a pas encore déposé le document complété")
        if parent.get("retour_confirme_at"):
            return public_doc(parent)
        stamp = now_iso()
        await db[COLLECTION_DOCS].update_one(
            {"id": doc_id, "demande_id": demande_id},
            {"$set": {
                "retour_confirme_at": stamp,
                "retour_confirme_by": actor_name(user),
                "retour_recu_at": stamp,
                "retour_recu_by": actor_name(user),
            }},
        )
        await db[COLLECTION].update_one(
            {"id": demande_id, "user_id": TENANT_USER_ID},
            {
                "$set": {"updated_at": stamp},
                "$push": {
                    "historique": history(
                        "Retour confirmé",
                        user,
                        parent.get("original_filename") or "",
                    )
                },
            },
        )
        fresh = await db[COLLECTION_DOCS].find_one(
            {"id": doc_id, "demande_id": demande_id},
            {"_id": 0, "storage_path": 0, "storage_path_legacy": 0},
        )
        return public_doc(fresh or parent)
