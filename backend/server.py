from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Query, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import re
import io
import zipfile
import asyncio
import inspect
import requests
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from access_control import (
    User,
    LoginRequest,
    UserCreate,
    UserUpdate,
    PasswordReset,
    ChangePasswordRequest,
    TENANT_USER_ID,
    ROLES,
    ROLE_LABELS,
    ROLE_ADMIN,
    ROLE_CEO,
    ROLE_GESTIONNAIRE_OFFRES,
    ROLE_CONSEILLER,
    hash_password,
    verify_password,
    display_name,
    permission_storage_fields,
    default_permissions,
    default_see_all_dossiers,
    PERMISSION_CATALOG,
    PERM_USERS_MANAGE,
    public_user,
    is_global_viewer,
    can_access_client,
    labels_match_conseiller,
    require_admin,
    require_settings,
    clients_base_query,
    force_conseiller_on_write,
    create_session,
    resolve_session_user,
    ensure_bootstrap_admin,
    accessible_client_ids,
    enforce_route_permission,
)
from pdf_generator import (
    list_templates,
    list_demand_packs,
    generate_document_pdf,
    generate_demand_pack,
    generate_decompte_letters,
    get_template,
    extract_pension_funds_from_pdf,
    extract_pension_funds_from_pdf_with_text,
    extract_3p_expiry_from_pdf,
    extract_3p_contracts_from_pdf,
    fill_pdf_bytes_with_client,
    prepare_library_form_pdf,
    render_pdf_page_png,
    repair_library_pdf_bytes,
    resolve_lpp_person,
    tag_lpp_funds_with_person,
    merge_lpp_detected_funds,
    CRM_FIELD_SOURCES,
    DEMAND_PACKS,
    DOCUMENT_TYPES_3P,
)
from offre_extract import extract_offre_fields, offre_fields_for_storage, NON_INDIQUE
from data_crypto_keys import EncryptionNotConfigured, encryption_configured
from field_crypto import (
    decrypt_client_fields,
    encrypt_client_fields,
    patch_encrypt_sensitive,
)
from storage_crypto import decrypt_blob, encrypt_blob
from suivi_3p import (
    SUIVI_3P_STATUTS,
    DEFAULT_SUIVI_3P_STATUT,
    ANALYSE_DOC_CATEGORY,
    COURRIER_KIND,
    COURRIER_DISPLAY_PREFIX,
    GAIN_OPTIM_MIN_EXCLUSIVE,
    COLLECTION_CLIENTS as SUIVI_3P_CLIENTS,
    COLLECTION_DOCS as SUIVI_3P_DOCS,
    COLLECTION_PENDING as SUIVI_3P_PENDING,
    normalize_statut as normalize_suivi_statut,
    parse_gain,
    extract_economie_fiscale_from_pdf,
    suivi_3p_base_query,
    can_access_suivi_client,
    serialize_suivi_client,
    analyse_summary_from_docs,
    is_offre_envoyee_eligible,
    build_new_client,
    compute_stats as compute_suivi_stats,
    parse_analyse_pdf_filename,
    build_client_name_index,
    find_clients_for_pdf_name,
    filter_suivi_3p_rows,
    build_suivi_3p_export_xlsx,
    build_suivi_3p_phone_export_xlsx,
    normalize_export_columns,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

if os.environ.get("DATABASE_URL"):
    from postgres_mongo_compat import PostgresMongoCompatDB

    db = PostgresMongoCompatDB()
else:
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ['MONGO_URL']
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

@app.get("/health")
async def health_check():
    return JSONResponse(status_code=200, content={"status": "ok"})

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------- Object Storage (S3) ----------------
import object_storage

APP_NAME = "prevoyance-crm"
# Catégories historiquement partagées avant le partage global couple (conservé pour rétrocompatibilité).
SHARED_DOSSIER_DOC_CATEGORIES = frozenset({"Analyse de prévoyance", "Offre"})

MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    "json": "application/json", "csv": "text/csv", "txt": "text/plain",
    "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

def init_storage():
    """Vérifie que le stockage S3 Infomaniak est configuré."""
    if not object_storage.configured():
        raise RuntimeError(
            "S3 non configuré (S3_ENDPOINT_URL / S3_ACCESS_KEY / S3_SECRET_KEY / S3_BUCKET)."
        )
    return "s3"


def _allow_local_storage() -> bool:
    """
    Repli disque local interdit en prod Railway (fichiers ephemeres).
    Autorise en local/dev, ou si ALLOW_LOCAL_STORAGE=true.
    """
    explicit = (os.environ.get("ALLOW_LOCAL_STORAGE") or "").strip().lower()
    if explicit in ("1", "true", "yes", "y", "on"):
        return True
    if explicit in ("0", "false", "no", "n", "off"):
        return False
    # Defaut: interdit si on detecte Railway
    if (os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_SERVICE_ID") or "").strip():
        return False
    return True


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_local_path(storage_path: str) -> Path:
    """
    Resolve local:// paths under ROOT_DIR only (blocks path traversal).
    """
    if not storage_path.startswith("local://"):
        raise ValueError("Not a local:// storage_path")
    rel = storage_path.replace("local://", "", 1).lstrip("/").replace("\\", "/")
    if not rel or ".." in Path(rel).parts:
        raise FileNotFoundError(storage_path)
    root = ROOT_DIR.resolve()
    candidate = (ROOT_DIR / rel).resolve()
    if not _is_relative_to(candidate, root):
        raise FileNotFoundError(storage_path)
    return candidate


def _local_storage_fallback(relative_dir: Path, filename: str, data: bytes) -> str:
    if not _allow_local_storage():
        raise RuntimeError(
            "Stockage distant indisponible et ALLOW_LOCAL_STORAGE=false "
            "(evite la perte de fichiers sur disque ephemere)."
        )
    safe_name = Path(filename).name
    if not safe_name or safe_name in (".", ".."):
        raise ValueError("Nom de fichier local invalide")
    relative_dir.mkdir(parents=True, exist_ok=True)
    target = (relative_dir / safe_name).resolve()
    if not _is_relative_to(target, ROOT_DIR.resolve()):
        raise RuntimeError("Chemin local hors ROOT_DIR refusé")
    raw = _coerce_file_bytes(data, label="local fallback")
    to_store = encrypt_blob(raw) if encryption_configured() else raw
    target.write_bytes(to_store)
    rel = target.relative_to(ROOT_DIR.resolve()).as_posix()
    return f"local://{rel}"


def public_storage_record(doc: Optional[dict]) -> Optional[dict]:
    """Strip internal storage keys before returning documents to the browser."""
    if not doc:
        return doc
    out = {
        k: v
        for k, v in doc.items()
        if k not in ("_id", "storage_path", "storage_path_legacy", "docx_storage_path", "docx_bytes")
    }
    if doc.get("docx_storage_path") or doc.get("has_word_download") or doc.get("docx_filename"):
        out["has_word_download"] = True
        if doc.get("docx_filename"):
            out["docx_filename"] = doc["docx_filename"]
    return out


_DOWNLOAD_FILENAME_FORBIDDEN = set('<>:"/\\|?*')


def _looks_like_storage_key_filename(name: str) -> bool:
    """True if name is a UUID / opaque storage key rather than a registered title."""
    stem = Path(str(name or "")).stem.strip()
    if not stem:
        return True
    try:
        uuid.UUID(stem)
        return True
    except ValueError:
        pass
    compact = stem.replace("-", "")
    if len(compact) >= 32 and all(c in "0123456789abcdefABCDEF" for c in compact):
        return True
    return False


def _sanitize_download_filename(name: Optional[str], fallback: str = "document.pdf") -> str:
    """Keep the registered name; only strip chars unsafe for Content-Disposition / filesystem."""
    raw = (name or "").strip() or fallback
    # Never expose a storage path — basename only
    raw = raw.replace("\\", "/").split("/")[-1].strip() or fallback
    cleaned = "".join(
        ch for ch in raw if ch >= " " and ch not in '"' and ch not in _DOWNLOAD_FILENAME_FORBIDDEN
    )
    cleaned = cleaned.replace("\r", "").replace("\n", "").strip(" .") or fallback
    return cleaned[:180]


def _resolve_download_filename(
    record: Optional[dict],
    fallback: str = "document.pdf",
    *,
    prefer_keys: Optional[tuple] = None,
) -> str:
    """
    Nom présenté au téléchargement = nom enregistré à l'upload / affiché en UI.
    Ne jamais utiliser storage_path ni une clé UUID.
    """
    rec = record or {}
    keys = prefer_keys or ("original_filename", "docx_filename", "filename", "title")
    for key in keys:
        candidate = rec.get(key)
        if candidate is None:
            continue
        text = str(candidate).strip()
        if not text:
            continue
        safe = _sanitize_download_filename(text, fallback="")
        if safe and not _looks_like_storage_key_filename(safe):
            return safe
    return _sanitize_download_filename(fallback)


def _content_disposition(disposition: str, filename: str) -> str:
    """Safe Content-Disposition (ASCII fallback + RFC 5987 UTF-8)."""
    from urllib.parse import quote

    safe = _sanitize_download_filename(filename)
    ascii_name = safe.encode("ascii", "ignore").decode("ascii").strip() or "document.pdf"
    if not any(c.isalnum() for c in ascii_name):
        ascii_name = "document.pdf"
    utf8_name = quote(safe, safe="")
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


def _file_response_headers(filename: str, inline: bool = True) -> dict:
    disposition = "inline" if inline else "attachment"
    return {
        "Content-Disposition": _content_disposition(disposition, filename),
        "Cache-Control": "private, no-store, no-cache, must-revalidate",
        "X-Content-Type-Options": "nosniff",
        "Pragma": "no-cache",
    }


def put_object(path: str, data: bytes, content_type: str, *, encrypt: bool = True) -> dict:
    """Upload vers S3. Jamais d'URL publique."""
    data = _coerce_file_bytes(data, label="put_object")
    if encrypt and encryption_configured():
        data = encrypt_blob(data)
    if not object_storage.configured():
        raise RuntimeError("S3 non configuré — upload impossible.")
    return object_storage.put_object(path, data, content_type)


def get_object(path: str):
    """Téléchargement depuis S3 (s3://). Proxy serveur uniquement."""
    if not isinstance(path, str) or not path.startswith(object_storage.S3_PREFIX):
        raise FileNotFoundError(f"Chemin storage non supporté (S3 attendu): {(path or '')[:120]}")
    data, ctype = object_storage.get_object(path)
    data = _coerce_file_bytes(data, label="s3 get_object")
    return decrypt_blob(data), ctype


def _coerce_file_bytes(value, *, label: str = "fichier") -> bytes:
    """Garantit un objet bytes (refuse les coroutines non résolues)."""
    if inspect.isawaitable(value):
        raise TypeError(
            f"{label}: coroutine non awaitée — un await manque avant l'usage des bytes"
        )
    if isinstance(value, memoryview):
        value = value.tobytes()
    elif isinstance(value, bytearray):
        value = bytes(value)
    if not isinstance(value, bytes):
        raise TypeError(f"{label}: bytes attendus, reçu {type(value).__name__}")
    return value


def _read_storage_bytes(storage_path: str) -> bytes:
    """Lecture synchrone sécurisée (S3 / local jailed) + déchiffrement."""
    storage_path = (storage_path or "").strip()
    if not storage_path:
        raise FileNotFoundError("empty storage_path")
    if storage_path.startswith("local://"):
        local_path = _safe_local_path(storage_path)
        if not local_path.is_file():
            raise FileNotFoundError(storage_path)
        raw = _coerce_file_bytes(local_path.read_bytes(), label="local storage")
        return decrypt_blob(raw)
    data, _ctype = get_object(storage_path)
    return _coerce_file_bytes(data, label="object storage")


def _write_storage_bytes(storage_path: str, data: bytes, content_type: str = "application/pdf") -> str:
    data = _coerce_file_bytes(data, label="write storage")
    if storage_path.startswith("local://"):
        if not _allow_local_storage():
            raise RuntimeError("Ecriture local:// interdite (ALLOW_LOCAL_STORAGE=false)")
        local_path = _safe_local_path(storage_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        to_store = encrypt_blob(data) if encryption_configured() else data
        local_path.write_bytes(to_store)
        return storage_path
    try:
        result = put_object(storage_path, data, content_type)
        return result["path"]
    except Exception:
        local_name = storage_path.replace("/", "_")
        return _local_storage_fallback(ROOT_DIR / "form_library_fallback", local_name, data)


async def _resolve_maybe_awaitable(value):
    """Résout une coroutine/awaitable oubliée ; laisse passer les valeurs sync."""
    if inspect.isawaitable(value):
        return await value
    return value


async def _load_storage_bytes(storage_path: str) -> bytes:
    """Lecture storage depuis un handler async (thread + validation bytes)."""
    data = await asyncio.to_thread(_read_storage_bytes, storage_path)
    data = await _resolve_maybe_awaitable(data)
    return _coerce_file_bytes(data, label="storage")


async def _try_read_storage_bytes(storage_path: str) -> Optional[bytes]:
    """Lecture async tolérante (None si échec) — utilisée par analyse Suivi 3P."""
    if not storage_path:
        return None
    try:
        return await _load_storage_bytes(storage_path)
    except Exception as e:
        logger.warning("Lecture storage échouée (%s): %s", storage_path, e)
        return None
# ---------------- Constants ----------------
STATUTS = [
    "Nouveau",
    "Documents en attente",
    "Analyse en cours",
    "Stand-by",
    "À présenter",
    "Clôturé",
]

# Anciens libellés → workflow simplifié
STATUT_LEGACY_MAP = {
    "Documents demandés": "Documents en attente",
    "Documents reçus": "Analyse en cours",
    "Rapport en préparation": "Analyse en cours",
    "À présenter au client": "À présenter",
}


def normalize_statut(statut: Optional[str]) -> str:
    if not statut:
        return "Nouveau"
    if statut in STATUTS:
        return statut
    return STATUT_LEGACY_MAP.get(statut, statut)

# ---------------- Models ----------------
class ClientBase(BaseModel):
    prenom: str = ""
    nom: str = ""
    date_naissance: Optional[str] = None
    sexe: Optional[str] = None
    nationalite: Optional[str] = None
    pays_residence: Optional[str] = None
    frontalier: Optional[str] = None  # "oui" | "non" | None/""
    avs_number: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    adresse: Optional[str] = None
    npa: Optional[str] = None
    ville: Optional[str] = None
    etat_civil: Optional[str] = None
    nombre_enfants: Optional[int] = 0
    conjoint: Optional[str] = None
    employeur: Optional[str] = None
    profession: Optional[str] = None
    taux_activite: Optional[str] = None
    salaire_annuel: Optional[float] = None
    conseiller: Optional[str] = None
    conseiller_finma: Optional[str] = None
    agent_apporteur: Optional[str] = None
    linked_spouse_id: Optional[str] = None
    dossier_id: Optional[str] = None
    dossier_label: Optional[str] = None
    echeance_3p: Optional[str] = None
    # Multi-contrats 3e pilier : une ligne par contrat (compagnie + n° + échéance)
    echeances_3p: Optional[List[dict]] = None
    statut: str = "Nouveau"
    priorite: str = "normale"

class ClientCreate(ClientBase):
    """activites: prevoyance | fiscalite | offre | autre (multi-sélection)."""
    activites: Optional[List[str]] = None

class NoteCreate(BaseModel):
    content: str

class NoteUpdate(BaseModel):
    content: str

class DemandeCreate(BaseModel):
    """Rappel (ex-demande). date=YYYY-MM-DD, heure=HH:MM."""
    titre: str
    description: Optional[str] = None
    date: Optional[str] = None
    heure: Optional[str] = None
    priorite: Optional[str] = "normale"
    client_id: Optional[str] = None  # pour POST /rappels global
    send_email: Optional[bool] = True
    notify_crm: Optional[bool] = True

class DemandeUpdate(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    heure: Optional[str] = None
    priorite: Optional[str] = None
    done: Optional[bool] = None
    statut: Optional[str] = None
    client_id: Optional[str] = None
    send_email: Optional[bool] = None
    notify_crm: Optional[bool] = None


class DemandeReporter(BaseModel):
    """Reporter un rappel (+14 j par défaut depuis la date actuelle du rappel)."""
    date: Optional[str] = None
    heure: Optional[str] = None
    days: int = 14

class StatutUpdate(BaseModel):
    statut: str

class DocumentChecklistUpdate(BaseModel):
    document_checklist: dict

class GenerateDocumentRequest(BaseModel):
    template_id: str
    custom_filename: Optional[str] = None
    checklist_item: Optional[str] = None

class GenerateLibraryFormRequest(BaseModel):
    library_form_id: str
    custom_filename: Optional[str] = None

class UpdateFormLibraryRequest(BaseModel):
    name: Optional[str] = None
    field_mapping: Optional[dict] = None

class TestLibraryFormRequest(BaseModel):
    client_id: str
    field_mapping: Optional[dict] = None

class GenerateDemandRequest(BaseModel):
    pack_id: str

class GenerateDecompteRequest(BaseModel):
    funds: List[dict] = Field(default_factory=list)

class Echeance3PUpdate(BaseModel):
    echeance_3p: Optional[str] = None

class Echeance3PLineUpdate(BaseModel):
    # Permet de corriger manuellement compagnie / n° de police / date / type
    # et un suivi simple de rachat (sans nouveau statut métier).
    echeance_3p: Optional[str] = None
    company: Optional[str] = None
    policy_number: Optional[str] = None
    document_type: Optional[str] = None
    rachat_effectue: Optional[bool] = None
    rachat_doc_id: Optional[str] = None
    rachat_doc_filename: Optional[str] = None

class Echeance3PLineCreate(BaseModel):
    company: Optional[str] = None
    policy_number: Optional[str] = None
    echeance_3p: Optional[str] = None
    document_type: Optional[str] = None

class Suivi3PUpdate(BaseModel):
    prenom: Optional[str] = None
    nom: Optional[str] = None
    date_naissance: Optional[str] = None
    etat_civil: Optional[str] = None
    nombre_enfants: Optional[int] = None
    conseiller: Optional[str] = None
    conjoint: Optional[str] = None
    conjoint_prenom: Optional[str] = None
    conjoint_nom: Optional[str] = None
    conjoint_date_naissance: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    adresse: Optional[str] = None
    npa: Optional[str] = None
    ville: Optional[str] = None
    adresse_complement: Optional[str] = None
    pays: Optional[str] = None
    sexe: Optional[str] = None
    statut: Optional[str] = None
    gain_fiscal_estime: Optional[float] = None
    date_derniere_analyse: Optional[str] = None
    client_contacte: Optional[bool] = None
    rdv_pris: Optional[bool] = None
    date_rdv: Optional[str] = None
    notes: Optional[str] = None


class Suivi3PAssignPending(BaseModel):
    client_id: str


class Suivi3PCourriersRequest(BaseModel):
    client_ids: Optional[List[str]] = None
    replace_existing: Optional[bool] = True


class Suivi3PBulkStatutRequest(BaseModel):
    statut: str
    client_ids: Optional[List[str]] = None
    # Si True (défaut pour « Offre envoyée ») : uniquement clients avec PDF/gain courrier
    only_offre_eligible: Optional[bool] = None


class Suivi3PCreate(BaseModel):
    prenom: str
    nom: str
    date_naissance: Optional[str] = None
    etat_civil: Optional[str] = None
    nombre_enfants: Optional[int] = 0
    conseiller: Optional[str] = None
    conjoint: Optional[str] = None
    conjoint_prenom: Optional[str] = None
    conjoint_nom: Optional[str] = None
    conjoint_date_naissance: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    adresse: Optional[str] = None
    npa: Optional[str] = None
    ville: Optional[str] = None
    adresse_complement: Optional[str] = None
    pays: Optional[str] = None
    sexe: Optional[str] = None
    statut: Optional[str] = DEFAULT_SUIVI_3P_STATUT
    gain_fiscal_estime: Optional[float] = None
    date_derniere_analyse: Optional[str] = None
    client_contacte: Optional[bool] = False
    rdv_pris: Optional[bool] = False
    date_rdv: Optional[str] = None
    notes: Optional[str] = None
    client_id: Optional[str] = None  # lien vers la base Clients hub


class LppCaisseTrackingUpdate(BaseModel):
    lpp_caisse_tracking: List[dict] = Field(default_factory=list)

class CreateSpouseRequest(BaseModel):
    prenom: str = ""
    nom: str = ""
    date_naissance: Optional[str] = None
    sexe: Optional[str] = None
    avs_number: Optional[str] = None

class AppointmentCreate(BaseModel):
    titre: str
    date: str
    duree: Optional[int] = 60
    lieu: Optional[str] = None
    type: Optional[str] = "Rendez-vous"
    notes: Optional[str] = None
    client_id: Optional[str] = None

class TaskCreate(BaseModel):
    titre: str
    echeance: Optional[str] = None
    priorite: Optional[str] = "normale"
    client_id: Optional[str] = None

# ---------------- Auth ----------------
async def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> User:
    user = await resolve_session_user(db, request, authorization)
    enforce_route_permission(user, request.method, request.url.path)
    return user


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60,
    )


@api_router.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    email = payload.email.strip().lower()
    doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not doc or not verify_password(payload.password, doc.get("password_hash") or ""):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if doc.get("active") is False:
        raise HTTPException(status_code=403, detail="Compte désactivé")
    token = await create_session(db, doc["user_id"])
    _set_session_cookie(response, token)
    fresh = await db.users.find_one({"user_id": doc["user_id"]}, {"_id": 0})
    return {"user": public_user(fresh or doc), "session_token": token}


@api_router.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)):
    doc = await db.users.find_one({"user_id": user.account_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return public_user(doc)


@api_router.post("/auth/logout")
async def logout(response: Response, request: Request):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@api_router.post("/auth/change-password")
async def change_own_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user)):
    """Chaque utilisateur peut modifier son propre mot de passe."""
    doc = await db.users.find_one({"user_id": user.account_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if not verify_password(payload.current_password, doc.get("password_hash") or ""):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    if len(payload.new_password or "") < 6:
        raise HTTPException(status_code=400, detail="Nouveau mot de passe trop court (min. 6)")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit être différent")
    await db.users.update_one(
        {"user_id": user.account_id},
        {"$set": {"password_hash": hash_password(payload.new_password)}},
    )
    # Invalider les autres sessions sauf celle en cours n'est pas simple sans token ici ;
    # on garde la session actuelle pour ne pas déconnecter l'utilisateur.
    return {"ok": True}


# ---------------- Users (admin) ----------------
@api_router.get("/users/roles")
async def list_roles(user: User = Depends(get_current_user)):
    require_admin(user)
    return [{"id": r, "label": ROLE_LABELS[r]} for r in ROLES]


@api_router.get("/users/permissions-catalog")
async def permissions_catalog(user: User = Depends(get_current_user)):
    require_admin(user)
    return {
        "catalog": PERMISSION_CATALOG,
        "defaults": {
            ROLE_ADMIN: {
                "see_all_dossiers": default_see_all_dossiers(ROLE_ADMIN),
                "permissions": default_permissions(ROLE_ADMIN),
            },
            ROLE_CEO: {
                "see_all_dossiers": default_see_all_dossiers(ROLE_CEO),
                "permissions": default_permissions(ROLE_CEO),
            },
            ROLE_GESTIONNAIRE_OFFRES: {
                "see_all_dossiers": default_see_all_dossiers(ROLE_GESTIONNAIRE_OFFRES),
                "permissions": default_permissions(ROLE_GESTIONNAIRE_OFFRES),
            },
            ROLE_CONSEILLER: {
                "see_all_dossiers": default_see_all_dossiers(ROLE_CONSEILLER),
                "permissions": default_permissions(ROLE_CONSEILLER),
            },
        },
    }


def _conseiller_name_key(name: Optional[str]) -> str:
    from conseiller_identity import normalize_conseiller_key

    return normalize_conseiller_key(name)


async def lookup_conseiller_finma(name: Optional[str]) -> str:
    key = _conseiller_name_key(name)
    if not key:
        return ""
    try:
        prof = await db.conseiller_profiles.find_one({"name_key": key}, {"_id": 0, "finma_number": 1})
        if prof and str(prof.get("finma_number") or "").strip():
            return str(prof.get("finma_number") or "").strip()
    except Exception:
        logger.exception("lookup conseiller_profiles échoué")
    try:
        async for u in db.users.find(
            {"active": {"$ne": False}, "finma_number": {"$nin": [None, ""]}},
            {"_id": 0, "conseiller": 1, "name": 1, "finma_number": 1},
        ):
            n = (u.get("conseiller") or u.get("name") or "").strip()
            if _conseiller_name_key(n) == key:
                return str(u.get("finma_number") or "").strip()
    except Exception:
        logger.exception("lookup users.finma_number échoué")
    return ""


async def upsert_conseiller_finma(name: Optional[str], finma_number: Optional[str]) -> str:
    """Source de vérité du N° FINMA au niveau du conseiller (nom)."""
    clean_name = (name or "").strip()
    finma = (finma_number or "").strip()
    if not clean_name:
        return ""
    key = _conseiller_name_key(clean_name)
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.conseiller_profiles.update_one(
            {"name_key": key},
            {
                "$set": {
                    "name": clean_name,
                    "name_key": key,
                    "finma_number": finma,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
    except Exception:
        logger.exception("upsert conseiller_profiles échoué — fallback users uniquement")
    try:
        async for u in db.users.find({}, {"_id": 0, "user_id": 1, "conseiller": 1, "name": 1}):
            n = (u.get("conseiller") or u.get("name") or "").strip()
            if _conseiller_name_key(n) == key:
                await db.users.update_one(
                    {"user_id": u["user_id"]},
                    {"$set": {"finma_number": finma or None}},
                )
    except Exception:
        logger.exception("sync users.finma_number échoué")
    return finma


async def attach_conseiller_finma(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    name = (doc.get("conseiller") or "").strip()
    try:
        doc["conseiller_finma"] = await lookup_conseiller_finma(name) if name else ""
    except Exception:
        logger.exception("attach_conseiller_finma échoué")
        doc["conseiller_finma"] = doc.get("conseiller_finma") or ""
    return doc


@api_router.get("/users/conseillers")
async def list_conseiller_names(user: User = Depends(get_current_user)):
    """
    Collaborateurs actifs pour attribution de dossier / filtres.
    Même source que la page Utilisateurs (db.users, active ≠ false),
    libellé = nom complet (comme dans la gestion des utilisateurs).
    """
    del user  # auth only
    finma_by_key: Dict[str, str] = {}

    try:
        async for p in db.conseiller_profiles.find({}, {"_id": 0, "name": 1, "name_key": 1, "finma_number": 1}):
            n = (p.get("name") or "").strip()
            if not n or not str(p.get("finma_number") or "").strip():
                continue
            key = p.get("name_key") or _conseiller_name_key(n)
            finma_by_key[key] = str(p.get("finma_number") or "").strip()
    except Exception:
        logger.exception("list conseiller_profiles échoué")

    rows_raw = await db.users.find(
        {"active": {"$ne": False}},
        {
            "_id": 0,
            "conseiller": 1,
            "name": 1,
            "prenom": 1,
            "nom": 1,
            "finma_number": 1,
        },
    ).to_list(500)
    rows_raw.sort(
        key=lambda u: ((u.get("nom") or "").lower(), (u.get("prenom") or "").lower())
    )

    out = []
    seen = set()
    for u in rows_raw:
        full_name = (
            (u.get("name") or "").strip()
            or display_name(u.get("prenom") or "", u.get("nom") or "").strip()
            or (u.get("conseiller") or "").strip()
        )
        if not full_name:
            continue
        key = _conseiller_name_key(full_name)
        if key in seen:
            continue
        seen.add(key)
        finma = str(u.get("finma_number") or "").strip()
        if not finma:
            finma = finma_by_key.get(key) or ""
            cons_key = _conseiller_name_key(u.get("conseiller") or "")
            if not finma and cons_key:
                finma = finma_by_key.get(cons_key) or ""
        out.append({"name": full_name, "finma_number": finma})
    return out


@api_router.get("/users")
async def list_users(user: User = Depends(get_current_user)):
    require_admin(user)
    rows = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    rows.sort(key=lambda u: ((u.get("nom") or "").lower(), (u.get("prenom") or "").lower()))
    return [public_user({**r, "password_hash": ""}) for r in rows]


@api_router.post("/users")
async def create_user(payload: UserCreate, user: User = Depends(get_current_user)):
    require_admin(user)
    role = payload.role if payload.role in ROLES else ROLE_CONSEILLER
    email = payload.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Cet e-mail est déjà utilisé")
    if len(payload.password or "") < 6:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (min. 6)")
    name = display_name(payload.prenom, payload.nom)
    conseiller = (payload.conseiller or "").strip() or (name if role == ROLE_CONSEILLER else None)
    account_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": account_id,
        "email": email,
        "prenom": payload.prenom.strip(),
        "nom": payload.nom.strip(),
        "name": name,
        "telephone": (payload.telephone or "").strip() or None,
        "picture": None,
        "role": role,
        "conseiller": conseiller,
        "finma_number": (payload.finma_number or "").strip() or None,
        "active": True,
        "password_hash": hash_password(payload.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "receive_conseiller_rappel_copies": bool(payload.receive_conseiller_rappel_copies)
        if role == ROLE_ADMIN
        else False,
        **permission_storage_fields(role, payload.permissions, payload.see_all_dossiers),
    }
    await db.users.insert_one(doc)
    if conseiller:
        await upsert_conseiller_finma(conseiller, doc.get("finma_number"))
    return public_user(doc)


@api_router.put("/users/{account_id}")
async def update_user(account_id: str, payload: UserUpdate, user: User = Depends(get_current_user)):
    require_admin(user)
    doc = await db.users.find_one({"user_id": account_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    updates = {}
    if payload.prenom is not None:
        updates["prenom"] = payload.prenom.strip()
    if payload.nom is not None:
        updates["nom"] = payload.nom.strip()
    if payload.email is not None:
        email = payload.email.strip().lower()
        other = await db.users.find_one({"email": email, "user_id": {"$ne": account_id}})
        if other:
            raise HTTPException(status_code=400, detail="Cet e-mail est déjà utilisé")
        updates["email"] = email
    if payload.telephone is not None:
        updates["telephone"] = payload.telephone.strip() or None
    if payload.role is not None:
        if payload.role not in ROLES:
            raise HTTPException(status_code=400, detail="Rôle invalide")
        updates["role"] = payload.role
    if payload.conseiller is not None:
        updates["conseiller"] = payload.conseiller.strip() or None
    if payload.finma_number is not None:
        updates["finma_number"] = payload.finma_number.strip() or None
    if payload.active is not None:
        if account_id == user.account_id and payload.active is False:
            raise HTTPException(status_code=400, detail="Vous ne pouvez pas désactiver votre propre compte")
        updates["active"] = payload.active
    if payload.receive_conseiller_rappel_copies is not None:
        role_for_flag = updates.get("role", doc.get("role"))
        if role_for_flag == ROLE_ADMIN:
            updates["receive_conseiller_rappel_copies"] = bool(payload.receive_conseiller_rappel_copies)
        else:
            updates["receive_conseiller_rappel_copies"] = False
    prenom = updates.get("prenom", doc.get("prenom") or "")
    nom = updates.get("nom", doc.get("nom") or "")
    updates["name"] = display_name(prenom, nom)
    role = updates.get("role", doc.get("role"))
    if role == ROLE_CONSEILLER and not updates.get("conseiller", doc.get("conseiller")):
        updates["conseiller"] = updates["name"]
    if role != ROLE_ADMIN and "receive_conseiller_rappel_copies" not in updates:
        updates["receive_conseiller_rappel_copies"] = False
    if payload.permissions is not None or payload.see_all_dossiers is not None or payload.role is not None:
        perms_in = payload.permissions if payload.permissions is not None else (
            None if payload.role is not None else doc.get("permissions")
        )
        see_all_in = payload.see_all_dossiers
        if see_all_in is None and payload.role is None:
            see_all_in = doc.get("see_all_dossiers")
        updates.update(permission_storage_fields(role, perms_in, see_all_in))
        if account_id == user.account_id and not updates.get("permissions", {}).get(PERM_USERS_MANAGE):
            raise HTTPException(
                status_code=400,
                detail="Vous ne pouvez pas retirer votre propre droit de gérer les utilisateurs",
            )
    await db.users.update_one({"user_id": account_id}, {"$set": updates})
    fresh = await db.users.find_one({"user_id": account_id}, {"_id": 0})
    cons_name = (fresh or {}).get("conseiller") or (fresh or {}).get("name")
    if cons_name and ("finma_number" in updates or "conseiller" in updates):
        await upsert_conseiller_finma(cons_name, (fresh or {}).get("finma_number"))
    return public_user(fresh)


@api_router.post("/users/{account_id}/reset-password")
async def reset_user_password(account_id: str, payload: PasswordReset, user: User = Depends(get_current_user)):
    require_admin(user)
    if len(payload.password or "") < 6:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (min. 6)")
    res = await db.users.update_one(
        {"user_id": account_id},
        {"$set": {"password_hash": hash_password(payload.password)}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    await db.user_sessions.delete_many({"user_id": account_id})
    return {"ok": True}


@api_router.post("/users/{account_id}/deactivate")
async def deactivate_user(account_id: str, user: User = Depends(get_current_user)):
    require_admin(user)
    if account_id == user.account_id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas désactiver votre propre compte")
    res = await db.users.update_one({"user_id": account_id}, {"$set": {"active": False}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    await db.user_sessions.delete_many({"user_id": account_id})
    return {"ok": True}


# ---------------- Helpers ----------------
def _decrypt_client_doc(doc: Optional[dict]) -> Optional[dict]:
    """Déchiffre les champs PII pour exposition API / PDF (dual-read clair legacy)."""
    if not doc:
        return doc
    try:
        return decrypt_client_fields(doc)
    except EncryptionNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


def _encrypt_client_for_storage(doc: dict) -> dict:
    """Chiffre les champs PII avant persistance (no-op si clé absente — mode dev)."""
    if not encryption_configured():
        return doc
    try:
        return encrypt_client_fields(doc)
    except EncryptionNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


def _encrypt_client_patch(updates: dict) -> dict:
    if not encryption_configured():
        return updates
    try:
        return patch_encrypt_sensitive(updates)
    except EncryptionNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


async def require_client(client_id: str, user: User) -> dict:
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    if not can_access_client(user, c):
        raise HTTPException(status_code=403, detail="Accès non autorisé à ce dossier")
    return _decrypt_client_doc(c)


async def require_resource_client(resource: dict, user: User, label: str = "Ressource"):
    cid = resource.get("client_id")
    if cid:
        client = await db.clients.find_one({"id": cid, "user_id": user.user_id}, {"_id": 0})
        if not client:
            raise HTTPException(status_code=404, detail="Client introuvable")
        if can_access_client(user, client):
            return
        scope = await _dossier_scope(user.user_id, client)
        if _is_couple_scope(scope):
            for mid in scope["member_ids"]:
                if mid == cid:
                    continue
                member = await db.clients.find_one({"id": mid, "user_id": user.user_id}, {"_id": 0})
                if member and can_access_client(user, member):
                    return
        raise HTTPException(status_code=403, detail=f"Accès non autorisé — {label}")
    if is_global_viewer(user):
        return
    if labels_match_conseiller(resource.get("conseiller"), user):
        return
    if resource.get("created_by") == user.account_id:
        return
    raise HTTPException(status_code=403, detail=f"Accès non autorisé — {label}")


async def log_action(user_id: str, client_id: str, description: str, dossier_id: Optional[str] = None):
    await db.actions.insert_one({
        "id": str(uuid.uuid4()), "user_id": user_id, "client_id": client_id,
        "dossier_id": dossier_id,
        "description": description, "created_at": datetime.now(timezone.utc).isoformat(),
    })

async def next_dossier_number(user_id: str) -> str:
    # Compte les dossiers distincts (pas chaque conjoint)
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": {"$ifNull": ["$dossier_id", "$id"]}}},
        {"$count": "n"},
    ]
    rows = await db.clients.aggregate(pipeline).to_list(1)
    count = rows[0]["n"] if rows else 0
    return f"DOS-{count + 1:04d}"


def _parse_conjoint_name(client: dict) -> tuple[str, str]:
    cp = (client.get("conjoint_prenom") or "").strip()
    cn = (client.get("conjoint_nom") or "").strip()
    if cp or cn:
        return cp, cn
    full = (client.get("conjoint") or "").strip()
    if not full:
        return "", ""
    parts = full.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return parts[0], ""


def _person_name_key(prenom: Optional[str], nom: Optional[str]) -> str:
    return f"{(prenom or '').strip()} {(nom or '').strip()}".strip().casefold()


async def _resolve_spouse_ids_by_name(user_id: str, client: dict) -> List[str]:
    """Retrouve le conjoint via prénom/nom ou le champ conjoint (couples non liés)."""
    cp, cn = _parse_conjoint_name(client)
    my_key = _person_name_key(client.get("prenom"), client.get("nom"))
    found: List[str] = []

    if cp and cn:
        matches = await db.clients.find(
            {
                "user_id": user_id,
                "id": {"$ne": client["id"]},
                "prenom": {"$regex": f"^{re.escape(cp)}$", "$options": "i"},
                "nom": {"$regex": f"^{re.escape(cn)}$", "$options": "i"},
            },
            {"id": 1},
        ).to_list(20)
        found.extend(m["id"] for m in matches)

    if my_key:
        candidates = await db.clients.find(
            {
                "user_id": user_id,
                "id": {"$ne": client["id"]},
                "conjoint": {"$exists": True, "$nin": [None, ""]},
            },
            {"id": 1, "conjoint": 1, "conjoint_prenom": 1, "conjoint_nom": 1},
        ).to_list(500)
        for row in candidates:
            other_key = _person_name_key(row.get("conjoint_prenom"), row.get("conjoint_nom"))
            if not other_key:
                other_key = (row.get("conjoint") or "").strip().casefold()
            if other_key == my_key:
                found.append(row["id"])

    return list(dict.fromkeys(found))


async def _collect_dossier_ids(user_id: str, member_ids: List[str], fallback: str) -> List[str]:
    ids = {fallback}
    if not member_ids:
        return list(ids)
    rows = await db.clients.find(
        {"user_id": user_id, "id": {"$in": member_ids}},
        {"id": 1, "dossier_id": 1},
    ).to_list(200)
    for row in rows:
        ids.add(row.get("dossier_id") or row["id"])
    return list(ids)


def _shared_dossier_doc_mongo_filter() -> dict:
    return {
        "$or": [
            {"category": {"$in": list(SHARED_DOSSIER_DOC_CATEGORIES)}},
            {"checklist_item": {"$in": list(SHARED_DOSSIER_DOC_CATEGORIES)}},
            {"shared_dossier": True},
        ]
    }


def _is_couple_scope(scope: dict) -> bool:
    return len(scope.get("member_ids") or []) > 1


def _documents_list_query(user_id: str, client_id: str, scope: dict) -> dict:
    """Requête Mongo pour lister les documents d'un client (partagés si couple)."""
    member_ids = scope.get("member_ids") or [client_id]
    dossier_ids = scope.get("dossier_ids") or [scope.get("dossier_id") or client_id]
    if _is_couple_scope(scope):
        or_clauses = [
            {"client_id": {"$in": member_ids}},
            {"dossier_id": {"$in": dossier_ids}},
        ]
    else:
        or_clauses = [{"client_id": client_id}]
    return {
        "user_id": user_id,
        "is_deleted": False,
        "$or": or_clauses,
    }


ANALYSE_PREVOYANCE_CATEGORY = "Analyse de prévoyance"


async def _dossier_has_analyse_prevoyance(user_id: str, client_id: str, scope: dict) -> bool:
    """True si au moins un PDF / document « Analyse de prévoyance » est présent sur le dossier."""
    base = _documents_list_query(user_id, client_id, scope)
    query = {
        "user_id": base["user_id"],
        "is_deleted": False,
        "$and": [
            {"$or": base["$or"]},
            {
                "$or": [
                    {"category": ANALYSE_PREVOYANCE_CATEGORY},
                    {"checklist_item": ANALYSE_PREVOYANCE_CATEGORY},
                ]
            },
        ],
    }
    doc = await db.documents.find_one(query, {"_id": 1})
    return doc is not None


async def _resolve_client_conseiller_email(client: dict) -> Optional[str]:
    """E-mail du conseiller responsable du dossier (users.email via client.conseiller)."""
    label = (client.get("conseiller") or "").strip()
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

    # Repli : propriétaire du dossier (user_id)
    owner_id = (client.get("user_id") or "").strip()
    if owner_id:
        u = await db.users.find_one(
            {"user_id": owner_id, "active": {"$ne": False}},
            {"_id": 0, "email": 1},
        )
        email = ((u or {}).get("email") or "").strip()
        if "@" in email:
            return email
    return None


async def _notify_conseiller_dossier_presente(
    *,
    user: User,
    client: dict,
    scope: dict,
    now_iso: str,
) -> None:
    """
    Envoie un e-mail au conseiller quand le dossier passe à « À présenter »
    et qu'une analyse de prévoyance est déjà dans le dossier.
    Anti-doublon : un seul envoi par séjour dans « À présenter » (flag dossier).
    """
    from email_service import (
        MAIL_TYPE_DOSSIER_PRESENTE,
        format_client_prenom_nom,
        format_dossier_presente_email,
        send_email_async,
    )

    member_ids = scope.get("member_ids") or [client.get("id")]
    dossier_id = scope.get("dossier_id") or client.get("id")
    claim_id = dossier_id or client.get("id")

    has_analyse = await _dossier_has_analyse_prevoyance(user.user_id, client["id"], scope)
    if not has_analyse:
        logger.info(
            "Dossier présenté sans analyse de prévoyance — e-mail conseiller non envoyé client=%s",
            client.get("id"),
        )
        return

    # Claim atomique : gère les PATCH parallèles Kanban (1 mail / présentation)
    claimed = await db.clients.find_one_and_update(
        {
            "id": claim_id,
            "user_id": user.user_id,
            "analyse_presentee_email_active": {"$ne": True},
        },
        {
            "$set": {
                "analyse_presentee_email_active": True,
                "analyse_presentee_email_at": now_iso,
                "updated_at": now_iso,
            }
        },
    )
    if not claimed:
        return

    await db.clients.update_many(
        {"user_id": user.user_id, "id": {"$in": member_ids}},
        {
            "$set": {
                "analyse_presentee_email_active": True,
                "analyse_presentee_email_at": now_iso,
            }
        },
    )

    to_email = await _resolve_client_conseiller_email(client)
    if not to_email:
        await log_action(
            user.user_id,
            client["id"],
            "E-mail « dossier présenté » non envoyé : conseiller sans adresse e-mail",
            dossier_id=dossier_id,
        )
        logger.warning(
            "Dossier présenté: pas d'e-mail conseiller client=%s conseiller=%r",
            client.get("id"),
            client.get("conseiller"),
        )
        return

    subject, body_text, body_html = format_dossier_presente_email(client)
    client_name = format_client_prenom_nom(client)

    # Toujours passer par send_email_async : journalise sent/error même si SMTP down
    ok, err = await send_email_async(
        to_email,
        subject,
        body_text,
        body_html=body_html,
        mail_type=MAIL_TYPE_DOSSIER_PRESENTE,
        log_meta={
            "client_id": client.get("id"),
            "dossier_id": dossier_id,
            "ref_id": claim_id,
            "user_id": user.user_id,
            "created_by": getattr(user, "email", None) or getattr(user, "name", None),
            "client_label": client_name,
            "conseiller": (client.get("conseiller") or "").strip() or None,
            "event": "dossier_presente",
            "module": "dossiers",
            "numero_dossier": client.get("numero_dossier"),
        },
    )
    if ok:
        await log_action(
            user.user_id,
            client["id"],
            f"E-mail « dossier présenté » envoyé à {to_email} le {now_iso}",
            dossier_id=dossier_id,
        )
    else:
        await log_action(
            user.user_id,
            client["id"],
            f"E-mail « dossier présenté » en échec vers {to_email} : {err or 'erreur'}",
            dossier_id=dossier_id,
        )


async def _clear_dossier_presente_email_flag(
    *,
    user_id: str,
    member_ids: list,
    now_iso: str,
) -> None:
    """Réinitialise le verrou d'envoi quand on quitte « À présenter » (autorise un nouvel envoi plus tard)."""
    if not member_ids:
        return
    await db.clients.update_many(
        {"user_id": user_id, "id": {"$in": member_ids}},
        {
            "$set": {
                "analyse_presentee_email_active": False,
                "updated_at": now_iso,
            }
        },
    )


async def _dossier_scope(user_id: str, client: dict) -> dict:
    """Retourne dossier_id + ids des membres du dossier familial."""
    client_id = client.get("id")
    if not client_id:
        raise ValueError("client id requis pour le périmètre dossier")
    dossier_id = client.get("dossier_id") or client_id
    members = await db.clients.find(
        {"user_id": user_id, "dossier_id": dossier_id}, {"id": 1, "linked_spouse_id": 1}
    ).to_list(100)
    member_ids = [m["id"] for m in members]
    if not member_ids:
        member_ids = [client_id]

    # Toujours inclure le conjoint lié, même si le dossier_id n'est pas encore partagé.
    spouse_id = client.get("linked_spouse_id")
    if spouse_id:
        member_ids.append(spouse_id)
        spouse = await db.clients.find_one({"id": spouse_id, "user_id": user_id}, {"_id": 0, "id": 1, "dossier_id": 1})
        if spouse and spouse.get("dossier_id") and spouse["dossier_id"] != dossier_id:
            extra = await db.clients.find(
                {"user_id": user_id, "dossier_id": spouse["dossier_id"]}, {"id": 1}
            ).to_list(100)
            member_ids.extend(m["id"] for m in extra)

    # Clients qui pointent vers ce client comme conjoint
    reverse = await db.clients.find(
        {"user_id": user_id, "linked_spouse_id": client_id}, {"id": 1}
    ).to_list(20)
    member_ids.extend(m["id"] for m in reverse)

    # Même numéro de dossier (couple importé sans linked_spouse_id)
    numero = (client.get("numero_dossier") or "").strip()
    if numero:
        same_numero = await db.clients.find(
            {"user_id": user_id, "numero_dossier": numero},
            {"id": 1},
        ).to_list(50)
        member_ids.extend(m["id"] for m in same_numero)

    # Conjoint par nom (champ conjoint / conjoint_prenom+nom)
    member_ids.extend(await _resolve_spouse_ids_by_name(user_id, client))

    member_ids = list(dict.fromkeys(member_ids))
    dossier_ids = await _collect_dossier_ids(user_id, member_ids, dossier_id)
    return {"dossier_id": dossier_id, "member_ids": member_ids, "dossier_ids": dossier_ids}

async def _upsert_echeance_3p_reminder(user_id: str, client: dict, echeance_iso: Optional[str]):
    """Create or update the open 3P reminder when the expiry is within one year."""
    if not echeance_iso:
        return
    try:
        due = datetime.fromisoformat(echeance_iso[:10])
        days_left = (due - datetime.now()).days
    except (TypeError, ValueError):
        return
    if not 0 <= days_left <= 365:
        return
    existing = await db.tasks.find_one({
        "user_id": user_id, "client_id": client["id"], "type": "echeance_3p", "done": False,
    }, {"_id": 0})
    titre = f"Échéance 3e pilier — {client.get('prenom', '')} {client.get('nom', '')}".strip()
    if existing:
        await db.tasks.update_one({"id": existing["id"]}, {"$set": {"echeance": echeance_iso, "titre": titre}})
    else:
        await db.tasks.insert_one({
            "id": str(uuid.uuid4()), "user_id": user_id, "client_id": client["id"],
            "titre": titre, "echeance": echeance_iso, "priorite": "haute",
            "type": "echeance_3p", "done": False, "created_at": datetime.now(timezone.utc).isoformat(),
        })

def _normalize_3p_str(v: Optional[str]) -> str:
    return str(v or "").strip().casefold()

def _echeance_3p_contract_key(company: Optional[str], policy_number: Optional[str], echeance_iso: Optional[str]) -> str:
    # Identifiant stable pour éviter les doublons de rappels.
    return "|".join([
        _normalize_3p_str(company),
        _normalize_3p_str(policy_number),
        str(echeance_iso or ""),
    ])

def _echeance_3p_line_identity(line: dict) -> tuple:
    company = _normalize_3p_str(line.get("company"))
    policy = _normalize_3p_str(line.get("policy_number"))
    date = line.get("echeance_3p")
    if date:
        return (company, policy, str(date))
    return (company, policy, None, str(line.get("source_doc_id") or ""))

def _merge_echeances_3p_lines(existing_lines: Optional[List[dict]], new_lines: List[dict]) -> List[dict]:
    """Fusionne en respectant : 1 source_doc_id = 1 ligne. Les lignes manuelles (sans source) sont conservées."""
    previous = [l for l in (existing_lines or []) if isinstance(l, dict)]
    now_iso = datetime.now(timezone.utc).isoformat()

    by_source = {}
    manual = []
    for l in previous:
        sid = l.get("source_doc_id")
        if sid:
            by_source[str(sid)] = l
        else:
            manual.append(l)

    for line in new_lines or []:
        if not isinstance(line, dict):
            continue
        sid = line.get("source_doc_id")
        if sid:
            key = str(sid)
            if key in by_source:
                existing = by_source[key]
                existing["company"] = line.get("company")
                existing["policy_number"] = line.get("policy_number")
                existing["source_doc_id"] = sid
                existing["raw_date"] = line.get("raw_date") or existing.get("raw_date")
                if line.get("document_type"):
                    existing["document_type"] = line.get("document_type")
                existing["updated_at"] = now_iso
                new_date = line.get("echeance_3p")
                if new_date:
                    existing["echeance_3p"] = new_date
                    existing["detected"] = True
                elif "detected" in line:
                    existing["detected"] = bool(line.get("detected"))
            else:
                by_source[key] = line
        else:
            manual.append(line)

    return manual + list(by_source.values())


def _normalize_document_type_3p(value: Optional[str]) -> str:
    if not value:
        return "Autre document"
    raw = str(value).strip()
    for t in DOCUMENT_TYPES_3P:
        if t.casefold() == raw.casefold():
            return t
    return "Autre document"


def _echeance_line_from_extraction(entry: Optional[dict], source_doc_id: str, now_iso: str) -> dict:
    entry = entry or {}
    document_type = _normalize_document_type_3p(entry.get("document_type"))
    # Types sans échéance automatique : ne jamais reporter une date inventée.
    no_expiry_types = {"Résiliation", "Rachat", "Libre passage"}
    expiry = entry.get("expiry_date") or entry.get("echeance_3p")
    if document_type in no_expiry_types:
        expiry = None
    return {
        "id": str(uuid.uuid4()),
        "company": entry.get("company") or None,
        "policy_number": entry.get("policy_number") or None,
        "echeance_3p": expiry,
        "detected": bool(expiry),
        "raw_date": entry.get("raw_date") if expiry else None,
        "document_type": document_type,
        "source_doc_id": source_doc_id,
        "manual": False,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

async def _upsert_echeance_3p_line_reminder(user_id: str, client: dict, line: dict):
    """Create or update a 3P reminder for a single contract line."""
    echeance_iso = line.get("echeance_3p")
    if not echeance_iso:
        return
    try:
        due = datetime.fromisoformat(str(echeance_iso)[:10])
        days_left = (due - datetime.now()).days
    except (TypeError, ValueError):
        return
    if not 0 <= days_left <= 365:
        return

    key = _echeance_3p_contract_key(line.get("company"), line.get("policy_number"), echeance_iso)
    existing = await db.tasks.find_one({
        "user_id": user_id,
        "client_id": client["id"],
        "type": "echeance_3p",
        "echeance_3p_key": key,
        "done": False,
    }, {"_id": 0})

    company = str(line.get("company") or "").strip() or "Compagnie inconnue"
    policy = str(line.get("policy_number") or "").strip()
    policy_part = f" (N° {policy})" if policy else ""
    due_display = due.strftime("%d.%m.%Y")
    client_name = f"{client.get('prenom', '')} {client.get('nom', '')}".strip() or "Client"
    titre = f"⚠ {client_name} — Contrat 3e pilier {company}{policy_part}"

    if existing:
        await db.tasks.update_one(
            {"id": existing["id"]},
            {"$set": {
                "echeance": echeance_iso,
                "titre": titre,
                "client_name": client_name,
            }},
        )
    else:
        await db.tasks.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "client_id": client["id"],
            "client_name": client_name,
            "titre": titre,
            "echeance": echeance_iso,
            "priorite": "haute",
            "type": "echeance_3p",
            "echeance_3p_key": key,
            "done": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

def _lpp_track_key(item: dict) -> str:
    person = str(item.get("person") or "").strip().casefold()
    name = str(item.get("name") or item.get("nom") or "").strip().casefold()
    return f"{person}|{name}"


def _lpp_tracking_from_funds(funds: List[dict], existing: Optional[List[dict]] = None) -> List[dict]:
    """Construit le suivi Envoyé/Reçu par caisse (clé = personne + nom).

    Les flags sent/received déjà enregistrés sont préservés. Les caisses d'une
    autre personne ne sont jamais écrasées par une nouvelle analyse OCR.
    """
    previous_list = [item for item in (existing or []) if isinstance(item, dict) and item.get("name")]
    previous = {_lpp_track_key(item): item for item in previous_list}
    tracking = []
    seen = set()
    for fund in funds or []:
        if not isinstance(fund, dict):
            continue
        name = str(fund.get("name") or fund.get("nom") or "").strip()
        if not name:
            continue
        person = str(fund.get("person") or "").strip()
        key = _lpp_track_key({"name": name, "person": person})
        prior = previous.get(key, {})
        tracking.append({
            "id": prior.get("id") or str(uuid.uuid4()),
            "name": name,
            "person": person or prior.get("person") or "",
            "address": fund.get("address") or fund.get("adresse") or prior.get("address") or "",
            "reference": fund.get("reference") or fund.get("ref") or prior.get("reference") or "",
            "source_doc_id": fund.get("source_doc_id") or prior.get("source_doc_id"),
            "sent": bool(prior.get("sent")),
            "received": bool(prior.get("received")),
            "sent_at": prior.get("sent_at"),
            "received_at": prior.get("received_at"),
        })
        seen.add(key)
    for item in previous_list:
        key = _lpp_track_key(item)
        if key in seen:
            continue
        tracking.append({
            "id": item.get("id") or str(uuid.uuid4()),
            "name": item.get("name"),
            "person": item.get("person") or "",
            "address": item.get("address") or "",
            "reference": item.get("reference") or "",
            "source_doc_id": item.get("source_doc_id"),
            "sent": bool(item.get("sent")),
            "received": bool(item.get("received")),
            "sent_at": item.get("sent_at"),
            "received_at": item.get("received_at"),
        })
        seen.add(key)
    return tracking


async def _persist_merged_lpp_funds(
    *,
    client_id: str,
    user_id: str,
    client: dict,
    new_funds: List[dict],
    replace_source_doc_id: Optional[str] = None,
    response_doc_id: Optional[str] = None,
) -> tuple:
    """Fusionne les caisses détectées (M./Mme) et met à jour le suivi."""
    existing = list(client.get("lpp_detected_funds") or [])
    if replace_source_doc_id:
        existing = [
            f for f in existing
            if not isinstance(f, dict) or f.get("source_doc_id") != replace_source_doc_id
        ]
    merged = merge_lpp_detected_funds(existing, new_funds)
    tracking = _lpp_tracking_from_funds(merged, client.get("lpp_caisse_tracking"))
    payload = {
        "lpp_detected_funds": merged,
        "lpp_caisse_tracking": tracking,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if response_doc_id:
        payload["lpp_response_doc_id"] = response_doc_id
    await db.clients.update_one(
        {"id": client_id, "user_id": user_id},
        {"$set": payload},
    )
    return merged, tracking

# ---------------- Clients ----------------
def _fold_search(text: Any) -> str:
    """Normalise pour recherche partielle (casse + accents)."""
    import unicodedata

    s = unicodedata.normalize("NFD", str(text or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.casefold().strip()


def _client_matches_q(client: dict, ql: str) -> bool:
    if not ql:
        return True
    prenom = _fold_search(client.get("prenom"))
    nom = _fold_search(client.get("nom"))
    full = f"{prenom} {nom}".strip()
    full_rev = f"{nom} {prenom}".strip()
    haystacks = [
        prenom,
        nom,
        full,
        full_rev,
        _fold_search(client.get("email")),
        _fold_search(client.get("telephone")),
        _fold_search(client.get("numero_dossier")),
        _fold_search(client.get("ville")),
    ]
    return any(ql in h for h in haystacks if h)


def _rank_client_match(client: dict, ql: str) -> tuple:
    prenom = _fold_search(client.get("prenom"))
    nom = _fold_search(client.get("nom"))
    full = f"{prenom} {nom}".strip()
    if nom.startswith(ql) or prenom.startswith(ql) or full.startswith(ql):
        return (0, nom, prenom)
    if ql in nom or ql in prenom:
        return (1, nom, prenom)
    return (2, nom, prenom)


@api_router.get("/clients")
async def list_clients(
    q: Optional[str] = None,
    statut: Optional[str] = None,
    conseiller: Optional[str] = None,
    scope: Optional[str] = Query(
        None,
        description="clients (défaut, base hub) | dossiers (prévoyance / Kanban uniquement)",
    ),
    limit: int = Query(2000, ge=1, le=10000),
    skip: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    for_dossiers = (scope or "").strip().lower() in ("dossiers", "dossier", "prevoyance", "kanban")
    query = clients_base_query(user, conseiller=conseiller, for_dossiers=for_dossiers)
    wanted = normalize_statut(statut) if statut else None
    # Inclure aussi les anciens libellés si le filtre correspond à un statut migré.
    if wanted:
        legacy_aliases = [old for old, new in STATUT_LEGACY_MAP.items() if new == wanted]
        query["statut"] = {"$in": [wanted, *legacy_aliases]} if legacy_aliases else wanted

    q_term = (q or "").strip()
    # Recherche texte : charger toute la base accessible AVANT filtre
    # (sinon limit=15 ne regardait que les 15 derniers créés → clients manquants)
    if q_term:
        fetch_cap = 10000
    else:
        fetch_cap = min(max(limit + skip, limit), 10000)

    clients = await db.clients.find(query, {"_id": 0}).sort("created_at", -1).to_list(fetch_cap)
    for c in clients:
        c["statut"] = normalize_statut(c.get("statut"))
    clients = [_decrypt_client_doc(c) for c in clients]
    if q_term:
        ql = _fold_search(q_term)
        clients = [c for c in clients if _client_matches_q(c, ql)]
        clients.sort(key=lambda c: _rank_client_match(c, ql))
    if skip:
        clients = clients[skip:]
    if limit and len(clients) > limit:
        clients = clients[:limit]
    return clients


@api_router.get("/clients/search")
async def search_clients_hub(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """Recherche partielle temps réel dans TOUTE la base Clients (hub), hors imports Excel."""
    ql = _fold_search(q)
    if len(ql) < 1:
        return []
    query = clients_base_query(user, for_dossiers=False)
    # Toujours toute la population hub visible (pas de filtre dossiers / offres)
    raw = await db.clients.find(query, {"_id": 0}).to_list(10000)
    clients = [_decrypt_client_doc(c) for c in raw]
    for c in clients:
        c["statut"] = normalize_statut(c.get("statut"))
    matched = [c for c in clients if _client_matches_q(c, ql)]
    matched.sort(key=lambda c: _rank_client_match(c, ql))
    return matched[:limit]

@api_router.post("/clients")
async def create_client(payload: ClientCreate, user: User = Depends(get_current_user)):
    from client_identity import identity_fields_for_storage, require_unique_identity

    ALLOWED_ACTIVITES = {"prevoyance", "fiscalite", "offre", "autre"}
    doc = payload.model_dump()
    finma_in = doc.pop("conseiller_finma", None)
    raw_activites = doc.pop("activites", None)
    if raw_activites is None:
        # Compat : anciennes créations / Kanban sans champ → dossier prévoyance
        activites = ["prevoyance"]
    else:
        activites = []
        for a in raw_activites:
            key = str(a or "").strip().lower()
            if key in ("fiscalite", "fiscalité", "suivi_3p", "3p"):
                key = "fiscalite"
            if key in ("offre", "offres"):
                key = "offre"
            if key in ALLOWED_ACTIVITES and key not in activites:
                activites.append(key)

    prenom = (doc.get("prenom") or "").strip()
    nom = (doc.get("nom") or "").strip()
    if not prenom or not nom:
        raise HTTPException(status_code=400, detail="Prénom et nom obligatoires")

    # Une personne = un profil : interdit si identité déjà connue
    await require_unique_identity(
        db,
        prenom=prenom,
        nom=nom,
        date_naissance=doc.get("date_naissance"),
        user_id=user.user_id,
    )

    doc["prenom"] = prenom
    doc["nom"] = nom
    doc.update(identity_fields_for_storage(prenom, nom, doc.get("date_naissance")))
    doc["id"] = str(uuid.uuid4())
    doc["user_id"] = user.user_id
    doc["conseiller"] = force_conseiller_on_write(user, doc.get("conseiller"))
    doc["statut"] = normalize_statut(doc.get("statut"))
    doc["numero_dossier"] = await next_dossier_number(user.user_id)
    doc["dossier_id"] = doc["id"]
    etat = (doc.get("etat_civil") or "").casefold()
    married = "mari" in etat or "partenariat" in etat
    doc["dossier_label"] = f"Famille {doc['nom']}" if married else f"{doc['prenom']} {doc['nom']}".strip()
    doc["activites"] = activites
    doc["in_dossiers"] = "prevoyance" in activites
    source_modules = []
    if "prevoyance" in activites:
        source_modules.append("prevoyance")
    if "fiscalite" in activites:
        source_modules.append("suivi_3p")
    if "offre" in activites:
        source_modules.append("offres")
    if "autre" in activites:
        source_modules.append("autre")
    doc["source_modules"] = source_modules
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = doc["created_at"]
    if doc.get("conseiller") and finma_in is not None:
        await upsert_conseiller_finma(doc["conseiller"], finma_in)
    to_store = _encrypt_client_for_storage(doc)
    try:
        await db.clients.insert_one(to_store)
    except Exception as e:
        # Course : index unique identity_key (Mongo DuplicateKey / PG unique)
        err = str(e).lower()
        if "duplicate" in err or "unique" in err or "e11000" in err:
            await require_unique_identity(
                db,
                prenom=prenom,
                nom=nom,
                date_naissance=doc.get("date_naissance"),
                user_id=user.user_id,
            )
        raise
    await log_action(
        user.user_id,
        doc["id"],
        f"Client créé ({doc['numero_dossier']})"
        + (f" · activités: {', '.join(activites)}" if activites else " · Clients uniquement"),
    )

    # Fiscalité : une fiche Suivi 3P liée au même client_id (pas de 2e fiche hub)
    if "fiscalite" in activites:
        try:
            suivi_doc = build_new_client(
                user_id=TENANT_USER_ID,
                prenom=doc.get("prenom") or "",
                nom=doc.get("nom") or "",
                date_naissance=doc.get("date_naissance"),
                etat_civil=doc.get("etat_civil"),
                nombre_enfants=doc.get("nombre_enfants") or 0,
                conseiller=doc.get("conseiller"),
                conjoint=doc.get("conjoint"),
                email=doc.get("email"),
                telephone=doc.get("telephone"),
                adresse=doc.get("adresse"),
                npa=doc.get("npa"),
                ville=doc.get("ville"),
                pays=doc.get("pays_residence"),
                sexe=doc.get("sexe"),
            )
            suivi_doc["client_id"] = doc["id"]
            to_suivi = _encrypt_client_for_storage(suivi_doc)
            await db[SUIVI_3P_CLIENTS].insert_one(to_suivi)
        except Exception:
            logger.exception("Création fiche Fiscalité liée échouée client=%s", doc["id"])

    return await attach_conseiller_finma(_decrypt_client_doc({k: v for k, v in to_store.items() if k != "_id"}))


@api_router.get("/clients/match")
async def match_hub_client(
    prenom: str = "",
    nom: str = "",
    date_naissance: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
):
    """Correspondance hub Clients (toute la base centrale, hors import Excel).

    - Avec q : recherche partielle (Wah → Wahlen), liste de suggestions.
    - Avec prenom+nom+date_naissance : match fort unique.
    """
    from client_hub import find_hub_client

    q_term = (q or "").strip()
    if q_term:
        ql = _fold_search(q_term)
        query = clients_base_query(user, for_dossiers=False)
        raw = await db.clients.find(query, {"_id": 0}).to_list(10000)
        clients = [_decrypt_client_doc(c) for c in raw]
        matched = [c for c in clients if _client_matches_q(c, ql)]
        matched.sort(key=lambda c: _rank_client_match(c, ql))
        items = []
        for c in matched[:limit]:
            items.append(await attach_conseiller_finma(c))
        return {
            "matched": len(items) > 0,
            "client": items[0] if len(items) == 1 else None,
            "clients": items,
            "reason": "found" if items else "not_found",
        }

    p = (prenom or "").strip()
    n = (nom or "").strip()
    dob = (date_naissance or "").strip()[:10] if date_naissance else ""
    if not p or not n or not dob:
        return {"matched": False, "client": None, "clients": [], "reason": "incomplete"}

    hub = await find_hub_client(
        db,
        nom=n,
        prenom=p,
        date_naissance=dob,
        user_id=user.user_id,
    )
    if not hub:
        return {"matched": False, "client": None, "clients": [], "reason": "not_found"}
    client = await attach_conseiller_finma(hub)
    return {
        "matched": True,
        "client": client,
        "clients": [client],
        "reason": "found",
    }


@api_router.get("/clients/{client_id}")
async def get_client(client_id: str, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    try:
        # Nettoyage "strict" côté lecture : évite que d'anciennes lignes erronées restent visibles
        # si l'utilisateur n'a pas re-upload/supprimé un document depuis.
        lines = c.get("echeances_3p")
        if isinstance(lines, list) and len(lines) > 0:
            await _reconcile_echeances_3p_lines(user.user_id, client_id)
            c = await require_client(client_id, user)
    except Exception:
        logger.exception("Reconciliation echeances_3p échouée (get_client)")
    if c:
        c["statut"] = normalize_statut(c.get("statut"))
    return await attach_conseiller_finma(c)


@api_router.get("/clients/{client_id}/modules")
async def get_client_modules(client_id: str, user: User = Depends(get_current_user)):
    """Activité croisée : prévoyance, offres, suivi 3P, mandats liés au client hub."""
    await require_client(client_id, user)
    from client_hub import client_modules_activity

    return await client_modules_activity(db, client_id, user_id=user.user_id)

@api_router.get("/dossiers/{dossier_id}")
async def get_dossier(dossier_id: str, user: User = Depends(get_current_user)):
    members = await db.clients.find(
        {"user_id": user.user_id, "dossier_id": dossier_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    if not members:
        # Compat: ancien couple lié sans dossier_id partagé
        primary = await db.clients.find_one({"id": dossier_id, "user_id": user.user_id}, {"_id": 0})
        if not primary:
            raise HTTPException(status_code=404, detail="Dossier introuvable")
        if not can_access_client(user, primary):
            raise HTTPException(status_code=403, detail="Accès non autorisé à ce dossier")
        members = [primary]
        spouse_id = primary.get("linked_spouse_id")
        if spouse_id:
            spouse = await db.clients.find_one({"id": spouse_id, "user_id": user.user_id}, {"_id": 0})
            if spouse:
                members.append(spouse)
        dossier_label = primary.get("dossier_label") or (
            f"Famille {primary.get('nom', '')}" if len(members) > 1 else f"{primary.get('prenom', '')} {primary.get('nom', '')}".strip()
        )
        for m in members:
            await db.clients.update_one(
                {"id": m["id"]},
                {"$set": {
                    "dossier_id": dossier_id,
                    "dossier_label": dossier_label,
                    "numero_dossier": primary.get("numero_dossier"),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            m["dossier_id"] = dossier_id
            m["dossier_label"] = dossier_label
            m["numero_dossier"] = primary.get("numero_dossier")
    else:
        if not any(can_access_client(user, m) for m in members):
            raise HTTPException(status_code=403, detail="Accès non autorisé à ce dossier")
        if not is_global_viewer(user):
            members = [m for m in members if can_access_client(user, m)]
            if not members:
                raise HTTPException(status_code=403, detail="Accès non autorisé à ce dossier")
    primary = members[0]
    scope_id = primary.get("dossier_id") or dossier_id
    member_ids = [m["id"] for m in members]
    docs = await db.documents.find(
        {
            "user_id": user.user_id,
            "is_deleted": False,
            "$or": [
                {"client_id": {"$in": member_ids}},
                {"dossier_id": scope_id},
            ],
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(50)
    notes = await db.notes.find(
        {
            "user_id": user.user_id,
            "$or": [
                {"client_id": {"$in": member_ids}},
                {"dossier_id": scope_id},
            ],
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(20)
    return {
        "dossier_id": dossier_id,
        "dossier_label": primary.get("dossier_label") or f"{primary.get('prenom', '')} {primary.get('nom', '')}".strip(),
        "numero_dossier": primary.get("numero_dossier"),
        "members": [_decrypt_client_doc(m) for m in members],
        "documents": docs,
        "notes": notes,
    }

@api_router.put("/clients/{client_id}")
async def update_client(client_id: str, payload: ClientCreate, user: User = Depends(get_current_user)):
    from client_identity import client_identity_key, identity_fields_for_storage, require_unique_identity

    c = await require_client(client_id, user)
    update = payload.model_dump()
    finma_in = update.pop("conseiller_finma", None)
    update.pop("activites", None)  # activités gérées à la création (évite écrasement involontaire)
    prenom = (update.get("prenom") or "").strip()
    nom = (update.get("nom") or "").strip()
    if not prenom or not nom:
        raise HTTPException(status_code=400, detail="Prénom et nom obligatoires")
    new_key = client_identity_key(prenom, nom, update.get("date_naissance"))
    old_key = client_identity_key(c.get("prenom"), c.get("nom"), c.get("date_naissance"))
    # Ne bloquer que si l'identité change vers une clé déjà prise
    # (les doublons historiques restent éditables jusqu'à nettoyage manuel)
    if new_key and new_key != old_key:
        await require_unique_identity(
            db,
            prenom=prenom,
            nom=nom,
            date_naissance=update.get("date_naissance"),
            user_id=user.user_id,
            exclude_id=client_id,
        )
    update["prenom"] = prenom
    update["nom"] = nom
    update.update(identity_fields_for_storage(prenom, nom, update.get("date_naissance")))
    update["conseiller"] = force_conseiller_on_write(user, update.get("conseiller"))
    update["statut"] = normalize_statut(update.get("statut"))
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    if update.get("conseiller") and finma_in is not None:
        await upsert_conseiller_finma(update["conseiller"], finma_in)
    update = _encrypt_client_patch(update)
    await db.clients.update_one({"id": client_id}, {"$set": update})
    await log_action(user.user_id, client_id, "Fiche client mise à jour")
    # Propager l'identité vers Offres + Suivi 3P liés
    try:
        from client_hub import propagate_hub_identity

        await propagate_hub_identity(db, client_id, user_id=user.user_id)
    except Exception:
        logger.exception("Propagation hub identité échouée client=%s", client_id)
    return await attach_conseiller_finma(await require_client(client_id, user))

@api_router.patch("/clients/{client_id}/statut")
async def update_statut(client_id: str, payload: StatutUpdate, user: User = Depends(get_current_user)):
    statut = normalize_statut(payload.statut)
    if statut not in STATUTS:
        raise HTTPException(status_code=400, detail="Statut invalide")
    c = await require_client(client_id, user)

    # Statut commun au dossier familial : tous les membres avancent ensemble.
    scope = await _dossier_scope(user.user_id, c)
    member_ids = scope.get("member_ids") or [client_id]
    now_iso = datetime.now(timezone.utc).isoformat()
    old_statut = normalize_statut(c.get("statut"))

    await db.clients.update_many(
        {"user_id": user.user_id, "id": {"$in": member_ids}},
        {"$set": {"statut": statut, "updated_at": now_iso}},
    )
    await log_action(
        user.user_id,
        client_id,
        f"Statut dossier changé: {c.get('statut')} → {statut}",
        dossier_id=scope.get("dossier_id"),
    )

    # E-mail auto conseiller : passage à « À présenter » si analyse de prévoyance déjà présente.
    # (Le CRM n'a pas de statut « Présenté » — la colonne Kanban est « À présenter ».)
    if statut == "À présenter" and old_statut != "À présenter":
        try:
            await _notify_conseiller_dossier_presente(
                user=user,
                client=c,
                scope=scope,
                now_iso=now_iso,
            )
        except Exception:
            logger.exception(
                "E-mail dossier présenté échoué client=%s",
                client_id,
            )
    elif old_statut == "À présenter" and statut != "À présenter":
        try:
            await _clear_dossier_presente_email_flag(
                user_id=user.user_id,
                member_ids=member_ids,
                now_iso=now_iso,
            )
        except Exception:
            logger.exception("Clear flag e-mail dossier présenté échoué client=%s", client_id)

    return await require_client(client_id, user)

@api_router.patch("/clients/{client_id}/document-checklist")
async def update_document_checklist(client_id: str, payload: DocumentChecklistUpdate, user: User = Depends(get_current_user)):
    from demande_envoi_relances import enrich_checklist_map, sync_client_relances

    c = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, c)
    member_ids = scope.get("member_ids") or [client_id]
    previous = c.get("document_checklist") or {}
    checklist = enrich_checklist_map(previous, payload.document_checklist)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.clients.update_many(
        {"user_id": user.user_id, "id": {"$in": member_ids}},
        {"$set": {
            "document_checklist": checklist,
            "updated_at": now_iso,
        }},
    )
    # Historique explicite pour les futurs backfills sent_at
    for name, entry in checklist.items():
        if not isinstance(entry, dict):
            continue
        prev = previous.get(name) if isinstance(previous, dict) else {}
        prev = prev if isinstance(prev, dict) else {}
        if entry.get("sent") and not prev.get("sent"):
            await log_action(
                user.user_id,
                client_id,
                f"Demande marquée Envoyé: {name}",
                dossier_id=scope.get("dossier_id"),
            )
        if entry.get("received") and not prev.get("received"):
            await log_action(
                user.user_id,
                client_id,
                f"Demande marquée Reçu: {name}",
                dossier_id=scope.get("dossier_id"),
            )
    updated = await require_client(client_id, user)
    try:
        await sync_client_relances(
            db,
            user_id=user.user_id,
            client=updated,
            dossier_id=scope.get("dossier_id"),
        )
    except Exception:
        logger.exception("Sync relances checklist échoué client=%s", client_id)
    return updated

@api_router.patch("/clients/{client_id}/lpp-caisse-tracking")
async def update_lpp_caisse_tracking(client_id: str, payload: LppCaisseTrackingUpdate, user: User = Depends(get_current_user)):
    from demande_envoi_relances import enrich_lpp_tracking_list, sync_client_relances

    c = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, c)
    member_ids = scope.get("member_ids") or [client_id]
    previous = c.get("lpp_caisse_tracking") or []
    tracking = enrich_lpp_tracking_list(previous, payload.lpp_caisse_tracking or [])
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.clients.update_many(
        {"user_id": user.user_id, "id": {"$in": member_ids}},
        {"$set": {"lpp_caisse_tracking": tracking, "updated_at": now_iso}},
    )
    prev_by_id = {str(e.get("id") or ""): e for e in previous if isinstance(e, dict)}
    for entry in tracking:
        if not isinstance(entry, dict):
            continue
        prior = prev_by_id.get(str(entry.get("id") or "")) or {}
        label = entry.get("name") or "caisse"
        if entry.get("sent") and not prior.get("sent"):
            await log_action(
                user.user_id,
                client_id,
                f"Caisse LPP marquée Envoyé: {label}",
                dossier_id=scope.get("dossier_id"),
            )
        if entry.get("received") and not prior.get("received"):
            await log_action(
                user.user_id,
                client_id,
                f"Caisse LPP marquée Reçu: {label}",
                dossier_id=scope.get("dossier_id"),
            )
    try:
        client_for_sync = {**c, "lpp_caisse_tracking": tracking, "id": client_id}
        await sync_client_relances(
            db,
            user_id=user.user_id,
            client=client_for_sync,
            dossier_id=scope.get("dossier_id"),
        )
    except Exception:
        logger.exception("Sync relances LPP échoué client=%s", client_id)
    return {"lpp_caisse_tracking": tracking}


@api_router.get("/admin/demande-envoi-missing-sent-at")
async def admin_demande_envoi_missing_sent_at(user: User = Depends(get_current_user)):
    """Rapport : Envoyé sans date — non récupérables faute d'historique de coche."""
    require_admin(user)
    from demande_envoi_relances import list_missing_sent_at

    return await list_missing_sent_at(db, user_id=user.user_id)


@api_router.post("/admin/link-clients-hub")
async def admin_link_clients_hub(user: User = Depends(get_current_user)):
    """Rattache Offres + Suivi 3P existants à la base Clients (idempotent)."""
    require_admin(user)
    from client_hub import link_existing_module_records

    report = await link_existing_module_records(db, user_id=user.user_id)
    return report


@api_router.get("/admin/clients/duplicates")
async def admin_clients_duplicates(user: User = Depends(get_current_user)):
    """Liste les clusters de doublons (prénom+nom+DOB normalisés). Aucune suppression."""
    require_admin(user)
    from client_identity import cluster_duplicates

    raw = await db.clients.find(
        {
            "user_id": user.user_id,
            "source_import": {"$ne": "suivi_3p_excel"},
            "is_deleted": {"$ne": True},
        },
        {"_id": 0},
    ).to_list(50000)
    clusters = cluster_duplicates(raw)
    return {
        "scanned": len(raw),
        "duplicate_groups": len(clusters),
        "extra_profiles": sum(max(0, c["count"] - 1) for c in clusters),
        "clusters": clusters,
    }


@api_router.post("/admin/clients/backfill-identity-keys")
async def admin_backfill_identity_keys(user: User = Depends(get_current_user)):
    """Backfill prenom_norm / nom_norm / date_naissance_norm / identity_key (idempotent)."""
    require_admin(user)
    from client_identity import identity_fields_for_storage

    raw = await db.clients.find(
        {"user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    ).to_list(50000)
    updated = 0
    skipped = 0
    for doc in raw:
        plain = _decrypt_client_doc(doc) or doc
        fields = identity_fields_for_storage(
            plain.get("prenom"),
            plain.get("nom"),
            plain.get("date_naissance"),
        )
        if (
            plain.get("identity_key") == fields.get("identity_key")
            and plain.get("prenom_norm") == fields.get("prenom_norm")
            and plain.get("nom_norm") == fields.get("nom_norm")
            and plain.get("date_naissance_norm") == fields.get("date_naissance_norm")
        ):
            skipped += 1
            continue
        await db.clients.update_one(
            {"id": plain["id"], "user_id": user.user_id},
            {"$set": {**fields, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        updated += 1
    return {"updated": updated, "skipped": skipped, "total": len(raw)}


@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    spouse_id = c.get("linked_spouse_id")
    if spouse_id:
        await db.clients.update_one(
            {"id": spouse_id, "user_id": user.user_id},
            {"$unset": {"linked_spouse_id": ""}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    res = await db.clients.delete_one({"id": client_id, "user_id": user.user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return {"ok": True}

# ---------------- Notes ----------------
@api_router.get("/clients/{client_id}/notes")
async def list_notes(client_id: str, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, c)
    query = {
        "user_id": user.user_id,
        "$or": [
            {"client_id": {"$in": scope["member_ids"]}},
            {"dossier_id": scope["dossier_id"]},
        ],
    }
    return await db.notes.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)

@api_router.post("/clients/{client_id}/notes")
async def add_note(client_id: str, payload: NoteCreate, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, c)
    doc = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "dossier_id": scope["dossier_id"],
        "user_id": user.user_id,
        "content": payload.content,
        "author": user.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notes.insert_one(doc)
    await log_action(user.user_id, client_id, "Note interne ajoutée", dossier_id=scope["dossier_id"])
    doc.pop("_id", None)
    return doc

@api_router.patch("/clients/{client_id}/notes/{note_id}")
async def update_note(client_id: str, note_id: str, payload: NoteUpdate, user: User = Depends(get_current_user)):
    await require_client(client_id, user)
    note = await db.notes.find_one({"id": note_id, "user_id": user.user_id}, {"_id": 0})
    if not note:
        raise HTTPException(status_code=404, detail="Note introuvable")
    now = datetime.now(timezone.utc).isoformat()
    await db.notes.update_one(
        {"id": note_id, "user_id": user.user_id},
        {"$set": {"content": payload.content, "updated_at": now}},
    )
    await log_action(user.user_id, client_id, "Note interne modifiée")
    updated = {**note, "content": payload.content, "updated_at": now}
    return updated

# ---------------- Rappels (ex-Demandes à faire) ----------------
RAPPEL_STATUTS = ("a_faire", "en_attente", "termine")


def _normalize_demande_priorite(value: Optional[str]) -> str:
    raw = (value or "normale").strip().lower()
    if raw in {"haute", "high", "urgent", "urgente"}:
        return "haute"
    if raw in {"faible", "low", "basse"}:
        return "faible"
    return "normale"


def _normalize_rappel_statut(value: Optional[str], done: Any = None) -> str:
    raw = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    raw = raw.replace("é", "e").replace("è", "e").replace("ê", "e")
    aliases = {
        "a_faire": "a_faire",
        "afaire": "a_faire",
        "todo": "a_faire",
        "open": "a_faire",
        "en_attente": "en_attente",
        "attente": "en_attente",
        "pending": "en_attente",
        "waiting": "en_attente",
        "termine": "termine",
        "terminee": "termine",
        "done": "termine",
        "effectue": "termine",
        "effectuee": "termine",
        "echeance_passee": "a_faire",
        "echeancepassee": "a_faire",
    }
    if raw in RAPPEL_STATUTS:
        return raw
    if raw in aliases:
        return aliases[raw]
    return "termine" if done else "a_faire"


def _rappel_due_datetime_sync(rappel: dict):
    """Datetime d'échéance en Europe/Zurich (sync, pour calcul statut)."""
    from zoneinfo import ZoneInfo

    date_s = (rappel.get("date") or "")[:10]
    if not date_s:
        return None
    heure_s = (rappel.get("heure") or "09:00").strip()
    if not re.match(r"^\d{1,2}:\d{2}$", heure_s):
        heure_s = "09:00"
    h, m = heure_s.split(":")
    try:
        tz = ZoneInfo("Europe/Zurich")
        return datetime(int(date_s[:4]), int(date_s[5:7]), int(date_s[8:10]), int(h), int(m), tzinfo=tz)
    except Exception:
        return None


def _rappel_is_overdue(rappel: dict, now: Optional[datetime] = None) -> bool:
    """True si le rappel est « à faire » et que son échéance est dépassée."""
    from zoneinfo import ZoneInfo

    if _normalize_rappel_statut(rappel.get("statut"), rappel.get("done")) != "a_faire":
        return False
    due = _rappel_due_datetime_sync(rappel)
    if not due:
        return False
    tz = ZoneInfo("Europe/Zurich")
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    return now > due


def _rappel_creator_snapshot(user) -> dict:
    """Attribution figée à la création (session serveur uniquement)."""
    account_id = (getattr(user, "account_id", None) or "").strip() or None
    name = (getattr(user, "name", None) or "").strip() or None
    email = (getattr(user, "email", None) or "").strip() or None
    return {
        "created_by_user_id": account_id,
        "created_by_name": name,
        "created_by_email": email,
        # Compat legacy (emails / filtres calendrier)
        "created_by": account_id,
        "author": name,
    }


def _rappel_creator_id(doc: Optional[dict]) -> Optional[str]:
    """Identifiant créateur : nouveau champ, sinon legacy created_by."""
    if not doc:
        return None
    for key in ("created_by_user_id", "created_by"):
        val = (doc.get(key) or "").strip()
        if val:
            return val
    return None


def _stamp_rappel_creator(doc: Optional[dict]) -> Optional[dict]:
    """Normalise les champs créateur pour l'API (legacy inclus, sans backfill écrit)."""
    if not doc:
        return doc
    uid = _rappel_creator_id(doc)
    name = (doc.get("created_by_name") or doc.get("author") or "").strip() or None
    email = (doc.get("created_by_email") or "").strip() or None
    if uid:
        doc["created_by_user_id"] = uid
    elif "created_by_user_id" not in doc:
        doc["created_by_user_id"] = None
    doc["created_by_name"] = name
    if email:
        doc["created_by_email"] = email
    elif "created_by_email" not in doc:
        doc["created_by_email"] = None
    if name and not doc.get("author"):
        doc["author"] = name
    return doc


# Champs créateur immuables (ne jamais patcher via update / reporter / effectuer)
_RAPPEL_CREATOR_IMMUTABLE_KEYS = frozenset({
    "created_by_user_id",
    "created_by_name",
    "created_by_email",
    "created_by",
    "author",
})


def _strip_rappel_creator_from_updates(updates: dict) -> dict:
    for key in _RAPPEL_CREATOR_IMMUTABLE_KEYS:
        updates.pop(key, None)
    return updates


def _stamp_rappel_statut(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    statut = _normalize_rappel_statut(doc.get("statut"), doc.get("done"))
    doc["statut"] = statut
    doc["done"] = statut == "termine"
    overdue = _rappel_is_overdue(doc)
    doc["is_echeance_passee"] = overdue
    doc["statut_effectif"] = "echeance_passee" if overdue else statut
    return _stamp_rappel_creator(doc)


def _statut_field_updates(previous: dict, new_statut: str, user) -> dict:
    new_statut = _normalize_rappel_statut(new_statut)
    was_done = _normalize_rappel_statut(previous.get("statut"), previous.get("done")) == "termine"
    now_done = new_statut == "termine"
    updates = {"statut": new_statut, "done": now_done}
    if now_done and not was_done:
        updates["done_at"] = datetime.now(timezone.utc).isoformat()
        updates["done_by"] = user.account_id
        updates["done_by_name"] = getattr(user, "name", None) or None
    elif not now_done and was_done:
        updates["done_at"] = None
        updates["done_by"] = None
        updates["done_by_name"] = None
    return updates


async def _enrich_demande_with_client(demande: dict) -> dict:
    client_id = demande.get("client_id")
    if not client_id:
        demande["client_name"] = None
        return demande
    c = await db.clients.find_one(
        {"id": client_id},
        {"_id": 0, "prenom": 1, "nom": 1, "numero_dossier": 1},
    )
    if c:
        demande["client_name"] = f"{c.get('prenom') or ''} {c.get('nom') or ''}".strip() or None
        demande["numero_dossier"] = c.get("numero_dossier")
    else:
        demande["client_name"] = None
    return _stamp_rappel_statut(demande)


@api_router.get("/demandes")
async def list_all_demandes(
    done: Optional[bool] = Query(None),
    statut: Optional[str] = Query(None),
    conseiller: Optional[str] = None,
    date: Optional[str] = None,
    mine: Optional[bool] = Query(False, description="Si true : uniquement les rappels créés par l'utilisateur connecté"),
    user: User = Depends(get_current_user),
):
    """Liste globale des rappels (ex-demandes). done=null et statut=null → tous."""
    client_ids = await accessible_client_ids(db, user, conseiller=conseiller)
    query: dict = {"user_id": user.user_id, "client_id": {"$in": client_ids}}
    and_clauses: list = []
    if mine:
        # Mes rappels : id créateur uniquement (legacy created_by ok ; sans id → exclus)
        creator_id = (user.account_id or "").strip()
        if not creator_id:
            return []
        and_clauses.append({
            "$or": [
                {"created_by_user_id": creator_id},
                {"created_by": creator_id},
            ]
        })
    if statut:
        s = _normalize_rappel_statut(statut)
        if s == "termine":
            and_clauses.append({"$or": [{"done": True}, {"statut": "termine"}]})
        elif s == "en_attente":
            query["statut"] = "en_attente"
            query["done"] = {"$ne": True}
        else:
            query["done"] = {"$ne": True}
            query["statut"] = {"$nin": ["en_attente", "termine"]}
    elif done is not None:
        if done:
            and_clauses.append({"$or": [{"done": True}, {"statut": "termine"}]})
        else:
            query["done"] = {"$ne": True}
    if date:
        query["date"] = str(date)[:10]
    if and_clauses:
        if len(and_clauses) == 1 and "$or" in and_clauses[0] and not any(
            k.startswith("$") for k in query
        ):
            # Un seul $or + champs simples → fusion directe
            query["$or"] = and_clauses[0]["$or"]
        else:
            query["$and"] = and_clauses
    demandes = await db.demandes.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    # Tri : date/heure croissantes pour les ouverts, sinon created_at
    def _sort_key(d):
        return (
            d.get("date") or "9999-99-99",
            d.get("heure") or "99:99",
            d.get("created_at") or "",
        )
    demandes.sort(key=_sort_key)
    enriched = []
    for d in demandes:
        enriched.append(await _enrich_demande_with_client(d))
    return enriched


@api_router.get("/rappels/email-status")
async def rappel_email_status(user: User = Depends(get_current_user)):
    """État SMTP pour l'onglet Rappels (sans confondre avec le module Offres)."""
    from email_service import mail_status_public, smtp_from_address, smtp_configured

    del user
    status = mail_status_public()
    # Ne pas exposer offres@ ici — réservé au module Demandes d'offres
    return {
        "smtp_configured": bool(status.get("smtp_configured") or smtp_configured()),
        "provider": status.get("provider"),
        "smtp_from": status.get("smtp_from") or smtp_from_address() or None,
        "smtp_from_name": status.get("smtp_from_name"),
        "smtp_host": status.get("smtp_host"),
        "smtp_port": status.get("smtp_port"),
        "notify_rule": "creator",
        "notify_hint": "Chaque rappel est envoyé à l'e-mail de la personne qui l'a créé.",
    }


@api_router.post("/admin/smtp-test")
async def admin_smtp_test(
    to: Optional[str] = Query(None, description="Si fourni, envoie un e-mail de test à cette adresse"),
    user: User = Depends(get_current_user),
):
    """
    Admin : teste la connexion SMTP Infomaniak.
    Avec ?to=adresse@… : envoie aussi un e-mail de test depuis SMTP_FROM.
    """
    require_admin(user)
    from email_service import (
        MAIL_TYPE_TEST,
        mail_status_public,
        send_email_async,
        smtp_from_address,
        test_smtp_connection,
    )

    status = mail_status_public()
    ok, err = test_smtp_connection()
    result = {
        **status,
        "connection_ok": ok,
        "connection_error": err,
        "test_email_sent": False,
        "test_email_to": None,
        "test_email_error": None,
    }
    if not ok:
        return result

    dest = (to or "").strip()
    if dest:
        subject = "Test SMTP LeoSoft"
        body = (
            "Ceci est un e-mail de test envoyé depuis le CRM.\n\n"
            f"Expéditeur configuré : {smtp_from_address()}\n"
            "Si vous recevez ce message, la boîte SMTP Infomaniak fonctionne.\n"
        )
        body_html = (
            "<div style='font-family:Arial,sans-serif;font-size:14px;line-height:1.5;'>"
            "<p>Ceci est un e-mail de test envoyé depuis le CRM.</p>"
            f"<p>Expéditeur configuré : <strong>{smtp_from_address()}</strong></p>"
            "<p>Si vous recevez ce message, la boîte SMTP Infomaniak fonctionne.</p>"
            "</div>"
        )
        sent, send_err = await send_email_async(
            dest,
            subject,
            body,
            body_html=body_html,
            mail_type=MAIL_TYPE_TEST,
            log_meta={
                "module": "admin_smtp_test",
                "created_by": getattr(user, "email", None) or getattr(user, "name", None),
                "user_id": getattr(user, "user_id", None),
                "event": "smtp_test",
                "client_label": None,
            },
        )
        result["test_email_sent"] = bool(sent)
        result["test_email_to"] = dest
        result["test_email_error"] = send_err
    return result


@api_router.post("/admin/rappels/process-emails")
async def admin_process_rappel_emails(user: User = Depends(get_current_user)):
    """Admin : force un passage immédiat du job d'envoi des rappels dus."""
    require_admin(user)
    # Réarme les rappels dus dont le dernier envoi a échoué (email_sent encore false)
    n = await _process_rappel_emails_once()
    return {"ok": True, "batches_sent": n}


@api_router.get("/rappels")
async def list_all_rappels(
    done: Optional[bool] = Query(None),
    statut: Optional[str] = Query(None),
    conseiller: Optional[str] = None,
    date: Optional[str] = None,
    mine: Optional[bool] = Query(False),
    user: User = Depends(get_current_user),
):
    return await list_all_demandes(
        done=done, statut=statut, conseiller=conseiller, date=date, mine=mine, user=user
    )


@api_router.get("/rappels/mine")
async def list_my_rappels(
    done: Optional[bool] = Query(None),
    statut: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
):
    """Rappels créés par l'utilisateur connecté uniquement (Mes rappels)."""
    return await list_all_demandes(done=done, statut=statut, mine=True, user=user)


@api_router.get("/clients/{client_id}/demandes")
async def list_client_demandes(client_id: str, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, c)
    dossier_ids = scope.get("dossier_ids") or [scope["dossier_id"]]
    query = {
        "user_id": user.user_id,
        "$or": [
            {"client_id": {"$in": scope["member_ids"]}},
            {"dossier_id": {"$in": dossier_ids}},
        ],
    }
    demandes = await db.demandes.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    open_ones = [d for d in demandes if not d.get("done")]
    done_ones = [d for d in demandes if d.get("done")]
    open_ones.sort(key=lambda d: (d.get("date") or "9999", d.get("heure") or "99:99", d.get("created_at") or ""))
    done_ones.sort(key=lambda d: (d.get("date") or "9999", d.get("heure") or "99:99", d.get("created_at") or ""), reverse=True)
    return [_stamp_rappel_statut(d) for d in (open_ones + done_ones)]


@api_router.get("/clients/{client_id}/rappels")
async def list_client_rappels(client_id: str, user: User = Depends(get_current_user)):
    return await list_client_demandes(client_id, user)


def _normalize_heure(heure: Optional[str]) -> Optional[str]:
    if heure is None:
        return None
    s = str(heure).strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        raise HTTPException(status_code=400, detail="Heure invalide (attendu HH:MM)")
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        raise HTTPException(status_code=400, detail="Heure invalide (attendu HH:MM)")
    return f"{h:02d}:{mi:02d}"


def _normalize_rappel_date(date_str: Optional[str]) -> Optional[str]:
    if date_str is None:
        return None
    s = str(date_str).strip()
    if not s:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", s)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    raise HTTPException(status_code=400, detail="Date invalide (attendu AAAA-MM-JJ)")


@api_router.post("/clients/{client_id}/demandes")
async def create_demande(client_id: str, payload: DemandeCreate, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    titre = (payload.titre or "").strip()
    if not titre:
        raise HTTPException(status_code=400, detail="Titre obligatoire")
    description = (payload.description or "").strip() or None
    rappel_date = _normalize_rappel_date(payload.date)
    if not rappel_date:
        raise HTTPException(status_code=400, detail="Date obligatoire")
    heure = _normalize_heure(payload.heure)
    scope = await _dossier_scope(user.user_id, c)
    now_iso = datetime.now(timezone.utc).isoformat()
    send_email = True if payload.send_email is None else bool(payload.send_email)
    notify_crm = True if payload.notify_crm is None else bool(payload.notify_crm)
    if not send_email and not notify_crm:
        raise HTTPException(
            status_code=400,
            detail="Activez au moins l'e-mail ou la notification CRM",
        )
    creator_email = (getattr(user, "email", None) or "").strip() or None
    if send_email and not creator_email:
        raise HTTPException(
            status_code=400,
            detail="Aucune adresse e-mail sur votre compte — désactivez l'e-mail ou mettez à jour votre profil",
        )
    # Sécurité : un rappel ne part jamais vers la boîte offres@
    if send_email and creator_email:
        try:
            from email_service import offres_email_to

            if creator_email.lower() == (offres_email_to() or "").strip().lower():
                raise HTTPException(
                    status_code=400,
                    detail="Adresse e-mail du compte invalide pour les rappels — contactez un administrateur",
                )
        except HTTPException:
            raise
        except Exception:
            pass
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "client_id": client_id,
        "dossier_id": scope["dossier_id"],
        "titre": titre,
        "description": description,
        "date": rappel_date,
        "heure": heure,
        "priorite": _normalize_demande_priorite(payload.priorite),
        "statut": "a_faire",
        "done": False,
        **_rappel_creator_snapshot(user),
        "send_email": send_email,
        "notify_crm": notify_crm,
        "notify_email": creator_email if send_email else None,
        "email_sent": False,
        "email_notified_offsets": [],
        "email_notified_at": None,
        "conseiller": c.get("conseiller"),
        "created_at": now_iso,
        "done_at": None,
        "done_by": None,
        "done_by_name": None,
    }
    await db.demandes.insert_one(doc)
    await log_action(user.user_id, client_id, f"Rappel créé: {titre}", dossier_id=scope["dossier_id"])
    doc.pop("_id", None)
    return await _enrich_demande_with_client(doc)


@api_router.post("/clients/{client_id}/rappels")
async def create_rappel(client_id: str, payload: DemandeCreate, user: User = Depends(get_current_user)):
    return await create_demande(client_id, payload, user)


@api_router.post("/rappels")
async def create_rappel_global(payload: DemandeCreate, user: User = Depends(get_current_user)):
    client_id = (payload.client_id or "").strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="Client associé obligatoire")
    return await create_demande(client_id, payload, user)


@api_router.patch("/demandes/{demande_id}")
async def update_demande(demande_id: str, payload: DemandeUpdate, user: User = Depends(get_current_user)):
    d = await db.demandes.find_one({"id": demande_id, "user_id": user.user_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Rappel introuvable")
    await require_resource_client(d, user, "demande")

    updates: dict = {}
    if payload.titre is not None:
        titre = payload.titre.strip()
        if not titre:
            raise HTTPException(status_code=400, detail="Titre obligatoire")
        updates["titre"] = titre
    if payload.description is not None:
        updates["description"] = payload.description.strip() or None
    if payload.date is not None:
        updates["date"] = _normalize_rappel_date(payload.date)
        if not updates["date"]:
            raise HTTPException(status_code=400, detail="Date obligatoire")
        updates["email_sent"] = False
        updates["email_notified_offsets"] = []
        updates["email_notified_at"] = None
    if payload.heure is not None:
        updates["heure"] = _normalize_heure(payload.heure)
        updates["email_sent"] = False
        updates["email_notified_offsets"] = []
        updates["email_notified_at"] = None
    if payload.priorite is not None:
        updates["priorite"] = _normalize_demande_priorite(payload.priorite)
    if payload.send_email is not None:
        updates["send_email"] = bool(payload.send_email)
        if updates["send_email"]:
            dest = None
            creator_id = (
                (d.get("created_by_user_id") or d.get("created_by") or "")
            ).strip()
            if creator_id:
                u = await db.users.find_one(
                    {"$or": [{"user_id": creator_id}, {"account_id": creator_id}]},
                    {"_id": 0, "email": 1},
                )
                dest = ((u or {}).get("email") or "").strip() or None
            if not dest:
                dest = (
                    d.get("created_by_email")
                    or d.get("notify_email")
                    or getattr(user, "email", None)
                    or ""
                ).strip() or None
            # Jamais la boîte offres@ pour un rappel
            try:
                from email_service import offres_email_to

                offres_box = (offres_email_to() or "").strip().lower()
                if dest and offres_box and dest.strip().lower() == offres_box:
                    dest = (getattr(user, "email", None) or "").strip() or None
            except Exception:
                pass
            if not dest:
                raise HTTPException(
                    status_code=400,
                    detail="Aucune adresse e-mail disponible pour ce rappel",
                )
            updates["notify_email"] = dest
            updates["email_sent"] = False
            updates["email_notified_at"] = None
            updates["email_notified_offsets"] = []
        else:
            updates["notify_email"] = None
    if payload.notify_crm is not None:
        updates["notify_crm"] = bool(payload.notify_crm)
    if payload.client_id is not None and payload.client_id != d.get("client_id"):
        new_c = await require_client(payload.client_id, user)
        scope = await _dossier_scope(user.user_id, new_c)
        updates["client_id"] = payload.client_id
        updates["dossier_id"] = scope["dossier_id"]
        updates["conseiller"] = new_c.get("conseiller")

    # Au moins un canal actif après patch
    final_send = updates.get("send_email", d.get("send_email", True))
    final_crm = updates.get("notify_crm", d.get("notify_crm", True))
    if final_send is False and final_crm is False:
        raise HTTPException(
            status_code=400,
            detail="Activez au moins l'e-mail ou la notification CRM",
        )

    if payload.statut is not None or payload.done is not None:
        if payload.statut is not None:
            new_statut = _normalize_rappel_statut(payload.statut, payload.done)
        else:
            new_statut = "termine" if payload.done else "a_faire"
        updates.update(_statut_field_updates(d, new_statut, user))

    if updates:
        _strip_rappel_creator_from_updates(updates)
        await db.demandes.update_one({"id": demande_id, "user_id": user.user_id}, {"$set": updates})

    updated = await db.demandes.find_one({"id": demande_id}, {"_id": 0})
    return await _enrich_demande_with_client(updated)


@api_router.patch("/rappels/{rappel_id}")
async def update_rappel(rappel_id: str, payload: DemandeUpdate, user: User = Depends(get_current_user)):
    return await update_demande(rappel_id, payload, user)


@api_router.post("/rappels/{rappel_id}/effectuer")
async def effectuer_rappel(rappel_id: str, user: User = Depends(get_current_user)):
    return await update_demande(rappel_id, DemandeUpdate(done=True), user)


@api_router.post("/rappels/{rappel_id}/reporter")
async def reporter_rappel(rappel_id: str, payload: DemandeReporter, user: User = Depends(get_current_user)):
    """Report à une nouvelle date/heure et réarme email_sent=false."""
    d = await db.demandes.find_one({"id": rappel_id, "user_id": user.user_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Rappel introuvable")
    await require_resource_client(d, user, "demande")
    days = int(payload.days or 14)
    if days < 1:
        raise HTTPException(status_code=400, detail="Le report doit être d'au moins 1 jour")
    if payload.date:
        new_date = _normalize_rappel_date(payload.date)
    else:
        base_date = (d.get("date") or "")[:10]
        if not base_date:
            raise HTTPException(status_code=400, detail="Date actuelle du rappel manquante")
        try:
            from datetime import date as date_cls

            new_date = (date_cls.fromisoformat(base_date) + timedelta(days=days)).isoformat()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Date actuelle du rappel invalide") from exc
    if not new_date:
        raise HTTPException(status_code=400, detail="Date obligatoire")
    new_heure = _normalize_heure(payload.heure) if payload.heure is not None else _normalize_heure(d.get("heure"))
    now_iso = datetime.now(timezone.utc).isoformat()
    prev_statut = _normalize_rappel_statut(d.get("statut"), d.get("done"))
    new_statut = "en_attente" if prev_statut == "en_attente" else "a_faire"
    updates = {
        "date": new_date,
        "heure": new_heure,
        "statut": new_statut,
        "done": False,
        "done_at": None,
        "done_by": None,
        "done_by_name": None,
        "email_sent": False,
        "email_notified_at": None,
        "email_notified_offsets": [],
        "reported_at": now_iso,
        "reported_by": user.account_id,
        "previous_date": d.get("date"),
        "previous_heure": d.get("heure"),
    }
    _strip_rappel_creator_from_updates(updates)
    await db.demandes.update_one({"id": rappel_id, "user_id": user.user_id}, {"$set": updates})
    updated = await db.demandes.find_one({"id": rappel_id}, {"_id": 0})
    return await _enrich_demande_with_client(updated)


@api_router.get("/notifications/rappels")
async def notifications_rappels(user: User = Depends(get_current_user)):
    """Rappels CRM en attente pour la cloche (notify_crm, non effectués)."""
    from zoneinfo import ZoneInfo

    client_ids = await accessible_client_ids(db, user)
    rows = await db.demandes.find(
        {
            "user_id": user.user_id,
            "client_id": {"$in": client_ids},
            "done": {"$ne": True},
            "notify_crm": {"$ne": False},
        },
        {"_id": 0},
    ).to_list(2000)

    now = datetime.now(ZoneInfo("Europe/Zurich"))
    today = now.date().isoformat()
    horizon = (now.date() + timedelta(days=7)).isoformat()
    pending = []
    for r in rows:
        if r.get("notify_crm") is False:
            continue
        if _normalize_rappel_statut(r.get("statut"), r.get("done")) == "en_attente":
            continue
        date_s = (r.get("date") or "")[:10]
        enriched = await _enrich_demande_with_client(dict(r))
        overdue = bool(enriched.get("is_echeance_passee"))
        if not date_s:
            continue
        if not overdue and date_s > horizon:
            continue
        due = await _rappel_due_datetime(r)
        enriched["is_due"] = bool(due and now >= due)
        enriched["is_overdue"] = overdue
        pending.append(enriched)

    pending.sort(
        key=lambda d: (
            d.get("date") or "9999",
            d.get("heure") or "99:99",
            d.get("created_at") or "",
        )
    )
    due_count = sum(
        1
        for p in pending
        if p.get("is_due") or p.get("is_overdue") or (p.get("date") or "")[:10] <= today
    )
    return {
        "count": due_count,
        "total": len(pending),
        "items": pending[:50],
    }


@api_router.get("/rappel-email-logs")
async def list_rappel_email_logs(
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(get_current_user),
):
    """Historique des e-mails rappels — réservé à l'administrateur."""
    from email_service import EMAIL_LOGS_COLLECTION

    require_admin(user)
    query: dict = {}
    # Préférer le journal unifié ; compléter avec l'ancien rappel_email_logs
    unified = await db[EMAIL_LOGS_COLLECTION].find(query, {"_id": 0}).to_list(limit * 2)
    legacy_q = dict(query)
    legacy = await db.rappel_email_logs.find(legacy_q, {"_id": 0}).to_list(limit * 2)
    for row in legacy:
        row.setdefault("type", "rappel")
        if row.get("status") == "failed":
            row["status"] = "error"
        row.setdefault("to", row.get("to_email"))
    # Dédupliquer par id
    by_id = {r.get("id"): r for r in legacy + unified if r.get("id")}
    rows = list(by_id.values())
    rows.sort(key=lambda x: x.get("sent_at") or x.get("created_at") or "", reverse=True)
    return rows[:limit]


def _public_email_row(row: dict, *, detail: bool = False) -> dict:
    """Projection list/détail pour l'historique e-mails CRM."""
    from email_service import normalize_email_status

    extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
    status_raw = (row.get("status") or "").strip().lower()
    if status_raw in {"sent", "ok", "success", "pending", "en_cours", "in_progress", "processing", "skipped", "skip", "error", "failed", "fail"}:
        status = normalize_email_status(status_raw)
    else:
        status = status_raw or ""

    client_label = row.get("client_label") or extra.get("client_label") or ""
    if not client_label and row.get("rappel_count") and int(row.get("rappel_count") or 0) > 1:
        client_label = f"{row.get('rappel_count')} clients"

    out = {
        "id": row.get("id"),
        "type": row.get("type") or row.get("mail_type") or "",
        "to": row.get("to") or row.get("to_email") or "",
        "from": row.get("from") or row.get("from_email") or "",
        "cc": list(row.get("cc") or []),
        "bcc": list(row.get("bcc") or []),
        "subject": row.get("subject") or row.get("email_subject") or "",
        "status": status,
        "error": row.get("error"),
        "client_id": row.get("client_id"),
        "client_label": client_label,
        "numero": row.get("numero") or "",
        "numero_dossier": row.get("numero_dossier") or "",
        "ref_id": row.get("ref_id"),
        "agent_label": row.get("agent_label") or "",
        "module": row.get("module") or extra.get("module") or "",
        "sent_at": row.get("sent_at") or row.get("created_at"),
        "created_at": row.get("created_at"),
        "attachments": list(row.get("attachments") or []),
        "kind": row.get("kind") or extra.get("kind") or "",
        "rappel_count": row.get("rappel_count") or extra.get("rappel_count"),
        "message_id": row.get("message_id") or "",
        "created_by": row.get("created_by") or "",
    }
    if detail:
        out["body_preview"] = row.get("body_preview") or ""
        out["body_text"] = row.get("body_text") or row.get("body_preview") or ""
        out["body_html"] = row.get("body_html") or None
        out["form_type_label"] = row.get("form_type_label") or ""
        out["event"] = row.get("event") or ""
        out["dossier_id"] = row.get("dossier_id")
    return out


@api_router.get("/emails")
async def list_crm_emails(
    limit: int = Query(100, ge=1, le=500),
    mail_type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date début (inclus) — ex. 2026-09-01"),
    date_to: Optional[str] = Query(None, description="ISO date fin (inclus) — ex. 2026-09-22"),
    include_old_errors: bool = Query(
        False,
        description="Inclure les anciens échecs rappels (Resend/SMTP d'avant le 10/09/2026)",
    ),
    user: User = Depends(get_current_user),
):
    """
    Historique des e-mails CRM — réservé à l'administrateur (users.manage).
    Tous types : offres, rappels, dossiers présentés, tests SMTP, notifications…
    """
    from email_service import EMAIL_LOGS_COLLECTION, normalize_email_status

    require_admin(user)

    # Coupe nette : avant cette date, ~15k échecs Resend polluent l'historique
    LEGACY_ERROR_CUTOFF = "2026-09-10T00:00:00"

    query: dict = {}
    if mail_type and mail_type.strip() and mail_type != "all":
        query["type"] = mail_type.strip()
    try:
        rows = await db[EMAIL_LOGS_COLLECTION].find(query, {"_id": 0}).to_list(limit * 5)
    except Exception:
        logger.exception("email_logs find failed")
        rows = []
    if not mail_type or mail_type in ("all", "rappel", None):
        try:
            legacy = await db.rappel_email_logs.find({}, {"_id": 0}).to_list(limit * 2)
        except Exception:
            legacy = []
        for row in legacy:
            row.setdefault("type", "rappel")
            if row.get("status") == "failed":
                row["status"] = "error"
            row.setdefault("to", row.get("to_email"))
            row.setdefault("subject", row.get("subject") or "")
            rows.append(row)

    by_id = {}
    for r in rows:
        rid = r.get("id")
        if rid:
            # Préférer email_logs (déjà dans by_id) à un doublon legacy
            if rid not in by_id:
                by_id[rid] = r
        else:
            by_id[f"_noid_{len(by_id)}"] = r
    out = list(by_id.values())

    if not include_old_errors:
        filtered_old = []
        for r in out:
            st = (r.get("status") or "").strip().lower()
            when = str(r.get("sent_at") or r.get("created_at") or "")
            is_error = st in {"error", "failed", "fail"}
            if is_error and when and when < LEGACY_ERROR_CUTOFF:
                continue
            filtered_old.append(r)
        out = filtered_old

    # Dédupliquer envois récents loggés 2× (email_logs + rappel_email_logs)
    def _dedupe_key(r: dict) -> str:
        to_v = (r.get("to") or r.get("to_email") or "").strip().lower()
        subj = (r.get("subject") or "").strip().casefold()
        when = str(r.get("sent_at") or r.get("created_at") or "")[:16]  # à la minute
        return f"{to_v}|{subj}|{when}"

    def _rank(r: dict) -> tuple:
        st = (r.get("status") or "").strip().lower()
        # Préférer sent, puis email_logs (provider smtp), puis id stable
        sent_rank = 0 if st in {"sent", "ok", "success"} else 1
        provider = 0 if (r.get("provider") or "") == "smtp_infomaniak" else 1
        has_body = 0 if (r.get("body_text") or r.get("body_html") or r.get("body_preview")) else 1
        return (sent_rank, provider, has_body)

    deduped: dict = {}
    for r in out:
        key = _dedupe_key(r)
        prev = deduped.get(key)
        if prev is None or _rank(r) < _rank(prev):
            deduped[key] = r
    out = list(deduped.values())

    status_filter = (status or "").strip().lower()
    if status_filter and status_filter != "all":
        if status_filter in {"error", "failed", "echec", "échec"}:
            want = "error"
        elif status_filter in {"pending", "en_cours", "encours", "in_progress"}:
            want = "pending"
        elif status_filter in {"sent", "envoye", "envoyé", "ok"}:
            want = "sent"
        else:
            want = normalize_email_status(status_filter) if status_filter else status_filter
        filtered_status = []
        for r in out:
            st = normalize_email_status(r.get("status") or "") if (r.get("status") or "").strip() else ""
            # pending bruts non normalisés (legacy)
            raw = (r.get("status") or "").strip().lower()
            if want == "pending" and raw in {"pending", "en_cours", "in_progress", "processing"}:
                filtered_status.append(r)
            elif want == "sent" and st == "sent":
                filtered_status.append(r)
            elif want == "error" and st == "error":
                filtered_status.append(r)
            elif st == want:
                filtered_status.append(r)
        out = filtered_status

    # Filtre période (comparaison lexicographique ISO)
    df = (date_from or "").strip()[:10]
    dt = (date_to or "").strip()[:10]
    if df or dt:
        period_filtered = []
        for r in out:
            when = str(r.get("sent_at") or r.get("created_at") or "")[:10]
            if not when:
                continue
            if df and when < df:
                continue
            if dt and when > dt:
                continue
            period_filtered.append(r)
        out = period_filtered

    needle = (q or "").strip().casefold()
    if needle:
        filtered = []
        for r in out:
            hay = " ".join(
                str(x or "")
                for x in (
                    r.get("to"),
                    r.get("to_email"),
                    r.get("from"),
                    r.get("client_label"),
                    r.get("numero"),
                    r.get("numero_dossier"),
                    r.get("subject"),
                    r.get("type"),
                    r.get("agent_label"),
                    r.get("module"),
                    r.get("created_by"),
                )
            ).casefold()
            if needle in hay:
                filtered.append(r)
        out = filtered
    out.sort(key=lambda x: x.get("sent_at") or x.get("created_at") or "", reverse=True)
    return [_public_email_row(r) for r in out[:limit]]


@api_router.get("/emails/{email_id}")
async def get_crm_email(
    email_id: str,
    user: User = Depends(get_current_user),
):
    """Détail / aperçu d'un e-mail du journal CRM — admin uniquement."""
    from email_service import EMAIL_LOGS_COLLECTION

    require_admin(user)

    row = None
    try:
        row = await db[EMAIL_LOGS_COLLECTION].find_one({"id": email_id}, {"_id": 0})
    except Exception:
        logger.exception("email_logs get failed id=%s", email_id)
    if not row:
        row = await db.rappel_email_logs.find_one({"id": email_id}, {"_id": 0})
        if row:
            row.setdefault("type", "rappel")
            row.setdefault("to", row.get("to_email"))
            row.setdefault("subject", row.get("subject") or "")
    if not row:
        raise HTTPException(status_code=404, detail="E-mail introuvable")
    return _public_email_row(row, detail=True)


@api_router.get("/admin/email-logs")
async def admin_email_logs(
    limit: int = Query(100, ge=1, le=500),
    mail_type: Optional[str] = Query(None, alias="type"),
    include_old_errors: bool = Query(False),
    user: User = Depends(get_current_user),
):
    """Journal unifié des e-mails CRM (admin / users.manage)."""
    from email_service import EMAIL_LOGS_COLLECTION

    require_admin(user)
    LEGACY_ERROR_CUTOFF = "2026-09-10T00:00:00"
    query: dict = {}
    if mail_type and mail_type.strip() and mail_type != "all":
        query["type"] = mail_type.strip()
    rows = await db[EMAIL_LOGS_COLLECTION].find(query, {"_id": 0}).to_list(limit * 2)
    # Inclure anciens logs rappels si journal encore vide / partiel
    if not mail_type or mail_type in ("all", "rappel", None):
        legacy = await db.rappel_email_logs.find({}, {"_id": 0}).to_list(limit)
        for row in legacy:
            row.setdefault("type", "rappel")
            if row.get("status") == "failed":
                row["status"] = "error"
            row.setdefault("to", row.get("to_email"))
            rows.append(row)
    by_id = {}
    for r in rows:
        rid = r.get("id")
        if rid:
            by_id[rid] = r
    out = list(by_id.values())
    if not include_old_errors:
        out = [
            r
            for r in out
            if not (
                (r.get("status") or "").strip().lower() in {"error", "failed", "fail"}
                and str(r.get("sent_at") or r.get("created_at") or "") < LEGACY_ERROR_CUTOFF
            )
        ]
    out.sort(key=lambda x: x.get("sent_at") or x.get("created_at") or "", reverse=True)
    return [_public_email_row(r) for r in out[:limit]]


@api_router.delete("/demandes/{demande_id}")
async def delete_demande(demande_id: str, user: User = Depends(get_current_user)):
    d = await db.demandes.find_one({"id": demande_id, "user_id": user.user_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Rappel introuvable")
    await require_resource_client(d, user, "demande")
    await db.demandes.delete_one({"id": demande_id, "user_id": user.user_id})
    return {"ok": True}


@api_router.delete("/rappels/{rappel_id}")
async def delete_rappel(rappel_id: str, user: User = Depends(get_current_user)):
    return await delete_demande(rappel_id, user)

# ---------------- Actions history ----------------
@api_router.get("/clients/{client_id}/actions")
async def list_actions(client_id: str, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, c)
    query = {
        "user_id": user.user_id,
        "$or": [
            {"client_id": {"$in": scope["member_ids"]}},
            {"dossier_id": scope["dossier_id"]},
        ],
    }
    return await db.actions.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)

# ---------------- Documents ----------------
# ---------------- Documents ----------------
async def _store_pdf_bytes(user_id: str, pdf_bytes: bytes, meta: dict, client_id: str, checklist_item: Optional[str] = None) -> dict:
    pdf_bytes = await _resolve_maybe_awaitable(pdf_bytes)
    pdf_bytes = _coerce_file_bytes(pdf_bytes, label="document généré")
    content_type = meta.get("content_type") or "application/pdf"
    filename = meta.get("original_filename") or "document.pdf"
    if filename.lower().endswith(".docx") or "wordprocessingml" in content_type:
        ext = "docx"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        ext = "pdf"
        content_type = "application/pdf"
    path = f"{APP_NAME}/generated/{user_id}/{uuid.uuid4()}.{ext}"
    try:
        result = await asyncio.to_thread(put_object, path, pdf_bytes, content_type)
        storage_path = result["path"]
        size = result.get("size", len(pdf_bytes))
    except Exception as e:
        logger.error(f"Storage upload failed for generated document: {e}")
        local_name = f"{uuid.uuid4()}.{ext}"
        storage_path = await asyncio.to_thread(
            _local_storage_fallback, ROOT_DIR / "generated" / user_id, local_name, pdf_bytes
        )
        size = len(pdf_bytes)

    docx_storage_path = None
    docx_filename = meta.get("docx_filename")
    docx_bytes = meta.get("docx_bytes")
    if docx_bytes:
        docx_bytes = _coerce_file_bytes(docx_bytes, label="docx généré")
        docx_filename = docx_filename or (filename.rsplit(".", 1)[0] + ".docx")
        docx_ctype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        docx_path = f"{APP_NAME}/generated/{user_id}/{uuid.uuid4()}.docx"
        try:
            docx_result = await asyncio.to_thread(put_object, docx_path, docx_bytes, docx_ctype)
            docx_storage_path = docx_result["path"]
        except Exception as e:
            logger.error(f"Storage upload failed for Word companion: {e}")
            local_name = f"{uuid.uuid4()}.docx"
            docx_storage_path = await asyncio.to_thread(
                _local_storage_fallback, ROOT_DIR / "generated" / user_id, local_name, docx_bytes
            )

    client = await db.clients.find_one({"id": client_id, "user_id": user_id}, {"_id": 0})
    if not client:
        client = {"id": client_id}
    scope = await _dossier_scope(user_id, client)
    dossier_id = scope.get("dossier_id") or (client or {}).get("dossier_id") or meta.get("dossier_id") or client_id
    category = meta.get("category") or "Autre"
    checklist = checklist_item or meta.get("checklist_item")
    is_couple = _is_couple_scope(scope)
    shared_dossier = (
        is_couple
        or category in SHARED_DOSSIER_DOC_CATEGORIES
        or (checklist or "") in SHARED_DOSSIER_DOC_CATEGORIES
    )

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "client_id": client_id,
        "dossier_id": dossier_id if shared_dossier else (client or {}).get("dossier_id"),
        "shared_dossier": shared_dossier,
        "storage_path": storage_path,
        "original_filename": meta["original_filename"],
        "content_type": content_type,
        "size": size,
        "category": meta.get("category") or "Autre",
        "template_id": meta.get("template_id"),
        "checklist_item": checklist_item or meta.get("checklist_item"),
        "caisse_name": meta.get("caisse_name"),
        "caisse_address": meta.get("caisse_address"),
        "caisse_reference": meta.get("caisse_reference"),
        "lpp_person": meta.get("lpp_person"),
        "lpp_tracking_id": meta.get("lpp_tracking_id"),
        "assure_prenom": meta.get("assure_prenom"),
        "assure_nom": meta.get("assure_nom"),
        "assure_avs": meta.get("assure_avs"),
        "generated": True,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if docx_storage_path:
        doc["docx_storage_path"] = docx_storage_path
        doc["docx_filename"] = docx_filename
        doc["has_word_download"] = True
    await db.documents.insert_one(doc)
    doc.pop("_id", None)
    return public_storage_record(doc)


@api_router.get("/clients/{client_id}/documents")
async def list_documents(
    client_id: str,
    limit: int = Query(2000, ge=1, le=10000),
    user: User = Depends(get_current_user),
):
    """Documents du client ; pour un couple, tous les documents du dossier familial."""
    client = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, client)
    query = _documents_list_query(user.user_id, client_id, scope)
    rows = await db.documents.find(
        query,
        {"_id": 0, "storage_path": 0, "storage_path_legacy": 0},
    ).sort("created_at", -1).to_list(limit)
    return rows


async def _reconcile_echeances_3p_lines(user_id: str, client_id: str) -> None:
    """
    Synchronisation stricte :
    - 1 document PDF « Police 3e pilier » = 1 ligne Échéance 3P
    - Les lignes manuelles (sans source_doc_id) sont conservées
    - Pour chaque PDF 3P sans ligne, crée une ligne (extraction si possible)
    - Supprime les lignes liées à des documents disparus
    """
    client = await db.clients.find_one({"id": client_id, "user_id": user_id}, {"_id": 0})
    if not client:
        return

    three_p_labels = ["Police 3e pilier", "Police de 3e pilier"]
    scope = await _dossier_scope(user_id, client)
    doc_query = _documents_list_query(user_id, client_id, scope)
    doc_or = doc_query.pop("$or")
    docs = await db.documents.find(
        {
            **doc_query,
            "$and": [
                {"$or": doc_or},
                {
                    "$or": [
                        {"checklist_item": {"$in": three_p_labels}},
                        {"category": {"$in": three_p_labels}},
                    ]
                },
            ],
        },
        {"_id": 0},
    ).to_list(1000)
    docs_by_id = {d.get("id"): d for d in docs if d.get("id")}
    doc_ids = set(docs_by_id.keys())

    lines = client.get("echeances_3p") or []
    if not isinstance(lines, list):
        lines = []

    now_iso = datetime.now(timezone.utc).isoformat()
    manual_lines = []
    best_by_source = {}

    for l in lines:
        if not isinstance(l, dict):
            continue
        sid = l.get("source_doc_id")
        if not sid:
            # Ligne saisie manuellement
            manual_lines.append(l)
            continue
        if sid not in doc_ids:
            continue
        updated = l.get("updated_at") or l.get("created_at") or ""
        prev = best_by_source.get(sid)
        prev_updated = (prev.get("updated_at") or prev.get("created_at") or "") if prev else ""
        if (not prev) or (updated >= prev_updated):
            best_by_source[sid] = l

    # Créer une ligne pour chaque PDF 3P qui n'en a pas encore.
    # Enrichir aussi document_type si manquant (sans écraser les corrections manuelles de date).
    for doc_id, doc in docs_by_id.items():
        if doc_id in best_by_source:
            existing_line = best_by_source[doc_id]
            if not existing_line.get("document_type"):
                extracted = doc.get("extracted_echeances_3p") or []
                entry = extracted[0] if isinstance(extracted, list) and extracted and isinstance(extracted[0], dict) else None
                if entry and entry.get("document_type"):
                    existing_line["document_type"] = _normalize_document_type_3p(entry.get("document_type"))
                    existing_line["updated_at"] = now_iso
                    if existing_line["document_type"] in {"Résiliation", "Rachat", "Libre passage"}:
                        existing_line["echeance_3p"] = None
                        existing_line["detected"] = False
                        existing_line["raw_date"] = None
                    elif not existing_line.get("echeance_3p") and entry.get("expiry_date"):
                        existing_line["echeance_3p"] = entry.get("expiry_date")
                        existing_line["detected"] = True
                        existing_line["raw_date"] = entry.get("raw_date")
                    if not existing_line.get("company") and entry.get("company"):
                        existing_line["company"] = entry.get("company")
                    if not existing_line.get("policy_number") and entry.get("policy_number"):
                        existing_line["policy_number"] = entry.get("policy_number")
                else:
                    # Ancien cache sans document_type → re-extraction une fois
                    storage_path = doc.get("storage_path")
                    ctype = (doc.get("content_type") or "").lower()
                    fname = (doc.get("original_filename") or "").lower()
                    if storage_path and (ctype == "application/pdf" or fname.endswith(".pdf")):
                        try:
                            data = _read_storage_bytes(storage_path)
                            detected = extract_3p_contracts_from_pdf(data) or []
                            entry = detected[0] if detected else {}
                            await db.documents.update_one(
                                {"id": doc_id},
                                {"$set": {
                                    "extracted_echeances_3p": detected,
                                    "extracted_echeance_3p": (entry or {}).get("expiry_date"),
                                    "extracted_document_type": (entry or {}).get("document_type"),
                                }},
                            )
                            if entry.get("document_type"):
                                existing_line["document_type"] = _normalize_document_type_3p(entry.get("document_type"))
                                existing_line["updated_at"] = now_iso
                            # Compléter compagnie / police / échéance seulement si vides
                            if not existing_line.get("company") and entry.get("company"):
                                existing_line["company"] = entry.get("company")
                            if not existing_line.get("policy_number") and entry.get("policy_number"):
                                existing_line["policy_number"] = entry.get("policy_number")
                            doc_type = existing_line.get("document_type") or _normalize_document_type_3p(entry.get("document_type"))
                            if (
                                not existing_line.get("echeance_3p")
                                and entry.get("expiry_date")
                                and doc_type not in {"Résiliation", "Rachat", "Libre passage"}
                            ):
                                existing_line["echeance_3p"] = entry.get("expiry_date")
                                existing_line["detected"] = True
                                existing_line["raw_date"] = entry.get("raw_date")
                            if doc_type in {"Résiliation", "Rachat", "Libre passage"}:
                                existing_line["echeance_3p"] = None
                                existing_line["detected"] = False
                                existing_line["raw_date"] = None
                            if not existing_line.get("document_type"):
                                existing_line["document_type"] = "Autre document"
                        except Exception:
                            logger.exception("Re-extraction type 3P échouée pour doc %s", doc_id)
                            if not existing_line.get("document_type"):
                                existing_line["document_type"] = "Autre document"
                    elif not existing_line.get("document_type"):
                        existing_line["document_type"] = "Autre document"
            # Re-extraction échéance manquante avec le moteur robuste (une seule fois / doc).
            doc_type = existing_line.get("document_type") or "Autre document"
            needs_expiry_refresh = (
                not existing_line.get("echeance_3p")
                and doc_type not in {"Résiliation", "Rachat", "Libre passage"}
                and doc.get("extracted_expiry_engine") != "v2-robust"
            )
            if needs_expiry_refresh:
                storage_path = doc.get("storage_path")
                ctype = (doc.get("content_type") or "").lower()
                fname = (doc.get("original_filename") or "").lower()
                if storage_path and (ctype == "application/pdf" or fname.endswith(".pdf")):
                    try:
                        data = _read_storage_bytes(storage_path)
                        detected = extract_3p_contracts_from_pdf(data) or []
                        entry = detected[0] if detected else {}
                        await db.documents.update_one(
                            {"id": doc_id},
                            {"$set": {
                                "extracted_echeances_3p": detected,
                                "extracted_echeance_3p": (entry or {}).get("expiry_date"),
                                "extracted_document_type": (entry or {}).get("document_type"),
                                "extracted_expiry_engine": "v2-robust",
                            }},
                        )
                        if entry.get("document_type") and not existing_line.get("document_type"):
                            existing_line["document_type"] = _normalize_document_type_3p(entry.get("document_type"))
                        if not existing_line.get("company") and entry.get("company"):
                            existing_line["company"] = entry.get("company")
                        if not existing_line.get("policy_number") and entry.get("policy_number"):
                            existing_line["policy_number"] = entry.get("policy_number")
                        if entry.get("expiry_date"):
                            existing_line["echeance_3p"] = entry.get("expiry_date")
                            existing_line["detected"] = True
                            existing_line["raw_date"] = entry.get("raw_date")
                            existing_line["updated_at"] = now_iso
                    except Exception:
                        logger.exception("Re-extraction échéance robuste échouée pour doc %s", doc_id)
                        await db.documents.update_one(
                            {"id": doc_id},
                            {"$set": {"extracted_expiry_engine": "v2-robust"}},
                        )
            continue

        entry = None
        extracted = doc.get("extracted_echeances_3p") or []
        if isinstance(extracted, list) and extracted:
            entry = extracted[0] if isinstance(extracted[0], dict) else None
            # Cache ancien sans échéance → forcer le nouveau moteur
            if (not entry or not entry.get("expiry_date")) and doc.get("extracted_expiry_engine") != "v2-robust":
                entry = None
        if entry is None:
            # Tentative d'extraction à la volée (une fois).
            storage_path = doc.get("storage_path")
            ctype = (doc.get("content_type") or "").lower()
            fname = (doc.get("original_filename") or "").lower()
            if storage_path and (ctype == "application/pdf" or fname.endswith(".pdf")):
                try:
                    data = _read_storage_bytes(storage_path)
                    detected = extract_3p_contracts_from_pdf(data) or []
                    entry = detected[0] if detected else {}
                    await db.documents.update_one(
                        {"id": doc_id},
                        {"$set": {
                            "extracted_echeances_3p": detected,
                            "extracted_echeance_3p": (entry or {}).get("expiry_date"),
                            "extracted_document_type": (entry or {}).get("document_type"),
                            "extracted_expiry_engine": "v2-robust",
                        }},
                    )
                except Exception:
                    logger.exception("Re-extraction 3P échouée pour doc %s", doc_id)
                    entry = {}

        best_by_source[doc_id] = _echeance_line_from_extraction(entry, doc_id, now_iso)

    reconciled_lines = manual_lines + list(best_by_source.values())
    detected_dates = [l.get("echeance_3p") for l in reconciled_lines if isinstance(l, dict) and l.get("echeance_3p")]
    new_first = min(detected_dates) if detected_dates else None

    await db.clients.update_one(
        {"id": client_id, "user_id": user_id},
        {"$set": {"echeances_3p": reconciled_lines, "echeance_3p": new_first, "updated_at": now_iso}},
    )

    await db.tasks.delete_many(
        {"user_id": user_id, "client_id": client_id, "type": "echeance_3p", "done": False}
    )
    for line in reconciled_lines:
        await _upsert_echeance_3p_line_reminder(user_id, client, line)


async def _store_uploaded_client_document(
    *,
    client: dict,
    client_id: str,
    user: User,
    filename: Optional[str],
    data: bytes,
    content_type: Optional[str],
    category: str = "Autre",
    checklist_item: Optional[str] = None,
    title: Optional[str] = None,
) -> dict:
    """Enregistre un fichier uploadé comme document client (1 fichier = 1 ligne)."""
    original_filename = (filename or "fichier").strip() or "fichier"
    ext = original_filename.split(".")[-1].lower() if "." in original_filename else "bin"
    path = f"{APP_NAME}/uploads/{user.user_id}/{uuid.uuid4()}.{ext}"
    ctype = content_type or MIME_TYPES.get(ext, "application/octet-stream")
    try:
        result = put_object(path, data, ctype)
        storage_path = result["path"]
        size = result.get("size", len(data))
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        local_name = f"{uuid.uuid4()}.{ext}"
        storage_path = _local_storage_fallback(ROOT_DIR / "generated" / user.user_id, local_name, data)
        size = len(data)

    doc_title = (title or "").strip() or None
    scope = await _dossier_scope(user.user_id, client)
    dossier_id = scope.get("dossier_id") or client.get("dossier_id") or client_id
    is_couple = _is_couple_scope(scope)
    shared_dossier = (
        is_couple
        or category in SHARED_DOSSIER_DOC_CATEGORIES
        or (checklist_item or "") in SHARED_DOSSIER_DOC_CATEGORIES
    )
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "client_id": client_id,
        "dossier_id": dossier_id if shared_dossier else client.get("dossier_id"),
        "shared_dossier": shared_dossier,
        "storage_path": storage_path,
        "original_filename": original_filename,
        "title": doc_title,
        "content_type": ctype,
        "size": size,
        "category": category,
        "checklist_item": checklist_item or category,
        "author": getattr(user, "name", None) or None,
        "uploaded_by": getattr(user, "user_id", None) or None,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.insert_one(doc)

    detected_echeances: List[dict] = []
    detected_first_echeance: Optional[str] = None
    is_3p_police = (checklist_item or "") in {"Police 3e pilier", "Police de 3e pilier"} or category in {
        "Police 3e pilier",
        "Police de 3e pilier",
    }
    if is_3p_police and (ext == "pdf" or ctype == "application/pdf"):
        try:
            detected_echeances = extract_3p_contracts_from_pdf(data) or []
        except Exception:
            logger.exception("Extraction contrats 3P échouée")
            detected_echeances = []

        now_iso = datetime.now(timezone.utc).isoformat()
        entry = detected_echeances[0] if detected_echeances else {}
        new_line = _echeance_line_from_extraction(entry, doc["id"], now_iso)
        new_lines = [new_line]

        existing_lines = client.get("echeances_3p") or []
        merged_lines = _merge_echeances_3p_lines(existing_lines, new_lines)
        detected_dates = [l.get("echeance_3p") for l in merged_lines if l.get("echeance_3p")]
        if detected_dates:
            detected_first_echeance = min(detected_dates)

        await db.clients.update_one(
            {"id": client_id, "user_id": user.user_id},
            {
                "$set": {
                    "echeances_3p": merged_lines,
                    "echeance_3p": detected_first_echeance,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
        # Keep in-memory client in sync for subsequent files in the same batch
        client["echeances_3p"] = merged_lines
        client["echeance_3p"] = detected_first_echeance

        await _upsert_echeance_3p_line_reminder(user.user_id, client, new_line)
        await db.documents.update_one(
            {"id": doc["id"]},
            {
                "$set": {
                    "extracted_echeances_3p": detected_echeances[:1] if detected_echeances else [entry],
                    "extracted_echeance_3p": new_line.get("echeance_3p"),
                    "extracted_document_type": new_line.get("document_type"),
                    "extracted_expiry_engine": "v2-robust",
                }
            },
        )
        doc["extracted_echeance_3p"] = new_line.get("echeance_3p")
        doc["document_type"] = new_line.get("document_type")
        await _reconcile_echeances_3p_lines(user.user_id, client_id)

    # Offres client : extraction automatique compagnie / rente / montant / durée
    is_offre = category == "Offre" or (checklist_item or "") == "Offre"
    if is_offre and (ext == "pdf" or ctype == "application/pdf"):
        try:
            extracted = extract_offre_fields(data, filename=original_filename)
            fields = offre_fields_for_storage(extracted)
            await db.documents.update_one({"id": doc["id"]}, {"$set": fields})
            doc.update(fields)
        except Exception:
            logger.exception("Extraction métadonnées offre échouée")

    await log_action(user.user_id, client_id, f"Document ajouté: {original_filename} ({category})")

    # Analyse de prévoyance → le client apparaît dans Dossiers (Kanban)
    is_analyse_prevoyance = (
        (category or "").strip() == "Analyse de prévoyance"
        or (checklist_item or "").strip() == "Analyse de prévoyance"
    )
    if is_analyse_prevoyance and client.get("in_dossiers") is False:
        try:
            await db.clients.update_one(
                {"id": client_id, "user_id": user.user_id},
                {"$set": {"in_dossiers": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            logger.exception("Promotion in_dossiers échouée client=%s", client_id)

    doc.pop("_id", None)
    doc["echeance_3p"] = detected_first_echeance
    doc["echeance_3p_detected"] = bool(detected_first_echeance)
    return public_storage_record(doc)


@api_router.post("/clients/{client_id}/documents")
async def upload_document(
    client_id: str,
    file: UploadFile = File(...),
    category: str = Form("Autre"),
    checklist_item: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    c = await require_client(client_id, user)
    data = await file.read()
    return await _store_uploaded_client_document(
        client=c,
        client_id=client_id,
        user=user,
        filename=file.filename,
        data=data,
        content_type=file.content_type,
        category=category,
        checklist_item=checklist_item,
        title=title,
    )


@api_router.post("/clients/{client_id}/documents/batch")
async def upload_documents_batch(
    client_id: str,
    files: List[UploadFile] = File(...),
    category: str = Form("Autre"),
    checklist_item: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    """Import groupé : chaque fichier est enregistré séparément avec son nom d'origine."""
    c = await require_client(client_id, user)
    if not files:
        raise HTTPException(status_code=400, detail="Aucun fichier fourni")

    documents: List[dict] = []
    errors: List[dict] = []
    for f in files:
        try:
            data = await f.read()
            if not data:
                errors.append({"filename": f.filename or "fichier", "error": "Fichier vide"})
                continue
            doc = await _store_uploaded_client_document(
                client=c,
                client_id=client_id,
                user=user,
                filename=f.filename,
                data=data,
                content_type=f.content_type,
                category=category,
                checklist_item=checklist_item,
                title=title,
            )
            documents.append(doc)
        except Exception as e:
            logger.exception("Batch upload failed for %s", f.filename)
            errors.append({"filename": f.filename or "fichier", "error": str(e)})

    return {
        "ok": len(errors) == 0,
        "uploaded_count": len(documents),
        "error_count": len(errors),
        "documents": documents,
        "errors": errors,
    }


def _offre_needs_extract(doc: dict) -> bool:
    """True si aucune extraction d'offre n'a encore été enregistrée."""
    if doc.get("offre_extract") is not None:
        return False
    if any(
        doc.get(k) is not None
        for k in ("compagnie", "rente_mensuelle_garantie", "montant_investi", "duree")
    ):
        return False
    return True


def _empty_offre_extract_fields() -> dict:
    return offre_fields_for_storage(
        {
            "compagnie": None,
            "rente_mensuelle_garantie": None,
            "montant_investi": None,
            "duree": None,
            "compagnie_label": NON_INDIQUE,
            "rente_mensuelle_garantie_label": NON_INDIQUE,
            "montant_investi_label": NON_INDIQUE,
            "duree_label": NON_INDIQUE,
        }
    )


@api_router.post("/clients/{client_id}/offres/extract-missing")
async def extract_missing_offres(client_id: str, user: User = Depends(get_current_user)):
    """
    Analyse rétroactive des PDF Offre déjà présents sans métadonnées extraites.
    Ne réanalyse pas les offres déjà traitées. N'échoue pas globalement si un PDF plante.
    """
    client = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, client)
    doc_query = _documents_list_query(user.user_id, client_id, scope)
    doc_or = doc_query.pop("$or")

    rows = await db.documents.find(
        {
            **doc_query,
            "$and": [
                {"$or": doc_or},
                {
                    "$or": [
                        {"category": "Offre"},
                        {"checklist_item": "Offre"},
                    ]
                },
            ],
        },
        {"_id": 0},
    ).to_list(500)

    updated: List[dict] = []
    skipped = 0
    failed = 0

    for row in rows:
        if not _offre_needs_extract(row):
            skipped += 1
            continue
        doc_id = row.get("id")
        filename = row.get("original_filename") or "offre.pdf"
        ctype = (row.get("content_type") or "").lower()
        is_pdf = filename.lower().endswith(".pdf") or "pdf" in ctype
        fields = _empty_offre_extract_fields()
        if is_pdf and row.get("storage_path"):
            try:
                data = await _try_read_storage_bytes(row["storage_path"])
                if data:
                    extracted = await asyncio.to_thread(
                        lambda: extract_offre_fields(data, filename=filename)
                    )
                    fields = offre_fields_for_storage(extracted)
            except Exception:
                logger.exception("Backfill offre échoué pour %s", doc_id)
                failed += 1
                fields = _empty_offre_extract_fields()
        else:
            # Pas un PDF : marquer comme analysé pour éviter les boucles
            fields = _empty_offre_extract_fields()

        await db.documents.update_one(
            {"id": doc_id, "user_id": user.user_id},
            {"$set": fields},
        )
        merged = {**row, **fields}
        merged.pop("storage_path", None)
        merged.pop("storage_path_legacy", None)
        updated.append(public_storage_record(merged))

    return {
        "ok": True,
        "updated_count": len(updated),
        "skipped_count": skipped,
        "failed_count": failed,
        "updated": updated,
    }


@api_router.get("/document-templates")
async def document_templates(user: User = Depends(get_current_user)):
    return list_templates()

@api_router.get("/demand-packs")
async def demand_packs(user: User = Depends(get_current_user)):
    return list_demand_packs()

# ---------------- Bibliothèque de formulaires ----------------
async def _prepare_and_store_library_pdf(user_id: str, form_id: str, raw_pdf: bytes, existing_path: Optional[str] = None) -> dict:
    raw_pdf = await _resolve_maybe_awaitable(raw_pdf)
    raw_pdf = _coerce_file_bytes(raw_pdf, label="pdf bibliothèque")
    prepared = await asyncio.to_thread(prepare_library_form_pdf, raw_pdf)
    pdf_out = _coerce_file_bytes(prepared["pdf_bytes"], label="pdf préparé")
    prepared["pdf_bytes"] = pdf_out
    path = existing_path or f"{APP_NAME}/form-library/{user_id}/{form_id}.pdf"
    try:
        if path.startswith("local://"):
            storage_path = await asyncio.to_thread(_write_storage_bytes, path, pdf_out)
            size = len(pdf_out)
        else:
            result = await asyncio.to_thread(put_object, path, pdf_out, "application/pdf")
            storage_path = result["path"]
            size = result.get("size", len(pdf_out))
    except Exception:
        local_name = f"{form_id}.pdf"
        storage_path = _local_storage_fallback(ROOT_DIR / "form_library" / user_id, local_name, pdf_out)
        size = len(pdf_out)
    return {
        "storage_path": storage_path,
        "size": size,
        "widgets": prepared["widgets"],
        "page_count": prepared["page_count"],
        "field_names": prepared["field_names"],
        "field_mapping": prepared["field_mapping"],
        "field_count": len(prepared["widgets"]),
        "widgets_prepared": True,
        "checkboxes_scrubbed": True,
    }


async def _ensure_library_widgets(record: dict) -> dict:
    """Prépare les widgets uniques si besoin, et nettoie les ronds dans les cases."""
    if record.get("widgets_prepared") and record.get("widgets"):
        # Nettoyer les PDF déjà préparés (artefacts cercles sur cases)
        if not record.get("checkboxes_scrubbed"):
            try:
                raw = await _load_storage_bytes(record["storage_path"])
                cleaned = await asyncio.to_thread(repair_library_pdf_bytes, raw)
                cleaned = _coerce_file_bytes(cleaned, label="pdf nettoyé")
                storage_path = await asyncio.to_thread(
                    _write_storage_bytes, record["storage_path"], cleaned
                )
                updates = {
                    "storage_path": storage_path,
                    "size": len(cleaned),
                    "checkboxes_scrubbed": True,
                }
                await db.form_library.update_one({"id": record["id"]}, {"$set": updates})
                record.update(updates)
            except Exception:
                logger.exception("Nettoyage cases à cocher échoué pour %s", record.get("id"))
        return record
    try:
        raw = await _load_storage_bytes(record["storage_path"])
        meta = await _prepare_and_store_library_pdf(
            record["user_id"],
            record["id"],
            raw,
            existing_path=record.get("storage_path"),
        )
    except Exception as e:
        logger.exception("Préparation widgets formulaire échouée")
        raise HTTPException(status_code=500, detail=f"Analyse du PDF impossible: {e}")

    # Préserver un mapping existant si les clés matchent encore des ids
    old_mapping = record.get("field_mapping") or {}
    new_mapping = meta["field_mapping"]
    if old_mapping:
        widget_ids = {w["id"] for w in meta["widgets"]}
        # Mapping déjà basé sur ids uniques
        if any(k in widget_ids for k in old_mapping.keys()):
            for wid in widget_ids:
                if wid in old_mapping:
                    new_mapping[wid] = old_mapping.get(wid) or new_mapping.get(wid, "")
        else:
            # Ancien mapping par nom d'origine : appliquer 1re occurrence de chaque nom
            used_names = set()
            for w in meta["widgets"]:
                oname = w.get("original_name")
                if oname in old_mapping and oname not in used_names:
                    new_mapping[w["id"]] = old_mapping.get(oname) or new_mapping.get(w["id"], "")
                    used_names.add(oname)
            # Mapping indexé par anciens ids : reporter via original_name
            by_original = {}
            for w in meta["widgets"]:
                by_original.setdefault(w.get("original_name"), []).append(w["id"])
            for key, src in old_mapping.items():
                if not src or key in widget_ids:
                    continue
                for old_w in (record.get("widgets") or []):
                    if old_w.get("id") == key and old_w.get("original_name") in by_original:
                        for new_id in by_original[old_w["original_name"]]:
                            if not new_mapping.get(new_id):
                                new_mapping[new_id] = src
                                break

    updates = {
        "storage_path": meta["storage_path"],
        "size": meta["size"],
        "widgets": meta["widgets"],
        "page_count": meta["page_count"],
        "field_names": meta["field_names"],
        "field_mapping": new_mapping,
        "field_count": meta["field_count"],
        "widgets_prepared": True,
        "checkboxes_scrubbed": True,
    }
    await db.form_library.update_one({"id": record["id"]}, {"$set": updates})
    record.update(updates)
    return record


async def _appointment_date_for_client(user_id: str, client_id: str) -> str:
    # Compatible Motor (sort=) et PostgresMongoCompat (find().sort().to_list).
    try:
        appt = await db.appointments.find_one(
            {"user_id": user_id, "client_id": client_id},
            {"_id": 0},
            sort=[("date", 1)],
        )
    except TypeError:
        cursor = db.appointments.find(
            {"user_id": user_id, "client_id": client_id},
            {"_id": 0},
        )
        if hasattr(cursor, "sort"):
            cursor = cursor.sort("date", 1)
        rows = await cursor.to_list(1)
        appt = rows[0] if rows else None
    if not appt or not appt.get("date"):
        return ""
    try:
        raw = appt["date"]
        if "T" in str(raw):
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return dt.strftime("%d.%m.%Y")
        return _format_date_safe(raw)
    except Exception:
        return str(appt.get("date") or "")


def _format_date_safe(value) -> str:
    try:
        from pdf_generator import _format_date
        return _format_date(value)
    except Exception:
        return str(value or "")


@api_router.get("/form-library")
async def list_form_library(user: User = Depends(get_current_user)):
    items = await db.form_library.find(
        {"user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0, "storage_path": 0, "storage_path_legacy": 0},
    ).sort("created_at", -1).to_list(500)
    return items


@api_router.get("/form-library/field-sources")
async def list_form_field_sources(user: User = Depends(get_current_user)):
    return CRM_FIELD_SOURCES


@api_router.post("/form-library")
async def upload_form_library(
    user: User = Depends(get_current_user),
    file: UploadFile = File(...),
    name: str = Form(...),
):
    require_settings(user)
    label = (name or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Nom du formulaire requis")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if not (file.filename or "").lower().endswith(".pdf") and (file.content_type or "") != "application/pdf":
        if not data[:4] == b"%PDF":
            raise HTTPException(status_code=400, detail="Seuls les PDF sont acceptés")

    form_id = str(uuid.uuid4())
    try:
        meta = await _prepare_and_store_library_pdf(user.user_id, form_id, data)
    except Exception as e:
        logger.exception("Upload formulaire bibliothèque échoué")
        raise HTTPException(status_code=500, detail=f"Analyse du PDF impossible: {e}")

    doc = {
        "id": form_id,
        "user_id": user.user_id,
        "name": label,
        "original_filename": file.filename or f"{label}.pdf",
        "storage_path": meta["storage_path"],
        "content_type": "application/pdf",
        "size": meta["size"],
        "widgets": meta["widgets"],
        "page_count": meta["page_count"],
        "field_names": meta["field_names"],
        "field_count": meta["field_count"],
        "field_mapping": meta["field_mapping"],
        "widgets_prepared": True,
        "mapping_configured": False,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.form_library.insert_one(doc)
    doc.pop("_id", None)
    return public_storage_record(doc)


@api_router.get("/form-library/{form_id}")
async def get_form_library(form_id: str, user: User = Depends(get_current_user)):
    record = await db.form_library.find_one(
        {"id": form_id, "user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="Formulaire introuvable")
    record = await _ensure_library_widgets(record)
    return public_storage_record(record)


@api_router.patch("/form-library/{form_id}")
async def update_form_library(
    form_id: str,
    payload: UpdateFormLibraryRequest,
    user: User = Depends(get_current_user),
):
    require_settings(user)
    record = await db.form_library.find_one(
        {"id": form_id, "user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="Formulaire introuvable")
    record = await _ensure_library_widgets(record)

    updates: dict = {}
    if payload.name is not None:
        label = payload.name.strip()
        if not label:
            raise HTTPException(status_code=400, detail="Nom du formulaire requis")
        updates["name"] = label
    if payload.field_mapping is not None:
        known = {w["id"] for w in (record.get("widgets") or [])}
        if not known:
            known = set(record.get("field_names") or [])
        cleaned = {}
        for pdf_field, source_key in payload.field_mapping.items():
            key = str(pdf_field)
            if known and key not in known:
                continue
            cleaned[key] = str(source_key or "")
        for wid in known:
            cleaned.setdefault(wid, "")
        updates["field_mapping"] = cleaned
        updates["mapping_configured"] = True
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    if not updates:
        return public_storage_record(record)

    await db.form_library.update_one(
        {"id": form_id, "user_id": user.user_id},
        {"$set": updates},
    )
    record.update(updates)
    return public_storage_record(record)


@api_router.delete("/form-library/{form_id}")
async def delete_form_library(form_id: str, user: User = Depends(get_current_user)):
    require_settings(user)
    res = await db.form_library.update_one(
        {"id": form_id, "user_id": user.user_id},
        {"$set": {"is_deleted": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Formulaire introuvable")
    return {"ok": True}


@api_router.get("/form-library/{form_id}/download")
async def download_form_library(form_id: str, user: User = Depends(get_current_user)):
    record = await db.form_library.find_one(
        {"id": form_id, "user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="Formulaire introuvable")
    try:
        data = await _load_storage_bytes(record["storage_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    fname = _resolve_download_filename(
        record, fallback=f"{record.get('name', 'formulaire')}.pdf"
    )
    return Response(
        content=data,
        media_type="application/pdf",
        headers=_file_response_headers(fname, inline=True),
    )


@api_router.get("/form-library/{form_id}/pages/{page_index}")
async def form_library_page_preview(
    form_id: str,
    page_index: int,
    user: User = Depends(get_current_user),
):
    record = await db.form_library.find_one(
        {"id": form_id, "user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="Formulaire introuvable")
    record = await _ensure_library_widgets(record)
    try:
        raw = await _load_storage_bytes(record["storage_path"])
        png = await asyncio.to_thread(render_pdf_page_png, raw, page_index, 144.0)
        png = _coerce_file_bytes(png, label="aperçu png")
    except IndexError:
        raise HTTPException(status_code=404, detail="Page introuvable")
    except Exception as e:
        logger.exception("Rendu page formulaire échoué")
        raise HTTPException(status_code=500, detail=f"Aperçu impossible: {e}")
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@api_router.post("/form-library/{form_id}/test-fill")
async def test_fill_library_form(
    form_id: str,
    payload: TestLibraryFormRequest,
    user: User = Depends(get_current_user),
):
    record = await db.form_library.find_one(
        {"id": form_id, "user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="Formulaire introuvable")
    record = await _ensure_library_widgets(record)
    c = await require_client(payload.client_id, user)
    spouse = None
    if c.get("linked_spouse_id"):
        spouse = await db.clients.find_one(
            {"id": c["linked_spouse_id"], "user_id": user.user_id},
            {"_id": 0},
        )
        spouse = _decrypt_client_doc(spouse)
    mapping = payload.field_mapping if isinstance(payload.field_mapping, dict) else record.get("field_mapping")
    try:
        raw = await _load_storage_bytes(record["storage_path"])
        agent = c.get("conseiller") or user.name or ""
        date_rdv = await _appointment_date_for_client(user.user_id, c["id"])
        pdf_bytes = await asyncio.to_thread(
            fill_pdf_bytes_with_client,
            raw,
            c,
            agent,
            mapping if isinstance(mapping, dict) else None,
            spouse,
            {"date_rdv": date_rdv},
            record.get("widgets"),
        )
        pdf_bytes = await _resolve_maybe_awaitable(pdf_bytes)
        pdf_bytes = _coerce_file_bytes(pdf_bytes, label="pdf test-fill")
    except Exception as e:
        logger.exception("Test fill formulaire échoué")
        raise HTTPException(status_code=500, detail=f"Test impossible: {e}")
    fname = f"TEST_{record.get('name', 'formulaire')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_file_response_headers(fname, inline=True),
    )


@api_router.post("/clients/{client_id}/generate-library-form")
async def generate_library_form_for_client(
    client_id: str,
    payload: GenerateLibraryFormRequest,
    user: User = Depends(get_current_user),
):
    c = await require_client(client_id, user)
    form = await db.form_library.find_one(
        {"id": payload.library_form_id, "user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not form:
        raise HTTPException(status_code=404, detail="Formulaire introuvable dans la bibliothèque")
    form = await _ensure_library_widgets(form)

    spouse = None
    if c.get("linked_spouse_id"):
        spouse = await db.clients.find_one(
            {"id": c["linked_spouse_id"], "user_id": user.user_id},
            {"_id": 0},
        )
        spouse = _decrypt_client_doc(spouse)

    try:
        raw = await _load_storage_bytes(form["storage_path"])
        agent = c.get("conseiller") or user.name or ""
        mapping = form.get("field_mapping")
        use_mapping = mapping if isinstance(mapping, dict) else None
        date_rdv = await _appointment_date_for_client(user.user_id, client_id)
        # Remplissage sync (PyMuPDF/pypdf) hors event loop — bytes déjà validés.
        pdf_bytes = await asyncio.to_thread(
            fill_pdf_bytes_with_client,
            raw,
            c,
            agent,
            use_mapping,
            spouse,
            {"date_rdv": date_rdv},
            form.get("widgets"),
        )
        pdf_bytes = await _resolve_maybe_awaitable(pdf_bytes)
        pdf_bytes = _coerce_file_bytes(pdf_bytes, label="pdf formulaire bibliothèque")
    except Exception as e:
        logger.exception("Génération formulaire bibliothèque échouée")
        raise HTTPException(status_code=500, detail=f"Génération impossible: {e}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{c.get('nom','')}_{c.get('prenom','')}").strip("_") or "client"
    if payload.custom_filename:
        output_name = payload.custom_filename if payload.custom_filename.lower().endswith(".pdf") else f"{payload.custom_filename}.pdf"
        output_name = re.sub(r'[\\/:*?"<>|]+', "_", output_name)
    else:
        form_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", form.get("name") or "Formulaire").strip("_")
        output_name = f"{form_slug}_{slug}_{stamp}.pdf"

    meta = {
        "original_filename": output_name,
        "category": "Autre formulaire",
        "template_id": f"library:{form['id']}",
        "template_label": form.get("name"),
        "checklist_item": "Autre formulaire",
        "library_form_id": form["id"],
    }
    doc = await _store_pdf_bytes(user.user_id, pdf_bytes, meta, client_id, checklist_item="Autre formulaire")
    await log_action(user.user_id, client_id, f"Autre formulaire généré: {form.get('name')}")
    return doc

@api_router.post("/clients/{client_id}/generate-document")
async def generate_client_document(client_id: str, payload: GenerateDocumentRequest, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    try:
        get_template(payload.template_id)
    except KeyError:
        raise HTTPException(status_code=400, detail="Modèle de document inconnu")
    try:
        agent = c.get("conseiller") or user.name or ""
        spouse = None
        spouse_id = c.get("linked_spouse_id")
        if not spouse_id:
            reverse = await db.clients.find_one(
                {"user_id": user.user_id, "linked_spouse_id": client_id},
                {"_id": 0, "id": 1},
            )
            spouse_id = (reverse or {}).get("id")
        if not spouse_id:
            name_ids = await _resolve_spouse_ids_by_name(user.user_id, c)
            spouse_id = name_ids[0] if name_ids else None
        if spouse_id:
            spouse_doc = await db.clients.find_one(
                {"id": spouse_id, "user_id": user.user_id},
                {"_id": 0},
            )
            spouse = _decrypt_client_doc(spouse_doc) if spouse_doc else None
        client_for_pdf = dict(c)
        if payload.template_id == "mandat_de_gestion":
            cons_name = (client_for_pdf.get("conseiller") or agent or "").strip()
            finma = await lookup_conseiller_finma(cons_name)
            if not finma:
                u_cons = (user.conseiller or user.name or "").strip()
                if cons_name and _conseiller_name_key(cons_name) == _conseiller_name_key(u_cons):
                    u_doc = await db.users.find_one(
                        {"user_id": user.account_id},
                        {"_id": 0, "finma_number": 1},
                    )
                    finma = str((u_doc or {}).get("finma_number") or "").strip()
            client_for_pdf["conseiller_finma"] = finma
            client_for_pdf["conseiller"] = cons_name or client_for_pdf.get("conseiller")
        pdf_bytes, meta = await asyncio.to_thread(
            generate_document_pdf,
            payload.template_id,
            client_for_pdf,
            agent,
            payload.custom_filename,
            None,
            spouse,
        )
        pdf_bytes = await _resolve_maybe_awaitable(pdf_bytes)
        pdf_bytes = _coerce_file_bytes(pdf_bytes, label="pdf document")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Génération PDF échouée")
        raise HTTPException(status_code=500, detail=f"Génération impossible: {e}")

    if payload.template_id == "mandat_de_gestion":
        await db.documents.update_many(
            {
                "user_id": user.user_id,
                "client_id": client_id,
                "is_deleted": False,
                "$or": [
                    {"template_id": "mandat_de_gestion"},
                    {"checklist_item": "Mandat de gestion"},
                    {"category": "Mandat de gestion"},
                ],
            },
            {"$set": {"is_deleted": True}},
        )

    doc = await _store_pdf_bytes(
        user.user_id,
        pdf_bytes,
        meta,
        client_id,
        checklist_item=payload.checklist_item or meta.get("checklist_item"),
    )
    await log_action(user.user_id, client_id, f"Document généré: {meta['template_label']}")
    return doc

@api_router.post("/clients/{client_id}/generate-demand")
async def generate_client_demand(client_id: str, payload: GenerateDemandRequest, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    if payload.pack_id not in DEMAND_PACKS:
        raise HTTPException(status_code=400, detail="Type de demande inconnu")
    try:
        agent = c.get("conseiller") or user.name or ""
        generated = generate_demand_pack(payload.pack_id, c, agent_name=agent)
    except Exception as e:
        logger.exception("Génération demande échouée")
        raise HTTPException(status_code=500, detail=f"Génération impossible: {e}")

    docs = []
    for pdf_bytes, meta in generated:
        doc = await _store_pdf_bytes(user.user_id, pdf_bytes, meta, client_id, checklist_item=meta.get("checklist_item"))
        docs.append(doc)
    pack_label = DEMAND_PACKS[payload.pack_id]["label"]
    await log_action(user.user_id, client_id, f"Demande générée: {pack_label} ({len(docs)} documents)")
    return {"pack_id": payload.pack_id, "label": pack_label, "documents": docs}

@api_router.post("/clients/{client_id}/parse-lpp-response")
async def parse_lpp_response(client_id: str, file: UploadFile = File(...), user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    data = await file.read()
    path = f"{APP_NAME}/uploads/{user.user_id}/{uuid.uuid4()}.pdf"
    try:
        result = put_object(path, data, "application/pdf")
        storage_path = result["path"]
        size = result.get("size", len(data))
    except Exception:
        local_name = f"{uuid.uuid4()}.pdf"
        storage_path = _local_storage_fallback(ROOT_DIR / "generated" / user.user_id, local_name, data)
        size = len(data)
    doc = {
        "id": str(uuid.uuid4()), "user_id": user.user_id, "client_id": client_id,
        "dossier_id": c.get("dossier_id"),
        "storage_path": storage_path, "original_filename": file.filename or "reponse_lpp.pdf",
        "content_type": "application/pdf", "size": size,
        "category": "Réponse recherche LPP",
        "checklist_item": "Formulaire Recherche LPP",
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.insert_one(doc)
    doc.pop("_id", None)

    try:
        funds, ocr_text = extract_pension_funds_from_pdf_with_text(data)
    except Exception as e:
        logger.exception("OCR / parse LPP échoué")
        funds, ocr_text = [], ""
        await log_action(user.user_id, client_id, f"Réponse LPP enregistrée mais analyse échouée: {e}")
        return {"document": public_storage_record(doc), "funds": [], "fund_count": 0, "error": str(e)}

    person = resolve_lpp_person(
        filename=file.filename,
        text=ocr_text,
        client=c,
    )
    funds = tag_lpp_funds_with_person(funds, person, source_doc_id=doc["id"])

    await db.documents.update_one(
        {"id": doc["id"]},
        {"$set": {
            "detected_funds": funds,
            "fund_count": len(funds),
            "lpp_person": person,
        }},
    )
    doc["detected_funds"] = funds
    doc["fund_count"] = len(funds)
    doc["lpp_person"] = person

    merged, tracking = await _persist_merged_lpp_funds(
        client_id=client_id,
        user_id=user.user_id,
        client=c,
        new_funds=funds,
        response_doc_id=doc["id"],
    )
    logger.info(
        "parse-lpp-response client=%s person=%s new=%s total=%s",
        client_id, person or "?", len(funds), len(merged),
    )
    await log_action(
        user.user_id,
        client_id,
        f"Réponse LPP analysée ({person or 'personne ?'}): {len(funds)} caisse(s), total dossier {len(merged)}",
    )
    return {
        "document": public_storage_record(doc),
        "funds": merged,
        "fund_count": len(merged),
        "lpp_person": person,
        "lpp_caisse_tracking": tracking,
    }

@api_router.post("/clients/{client_id}/reparse-lpp-response/{doc_id}")
async def reparse_lpp_response(client_id: str, doc_id: str, user: User = Depends(get_current_user)):
    """Relance l'OCR sur une réponse LPP déjà téléversée (sans écraser l'autre personne)."""
    c = await require_client(client_id, user)
    doc = await db.documents.find_one(
        {"id": doc_id, "client_id": client_id, "user_id": user.user_id, "is_deleted": False},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    storage_path = doc.get("storage_path") or ""
    try:
        data = await _load_storage_bytes(storage_path)
    except Exception as e:
        logger.exception("Lecture PDF pour reparse échouée")
        raise HTTPException(status_code=500, detail=f"Impossible de relire le PDF: {e}")

    funds, ocr_text = extract_pension_funds_from_pdf_with_text(data)
    person = resolve_lpp_person(
        filename=doc.get("original_filename"),
        text=ocr_text,
        client=c,
        explicit=doc.get("lpp_person"),
    )
    funds = tag_lpp_funds_with_person(funds, person, source_doc_id=doc_id)
    await db.documents.update_one(
        {"id": doc_id},
        {"$set": {"detected_funds": funds, "fund_count": len(funds), "lpp_person": person}},
    )
    merged, tracking = await _persist_merged_lpp_funds(
        client_id=client_id,
        user_id=user.user_id,
        client=c,
        new_funds=funds,
        replace_source_doc_id=doc_id,
        response_doc_id=doc_id,
    )
    doc["detected_funds"] = funds
    doc["fund_count"] = len(funds)
    doc["lpp_person"] = person
    await log_action(
        user.user_id,
        client_id,
        f"Réanalyse LPP ({person or 'personne ?'}): {len(funds)} caisse(s), total {len(merged)}",
    )
    return {
        "document": public_storage_record(doc),
        "funds": merged,
        "fund_count": len(merged),
        "lpp_person": person,
        "lpp_caisse_tracking": tracking,
    }


@api_router.post("/clients/{client_id}/reparse-all-lpp-responses")
async def reparse_all_lpp_responses(client_id: str, user: User = Depends(get_current_user)):
    """Réanalyse toutes les réponses LPP du dossier et fusionne Monsieur + Madame."""
    c = await require_client(client_id, user)
    scope = await _dossier_scope(user.user_id, c)
    query = _documents_list_query(user.user_id, client_id, scope)
    query["category"] = "Réponse recherche LPP"
    query["is_deleted"] = False
    docs = await db.documents.find(query, {"_id": 0}).sort("created_at", 1).to_list(100)
    if not docs:
        raise HTTPException(status_code=404, detail="Aucune réponse LPP à réanalyser")

    all_funds: List[dict] = []
    last_doc = None
    for doc in docs:
        try:
            data = await _load_storage_bytes(doc.get("storage_path") or "")
        except Exception:
            logger.exception("Skip reparse doc=%s", doc.get("id"))
            continue
        funds, ocr_text = extract_pension_funds_from_pdf_with_text(data)
        person = resolve_lpp_person(
            filename=doc.get("original_filename"),
            text=ocr_text,
            client=c,
            explicit=doc.get("lpp_person"),
        )
        funds = tag_lpp_funds_with_person(funds, person, source_doc_id=doc["id"])
        await db.documents.update_one(
            {"id": doc["id"]},
            {"$set": {"detected_funds": funds, "fund_count": len(funds), "lpp_person": person}},
        )
        all_funds = merge_lpp_detected_funds(all_funds, funds)
        last_doc = doc

    tracking = _lpp_tracking_from_funds(all_funds, c.get("lpp_caisse_tracking"))
    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {
            "lpp_detected_funds": all_funds,
            "lpp_caisse_tracking": tracking,
            "lpp_response_doc_id": (last_doc or {}).get("id"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await log_action(
        user.user_id,
        client_id,
        f"Réanalyse LPP complète: {len(docs)} fichier(s), {len(all_funds)} caisse(s)",
    )
    return {
        "funds": all_funds,
        "fund_count": len(all_funds),
        "documents_parsed": len(docs),
        "lpp_caisse_tracking": tracking,
    }

@api_router.post("/clients/{client_id}/generate-decompte-letters")
async def generate_decompte_for_funds(client_id: str, payload: GenerateDecompteRequest, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    if not payload.funds:
        raise HTTPException(status_code=400, detail="Sélectionnez au moins une caisse")
    # Enrichir avec tracking_id / person depuis le suivi client
    tracking = c.get("lpp_caisse_tracking") or []
    by_key = {
        _lpp_track_key(e): e for e in tracking if isinstance(e, dict) and e.get("name")
    }
    enriched = []
    for fund in payload.funds:
        if not isinstance(fund, dict):
            continue
        f = dict(fund)
        key = _lpp_track_key(f)
        prior = by_key.get(key) or {}
        # La personne de la caisse (PDF) prime ; le tracking ne comble que si absent.
        if not f.get("person") and prior.get("person"):
            f["person"] = prior["person"]
        f["tracking_id"] = prior.get("id") or f.get("tracking_id") or f.get("id")
        enriched.append(f)

    spouse = None
    spouse_id = c.get("linked_spouse_id")
    if not spouse_id:
        reverse = await db.clients.find_one(
            {"user_id": user.user_id, "linked_spouse_id": client_id},
            {"_id": 0},
        )
        spouse_id = (reverse or {}).get("id")
    if spouse_id:
        spouse = await db.clients.find_one(
            {"id": spouse_id, "user_id": user.user_id},
            {"_id": 0},
        )
        spouse = _decrypt_client_doc(spouse) if spouse else None

    try:
        agent = c.get("conseiller") or user.name or ""
        generated = generate_decompte_letters(
            c,
            enriched or payload.funds,
            agent_name=agent,
            spouse=spouse,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Génération décomptes échouée")
        raise HTTPException(status_code=500, detail=f"Génération impossible: {e}")

    docs = []
    for pdf_bytes, meta in generated:
        doc = await _store_pdf_bytes(user.user_id, pdf_bytes, meta, client_id, checklist_item=meta.get("checklist_item"))
        docs.append(doc)
    await log_action(user.user_id, client_id, f"Demandes de décompte générées: {len(docs)}")
    return {"documents": docs, "count": len(docs)}

@api_router.post("/clients/{client_id}/create-spouse")
async def create_spouse(client_id: str, payload: CreateSpouseRequest, user: User = Depends(get_current_user)):
    from client_identity import identity_fields_for_storage, require_unique_identity

    c = await require_client(client_id, user)
    if c.get("linked_spouse_id"):
        existing = await db.clients.find_one({"id": c["linked_spouse_id"], "user_id": user.user_id}, {"_id": 0})
        if existing:
            return _decrypt_client_doc(existing)

    spouse_prenom = payload.prenom or (c.get("conjoint") or "").split(" ")[0]
    spouse_nom = payload.nom or " ".join((c.get("conjoint") or "").split(" ")[1:]) or c.get("nom", "")
    if not spouse_prenom or not spouse_nom:
        raise HTTPException(status_code=400, detail="Prénom et nom du conjoint requis")

    # Conjoint = autre personne : interdit si un profil existe déjà pour cette identité
    await require_unique_identity(
        db,
        prenom=spouse_prenom,
        nom=spouse_nom,
        date_naissance=payload.date_naissance,
        user_id=user.user_id,
        exclude_id=client_id,
    )

    dossier_id = c.get("dossier_id") or c["id"]
    dossier_label = c.get("dossier_label") or f"Famille {c.get('nom', '')}".strip()
    spouse = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "prenom": spouse_prenom,
        "nom": spouse_nom,
        "date_naissance": payload.date_naissance,
        "sexe": payload.sexe,
        "avs_number": payload.avs_number,
        "nationalite": c.get("nationalite"),
        "email": None,
        "telephone": None,
        "adresse": c.get("adresse"),
        "npa": c.get("npa"),
        "ville": c.get("ville"),
        "etat_civil": c.get("etat_civil"),
        "nombre_enfants": c.get("nombre_enfants") or 0,
        "conjoint": f"{c.get('prenom', '')} {c.get('nom', '')}".strip(),
        "employeur": None,
        "profession": None,
        "taux_activite": None,
        "salaire_annuel": None,
        "conseiller": c.get("conseiller"),
        "agent_apporteur": c.get("agent_apporteur"),
        "linked_spouse_id": client_id,
        "echeance_3p": None,
        "statut": "Nouveau",
        "priorite": "normale",
        "numero_dossier": c.get("numero_dossier"),
        "dossier_id": dossier_id,
        "dossier_label": dossier_label,
        "in_dossiers": c.get("in_dossiers", True) is not False,
        "activites": c.get("activites") or (["prevoyance"] if c.get("in_dossiers") is not False else []),
        "source_modules": c.get("source_modules") or [],
        "document_checklist": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    spouse.update(identity_fields_for_storage(spouse_prenom, spouse_nom, payload.date_naissance))
    to_store = _encrypt_client_for_storage(spouse)
    try:
        await db.clients.insert_one(to_store)
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "unique" in err or "e11000" in err:
            await require_unique_identity(
                db,
                prenom=spouse_prenom,
                nom=spouse_nom,
                date_naissance=payload.date_naissance,
                user_id=user.user_id,
                exclude_id=client_id,
            )
        raise
    await db.clients.update_one(
        {"id": client_id},
        {"$set": {
            "linked_spouse_id": spouse["id"],
            "conjoint": f"{spouse_prenom} {spouse_nom}".strip(),
            "dossier_id": dossier_id,
            "dossier_label": dossier_label,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await log_action(user.user_id, client_id, f"Fiche conjoint créée: {spouse_prenom} {spouse_nom}")
    try:
        await _migrate_couple_document_sharing(user.user_id)
    except Exception:
        logger.exception("Migration documents couple après création conjoint")
    return _decrypt_client_doc({k: v for k, v in to_store.items() if k != "_id"})

@api_router.patch("/clients/{client_id}/echeance-3p")
async def update_echeance_3p(client_id: str, payload: Echeance3PUpdate, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)
    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {"echeance_3p": payload.echeance_3p, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await _upsert_echeance_3p_reminder(user.user_id, c, payload.echeance_3p)
    await log_action(user.user_id, client_id, f"Échéance 3P mise à jour: {payload.echeance_3p or '—'}")
    return await require_client(client_id, user)

@api_router.post("/clients/{client_id}/echeances-3p")
async def create_echeance_3p_line(client_id: str, payload: Echeance3PLineCreate, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)

    now_iso = datetime.now(timezone.utc).isoformat()
    company = payload.company.strip() if isinstance(payload.company, str) and payload.company.strip() else None
    policy_number = payload.policy_number.strip() if isinstance(payload.policy_number, str) and payload.policy_number.strip() else None
    echeance = payload.echeance_3p or None
    document_type = _normalize_document_type_3p(payload.document_type)

    new_line = {
        "id": str(uuid.uuid4()),
        "company": company,
        "policy_number": policy_number,
        "echeance_3p": echeance,
        "detected": False,
        "raw_date": None,
        "document_type": document_type,
        "source_doc_id": None,
        "manual": True,
        "rachat_effectue": False,
        "rachat_doc_id": None,
        "rachat_doc_filename": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    lines = list(c.get("echeances_3p") or [])
    if not isinstance(lines, list):
        lines = []
    lines.append(new_line)

    detected_dates = [l.get("echeance_3p") for l in lines if isinstance(l, dict) and l.get("echeance_3p")]
    new_first = min(detected_dates) if detected_dates else None

    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {"echeances_3p": lines, "echeance_3p": new_first, "updated_at": now_iso}},
    )
    if echeance:
        await _upsert_echeance_3p_line_reminder(user.user_id, c, new_line)
    await log_action(user.user_id, client_id, "Contrat 3e pilier ajouté manuellement")
    return await require_client(client_id, user)


@api_router.patch("/clients/{client_id}/echeances-3p/{line_id}")
async def update_echeance_3p_line(client_id: str, line_id: str, payload: Echeance3PLineUpdate, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)

    lines = c.get("echeances_3p") or []
    if not isinstance(lines, list):
        lines = []

    target = None
    for i, line in enumerate(lines):
        if isinstance(line, dict) and line.get("id") == line_id:
            target = line
            break

    if not target:
        raise HTTPException(status_code=404, detail="Ligne d'échéance introuvable")

    now_iso = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump(exclude_unset=True)
    old_date = target.get("echeance_3p")
    old_company = target.get("company")
    old_policy_number = target.get("policy_number")

    if "company" in data:
        val = data.get("company")
        target["company"] = val.strip() if isinstance(val, str) and val.strip() else None
    if "policy_number" in data:
        val = data.get("policy_number")
        target["policy_number"] = val.strip() if isinstance(val, str) and val.strip() else None
    if "echeance_3p" in data:
        target["echeance_3p"] = data.get("echeance_3p") or None
        target["detected"] = bool(target.get("echeance_3p"))
    if "document_type" in data:
        target["document_type"] = _normalize_document_type_3p(data.get("document_type"))
    elif not target.get("document_type"):
        target["document_type"] = "Autre document"

    if "rachat_effectue" in data:
        target["rachat_effectue"] = bool(data.get("rachat_effectue"))
    if "rachat_doc_id" in data:
        doc_id = data.get("rachat_doc_id") or None
        target["rachat_doc_id"] = doc_id
        if not doc_id:
            target["rachat_doc_filename"] = None
    if "rachat_doc_filename" in data:
        fn = data.get("rachat_doc_filename")
        target["rachat_doc_filename"] = fn.strip() if isinstance(fn, str) and fn.strip() else None

    target["updated_at"] = now_iso
    new_date = target.get("echeance_3p")

    detected_dates = [l.get("echeance_3p") for l in lines if isinstance(l, dict) and l.get("echeance_3p")]
    new_first = min(detected_dates) if detected_dates else None

    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {"echeances_3p": lines, "echeance_3p": new_first, "updated_at": now_iso}},
    )

    identity_changed = bool(data.keys() & {"echeance_3p", "company", "policy_number", "document_type"})
    if identity_changed:
        if old_date:
            old_key = _echeance_3p_contract_key(old_company, old_policy_number, old_date)
            await db.tasks.delete_many({
                "user_id": user.user_id,
                "client_id": client_id,
                "type": "echeance_3p",
                "echeance_3p_key": old_key,
                "done": False,
            })
        if new_date:
            await _upsert_echeance_3p_line_reminder(user.user_id, c, target)

    await log_action(user.user_id, client_id, "Échéance 3P mise à jour (ligne)")
    return await require_client(client_id, user)


@api_router.delete("/clients/{client_id}/echeances-3p/{line_id}")
async def delete_echeance_3p_line(client_id: str, line_id: str, user: User = Depends(get_current_user)):
    c = await require_client(client_id, user)

    lines = c.get("echeances_3p") or []
    if not isinstance(lines, list):
        lines = []

    target = None
    remaining = []
    for line in lines:
        if isinstance(line, dict) and line.get("id") == line_id:
            target = line
        else:
            remaining.append(line)

    if not target:
        raise HTTPException(status_code=404, detail="Ligne d'échéance introuvable")

    now_iso = datetime.now(timezone.utc).isoformat()
    old_date = target.get("echeance_3p")
    if old_date:
        old_key = _echeance_3p_contract_key(target.get("company"), target.get("policy_number"), old_date)
        await db.tasks.delete_many({
            "user_id": user.user_id,
            "client_id": client_id,
            "type": "echeance_3p",
            "echeance_3p_key": old_key,
            "done": False,
        })

    # Si la ligne était liée à un document, on le soft-supprime pour éviter qu'elle soit recréée.
    source_doc_id = target.get("source_doc_id")
    if source_doc_id:
        await db.documents.update_one(
            {"id": source_doc_id, "user_id": user.user_id, "is_deleted": False},
            {"$set": {"is_deleted": True}},
        )

    detected_dates = [l.get("echeance_3p") for l in remaining if isinstance(l, dict) and l.get("echeance_3p")]
    new_first = min(detected_dates) if detected_dates else None
    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {"echeances_3p": remaining, "echeance_3p": new_first, "updated_at": now_iso}},
    )
    await log_action(user.user_id, client_id, "Contrat 3e pilier supprimé")
    return await require_client(client_id, user)


@api_router.get("/echeances-3p")
async def list_echeances_3p(conseiller: Optional[str] = None, user: User = Depends(get_current_user)):
    base = clients_base_query(user, conseiller=conseiller)
    query = {
        "$and": [
            base,
            {
                "$or": [
                    {"echeances_3p": {"$exists": True}},
                    {"echeance_3p": {"$ne": None, "$exists": True}},
                ]
            },
        ]
    }
    clients = await db.clients.find(
        query,
        {"_id": 0, "id": 1, "prenom": 1, "nom": 1, "numero_dossier": 1, "echeances_3p": 1, "echeance_3p": 1},
    ).to_list(1000)

    now = datetime.now()
    items: List[dict] = []

    for c in clients:
        lines = c.get("echeances_3p") or []
        if not isinstance(lines, list) or len(lines) == 0:
            # Compat anciens clients (champ unique).
            if c.get("echeance_3p"):
                lines = [{
                    "company": None,
                    "policy_number": None,
                    "echeance_3p": c.get("echeance_3p"),
                }]
            else:
                continue

        for line in lines:
            due_raw = line.get("echeance_3p")
            if not due_raw:
                continue
            try:
                due = datetime.fromisoformat(str(due_raw)[:10])
            except Exception:
                continue

            days_left = (due - now).days
            items.append({
                "id": c.get("id"),
                "client_id": c.get("id"),
                "prenom": c.get("prenom"),
                "nom": c.get("nom"),
                "numero_dossier": c.get("numero_dossier"),
                "company": line.get("company") or None,
                "policy_number": line.get("policy_number") or None,
                "echeance_3p": str(due)[:10],
                "days_left": days_left,
                "alert": 0 <= days_left <= 365,
            })

    items.sort(key=lambda x: x.get("days_left", 99999))
    return items


# ---------------- Suivi 3e Pilier (collection indépendante) ----------------

async def _require_suivi_3p_client(client_id: str, user: User) -> dict:
    c = await db[SUIVI_3P_CLIENTS].find_one({"id": client_id, "user_id": TENANT_USER_ID}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client Suivi 3P introuvable")
    if not can_access_suivi_client(user, c):
        raise HTTPException(status_code=403, detail="Accès non autorisé à ce client Suivi 3P")
    return c


@api_router.get("/suivi-3p/statuts")
async def list_suivi_3p_statuts(user: User = Depends(get_current_user)):
    return {"statuts": SUIVI_3P_STATUTS}


@api_router.get("/suivi-3p/stats")
async def suivi_3p_stats(
    conseiller: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    # KPIs filtrés éventuels
    q = suivi_3p_base_query(user, conseiller=conseiller)
    clients = await db[SUIVI_3P_CLIENTS].find(q, {"_id": 0}).to_list(5000)
    rows = [serialize_suivi_client(c) for c in clients]
    stats = compute_suivi_stats(rows)

    # Répartition conseillers : toujours sur le scope global de l'utilisateur (sans filtre agent)
    by_conseiller = []
    if is_global_viewer(user):
        from conseiller_identity import (
            display_conseiller_name,
            merge_conseiller_display,
            normalize_conseiller_key,
        )

        all_clients = await db[SUIVI_3P_CLIENTS].find(suivi_3p_base_query(user), {"_id": 0}).to_list(5000)
        buckets: dict = {}
        for c in all_clients:
            r = serialize_suivi_client(c)
            raw = (r.get("conseiller") or "").strip() or "Non attribué"
            key = normalize_conseiller_key(raw) or "non attribue"
            b = buckets.get(key)
            if not b:
                b = {"conseiller": display_conseiller_name(raw), "total": 0, "signes": 0, "gain_total": 0.0}
                buckets[key] = b
            else:
                b["conseiller"] = merge_conseiller_display(b["conseiller"], raw)
            b["total"] += 1
            if r["statut_suivi"] == "Signé":
                b["signes"] += 1
            g = r.get("gain_fiscal_estime")
            if g is not None and r["statut_suivi"] not in ("Refusé", "Sans suite"):
                try:
                    b["gain_total"] += float(g)
                except (TypeError, ValueError):
                    pass
        by_conseiller = sorted(buckets.values(), key=lambda x: (-x["total"], x["conseiller"].lower()))
    return {
        **stats,
        "by_conseiller": by_conseiller,
        "scope": {
            "role": user.role,
            "conseiller": user.conseiller,
            "filter_conseiller": conseiller,
            "is_global": is_global_viewer(user),
        },
    }


@api_router.get("/suivi-3p/conseillers")
async def list_suivi_3p_conseillers(user: User = Depends(get_current_user)):
    """Liste des agents présents dans le module Suivi 3P + effectifs."""
    from conseiller_identity import (
        display_conseiller_name,
        merge_conseiller_display,
        normalize_conseiller_key,
    )

    q = suivi_3p_base_query(user)
    clients = await db[SUIVI_3P_CLIENTS].find(q, {"_id": 0, "conseiller": 1}).to_list(5000)
    buckets: dict = {}
    for c in clients:
        raw = (c.get("conseiller") or "").strip() or "Non attribué"
        key = normalize_conseiller_key(raw) or "non attribue"
        b = buckets.get(key)
        if not b:
            buckets[key] = {"conseiller": display_conseiller_name(raw), "total": 1}
        else:
            b["conseiller"] = merge_conseiller_display(b["conseiller"], raw)
            b["total"] += 1
    rows = list(buckets.values())
    rows.sort(key=lambda x: (-x["total"], x["conseiller"].lower()))
    return rows


@api_router.get("/suivi-3p")
async def list_suivi_3p(
    q: Optional[str] = None,
    statut: Optional[str] = None,
    conseiller: Optional[str] = None,
    filtre: Optional[str] = None,
    geo: Optional[str] = None,
    limit: int = Query(5000, ge=1, le=10000),
    user: User = Depends(get_current_user),
):
    query = suivi_3p_base_query(user, conseiller=conseiller)
    clients = await db[SUIVI_3P_CLIENTS].find(query, {"_id": 0}).to_list(limit)
    rows = [serialize_suivi_client(c) for c in clients]

    rows = filter_suivi_3p_rows(rows, statut=statut, filtre=filtre, geo=geo, q=q)

    # Enrichissement Analyses (3e Pilier / Fortune) après filtres
    client_ids = [r["id"] for r in rows if r.get("id")]
    docs_map = await _docs_by_suivi_client(client_ids)
    for r in rows:
        summary = analyse_summary_from_docs(docs_map.get(r.get("id")) or [])
        if not summary["has_analyse_3p"] and not summary["has_analyse_fortune"] and r.get("date_derniere_analyse"):
            summary["has_analyse_3p"] = True
        r.update(summary)

    return rows


@api_router.get("/suivi-3p/export.xlsx")
async def export_suivi_3p_phone_followup(
    q: Optional[str] = None,
    statut: Optional[str] = None,
    conseiller: Optional[str] = None,
    filtre: Optional[str] = None,
    geo: Optional[str] = None,
    scope: Optional[str] = Query("a_appeler", description="a_appeler | liste_filtree | selection"),
    regroupement: Optional[str] = Query("par_conseiller", description="par_conseiller | feuille_unique"),
    colonnes: Optional[str] = Query(None, description="Clés colonnes séparées par des virgules"),
    client_ids: Optional[str] = Query(None, description="IDs clients (scope=selection)"),
    user: User = Depends(get_current_user),
):
    """Export Excel Suivi 3P — périmètre, regroupement et colonnes configurables."""
    scope_norm = (scope or "a_appeler").strip().lower()
    if scope_norm not in ("a_appeler", "liste_filtree", "selection"):
        raise HTTPException(status_code=400, detail="Périmètre d'export invalide")

    selected_ids = [s.strip() for s in (client_ids or "").split(",") if s.strip()]
    if scope_norm == "selection" and not selected_ids:
        raise HTTPException(
            status_code=400,
            detail="Sélectionnez au moins un client dans le tableau (cases à cocher)",
        )

    col_keys = normalize_export_columns(
        [c.strip() for c in (colonnes or "").split(",") if c.strip()] or None
    )

    query = suivi_3p_base_query(user, conseiller=conseiller)
    clients = await db[SUIVI_3P_CLIENTS].find(query, {"_id": 0}).to_list(10000)
    rows = [serialize_suivi_client(c) for c in clients]
    rows = filter_suivi_3p_rows(rows, statut=statut, filtre=filtre, geo=geo, q=q)

    if scope_norm == "selection":
        id_set = set(selected_ids)
        rows = [r for r in rows if r.get("id") in id_set]

    client_ids_for_docs = [r["id"] for r in rows if r.get("id")]
    docs_map = await _docs_by_suivi_client(client_ids_for_docs)

    try:
        data = build_suivi_3p_export_xlsx(
            rows,
            docs_map,
            scope=scope_norm,
            grouping=(regroupement or "par_conseiller"),
            columns=col_keys,
        )
    except Exception as e:
        logger.exception("Export Suivi 3P échoué")
        raise HTTPException(status_code=500, detail=f"Export Excel impossible : {e}") from e

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"Suivi_3e_pilier_{stamp}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=_file_response_headers(filename, inline=False),
    )


@api_router.post("/suivi-3p/bulk-statut")
async def bulk_update_suivi_3p_statut(
    payload: Suivi3PBulkStatutRequest,
    user: User = Depends(get_current_user),
):
    """Passe plusieurs fiches au même statut (ex. Offre envoyée après envoi des courriers)."""
    statut = normalize_suivi_statut(payload.statut)
    if not statut:
        raise HTTPException(status_code=400, detail="Statut invalide")

    base = suivi_3p_base_query(user)
    ids = [str(i).strip() for i in (payload.client_ids or []) if str(i).strip()]

    # « Offre envoyée » : PDF d'analyse + gain fiscal > 250 CHF uniquement
    restrict_offre = payload.only_offre_eligible
    if restrict_offre is None:
        restrict_offre = statut == "Offre envoyée"

    if restrict_offre:
        clients = await db[SUIVI_3P_CLIENTS].find(base, {"_id": 0}).to_list(10000)
        if ids:
            id_set = set(ids)
            clients = [c for c in clients if c.get("id") in id_set]
        docs_map = await _docs_by_suivi_client([c["id"] for c in clients if c.get("id")])
        eligible_ids = []
        for c in clients:
            cid = c.get("id")
            if not cid:
                continue
            row = serialize_suivi_client(c)
            docs = docs_map.get(cid) or []
            if is_offre_envoyee_eligible(row, docs):
                eligible_ids.append(cid)
        if not eligible_ids:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Aucun client éligible (PDF d'analyse + gain fiscal > "
                    f"{int(GAIN_OPTIM_MIN_EXCLUSIVE)} CHF)"
                ),
            )
        ids = eligible_ids
    elif not ids:
        raise HTTPException(
            status_code=400,
            detail="Sélectionnez au moins un client (cases à cocher dans le tableau)",
        )

    query = {"$and": [base, {"id": {"$in": ids}}]}
    now = datetime.now(timezone.utc).isoformat()
    result = await db[SUIVI_3P_CLIENTS].update_many(
        query,
        {"$set": {"statut": statut, "updated_at": now}},
    )
    return {
        "ok": True,
        "statut": statut,
        "matched": result.matched_count,
        "updated": result.modified_count,
        "eligible_count": len(ids),
        "threshold": GAIN_OPTIM_MIN_EXCLUSIVE if restrict_offre else None,
    }


@api_router.post("/suivi-3p")
async def create_suivi_3p_client(payload: Suivi3PCreate, user: User = Depends(get_current_user)):
    from client_hub import apply_hub_to_suivi, get_hub_client, upsert_hub_client_from_person

    conseiller = force_conseiller_on_write(user, payload.conseiller)
    hub_id = (payload.client_id or "").strip() or None
    person = payload.model_dump()

    if hub_id:
        hub = await get_hub_client(db, hub_id, user_id=user.user_id)
        if hub:
            person = {**apply_hub_to_suivi(hub), **{k: v for k, v in person.items() if v not in (None, "")}}
            person["client_id"] = hub_id
        else:
            hub_id = None

    if not hub_id:
        hub, _ = await upsert_hub_client_from_person(
            db,
            person,
            user_id=user.user_id,
            module="suivi_3p",
            conseiller=conseiller,
        )
        if hub:
            hub_id = hub["id"]
            person = {**apply_hub_to_suivi(hub), **{k: v for k, v in person.items() if v not in (None, "")}}

    doc = build_new_client(
        user_id=TENANT_USER_ID,
        prenom=person.get("prenom") or payload.prenom,
        nom=person.get("nom") or payload.nom,
        date_naissance=person.get("date_naissance") or payload.date_naissance,
        etat_civil=person.get("etat_civil") or payload.etat_civil,
        nombre_enfants=payload.nombre_enfants or 0,
        conseiller=conseiller,
        conjoint=person.get("conjoint") or payload.conjoint,
        conjoint_prenom=person.get("conjoint_prenom") or payload.conjoint_prenom,
        conjoint_nom=person.get("conjoint_nom") or payload.conjoint_nom,
        conjoint_date_naissance=person.get("conjoint_date_naissance") or payload.conjoint_date_naissance,
        email=person.get("email") or payload.email,
        telephone=person.get("telephone") or payload.telephone,
        adresse=person.get("adresse") or payload.adresse,
        npa=person.get("npa") or payload.npa,
        ville=person.get("ville") or payload.ville,
        adresse_complement=person.get("adresse_complement") or payload.adresse_complement,
        pays=person.get("pays") or payload.pays,
        sexe=person.get("sexe") or payload.sexe,
        statut=payload.statut or DEFAULT_SUIVI_3P_STATUT,
        gain_fiscal_estime=payload.gain_fiscal_estime,
        date_derniere_analyse=payload.date_derniere_analyse,
        notes=payload.notes,
    )
    if hub_id:
        doc["client_id"] = hub_id
    if not doc["prenom"] or not doc["nom"]:
        raise HTTPException(status_code=400, detail="Prénom et nom requis")
    to_store = _encrypt_client_for_storage(doc)
    await db[SUIVI_3P_CLIENTS].insert_one(to_store)
    return serialize_suivi_client(to_store)


async def _apply_analyse_pdf_to_client(client_id: str, pdf_bytes: bytes) -> Optional[float]:
    """Met à jour date d'analyse + gain fiscal extrait du PDF."""
    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "date_derniere_analyse": now[:10],
        "updated_at": now,
    }
    gain = extract_economie_fiscale_from_pdf(pdf_bytes) if pdf_bytes else None
    if gain is not None:
        updates["gain_fiscal_estime"] = gain
    await db[SUIVI_3P_CLIENTS].update_one(
        {"id": client_id, "user_id": TENANT_USER_ID},
        {"$set": updates},
    )
    return gain


async def _store_suivi_3p_bytes(
    *,
    data: bytes,
    filename: str,
    content_type: str,
    client_id: Optional[str] = None,
    pending: bool = False,
    source_folder: Optional[str] = None,
    parsed_nom: Optional[str] = None,
    parsed_prenom: Optional[str] = None,
    match_reason: Optional[str] = None,
) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    folder = "pending" if pending else "analyses"
    path = f"{APP_NAME}/suivi-3p/{folder}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, data, content_type)
        storage_path = result["path"]
        size = result.get("size", len(data))
    except Exception as e:
        logger.error(f"Storage upload failed (suivi 3p {folder}): {e}")
        local_name = f"{uuid.uuid4()}.{ext}"
        storage_path = _local_storage_fallback(ROOT_DIR / "uploads" / "suivi-3p" / folder, local_name, data)
        size = len(data)

    now = datetime.now(timezone.utc).isoformat()
    extracted_gain = None
    if not pending and data and (ext == "pdf" or (content_type or "").lower().endswith("pdf")):
        extracted_gain = extract_economie_fiscale_from_pdf(data)

    folder_l = (source_folder or "").casefold()
    display_label = None
    if "fortune" in folder_l or "optimisation" in folder_l:
        display_label = "Analyse optimisation fiscale"

    if pending:
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": TENANT_USER_ID,
            "storage_path": storage_path,
            "original_filename": filename,
            "content_type": content_type,
            "size": size,
            "category": ANALYSE_DOC_CATEGORY,
            "source_folder": source_folder,
            "display_label": display_label,
            "parsed_nom": parsed_nom,
            "parsed_prenom": parsed_prenom,
            "match_reason": match_reason or "unmatched",
            "extracted_gain_fiscal": extracted_gain,
            "is_deleted": False,
            "created_at": now,
        }
        await db[SUIVI_3P_PENDING].insert_one(doc)
        doc.pop("_id", None)
        return doc

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": TENANT_USER_ID,
        "suivi_3p_client_id": client_id,
        "storage_path": storage_path,
        "original_filename": filename,
        "content_type": content_type,
        "size": size,
        "category": ANALYSE_DOC_CATEGORY,
        "source_folder": source_folder,
        "display_label": display_label,
        "extracted_gain_fiscal": extracted_gain,
        "is_deleted": False,
        "created_at": now,
    }
    await db[SUIVI_3P_DOCS].insert_one(doc)
    if client_id:
        await _apply_analyse_pdf_to_client(client_id, data)
    doc.pop("_id", None)
    return doc


async def _collect_analyse_uploads(
    files: Optional[List[UploadFile]],
    zip_file: Optional[UploadFile],
) -> List[dict]:
    collected: List[dict] = []

    async def add_one(filename: str, data: bytes, source_folder: Optional[str], content_type: str):
        if not filename.lower().endswith(".pdf"):
            return
        if not data:
            return
        collected.append({
            "filename": filename,
            "data": data,
            "source_folder": source_folder,
            "content_type": content_type or "application/pdf",
        })

    if zip_file is not None:
        raw = await zip_file.read()
        if raw:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = Path(info.filename).name
                    if not name.lower().endswith(".pdf"):
                        continue
                    # dossier parent dans le zip (ex. PDF Mariés avec Agent/xxx.pdf)
                    parts = Path(info.filename).parts
                    folder = parts[-2] if len(parts) >= 2 else None
                    with zf.open(info) as fh:
                        data = fh.read()
                    await add_one(name, data, folder, "application/pdf")

    for f in files or []:
        data = await f.read()
        await add_one(f.filename or "analyse.pdf", data, None, f.content_type or "application/pdf")

    return collected


@api_router.get("/suivi-3p/pending-documents")
async def list_suivi_3p_pending(user: User = Depends(get_current_user)):
    require_admin(user)
    rows = await db[SUIVI_3P_PENDING].find(
        {"user_id": TENANT_USER_ID, "is_deleted": False},
        {"_id": 0, "storage_path": 0, "storage_path_legacy": 0},
    ).sort("created_at", -1).to_list(2000)
    return rows


@api_router.get("/suivi-3p/pending-documents/{doc_id}/download")
async def download_suivi_3p_pending(doc_id: str, user: User = Depends(get_current_user)):
    require_admin(user)
    record = await db[SUIVI_3P_PENDING].find_one(
        {"id": doc_id, "user_id": TENANT_USER_ID, "is_deleted": False}, {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    try:
        data = await _load_storage_bytes(record["storage_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    content_type = record.get("content_type") or "application/pdf"
    return Response(
        content=data,
        media_type=content_type,
        headers=_file_response_headers(
            _resolve_download_filename(record, fallback="analyse.pdf"),
            inline=True,
        ),
    )


@api_router.post("/suivi-3p/pending-documents/{doc_id}/assign")
async def assign_suivi_3p_pending(
    doc_id: str,
    payload: Suivi3PAssignPending,
    user: User = Depends(get_current_user),
):
    require_admin(user)
    pending = await db[SUIVI_3P_PENDING].find_one(
        {"id": doc_id, "user_id": TENANT_USER_ID, "is_deleted": False}, {"_id": 0}
    )
    if not pending:
        raise HTTPException(status_code=404, detail="Document en attente introuvable")
    client = await _require_suivi_3p_client(payload.client_id, user)
    now = datetime.now(timezone.utc).isoformat()
    pdf_bytes = await _try_read_storage_bytes(pending.get("storage_path") or "")
    extracted_gain = pending.get("extracted_gain_fiscal")
    if extracted_gain is None and pdf_bytes:
        extracted_gain = extract_economie_fiscale_from_pdf(pdf_bytes)
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": TENANT_USER_ID,
        "suivi_3p_client_id": client["id"],
        "storage_path": pending["storage_path"],
        "original_filename": pending.get("original_filename"),
        "content_type": pending.get("content_type") or "application/pdf",
        "size": pending.get("size"),
        "category": ANALYSE_DOC_CATEGORY,
        "source_folder": pending.get("source_folder"),
        "assigned_from_pending": pending["id"],
        "extracted_gain_fiscal": extracted_gain,
        "is_deleted": False,
        "created_at": now,
    }
    await db[SUIVI_3P_DOCS].insert_one(doc)
    await db[SUIVI_3P_PENDING].update_one(
        {"id": doc_id},
        {"$set": {"is_deleted": True, "assigned_client_id": client["id"], "assigned_at": now}},
    )
    if pdf_bytes:
        await _apply_analyse_pdf_to_client(client["id"], pdf_bytes)
    else:
        updates = {"date_derniere_analyse": now[:10], "updated_at": now}
        if extracted_gain is not None:
            updates["gain_fiscal_estime"] = extracted_gain
        await db[SUIVI_3P_CLIENTS].update_one({"id": client["id"]}, {"$set": updates})
    doc.pop("_id", None)
    return public_storage_record(doc)


@api_router.delete("/suivi-3p/pending-documents/{doc_id}")
async def delete_suivi_3p_pending(doc_id: str, user: User = Depends(get_current_user)):
    require_admin(user)
    res = await db[SUIVI_3P_PENDING].update_one(
        {"id": doc_id, "user_id": TENANT_USER_ID},
        {"$set": {"is_deleted": True}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return {"ok": True}


@api_router.post("/admin/import-suivi-3p-analyses")
async def import_suivi_3p_analyses(
    files: Optional[List[UploadFile]] = File(None),
    zip_file: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user),
):
    """Associe automatiquement des PDF d'analyse aux clients Suivi 3P (NOM_Prenom.pdf)."""
    require_admin(user)
    uploads = await _collect_analyse_uploads(files, zip_file)
    if not uploads:
        raise HTTPException(status_code=400, detail="Aucun PDF fourni (fichiers ou zip)")

    clients = await db[SUIVI_3P_CLIENTS].find({"user_id": TENANT_USER_ID}, {"_id": 0}).to_list(5000)
    index = build_client_name_index(clients)

    matched = 0
    pending = 0
    skipped = 0
    details = []

    for item in uploads:
        filename = item["filename"]
        nom, prenom, matches = find_clients_for_pdf_name(filename, index)
        if nom is None:
            skipped += 1
            details.append({"filename": filename, "action": "skipped", "reason": "nom_invalide"})
            continue

        if len(matches) == 1:
            client = matches[0]
            # éviter doublon exact même nom de fichier (casse ignorée)
            exists = await db[SUIVI_3P_DOCS].find_one({
                "user_id": TENANT_USER_ID,
                "suivi_3p_client_id": client["id"],
                "is_deleted": False,
                "$or": [
                    {"original_filename": filename},
                    {"original_filename": {"$regex": f"^{re.escape(filename)}$", "$options": "i"}},
                ],
            }, {"_id": 0, "id": 1})
            if exists:
                skipped += 1
                details.append({
                    "filename": filename,
                    "action": "skipped",
                    "reason": "deja_importe",
                    "client_id": client["id"],
                })
                continue
            # Doublon contenu : même taille + même stem déjà présent
            stem_l = Path(filename).stem.strip().casefold()
            existing_docs = await db[SUIVI_3P_DOCS].find({
                "user_id": TENANT_USER_ID,
                "suivi_3p_client_id": client["id"],
                "is_deleted": False,
                "size": len(item["data"]),
            }, {"_id": 0, "id": 1, "original_filename": 1}).to_list(50)
            if any(Path(d.get("original_filename") or "").stem.strip().casefold() == stem_l for d in existing_docs):
                skipped += 1
                details.append({
                    "filename": filename,
                    "action": "skipped",
                    "reason": "deja_importe_taille_stem",
                    "client_id": client["id"],
                })
                continue
            await _store_suivi_3p_bytes(
                data=item["data"],
                filename=filename,
                content_type=item["content_type"],
                client_id=client["id"],
                pending=False,
                source_folder=item.get("source_folder"),
            )
            gain = extract_economie_fiscale_from_pdf(item["data"])
            matched += 1
            details.append({
                "filename": filename,
                "action": "matched",
                "client_id": client["id"],
                "client": f"{client.get('prenom')} {client.get('nom')}",
                "gain_fiscal_estime": gain,
            })
        else:
            reason = "ambiguous" if len(matches) > 1 else "unmatched"
            await _store_suivi_3p_bytes(
                data=item["data"],
                filename=filename,
                content_type=item["content_type"],
                pending=True,
                source_folder=item.get("source_folder"),
                parsed_nom=nom,
                parsed_prenom=prenom,
                match_reason=reason,
            )
            pending += 1
            details.append({
                "filename": filename,
                "action": "pending",
                "reason": reason,
                "parsed_nom": nom,
                "parsed_prenom": prenom,
                "candidates": len(matches),
            })

    return {
        "total": len(uploads),
        "matched": matched,
        "pending": pending,
        "skipped": skipped,
        "details_sample": details[:80],
        "details_total": len(details),
    }


@api_router.get("/suivi-3p/documents/{doc_id}/download")
async def download_suivi_3p_document(doc_id: str, user: User = Depends(get_current_user)):
    record = await db[SUIVI_3P_DOCS].find_one(
        {"id": doc_id, "user_id": TENANT_USER_ID, "is_deleted": False}, {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    await _require_suivi_3p_client(record["suivi_3p_client_id"], user)
    try:
        data = await _load_storage_bytes(record["storage_path"])
    except Exception as e:
        logger.exception(
            "Download suivi-3p doc %s failed path=%s: %s",
            doc_id,
            record.get("storage_path"),
            e,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Fichier introuvable ou illisible ({type(e).__name__})",
        )
    content_type = record.get("content_type") or "application/pdf"
    fname = _resolve_download_filename(record, fallback="analyse.pdf")
    is_docx = str(fname).lower().endswith(".docx") or "wordprocessingml" in str(content_type)
    return Response(
        content=data,
        media_type=content_type,
        headers=_file_response_headers(fname, inline=not is_docx),
    )


@api_router.delete("/suivi-3p/documents/{doc_id}")
async def delete_suivi_3p_document(doc_id: str, user: User = Depends(get_current_user)):
    record = await db[SUIVI_3P_DOCS].find_one(
        {"id": doc_id, "user_id": TENANT_USER_ID, "is_deleted": False}, {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    await _require_suivi_3p_client(record["suivi_3p_client_id"], user)
    await db[SUIVI_3P_DOCS].update_one(
        {"id": doc_id},
        {"$set": {"is_deleted": True}},
    )
    return {"ok": True}


def _courrier_docx_response(data: bytes, filename: str) -> Response:
    from courrier_word import DOCX_MEDIA_TYPE

    return Response(
        content=data,
        media_type=DOCX_MEDIA_TYPE,
        headers=_file_response_headers(filename, inline=False),
    )


async def _docs_by_suivi_client(client_ids: List[str]) -> dict:
    if not client_ids:
        return {}
    docs = await db[SUIVI_3P_DOCS].find(
        {
            "user_id": TENANT_USER_ID,
            "suivi_3p_client_id": {"$in": client_ids},
            "is_deleted": False,
        },
        {"_id": 0},
    ).to_list(20000)
    by_id: dict = {}
    for d in docs:
        by_id.setdefault(d.get("suivi_3p_client_id"), []).append(d)
    return by_id


async def _upsert_courrier_in_dossier(client: dict, data: bytes, filename: str, when) -> str:
    """Enregistre (ou remplace) le courrier dans le dossier documents du client Suivi 3P."""
    from courrier_word import DOCX_MEDIA_TYPE

    cid = client["id"]
    existing = await db[SUIVI_3P_DOCS].find_one(
        {
            "user_id": TENANT_USER_ID,
            "suivi_3p_client_id": cid,
            "is_deleted": False,
            "kind": COURRIER_KIND,
        },
        {"_id": 0},
    )
    ext = "docx"
    path = f"{APP_NAME}/suivi-3p/courriers/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, data, DOCX_MEDIA_TYPE)
        storage_path = result["path"]
        size = result.get("size", len(data))
    except Exception as e:
        logger.error("Storage upload failed (courrier): %s", e)
        local_name = f"{uuid.uuid4()}.{ext}"
        storage_path = _local_storage_fallback(ROOT_DIR / "uploads" / "suivi-3p" / "courriers", local_name, data)
        size = len(data)

    now = datetime.now(timezone.utc).isoformat()
    day = when.strftime("%d.%m.%Y") if hasattr(when, "strftime") else str(when)
    fields = {
        "storage_path": storage_path,
        "original_filename": filename,
        "content_type": DOCX_MEDIA_TYPE,
        "size": size,
        "category": ANALYSE_DOC_CATEGORY,
        "display_label": f"{COURRIER_DISPLAY_PREFIX} – {day}",
        "kind": COURRIER_KIND,
        "campaign": "optimisation_fiscale",
        "updated_at": now,
        "generated_at": now[:10],
    }
    if existing:
        await db[SUIVI_3P_DOCS].update_one({"id": existing["id"]}, {"$set": fields})
        return "updated"
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": TENANT_USER_ID,
        "suivi_3p_client_id": cid,
        "is_deleted": False,
        "created_at": now,
        **fields,
    }
    await db[SUIVI_3P_DOCS].insert_one(doc)
    return "created"


async def _remove_courrier_from_dossier(client_id: str) -> int:
    """Supprime le courrier d'optimisation du dossier (clients hors seuil)."""
    res = await db[SUIVI_3P_DOCS].update_many(
        {
            "user_id": TENANT_USER_ID,
            "suivi_3p_client_id": client_id,
            "kind": COURRIER_KIND,
            "is_deleted": False,
        },
        {"$set": {"is_deleted": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return int(res.modified_count or 0)


async def _prepare_courrier_client(c: dict) -> dict:
    """Complète pays et civilité à partir du CRM / prénom, et les enregistre si vides."""
    from courrier_word import infer_country, resolve_civilities, is_male_civ, is_female_civ

    patch = {}
    pays = infer_country(c)
    if pays and not str(c.get("pays") or "").strip():
        c["pays"] = pays
        patch["pays"] = pays
    client_civ, spouse_civ = resolve_civilities(c)
    if is_male_civ(client_civ) and not str(c.get("sexe") or "").strip():
        c["sexe"] = "Homme"
        patch["sexe"] = "Homme"
    elif is_female_civ(client_civ) and not str(c.get("sexe") or "").strip():
        c["sexe"] = "Femme"
        patch["sexe"] = "Femme"
    if spouse_civ and not str(c.get("conjoint_sexe") or "").strip():
        val = "Homme" if is_male_civ(spouse_civ) else "Femme"
        c["conjoint_sexe"] = val
        patch["conjoint_sexe"] = val
    if patch and c.get("id"):
        patch["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[SUIVI_3P_CLIENTS].update_one({"id": c["id"]}, {"$set": _encrypt_client_patch(patch)})
    return c


@api_router.post("/suivi-3p/courriers")
@api_router.post("/suivi-3p/courriers/generate")
async def generate_suivi_3p_courriers_campagne(
    payload: Suivi3PCourriersRequest = Suivi3PCourriersRequest(),
    user: User = Depends(get_current_user),
):
    """
    Génère les courriers d'optimisation fiscale pour les clients Suivi 3P
    dont le gain de l'analyse « Optimisation fiscale » est > 250 CHF.
    Enregistre chaque .docx dans le dossier documents du client (sans doublon).
    """
    from courrier_word import generate_courrier_docx, is_eligible_for_courrier
    from zoneinfo import ZoneInfo

    payload = payload or Suivi3PCourriersRequest()
    requested = [str(i).strip() for i in (payload.client_ids or []) if str(i).strip()]
    query = suivi_3p_base_query(user)
    if requested:
        query = {**query, "id": {"$in": requested}}
    raw_clients = await db[SUIVI_3P_CLIENTS].find(query, {"_id": 0}).to_list(10000)
    clients = [serialize_suivi_client(c) for c in raw_clients]
    docs_map = await _docs_by_suivi_client([c["id"] for c in clients])

    analyzed = len(clients)
    eligible = 0
    generated = 0
    updated = 0
    excluded = 0
    removed = 0
    errors: list[str] = []
    when = datetime.now(ZoneInfo("Europe/Zurich")).date()

    for c in clients:
        docs = docs_map.get(c["id"]) or []
        if not is_eligible_for_courrier(c, docs):
            excluded += 1
            try:
                removed += await _remove_courrier_from_dossier(c["id"])
            except Exception:
                logger.exception("Suppression courrier inéligible %s", c.get("id"))
            continue
        eligible += 1
        try:
            c = await _prepare_courrier_client(c)
            data, filename = generate_courrier_docx(c, when=when, docs=docs)
            action = await _upsert_courrier_in_dossier(c, data, filename, when)
            generated += 1
            if action == "updated":
                updated += 1
        except Exception as exc:
            logger.exception("Courrier %s %s: %s", c.get("prenom"), c.get("nom"), exc)
            errors.append(f"{c.get('prenom') or ''} {c.get('nom') or ''}: {exc}".strip())

    return {
        "analyzed": analyzed,
        "eligible": eligible,
        "generated": generated,
        "updated": updated,
        "excluded": excluded,
        "excluded_gain": excluded,
        "removed": removed,
        "threshold": GAIN_OPTIM_MIN_EXCLUSIVE,
        "errors": errors[:50],
        "error_count": len(errors),
        "generated_date": when.isoformat(),
    }


@api_router.get("/suivi-3p/courriers/download-all")
async def download_all_suivi_3p_courriers(user: User = Depends(get_current_user)):
    """ZIP de tous les courriers d'optimisation déjà générés (gain > 250 au moment du scan)."""
    from courrier_word import is_eligible_for_courrier
    from zoneinfo import ZoneInfo

    query = suivi_3p_base_query(user)
    raw_clients = await db[SUIVI_3P_CLIENTS].find(query, {"_id": 0}).to_list(10000)
    clients = [serialize_suivi_client(c) for c in raw_clients]
    ids = [c["id"] for c in clients]
    docs_map = await _docs_by_suivi_client(ids)

    buf = io.BytesIO()
    used: dict[str, int] = {}
    count = 0
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for c in clients:
            docs = docs_map.get(c["id"]) or []
            if not is_eligible_for_courrier(c, docs):
                continue
            letter = next((d for d in docs if (d.get("kind") or "") == COURRIER_KIND), None)
            if not letter:
                continue
            try:
                data = await _load_storage_bytes(letter["storage_path"])
            except Exception:
                logger.exception("ZIP courrier illisible %s", letter.get("id"))
                continue
            name = _resolve_download_filename(
                letter,
                fallback=f"Courrier_{c.get('nom')}_{c.get('prenom')}.docx",
            )
            stem = name[:-5] if name.lower().endswith(".docx") else name
            n = used.get(stem, 0)
            used[stem] = n + 1
            final = name if n == 0 else f"{stem}_{n + 1}.docx"
            zf.writestr(final, data)
            count += 1
    if count == 0:
        raise HTTPException(status_code=404, detail="Aucun courrier à télécharger (gain fiscal > 250 CHF requis)")
    when = datetime.now(ZoneInfo("Europe/Zurich")).date()
    zip_name = f"Courriers_Optimisation_Fiscale_{when.strftime('%d-%m-%Y')}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers=_file_response_headers(zip_name, inline=False),
    )


@api_router.post("/suivi-3p/{client_id}/courrier")
async def generate_suivi_3p_courrier(client_id: str, user: User = Depends(get_current_user)):
    from courrier_word import generate_courrier_docx, is_eligible_for_courrier
    from zoneinfo import ZoneInfo

    c = serialize_suivi_client(await _require_suivi_3p_client(client_id, user))
    docs_map = await _docs_by_suivi_client([client_id])
    docs = docs_map.get(client_id) or []
    if not is_eligible_for_courrier(c, docs):
        raise HTTPException(
            status_code=400,
            detail=f"Courrier réservé aux clients dont le gain d'optimisation fiscale est supérieur à {int(GAIN_OPTIM_MIN_EXCLUSIVE)} CHF",
        )
    when = datetime.now(ZoneInfo("Europe/Zurich")).date()
    c = await _prepare_courrier_client(c)
    try:
        data, filename = generate_courrier_docx(c, when=when, docs=docs)
        await _upsert_courrier_in_dossier(c, data, filename, when)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _courrier_docx_response(data, filename)


@api_router.get("/suivi-3p/{client_id}")
async def get_suivi_3p_fiche(client_id: str, user: User = Depends(get_current_user)):
    c = await _require_suivi_3p_client(client_id, user)
    return serialize_suivi_client(c)


@api_router.put("/suivi-3p/{client_id}")
async def update_suivi_3p_fiche(
    client_id: str,
    payload: Suivi3PUpdate,
    user: User = Depends(get_current_user),
):
    c = await _require_suivi_3p_client(client_id, user)
    data = payload.model_dump(exclude_unset=True)
    updates: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if "prenom" in data and not str(data.get("prenom") or "").strip():
        raise HTTPException(status_code=400, detail="Le prénom ne peut pas être vide")
    if "nom" in data and not str(data.get("nom") or "").strip():
        raise HTTPException(status_code=400, detail="Le nom ne peut pas être vide")

    for key in (
        "prenom", "nom", "etat_civil", "email", "telephone", "notes",
        "conjoint", "conjoint_prenom", "conjoint_nom",
        "adresse", "adresse_complement", "npa", "ville", "pays", "sexe",
    ):
        if key not in data:
            continue
        val = data[key]
        if isinstance(val, str):
            updates[key] = val.strip() or None
        elif val is not None:
            updates[key] = val
        else:
            updates[key] = None
    if "sexe" in updates:
        updates["civilite"] = updates["sexe"]

    if "date_naissance" in data:
        updates["date_naissance"] = (str(data["date_naissance"])[:10] if data["date_naissance"] else None)
    if "conjoint_date_naissance" in data:
        updates["conjoint_date_naissance"] = (
            str(data["conjoint_date_naissance"])[:10] if data["conjoint_date_naissance"] else None
        )
    if "nombre_enfants" in data and data["nombre_enfants"] is not None:
        updates["nombre_enfants"] = int(data["nombre_enfants"])
    if "conseiller" in data:
        updates["conseiller"] = force_conseiller_on_write(user, data.get("conseiller"))
    if "statut" in data and data["statut"] is not None:
        updates["statut"] = normalize_suivi_statut(data["statut"])
    if "gain_fiscal_estime" in data:
        updates["gain_fiscal_estime"] = parse_gain(data["gain_fiscal_estime"])
    if "date_derniere_analyse" in data:
        d = data["date_derniere_analyse"]
        updates["date_derniere_analyse"] = (str(d)[:10] if d else None)
    if "client_contacte" in data and data["client_contacte"] is not None:
        updates["client_contacte"] = bool(data["client_contacte"])
    if "rdv_pris" in data and data["rdv_pris"] is not None:
        updates["rdv_pris"] = bool(data["rdv_pris"])
        if not updates["rdv_pris"]:
            updates["date_rdv"] = None
    if "date_rdv" in data:
        d = data["date_rdv"]
        updates["date_rdv"] = (str(d)[:10] if d else None)
        if updates.get("date_rdv") and "rdv_pris" not in updates:
            updates["rdv_pris"] = True

    # Recalcul conjoint label si prénom/nom fournis
    if "conjoint_prenom" in updates or "conjoint_nom" in updates:
        cp = updates.get("conjoint_prenom", c.get("conjoint_prenom") or "")
        cn = updates.get("conjoint_nom", c.get("conjoint_nom") or "")
        if "conjoint" not in updates:
            updates["conjoint"] = f"{cp} {cn}".strip() or None

    updates = _encrypt_client_patch(updates)
    await db[SUIVI_3P_CLIENTS].update_one({"id": client_id}, {"$set": updates})
    fresh = await db[SUIVI_3P_CLIENTS].find_one({"id": client_id}, {"_id": 0})
    serialized = serialize_suivi_client(fresh or {**c, **updates})

    # Sync identité vers le hub Clients
    try:
        from client_hub import push_person_to_hub, upsert_hub_client_from_person

        hub_id = (fresh or c).get("client_id") if isinstance(fresh or c, dict) else None
        merged = {**(fresh or c), **updates}
        if hub_id:
            await push_person_to_hub(db, hub_id, merged, user_id=user.user_id, module="suivi_3p")
        elif merged.get("prenom") and merged.get("nom"):
            hub, _ = await upsert_hub_client_from_person(
                db, merged, user_id=user.user_id, module="suivi_3p",
                conseiller=merged.get("conseiller"),
            )
            if hub:
                await db[SUIVI_3P_CLIENTS].update_one(
                    {"id": client_id}, {"$set": {"client_id": hub["id"]}}
                )
                serialized["client_id"] = hub["id"]
    except Exception:
        logger.exception("Hub sync suivi 3P échoué client=%s", client_id)

    return serialized


@api_router.delete("/suivi-3p/{client_id}")
async def delete_suivi_3p_client(client_id: str, user: User = Depends(get_current_user)):
    await _require_suivi_3p_client(client_id, user)
    await db[SUIVI_3P_DOCS].update_many(
        {"suivi_3p_client_id": client_id, "user_id": TENANT_USER_ID},
        {"$set": {"is_deleted": True}},
    )
    res = await db[SUIVI_3P_CLIENTS].delete_one({"id": client_id, "user_id": TENANT_USER_ID})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Client Suivi 3P introuvable")
    return {"ok": True}


@api_router.get("/suivi-3p/{client_id}/documents")
async def list_suivi_3p_documents(client_id: str, user: User = Depends(get_current_user)):
    from courrier_word import is_eligible_for_courrier

    c = serialize_suivi_client(await _require_suivi_3p_client(client_id, user))
    docs = await db[SUIVI_3P_DOCS].find(
        {
            "user_id": TENANT_USER_ID,
            "suivi_3p_client_id": client_id,
            "is_deleted": False,
            "category": ANALYSE_DOC_CATEGORY,
        },
        {"_id": 0, "storage_path": 0, "storage_path_legacy": 0},
    ).sort("created_at", -1).to_list(100)
    if not is_eligible_for_courrier(c, docs):
        await _remove_courrier_from_dossier(client_id)
        docs = [d for d in docs if (d.get("kind") or "") != COURRIER_KIND]
    return docs


@api_router.post("/suivi-3p/{client_id}/documents")
async def upload_suivi_3p_document(
    client_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    await _require_suivi_3p_client(client_id, user)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    fname = file.filename or "analyse-3p.pdf"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "pdf"
    ctype = file.content_type or MIME_TYPES.get(ext, "application/octet-stream")
    path = f"{APP_NAME}/suivi-3p/{user.user_id}/{uuid.uuid4()}.{ext}"
    try:
        result = put_object(path, data, ctype)
        storage_path = result["path"]
        size = result.get("size", len(data))
    except Exception as e:
        logger.error(f"Storage upload failed (suivi 3p): {e}")
        local_name = f"{uuid.uuid4()}.{ext}"
        storage_path = _local_storage_fallback(ROOT_DIR / "uploads" / "suivi-3p" / user.user_id, local_name, data)
        size = len(data)

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": TENANT_USER_ID,
        "suivi_3p_client_id": client_id,
        "storage_path": storage_path,
        "original_filename": fname,
        "content_type": ctype,
        "size": size,
        "category": ANALYSE_DOC_CATEGORY,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": getattr(user, "account_id", None),
    }
    await db[SUIVI_3P_DOCS].insert_one(doc)
    if (ext == "pdf" or (ctype or "").lower().endswith("pdf")):
        await _apply_analyse_pdf_to_client(client_id, data)
        gain = extract_economie_fiscale_from_pdf(data)
        if gain is not None:
            await db[SUIVI_3P_DOCS].update_one(
                {"id": doc["id"]},
                {"$set": {"extracted_gain_fiscal": gain}},
            )
            doc["extracted_gain_fiscal"] = gain
    doc.pop("_id", None)
    return public_storage_record(doc)


async def _run_suivi_3p_gains_backfill_once() -> dict:
    """
    Migration unique : parcourt les PDF d'analyse déjà liés aux fiches,
    lit « ÉCONOMIE FISCALE ESTIMÉE » et renseigne gain_fiscal_estime.
    Idempotente via app_migrations.
    """
    migration_id = "suivi_3p_gains_from_pdf_v1"
    existing = await db.app_migrations.find_one({"id": migration_id}, {"_id": 0})
    if existing:
        return {"skipped": True, "reason": "already_done", **{k: existing.get(k) for k in ("updated", "at") if k in (existing or {})}}

    docs = await db[SUIVI_3P_DOCS].find(
        {
            "user_id": TENANT_USER_ID,
            "is_deleted": False,
            "category": ANALYSE_DOC_CATEGORY,
        },
        {"_id": 0},
    ).to_list(5000)

    latest_by_client: dict = {}
    for d in docs:
        cid = d.get("suivi_3p_client_id")
        if not cid:
            continue
        prev = latest_by_client.get(cid)
        if not prev or str(d.get("created_at") or "") >= str(prev.get("created_at") or ""):
            latest_by_client[cid] = d

    updated = 0
    skipped = 0
    failed = 0

    for cid, d in latest_by_client.items():
        gain = parse_gain(d.get("extracted_gain_fiscal"))
        if gain is None:
            data = await _try_read_storage_bytes(d.get("storage_path") or "")
            if not data:
                failed += 1
                continue
            gain = extract_economie_fiscale_from_pdf(data)
        if gain is None:
            skipped += 1
            continue

        await db[SUIVI_3P_DOCS].update_one(
            {"id": d["id"]},
            {"$set": {"extracted_gain_fiscal": gain}},
        )
        now = datetime.now(timezone.utc).isoformat()
        await db[SUIVI_3P_CLIENTS].update_one(
            {"id": cid, "user_id": TENANT_USER_ID},
            {"$set": {
                "gain_fiscal_estime": gain,
                "date_derniere_analyse": (d.get("created_at") or now)[:10],
                "updated_at": now,
            }},
        )
        updated += 1

    result = {
        "id": migration_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "clients_with_docs": len(latest_by_client),
        "updated": updated,
        "skipped_no_amount": skipped,
        "failed_read": failed,
    }
    await db.app_migrations.update_one(
        {"id": migration_id},
        {"$set": result},
        upsert=True,
    )
    return result


@api_router.post("/admin/migrate-suivi-3p-clients")
async def migrate_suivi_3p_clients_from_prevoyance(user: User = Depends(get_current_user)):
    """One-shot : déplace les clients import Excel Suivi_3p hors de la prévoyance."""
    require_admin(user)
    cursor = db.clients.find({"user_id": TENANT_USER_ID, "source_import": "suivi_3p_excel"}, {"_id": 0})
    imported = await cursor.to_list(5000)
    # Primaires = titulaire du dossier
    primaries = [c for c in imported if (c.get("dossier_id") or c.get("id")) == c.get("id")]
    spouses_by_id = {c["id"]: c for c in imported if (c.get("dossier_id") or c.get("id")) != c.get("id")}
    created = 0
    skipped = 0
    for p in primaries:
        p_plain = _decrypt_client_doc(p) or p
        candidates = await db[SUIVI_3P_CLIENTS].find({
            "user_id": TENANT_USER_ID,
            "nom": {"$regex": f"^{re.escape(p_plain.get('nom') or '')}$", "$options": "i"},
            "prenom": {"$regex": f"^{re.escape(p_plain.get('prenom') or '')}$", "$options": "i"},
        }, {"_id": 0}).to_list(50)
        existing = None
        want_dob = p_plain.get("date_naissance")
        for cand in candidates:
            cand_plain = decrypt_client_fields(cand) if encryption_configured() else cand
            if want_dob and cand_plain.get("date_naissance") != want_dob:
                continue
            existing = cand
            break
        if existing:
            skipped += 1
            continue
        s = (p_plain.get("suivi_3p") or {}) if isinstance(p_plain.get("suivi_3p"), dict) else {}
        spouse = spouses_by_id.get(p.get("linked_spouse_id") or "")
        spouse_plain = _decrypt_client_doc(spouse) if spouse else None
        doc = build_new_client(
            user_id=TENANT_USER_ID,
            prenom=p_plain.get("prenom") or "",
            nom=p_plain.get("nom") or "",
            date_naissance=p_plain.get("date_naissance"),
            etat_civil=p_plain.get("etat_civil"),
            nombre_enfants=p_plain.get("nombre_enfants") or 0,
            conseiller=p_plain.get("conseiller"),
            conjoint=p_plain.get("conjoint"),
            conjoint_prenom=(spouse_plain or {}).get("prenom") if spouse_plain else None,
            conjoint_nom=(spouse_plain or {}).get("nom") if spouse_plain else None,
            conjoint_date_naissance=(spouse_plain or {}).get("date_naissance") if spouse_plain else None,
            statut=s.get("statut") or DEFAULT_SUIVI_3P_STATUT,
            gain_fiscal_estime=s.get("gain_fiscal_estime"),
            date_derniere_analyse=s.get("date_derniere_analyse"),
            notes=s.get("notes"),
            source_import="suivi_3p_excel",
            client_id=str(uuid.uuid4()),
        )
        await db[SUIVI_3P_CLIENTS].insert_one(_encrypt_client_for_storage(doc))
        created += 1

    delete_res = await db.clients.delete_many({"user_id": TENANT_USER_ID, "source_import": "suivi_3p_excel"})
    return {
        "migrated": created,
        "skipped_existing": skipped,
        "deleted_from_prevoyance": delete_res.deleted_count,
        "message": f"{created} client(s) Suivi 3P créé(s), {delete_res.deleted_count} retiré(s) de la prévoyance",
    }


@api_router.get("/documents/{doc_id}")
async def get_document_meta(doc_id: str, user: User = Depends(get_current_user)):
    """Métadonnées d'un document (prévisualisation CRM, sans le fichier)."""
    record = await db.documents.find_one({"id": doc_id, "user_id": user.user_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    await require_resource_client(record, user, "document")
    return public_storage_record(record)


@api_router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: str,
    download: int = Query(0, ge=0, le=1),
    user: User = Depends(get_current_user),
):
    record = await db.documents.find_one({"id": doc_id, "user_id": user.user_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    await require_resource_client(record, user, "document")
    try:
        data = await _load_storage_bytes(record["storage_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    content_type = record.get("content_type") or "application/octet-stream"
    filename = _resolve_download_filename(record, fallback="document.pdf")
    is_docx = str(filename).lower().endswith(".docx") or "wordprocessingml" in str(content_type).lower()

    # Anciennes lettres AVS stockées en .docx uniquement : convertir pour le viewer PDF natif
    if is_docx and not download:
        from lettre_lpp_word import convert_docx_to_pdf

        pdf = await asyncio.to_thread(convert_docx_to_pdf, data)
        if not pdf:
            raise HTTPException(
                status_code=500,
                detail="Prévisualisation PDF indisponible (conversion LibreOffice).",
            )
        preview_name = filename.rsplit(".", 1)[0] + ".pdf"
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers=_file_response_headers(preview_name, inline=True),
        )

    inline = False if download else True
    return Response(
        content=data,
        media_type=content_type,
        headers=_file_response_headers(filename, inline=inline),
    )


@api_router.get("/documents/{doc_id}/download-word")
async def download_document_word(doc_id: str, user: User = Depends(get_current_user)):
    """Télécharge le .docx compagnon (lettre AVS) — vrai fichier Word du modèle."""
    record = await db.documents.find_one({"id": doc_id, "user_id": user.user_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    await require_resource_client(record, user, "document")

    docx_path = record.get("docx_storage_path")
    filename = _resolve_download_filename(
        record,
        fallback="document.docx",
        prefer_keys=("docx_filename", "original_filename", "filename", "title"),
    )
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if docx_path:
        try:
            data = await _load_storage_bytes(docx_path)
        except Exception:
            raise HTTPException(status_code=404, detail="Fichier Word introuvable")
    else:
        # Legacy : le document principal est déjà un .docx
        primary_name = str(record.get("original_filename") or "")
        primary_ctype = str(record.get("content_type") or "")
        if not (
            primary_name.lower().endswith(".docx")
            or "wordprocessingml" in primary_ctype.lower()
        ):
            raise HTTPException(status_code=404, detail="Aucun fichier Word pour ce document")
        try:
            data = await _load_storage_bytes(record["storage_path"])
        except Exception:
            raise HTTPException(status_code=404, detail="Fichier Word introuvable")

    if not str(filename).lower().endswith(".docx"):
        stem = str(filename).rsplit(".", 1)[0] if filename else "document"
        filename = f"{stem}.docx"

    return Response(
        content=data,
        media_type=content_type,
        headers=_file_response_headers(filename, inline=False),
    )


@api_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: User = Depends(get_current_user)):
    record = await db.documents.find_one(
        {"id": doc_id, "user_id": user.user_id, "is_deleted": False},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    await require_resource_client(record, user, "document")

    client_id = record.get("client_id")
    await db.documents.update_one({"id": doc_id, "user_id": user.user_id}, {"$set": {"is_deleted": True}})

    # Synchronisation Documents <-> Échéances 3P
    if not client_id:
        return {"ok": True}

    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        return {"ok": True}

    lines = c.get("echeances_3p") or []
    if not isinstance(lines, list):
        lines = []

    rachat_unlinked = False
    for l in lines:
        if isinstance(l, dict) and l.get("rachat_doc_id") == doc_id:
            l["rachat_doc_id"] = None
            l["rachat_doc_filename"] = None
            rachat_unlinked = True

    removed_lines = [l for l in lines if isinstance(l, dict) and l.get("source_doc_id") == doc_id]
    if not removed_lines:
        if rachat_unlinked:
            await db.clients.update_one(
                {"id": client_id, "user_id": user.user_id},
                {
                    "$set": {
                        "echeances_3p": lines,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
        return {"ok": True}

    removed_pairs = set()
    for l in removed_lines:
        company = _normalize_3p_str(l.get("company"))
        policy = _normalize_3p_str(l.get("policy_number"))
        if company or policy:
            removed_pairs.add((company, policy))

    remaining_lines = [l for l in lines if not (isinstance(l, dict) and l.get("source_doc_id") == doc_id)]

    # Fermer/supprimer les rappels liés aux lignes supprimées.
    for l in removed_lines:
        old_date = l.get("echeance_3p")
        if old_date:
            old_key = _echeance_3p_contract_key(l.get("company"), l.get("policy_number"), old_date)
            await db.tasks.delete_many({
                "user_id": user.user_id,
                "client_id": client_id,
                "type": "echeance_3p",
                "echeance_3p_key": old_key,
                "done": False,
            })

    # Si d'autres documents existent encore pour ces contrats, reconstruire les lignes
    # manquantes à partir des extractions stockées dans les documents restants.
    remaining_pairs = set()
    for l in remaining_lines:
        company = _normalize_3p_str(l.get("company"))
        policy = _normalize_3p_str(l.get("policy_number"))
        if company or policy:
            remaining_pairs.add((company, policy))

    missing_pairs = removed_pairs - remaining_pairs
    now_iso = datetime.now(timezone.utc).isoformat()

    if missing_pairs:
        other_docs = await db.documents.find(
            {
                "user_id": user.user_id,
                "client_id": client_id,
                "is_deleted": False,
                "extracted_echeances_3p": {"$exists": True},
            },
            {"_id": 0},
        ).sort("created_at", -1).to_list(300)

        latest_entry_by_pair = {}
        for d in other_docs:
            extracted = d.get("extracted_echeances_3p") or []
            for entry in extracted:
                comp = _normalize_3p_str(entry.get("company"))
                pol = _normalize_3p_str(entry.get("policy_number"))
                pair = (comp, pol)
                if pair in missing_pairs and pair not in latest_entry_by_pair and (comp or pol):
                    latest_entry_by_pair[pair] = {"source_doc_id": d.get("id"), "entry": entry}

        for pair in missing_pairs:
            packed = latest_entry_by_pair.get(pair)
            if not packed:
                continue
            entry = packed.get("entry") or {}
            new_date = entry.get("expiry_date")
            new_line = {
                "id": str(uuid.uuid4()),
                "company": entry.get("company") or None,
                "policy_number": entry.get("policy_number") or None,
                "echeance_3p": new_date,
                "detected": bool(entry.get("detected")),
                "raw_date": entry.get("raw_date"),
                "source_doc_id": packed.get("source_doc_id"),
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            remaining_lines.append(new_line)
            await _upsert_echeance_3p_line_reminder(user.user_id, c, new_line)

    detected_dates = [l.get("echeance_3p") for l in remaining_lines if isinstance(l, dict) and l.get("echeance_3p")]
    new_first = min(detected_dates) if detected_dates else None

    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {"echeances_3p": remaining_lines, "echeance_3p": new_first, "updated_at": now_iso}},
    )

    # Synchronisation stricte : enlever les lignes orphelines/doublons
    # (notamment si des anciennes lignes ont été générées sans source_doc_id).
    await _reconcile_echeances_3p_lines(user.user_id, client_id)

    return {"ok": True, "removed_lines": len(removed_lines)}

# ---------------- Appointments ----------------
@api_router.get("/appointments")
async def list_appointments(
    client_id: Optional[str] = None,
    conseiller: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    if client_id:
        await require_client(client_id, user)
        query = {"user_id": user.user_id, "client_id": client_id}
    elif is_global_viewer(user) and (not conseiller or conseiller == "all"):
        query = {"user_id": user.user_id}
    else:
        ids = await accessible_client_ids(db, user, conseiller=conseiller)
        cons_name = conseiller if (conseiller and conseiller != "all") else (user.conseiller or "")
        query = {
            "user_id": user.user_id,
            "$or": [
                {"client_id": {"$in": ids}},
                {"conseiller": cons_name},
                {"created_by": user.account_id},
            ],
        }
    return await db.appointments.find(query, {"_id": 0}).sort("date", 1).to_list(1000)

@api_router.post("/appointments")
async def create_appointment(payload: AppointmentCreate, user: User = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["user_id"] = user.user_id
    doc["done"] = False
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user.account_id
    if doc.get("client_id"):
        c = await require_client(doc["client_id"], user)
        doc["client_name"] = f"{c.get('prenom','')} {c.get('nom','')}".strip() if c else None
        doc["conseiller"] = c.get("conseiller")
        await log_action(user.user_id, doc["client_id"], f"Rendez-vous planifié: {doc['titre']}")
    else:
        doc["conseiller"] = force_conseiller_on_write(user, user.conseiller)
    await db.appointments.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.patch("/appointments/{appt_id}")
async def toggle_appointment(appt_id: str, user: User = Depends(get_current_user)):
    a = await db.appointments.find_one({"id": appt_id, "user_id": user.user_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Rendez-vous introuvable")
    await require_resource_client(a, user, "rendez-vous")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"done": not a.get("done", False)}})
    return await db.appointments.find_one({"id": appt_id}, {"_id": 0})

@api_router.delete("/appointments/{appt_id}")
async def delete_appointment(appt_id: str, user: User = Depends(get_current_user)):
    a = await db.appointments.find_one({"id": appt_id, "user_id": user.user_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Rendez-vous introuvable")
    await require_resource_client(a, user, "rendez-vous")
    await db.appointments.delete_one({"id": appt_id, "user_id": user.user_id})
    return {"ok": True}

# ---------------- Tasks ----------------
@api_router.get("/tasks")
async def list_tasks(
    client_id: Optional[str] = None,
    conseiller: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    if client_id:
        await require_client(client_id, user)
        query = {"user_id": user.user_id, "client_id": client_id}
    elif is_global_viewer(user) and (not conseiller or conseiller == "all"):
        query = {"user_id": user.user_id}
    else:
        ids = await accessible_client_ids(db, user, conseiller=conseiller)
        cons_name = conseiller if (conseiller and conseiller != "all") else (user.conseiller or "")
        query = {
            "user_id": user.user_id,
            "$or": [
                {"client_id": {"$in": ids}},
                {"conseiller": cons_name},
                {"created_by": user.account_id},
            ],
        }
    tasks = await db.tasks.find(query, {"_id": 0}).sort("echeance", 1).to_list(1000)

    # Enrichir avec le nom du client si manquant / met à jour les anciens titres 3P.
    client_ids = {t.get("client_id") for t in tasks if t.get("client_id")}
    by_id = {}
    if client_ids:
        clients = await db.clients.find(
            {"user_id": user.user_id, "id": {"$in": list(client_ids)}},
            {"_id": 0, "id": 1, "prenom": 1, "nom": 1},
        ).to_list(1000)
        by_id = {c["id"]: f"{c.get('prenom', '')} {c.get('nom', '')}".strip() for c in clients}

    for t in tasks:
        cid = t.get("client_id")
        if not cid:
            continue
        name = t.get("client_name") or by_id.get(cid)
        if name:
            t["client_name"] = name
        if t.get("type") == "echeance_3p" and name:
            titre = str(t.get("titre") or "")
            if name not in titre:
                cleaned = titre.lstrip("⚠ ").strip()
                # Retirer la date inline des anciens titres (affichée séparément).
                cleaned = re.sub(r"\s*arrivant à échéance le\s+\d{1,2}[./]\d{1,2}[./]\d{2,4}\s*$", "", cleaned, flags=re.IGNORECASE).strip()
                cleaned = cleaned.replace("Contrat 3e pilier — ", "Contrat 3e pilier ")
                t["titre"] = f"⚠ {name} — {cleaned}"
    return tasks

@api_router.post("/tasks")
async def create_task(payload: TaskCreate, user: User = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["user_id"] = user.user_id
    doc["done"] = False
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user.account_id
    if doc.get("client_id"):
        c = await require_client(doc["client_id"], user)
        doc["conseiller"] = c.get("conseiller")
        doc["client_name"] = f"{c.get('prenom','')} {c.get('nom','')}".strip()
    else:
        doc["conseiller"] = force_conseiller_on_write(user, user.conseiller)
    await db.tasks.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.patch("/tasks/{task_id}")
async def toggle_task(task_id: str, user: User = Depends(get_current_user)):
    t = await db.tasks.find_one({"id": task_id, "user_id": user.user_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    await require_resource_client(t, user, "tâche")
    await db.tasks.update_one({"id": task_id}, {"$set": {"done": not t.get("done", False)}})
    return await db.tasks.find_one({"id": task_id}, {"_id": 0})

@api_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: User = Depends(get_current_user)):
    t = await db.tasks.find_one({"id": task_id, "user_id": user.user_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    await require_resource_client(t, user, "tâche")
    await db.tasks.delete_one({"id": task_id, "user_id": user.user_id})
    return {"ok": True}

# ---------------- Dashboard ----------------
@api_router.get("/dashboard/stats")
async def dashboard_stats(
    conseiller: Optional[str] = None,
    categorie: Optional[str] = Query("all"),
    user: User = Depends(get_current_user),
):
    """
    Stats du tableau de bord commun.
    categorie: all | prevoyance | suivi_3p | offres
    Isolation: collaborateur = ses clients/dossiers ; admin/CEO (see_all) = tout.
    """
    cat = (categorie or "all").strip().lower().replace("-", "_").replace(" ", "_")
    if cat in ("3p", "3e_pilier", "fiscalite", "suivi3p"):
        cat = "suivi_3p"
    if cat in ("offre", "demandes", "demandes_offres"):
        cat = "offres"
    if cat not in ("all", "prevoyance", "suivi_3p", "offres"):
        cat = "all"

    need_prevoyance = cat in ("all", "prevoyance")
    need_suivi = cat in ("all", "suivi_3p")
    need_offres = cat in ("all", "offres")

    clients = []
    if need_prevoyance:
        clients = await db.clients.find(
            clients_base_query(user, conseiller=conseiller, for_dossiers=True),
            {"_id": 0},
        ).to_list(5000)
    dossiers = {}  # dossier_id -> {members, created_at_min, updated_at_max}

    for c in clients:
        dossier_id = c.get("dossier_id") or c.get("id")
        if not dossier_id:
            continue
        key = str(dossier_id)
        d = dossiers.setdefault(key, {"members": [], "created_at_min": None, "updated_at_max": None})
        d["members"].append(c)

        created_at = c.get("created_at")
        updated_at = c.get("updated_at")

        if created_at:
            d["created_at_min"] = min(filter(None, [d["created_at_min"], created_at])) if d["created_at_min"] else created_at
        if updated_at:
            d["updated_at_max"] = max(filter(None, [d["updated_at_max"], updated_at])) if d["updated_at_max"] else updated_at

    def pick_dossier_statut(members: list) -> str:
        # Majorité du statut, tie-break sur l'ordre STATUTS.
        counts = {}
        for m in members:
            st = normalize_statut(m.get("statut", "Nouveau"))
            counts[st] = counts.get(st, 0) + 1

        best = None
        best_count = -1
        for st, count in counts.items():
            if count > best_count:
                best = st
                best_count = count
            elif count == best_count:
                if best in STATUTS and st in STATUTS and STATUTS.index(st) < STATUTS.index(best):
                    best = st
        return best or "Nouveau"

    by_statut = {s: 0 for s in STATUTS}
    urgent = 0
    by_conseiller: dict = {}  # norm key -> { name, total, by_statut }

    dossier_statut_map = {}
    dossier_created_map = {}
    dossier_updated_map = {}

    from conseiller_identity import (
        display_conseiller_name,
        merge_conseiller_display,
        normalize_conseiller_key,
    )

    def pick_dossier_conseiller(members: list) -> str:
        names = [(m.get("conseiller") or "").strip() for m in members]
        names = [n for n in names if n]
        if not names:
            return "Non attribué"
        counts: dict = {}
        displays: dict = {}
        for n in names:
            key = normalize_conseiller_key(n) or n.casefold()
            counts[key] = counts.get(key, 0) + 1
            displays[key] = display_conseiller_name(displays.get(key), n)
        best_key = sorted(counts.items(), key=lambda x: (-x[1], displays[x[0]].lower()))[0][0]
        return displays[best_key]

    for did, d in dossiers.items():
        members = d.get("members") or []
        dossier_statut = pick_dossier_statut(members)
        dossier_statut_map[did] = dossier_statut
        dossier_created_map[did] = d.get("created_at_min")
        dossier_updated_map[did] = d.get("updated_at_max")

        if dossier_statut in by_statut:
            by_statut[dossier_statut] += 1

        # Urgent : au moins un membre urgent et pas clôturé.
        if any(m.get("priorite") == "urgent" and normalize_statut(m.get("statut")) != "Clôturé" for m in members):
            urgent += 1

        cons = pick_dossier_conseiller(members)
        cons_key = normalize_conseiller_key(cons) or "non attribue"
        entry = by_conseiller.get(cons_key)
        if not entry:
            entry = {"name": cons, "total": 0, "by_statut": {s: 0 for s in STATUTS}}
            by_conseiller[cons_key] = entry
        else:
            entry["name"] = merge_conseiller_display(entry["name"], cons)
        entry["total"] += 1
        if dossier_statut in entry["by_statut"]:
            entry["by_statut"][dossier_statut] += 1

    conseiller_list = sorted(
        by_conseiller.values(),
        key=lambda x: (x["name"] == "Non attribué", -x["total"], x["name"].lower()),
    )
    today = datetime.now(timezone.utc).date().isoformat()
    scoped_ids = [m["id"] for d in dossiers.values() for m in (d.get("members") or []) if m.get("id")]
    appts = []
    tasks = []
    if need_prevoyance:
        if is_global_viewer(user) and (not conseiller or conseiller == "all"):
            appts = await db.appointments.find({"user_id": user.user_id}, {"_id": 0}).to_list(5000)
            tasks = await db.tasks.find({"user_id": user.user_id, "done": False}, {"_id": 0}).to_list(1000)
        else:
            appt_q = {"user_id": user.user_id, "$or": [{"client_id": {"$in": scoped_ids}}, {"conseiller": user.conseiller if user.role == ROLE_CONSEILLER else {"$in": [conseiller] if conseiller else []}}]}
            if conseiller and is_global_viewer(user):
                appt_q = {"user_id": user.user_id, "client_id": {"$in": scoped_ids}}
            appts = await db.appointments.find(appt_q, {"_id": 0}).to_list(5000)
            tasks = await db.tasks.find(
                {"user_id": user.user_id, "done": False, "client_id": {"$in": scoped_ids}},
                {"_id": 0},
            ).to_list(1000)
    today_appts = [a for a in appts if (a.get("date") or "").startswith(today)]
    today_appts.sort(key=lambda a: a.get("date", ""))

    # monthly stats last 6 months (dossiers uniques)
    now = datetime.now(timezone.utc)
    monthly = []
    for i in range(5, -1, -1):
        ref = now - timedelta(days=30 * i)
        key = ref.strftime("%Y-%m")
        label = ref.strftime("%b")
        dossiers_count = sum(1 for did, created_at in dossier_created_map.items() if (created_at or "").startswith(key))
        appt_count = sum(1 for a in appts if (a.get("date") or "").startswith(key))
        report_count = sum(
            1
            for did, updated_at in dossier_updated_map.items()
            if (updated_at or "").startswith(key) and dossier_statut_map.get(did) in ["À présenter", "Clôturé"]
        )
        monthly.append({"mois": label, "dossiers": dossiers_count, "rendezvous": appt_count, "rapports": report_count})

    prevoyance_block = {
        "by_statut": by_statut,
        "total": len(dossiers),
        "urgent": urgent,
        "nouveaux": by_statut.get("Nouveau", 0),
        "en_attente_docs": by_statut.get("Documents en attente", 0),
        "en_analyse": by_statut.get("Analyse en cours", 0),
        "stand_by": by_statut.get("Stand-by", 0),
        "a_presenter": by_statut.get("À présenter", 0),
        "termines": by_statut.get("Clôturé", 0),
        "today_appointments": today_appts,
        "monthly": monthly,
        "pending_tasks": len(tasks),
        "tasks": tasks,
        "statuts": STATUTS,
        "by_conseiller": conseiller_list if is_global_viewer(user) else [],
    }

    suivi_block = None
    if need_suivi:
        suivi_q = suivi_3p_base_query(user, conseiller=conseiller)
        suivi_clients = await db[SUIVI_3P_CLIENTS].find(suivi_q, {"_id": 0}).to_list(5000)
        suivi_rows = [serialize_suivi_client(c) for c in suivi_clients]
        suivi_block = compute_suivi_stats(suivi_rows)
        if is_global_viewer(user):
            from conseiller_identity import (
                display_conseiller_name,
                merge_conseiller_display,
                normalize_conseiller_key,
            )

            buckets: dict = {}
            for r in suivi_rows:
                raw = (r.get("conseiller") or "").strip() or "Non attribué"
                key = normalize_conseiller_key(raw) or "non attribue"
                b = buckets.get(key)
                if not b:
                    b = {"conseiller": display_conseiller_name(raw), "total": 0, "signes": 0, "gain_total": 0.0}
                    buckets[key] = b
                else:
                    b["conseiller"] = merge_conseiller_display(b["conseiller"], raw)
                b["total"] += 1
                if r.get("statut_suivi") == "Signé":
                    b["signes"] += 1
                g = r.get("gain_fiscal_estime")
                if g is not None and r.get("statut_suivi") not in ("Refusé", "Sans suite"):
                    try:
                        b["gain_total"] += float(g)
                    except (TypeError, ValueError):
                        pass
            suivi_block["by_conseiller"] = sorted(
                buckets.values(), key=lambda x: (-x["total"], x["conseiller"].lower())
            )
        else:
            suivi_block["by_conseiller"] = []

    offres_block = None
    if need_offres:
        from demandes_offres_3p import (
            COLLECTION as DEMANDES_OFFRES_COLLECTION,
            compute_stats as compute_demandes_stats,
            demandes_offres_base_query,
        )
        offres_q = demandes_offres_base_query(user, conseiller)
        offres_docs = await db[DEMANDES_OFFRES_COLLECTION].find(offres_q, {"_id": 0}).to_list(10000)
        offres_block = compute_demandes_stats(offres_docs)

    # Champs plats = prévoyance (rétrocompat) + modules imbriqués
    return {
        **prevoyance_block,
        "categorie": cat,
        "prevoyance": prevoyance_block if need_prevoyance else None,
        "suivi_3p": suivi_block,
        "offres": offres_block,
        "scope": {
            "role": user.role,
            "conseiller": user.conseiller,
            "filter_conseiller": conseiller,
            "categorie": cat,
            "is_global": is_global_viewer(user),
        },
    }

@api_router.get("/")
async def root():
    return {"message": "Prévoyance CRM API"}

@api_router.post("/admin/merge-couple-dossiers")
async def merge_couple_dossiers(user: User = Depends(get_current_user)):
    """Migration manuelle : fusionne tous les dossiers couple de l'utilisateur."""
    require_admin(user)
    merged = await _migrate_couple_dossiers(user_id=user.user_id)
    return {"merged": merged, "message": f"{merged} couple(s) fusionné(s)"}


@api_router.post("/admin/import-suivi-3p")
async def admin_import_suivi_3p(
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    user: User = Depends(get_current_user),
):
    """Import one-shot identité clients depuis Excel Suivi_3p (admin)."""
    require_admin(user)
    name = (file.filename or "").lower()
    if not (name.endswith(".xlsm") or name.endswith(".xlsx") or name.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Fichier Excel (.xlsm / .xlsx) requis")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    try:
        from import_suivi_3p import import_suivi_3p
        report = await import_suivi_3p(db, data, user_id=user.user_id, dry_run=dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Import Suivi_3p échoué")
        raise HTTPException(status_code=500, detail=f"Import échoué: {exc}")
    # Limiter la taille de réponse : garder le résumé + 50 détails max
    details = report.get("details") or []
    return {
        "dry_run": report.get("dry_run"),
        "rows_read": report.get("rows_read"),
        "created": report.get("created"),
        "spouses_created": report.get("spouses_created"),
        "skipped_existing": report.get("skipped_existing"),
        "skipped_incomplete": report.get("skipped_incomplete"),
        "errors": report.get("errors") or [],
        "details_sample": details[:50],
        "details_total": len(details),
    }


@api_router.post("/suivi-3p/import-addresses")
async def import_suivi_3p_addresses(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    Import Excel d'adresses pour les clients Suivi 3e pilier.
    Matching par id ou nom+prénom. Ne crée aucun doublon.
    """
    name = (file.filename or "").lower()
    if not (name.endswith(".xlsm") or name.endswith(".xlsx") or name.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Fichier Excel (.xlsm / .xlsx) requis")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    try:
        from import_suivi_3p_addresses import apply_suivi_3p_address_import
        report = await apply_suivi_3p_address_import(db, user.user_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Import adresses Suivi 3P échoué")
        raise HTTPException(status_code=500, detail=f"Import échoué: {exc}")
    return report


from demandes_offres_routes import attach_demandes_offres_routes

attach_demandes_offres_routes(
    api_router,
    db=db,
    put_object=put_object,
    local_storage_fallback=_local_storage_fallback,
    file_response_headers=_file_response_headers,
    resolve_download_filename=_resolve_download_filename,
    mime_types=MIME_TYPES,
    app_name=APP_NAME,
    root_dir=ROOT_DIR,
    load_storage_bytes=_load_storage_bytes,
)

from tech_status_routes import attach_tech_status_routes

attach_tech_status_routes(api_router, db=db, get_current_user=get_current_user)

app.include_router(api_router)

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Serve React production build (same origin as /api) when present
FRONTEND_BUILD = Path(__file__).resolve().parent.parent / "frontend" / "build"
_SPA_NO_CACHE = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
}
_SPA_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}

if FRONTEND_BUILD.exists():
    static_dir = FRONTEND_BUILD / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.middleware("http")
    async def spa_cache_control(request: Request, call_next):
        """Avoid stale index.html after deploy; fingerprint /static assets for long cache."""
        response = await call_next(request)
        path = request.url.path or ""
        if path.startswith("/api") or path == "/health":
            return response
        if path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", _SPA_IMMUTABLE["Cache-Control"])
            return response
        content_type = (response.headers.get("content-type") or "").lower()
        if "text/html" in content_type:
            response.headers["Cache-Control"] = _SPA_NO_CACHE["Cache-Control"]
            response.headers["Pragma"] = _SPA_NO_CACHE["Pragma"]
        return response

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # API and health already registered above; this catches frontend routes.
        # Confine FileResponse strictly under frontend/build (no path traversal).
        build_root = FRONTEND_BUILD.resolve()
        if full_path:
            candidate = (FRONTEND_BUILD / full_path).resolve()
            if candidate.is_file() and _is_relative_to(candidate, build_root):
                # Non-hashed root assets (manifest, favicon…) must not stick after deploy
                headers = dict(_SPA_NO_CACHE)
                return FileResponse(candidate, headers=headers)
        index = FRONTEND_BUILD / "index.html"
        if index.exists():
            return FileResponse(index, headers=dict(_SPA_NO_CACHE))
        raise HTTPException(status_code=404, detail="Frontend non déployé")
else:
    logger.warning("Frontend build introuvable à %s", FRONTEND_BUILD)

async def _migrate_couple_dossiers(user_id: Optional[str] = None):
    """
    Fusionne les dossiers des couples liés (linked_spouse_id) qui ont encore
    deux dossier_id distincts. Le dossier du membre le plus ancien est conservé.
    Retourne le nombre de paires fusionnées.
    """
    query: dict = {"linked_spouse_id": {"$exists": True, "$ne": None}}
    if user_id:
        query["user_id"] = user_id
    primaries = await db.clients.find(query, {"_id": 0}).to_list(10000)
    merged = 0
    processed: set = set()
    for primary in primaries:
        pid = primary["id"]
        sid = primary.get("linked_spouse_id")
        if not sid or pid in processed or sid in processed:
            continue
        spouse = await db.clients.find_one({"id": sid}, {"_id": 0})
        if not spouse:
            continue
        processed.add(pid)
        processed.add(sid)
        # Même dossier_id → rien à faire
        if primary.get("dossier_id") and primary.get("dossier_id") == spouse.get("dossier_id"):
            continue
        # Choisir le dossier_id canonique : celui du plus ancien (ou du primary)
        canonical_dossier_id = primary.get("dossier_id") or primary["id"]
        canonical_numero = primary.get("numero_dossier") or spouse.get("numero_dossier")
        nom = primary.get("nom") or spouse.get("nom") or ""
        canonical_label = f"Famille {nom}"
        old_dossier_ids = set()
        if spouse.get("dossier_id") and spouse["dossier_id"] != canonical_dossier_id:
            old_dossier_ids.add(spouse["dossier_id"])
        # Mettre à jour les deux fiches
        now = datetime.now(timezone.utc).isoformat()
        await db.clients.update_one(
            {"id": pid},
            {"$set": {"dossier_id": canonical_dossier_id, "dossier_label": canonical_label,
                      "numero_dossier": canonical_numero, "updated_at": now}},
        )
        await db.clients.update_one(
            {"id": sid},
            {"$set": {"dossier_id": canonical_dossier_id, "dossier_label": canonical_label,
                      "numero_dossier": canonical_numero, "updated_at": now}},
        )
        # Réattribuer les documents de l'ancien dossier_id
        for old_did in old_dossier_ids:
            await db.documents.update_many(
                {"dossier_id": old_did},
                {"$set": {"dossier_id": canonical_dossier_id}},
            )
            await db.documents.update_many(
                {"client_id": sid, "dossier_id": {"$exists": False}},
                {"$set": {"dossier_id": canonical_dossier_id}},
            )
            await db.notes.update_many(
                {"client_id": sid, "dossier_id": {"$in": [old_did, None]}},
                {"$set": {"dossier_id": canonical_dossier_id}},
            )
            await db.actions.update_many(
                {"client_id": sid, "dossier_id": {"$in": [old_did, None]}},
                {"$set": {"dossier_id": canonical_dossier_id}},
            )
        # Aussi patcher les docs du primary sans dossier_id
        await db.documents.update_many(
            {"client_id": pid, "dossier_id": {"$exists": False}},
            {"$set": {"dossier_id": canonical_dossier_id}},
        )
        merged += 1
        logger.info("Merged couple dossier: %s + %s → %s", pid, sid, canonical_dossier_id)
    return merged


async def _migrate_couple_document_sharing(user_id: Optional[str] = None) -> int:
    """
    Marque les documents existants des couples comme partagés (dossier_id + shared_dossier).
    Idempotent — les couples déjà à jour ne sont pas modifiés.
    """
    query: dict = {"linked_spouse_id": {"$exists": True, "$ne": None}}
    if user_id:
        query["user_id"] = user_id
    primaries = await db.clients.find(query, {"_id": 0}).to_list(10000)
    updated = 0
    processed: set = set()
    for primary in primaries:
        pid = primary["id"]
        sid = primary.get("linked_spouse_id")
        uid = primary.get("user_id")
        if not sid or pid in processed:
            continue
        spouse = await db.clients.find_one({"id": sid, "user_id": uid}, {"_id": 0, "id": 1})
        if not spouse:
            continue
        processed.add(pid)
        processed.add(sid)
        scope = await _dossier_scope(uid, primary)
        if not _is_couple_scope(scope):
            continue
        dossier_id = scope.get("dossier_id") or primary.get("dossier_id") or pid
        member_ids = scope.get("member_ids") or [pid, sid]
        result = await db.documents.update_many(
            {
                "user_id": uid,
                "client_id": {"$in": member_ids},
                "is_deleted": False,
                "$or": [
                    {"shared_dossier": {"$ne": True}},
                    {"dossier_id": {"$ne": dossier_id}},
                    {"dossier_id": {"$exists": False}},
                ],
            },
            {"$set": {"dossier_id": dossier_id, "shared_dossier": True}},
        )
        updated += int(getattr(result, "modified_count", 0) or 0)
    return updated


async def _migrate_simplified_statuts():
    """Migre les anciens libellés de statut vers le workflow simplifié."""
    updated = 0
    for old, new in STATUT_LEGACY_MAP.items():
        result = await db.clients.update_many(
            {"statut": old},
            {"$set": {"statut": new, "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        updated += int(getattr(result, "modified_count", 0) or 0)
    return updated


async def _ensure_mongo_indexes():
    """Index essentiels pour ~10k clients (idempotent)."""
    if os.environ.get("DATABASE_URL"):
        # Couche Postgres: pas d'API create_index Motor — contrainte via app + colonne future
        return
    specs = [
        (db.clients, [("user_id", 1), ("created_at", -1)]),
        (db.clients, [("user_id", 1), ("statut", 1)]),
        (db.clients, [("user_id", 1), ("conseiller", 1)]),
        (db.clients, [("dossier_id", 1)]),
        (db.documents, [("user_id", 1), ("client_id", 1), ("is_deleted", 1), ("created_at", -1)]),
        (db.documents, [("user_id", 1), ("dossier_id", 1), ("is_deleted", 1)]),
        (db.documents, [("storage_path", 1)]),
        (db.notes, [("user_id", 1), ("client_id", 1), ("created_at", -1)]),
        (db.demandes, [("user_id", 1), ("done", 1), ("created_at", -1)]),
        (db.actions, [("user_id", 1), ("client_id", 1), ("created_at", -1)]),
        (db.appointments, [("user_id", 1), ("date", 1)]),
        (db.tasks, [("user_id", 1), ("done", 1), ("echeance", 1)]),
        (db[SUIVI_3P_CLIENTS], [("user_id", 1), ("conseiller", 1)]),
        (db[SUIVI_3P_DOCS], [("user_id", 1), ("suivi_3p_client_id", 1), ("is_deleted", 1)]),
        (db.users, [("email", 1)]),
        (db.user_sessions, [("session_token", 1)]),
        (db.user_sessions, [("user_id", 1)]),
    ]
    for coll, keys in specs:
        try:
            await coll.create_index(keys, background=True)
        except Exception as e:
            logger.warning("Index %s %s: %s", getattr(coll, "name", coll), keys, e)

    # Index unique partiel sur identity_key (prénom+nom+DOB normalisés).
    # Si des doublons existent déjà, on retombe sur un index non-unique + garde applicative.
    try:
        await db.clients.create_index(
            [("user_id", 1), ("identity_key", 1)],
            unique=True,
            name="uniq_client_identity_key",
            partialFilterExpression={
                "identity_key": {"$type": "string", "$gt": ""},
            },
            background=True,
        )
        logger.info("Index unique identity_key OK")
    except Exception as e:
        logger.warning(
            "Index unique identity_key impossible (doublons existants ?) : %s — "
            "index non-unique + contrôle applicatif 409",
            e,
        )
        try:
            await db.clients.create_index(
                [("user_id", 1), ("identity_key", 1)],
                name="idx_client_identity_key",
                background=True,
            )
        except Exception as e2:
            logger.warning("Index identity_key fallback: %s", e2)


@app.on_event("startup")
async def startup():
    # Journal unifié : tout send_email() persiste dans email_logs
    try:
        from email_service import (
            EMAIL_LOGS_COLLECTION,
            email_log_flush_worker,
            flush_pending_email_logs,
            set_email_log_persist,
        )

        async def _persist_email_log(doc: dict) -> None:
            """Insert ou met à jour (pending → sent/error) sans doublon d'id."""
            if not doc or not doc.get("id"):
                return
            existing = await db[EMAIL_LOGS_COLLECTION].find_one({"id": doc["id"]}, {"_id": 0})
            if existing:
                merged = dict(existing)
                merged.update(doc)
                # Conserver l'horodatage de création du pending
                if existing.get("created_at"):
                    merged["created_at"] = existing["created_at"]
                await db[EMAIL_LOGS_COLLECTION].update_one({"id": doc["id"]}, {"$set": merged})
            else:
                await db[EMAIL_LOGS_COLLECTION].insert_one(doc)

        set_email_log_persist(_persist_email_log)
        flushed = await flush_pending_email_logs()
        if flushed:
            logger.info("email_logs: %s entrées en file vidées au démarrage", flushed)
        # Worker périodique : file d'attente jamais abandonnée
        asyncio.create_task(email_log_flush_worker())
    except Exception as e:
        logger.error("email_logs sink init failed: %s", e)

    try:
        logger.info(
            "startup frontend_build_exists=%s mongo_set=%s s3=%s allow_local=%s",
            FRONTEND_BUILD.exists(),
            bool(os.environ.get("MONGO_URL")),
            object_storage.configured(),
            _allow_local_storage(),
        )
    except Exception:
        pass
    try:
        created = await ensure_bootstrap_admin(db)
        if created:
            logger.info("Bootstrap admin créé (%s)", os.environ.get("ADMIN_EMAIL") or "cdemirtas@agencemendes.ch")
    except Exception as e:
        logger.error("Bootstrap admin failed: %s", e)
    try:
        backend = init_storage()
        logger.info("Storage initialized backend=%s", backend or "none")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    try:
        await _ensure_mongo_indexes()
        logger.info("Mongo indexes ensured")
    except Exception as e:
        logger.error("Mongo index creation failed: %s", e)
    # Migration chiffrement PII + documents (idempotente)
    try:
        auto = (os.environ.get("AUTO_MIGRATE_ENCRYPTION") or "true").strip().lower()
        if auto in ("1", "true", "yes", "y", "on") and encryption_configured():
            import importlib.util

            mig_path = Path(__file__).resolve().parent / "scripts" / "migrate_encrypt_sensitive_data.py"
            spec = importlib.util.spec_from_file_location("migrate_encrypt_sensitive_data", mig_path)
            mod = importlib.util.module_from_spec(spec)
            assert spec and spec.loader
            spec.loader.exec_module(mod)
            report = await mod.run(dry_run=False, force=False)
            if report.get("skipped"):
                logger.info("Encryption migration already completed")
            else:
                logger.info(
                    "Encryption migration finished ok=%s phases=%s",
                    report.get("ok"),
                    list((report.get("phases") or {}).keys()),
                )
        elif not encryption_configured():
            logger.warning(
                "DATA_ENCRYPTION_KEY / DATA_ENCRYPTION_PASSPHRASE absent — "
                "PII et documents stockés en clair (dev uniquement)"
            )
    except Exception as e:
        logger.error("Startup encryption migration failed: %s", e)
    # Migration automatique des dossiers couple au démarrage
    try:
        merged = await _migrate_couple_dossiers()
        if merged:
            logger.info("Startup migration: %d couple dossier(s) merged", merged)
    except Exception as e:
        logger.error("Startup couple migration failed: %s", e)
    try:
        shared = await _migrate_couple_document_sharing()
        if shared:
            logger.info("Startup migration: %d couple document(s) marked shared", shared)
    except Exception as e:
        logger.error("Startup couple document sharing migration failed: %s", e)
    try:
        migrated = await _migrate_simplified_statuts()
        if migrated:
            logger.info("Startup migration: %d statut(s) simplifié(s)", migrated)
    except Exception as e:
        logger.error("Startup statut migration failed: %s", e)
    try:
        gains = await _run_suivi_3p_gains_backfill_once()
        if gains.get("skipped"):
            logger.info("Startup Suivi 3P gains backfill: already done")
        else:
            logger.info(
                "Startup Suivi 3P gains backfill: updated=%s skipped=%s failed=%s clients=%s",
                gains.get("updated"),
                gains.get("skipped_no_amount"),
                gains.get("failed_read"),
                gains.get("clients_with_docs"),
            )
    except Exception as e:
        logger.error("Startup Suivi 3P gains backfill failed: %s", e)

    # Boucle notifications e-mail des rappels
    asyncio.create_task(_rappel_email_loop())

    # Rappels auto : demandes Envoyé sans Reçu après 1,5 mois
    asyncio.create_task(_demande_envoi_relance_loop())

    # Lier Offres / Suivi 3P existants à la base Clients (idempotent)
    asyncio.create_task(_clients_hub_link_once())

    # Contrôle technique quotidien (lecture seule)
    asyncio.create_task(_tech_audit_daily_loop())

    try:
        from tech_audit import (
            COL_HISTORY,
            ensure_tech_audit_indexes,
            migrate_legacy_json_if_needed,
            load_snapshot,
            run_daily_audit_background,
            audit_is_running,
        )

        await ensure_tech_audit_indexes(db)
        await migrate_legacy_json_if_needed(db)
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _TZ

        snap = await load_snapshot(db)
        today = _dt.now(_TZ("Europe/Zurich")).date().isoformat()
        row = await db[COL_HISTORY].find_one({"audit_day": today}, {"_id": 0})
        anomalies = list(snap.get("anomalies") or []) + list((row or {}).get("anomalies") or [])
        stale = (
            (snap.get("global_status") or "") == "unavailable"
            or (row or {}).get("global_status") == "unavailable"
            or any("WinError" in str(a) for a in anomalies)
            or any("configuration absente" in str(a) and "serveur" not in str(a) for a in anomalies)
            or ((row or {}).get("runtime") or {}).get("in_process")
            and not ((row or {}).get("runtime") or {}).get("production")
        )
        if stale and not audit_is_running():
            logger.info(
                "Tech audit: entrée obsolète détectée (status=%s) — relance production force=true",
                (row or {}).get("global_status") or snap.get("global_status"),
            )
            asyncio.create_task(run_daily_audit_background(db, force=True))
    except Exception as e:
        logger.error("Tech audit init failed: %s", e)

    # Postgres : créer les tables manquantes (ex. rappel_email_logs)
    if os.environ.get("DATABASE_URL"):
        try:
            from db.engine import get_engine
            from db.models import Base

            engine = get_engine()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Postgres schema ensure (create_all) ok")
        except Exception as e:
            logger.error("Postgres create_all failed: %s", e)


async def _rappel_due_datetime(rappel: dict):
    """Construit un datetime local (Europe/Zurich) pour le rappel."""
    from zoneinfo import ZoneInfo

    date_s = (rappel.get("date") or "")[:10]
    if not date_s:
        return None
    heure_s = (rappel.get("heure") or "09:00").strip()
    if not re.match(r"^\d{1,2}:\d{2}$", heure_s):
        heure_s = "09:00"
    h, m = heure_s.split(":")
    try:
        tz = ZoneInfo("Europe/Zurich")
        return datetime(int(date_s[:4]), int(date_s[5:7]), int(date_s[8:10]), int(h), int(m), tzinfo=tz)
    except Exception:
        return None


RAPPEL_RELANCE_INTERVAL_DAYS = 2


def _parse_iso_dt(value) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _last_successful_rappel_email_at(rappel: dict) -> Optional[datetime]:
    """Dernier envoi réussi (historique ou email_notified_at)."""
    hist = list(rappel.get("email_history") or [])
    for entry in reversed(hist):
        if (entry or {}).get("status") != "sent":
            continue
        dt = _parse_iso_dt((entry or {}).get("sent_at"))
        if dt:
            return dt
    return _parse_iso_dt(rappel.get("email_notified_at"))


def _rappel_email_kind_needed(rappel: dict, now: datetime) -> Optional[str]:
    """
    Retourne 'initial' | 'relance' | None.
    - Dès l'échéance, si toujours À faire / En attente → e-mail initial
    - Puis relance tous les 2 jours jusqu'à Effectué (termine)
    """
    if rappel.get("send_email") is False:
        return None
    statut = _normalize_rappel_statut(rappel.get("statut"), rappel.get("done"))
    if statut == "termine" or rappel.get("done") is True:
        return None
    # a_faire et en_attente : relances actives
    if statut not in {"a_faire", "en_attente"}:
        return None

    due = _rappel_due_datetime_sync(rappel)
    if due is None:
        return None
    # Harmoniser fuseaux pour la comparaison
    if now.tzinfo is None:
        now_cmp = now.replace(tzinfo=timezone.utc)
    else:
        now_cmp = now
    due_cmp = due if due.tzinfo else due.replace(tzinfo=timezone.utc)
    try:
        if now_cmp.astimezone(timezone.utc) < due_cmp.astimezone(timezone.utc):
            return None
    except Exception:
        if now_cmp < due_cmp:
            return None

    last = _last_successful_rappel_email_at(rappel)
    if last is None:
        return "initial"
    try:
        last_utc = last.astimezone(timezone.utc)
        now_utc = now_cmp.astimezone(timezone.utc)
    except Exception:
        last_utc, now_utc = last, now_cmp
    if now_utc >= last_utc + timedelta(days=RAPPEL_RELANCE_INTERVAL_DAYS):
        return "relance"
    return None


async def _process_rappel_emails_once():
    """
    Envoie les e-mails de rappels dus, puis des relances automatiques tous les 2 jours
    tant que le rappel reste « À faire » ou « En attente ».
    Arrêt dès que le rappel est « Effectué » (termine).
    Historise chaque envoi dans email_history.
    """
    from collections import defaultdict

    from email_service import (
        MAIL_TYPE_RAPPEL,
        format_rappels_batch,
        offres_email_to,
        public_app_url,
        send_email_async,
        smtp_configured,
    )

    if not smtp_configured():
        logger.warning("Rappel email loop: SMTP Infomaniak non configuré — aucun envoi")
        return 0

    offres_box = (offres_email_to() or "").strip().lower()

    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Europe/Zurich"))

    cursor = db.demandes.find(
        {
            "done": {"$ne": True},
            "statut": {"$nin": ["termine"]},
            "send_email": {"$ne": False},
        },
        {"_id": 0},
    )
    rappels = await cursor.to_list(8000)
    logger.info(
        "Rappel email scan: candidates=%s now=%s (Europe/Zurich)",
        len(rappels),
        now.isoformat(),
    )

    admin_rows = await db.users.find(
        {"role": ROLE_ADMIN, "active": {"$ne": False}, "receive_conseiller_rappel_copies": True},
        {"_id": 0, "email": 1, "user_id": 1},
    ).to_list(100)
    admin_cc = [
        (a.get("email") or "").strip()
        for a in admin_rows
        if (a.get("email") or "").strip()
        and (not offres_box or (a.get("email") or "").strip().lower() != offres_box)
    ]

    groups: dict = defaultdict(list)

    async def _creator_email(rappel: dict) -> Optional[str]:
        """E-mail du créateur du rappel — jamais offres@."""
        creator_id = (
            (rappel.get("created_by_user_id") or rappel.get("created_by") or "")
        ).strip()
        if creator_id:
            u = await db.users.find_one(
                {"$or": [{"user_id": creator_id}, {"account_id": creator_id}]},
                {"_id": 0, "email": 1},
            )
            email = ((u or {}).get("email") or "").strip()
            if email and "@" in email and email.lower() != offres_box:
                return email
        for key in ("created_by_email", "notify_email"):
            stored = (rappel.get(key) or "").strip()
            if stored and "@" in stored and stored.lower() != offres_box:
                return stored
        return None

    for r in rappels:
        kind = _rappel_email_kind_needed(r, now)
        if not kind:
            continue

        to_email = await _creator_email(r)
        if not to_email:
            logger.warning(
                "Rappel %s titre=%r: pas d'e-mail créateur — skip",
                r.get("id"),
                r.get("titre"),
            )
            continue
        if offres_box and to_email.lower() == offres_box:
            logger.error("Rappel %s: destinataire interdit offres@ — envoi annulé", r.get("id"))
            continue

        enriched = await _enrich_demande_with_client(dict(r))
        date_s = (r.get("date") or "")[:10]
        heure_s = (r.get("heure") or "09:00").strip() or "09:00"
        # Grouper : initial par (to, date, heure) ; relances par (to, jour) pour un digest
        if kind == "initial":
            key = (to_email.lower(), "initial", date_s, heure_s)
        else:
            key = (to_email.lower(), "relance", now.date().isoformat(), "")
        groups[key].append({**enriched, "_to_email": to_email, "_raw": r, "_kind": kind})

    sent_batches = 0
    for key, items in groups.items():
        to_email = items[0]["_to_email"]
        kind = items[0]["_kind"]
        if offres_box and to_email.lower() == offres_box:
            continue

        date_s = (items[0].get("date") or "")[:10]
        heure_s = (items[0].get("heure") or "09:00").strip() or "09:00"
        if kind == "relance":
            when_label = "encore ouverts"
        elif len(date_s) == 10:
            when_label = f"{date_s[8:10]}/{date_s[5:7]}/{date_s[:4]} à {heure_s}"
        else:
            when_label = f"{date_s} {heure_s}"

        payload_items = [
            {
                "client_name": it.get("client_name") or "Client",
                "titre": it.get("titre") or "Rappel",
                "date": it.get("date") or date_s,
                "heure": it.get("heure") or heure_s,
                "client_id": it.get("client_id"),
                "description": it.get("description"),
            }
            for it in items
        ]
        subject, body_text, body_html = format_rappels_batch(
            payload_items, when_label=when_label, is_relance=(kind == "relance")
        )

        cc_list = [a for a in admin_cc if a.lower() != to_email.lower()]

        rappel_ids = [it.get("id") for it in items if it.get("id")]
        created_bys = list({it.get("created_by") for it in items if it.get("created_by")})

        ok, err = await send_email_async(
            to_email,
            subject,
            body_text,
            body_html=body_html,
            cc=cc_list or None,
            mail_type=MAIL_TYPE_RAPPEL,
            log_meta={
                "client_id": items[0].get("client_id") if len(items) == 1 else None,
                "dossier_id": items[0].get("dossier_id") if len(items) == 1 else None,
                "ref_ids": rappel_ids,
                "ref_id": rappel_ids[0] if len(rappel_ids) == 1 else None,
                "user_id": items[0].get("user_id"),
                "created_by": created_bys[0] if len(created_bys) == 1 else None,
                "rappel_count": len(rappel_ids),
                "date": date_s,
                "heure": heure_s,
                "kind": kind,
                "client_label": (
                    items[0].get("client_name")
                    if len(items) == 1
                    else f"{len(items)} clients"
                ),
                "module": "rappels",
                "numero": items[0].get("numero") if len(items) == 1 else None,
            },
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        status = "sent" if ok else "failed"
        # Conservé pour l'historique embarqué dans chaque rappel + UI Rappels legacy
        log_doc = {
            "id": str(uuid.uuid4()),
            "user_id": items[0].get("user_id"),
            "to_email": to_email,
            "cc": cc_list,
            "subject": subject,
            "status": status,
            "error": err,
            "sent_at": now_iso,
            "rappel_ids": rappel_ids,
            "rappel_count": len(rappel_ids),
            "date": date_s,
            "heure": heure_s,
            "kind": kind,
            "created_by": created_bys[0] if len(created_bys) == 1 else None,
            "created_by_list": created_bys,
            "public_app_url": public_app_url() or None,
            "client_label": items[0].get("client_name") if len(items) == 1 else f"{len(items)} clients",
            "body_preview": (body_text or "")[:800],
        }
        try:
            await db.rappel_email_logs.insert_one(log_doc)
        except Exception:
            logger.exception("Failed to write rappel_email_logs")

        if ok:
            for it in items:
                rid = it.get("id")
                if not rid:
                    continue
                raw = it.get("_raw") or it
                hist = list(raw.get("email_history") or [])
                hist.append(
                    {
                        "sent_at": now_iso,
                        "to_email": to_email,
                        "status": "sent",
                        "kind": kind,
                        "label": "Relance automatique" if kind == "relance" else "E-mail de rappel",
                        "subject": subject,
                        "log_id": log_doc["id"],
                    }
                )
                relance_count = sum(
                    1 for h in hist if h.get("status") == "sent" and h.get("kind") == "relance"
                )
                initial_count = sum(
                    1 for h in hist if h.get("status") == "sent" and h.get("kind") != "relance"
                )
                await db.demandes.update_one(
                    {"id": rid},
                    {
                        "$set": {
                            "email_sent": True,
                            "email_notified_at": now_iso,
                            "email_notified_offsets": ["0"],
                            "email_history": hist[-40:],
                            "email_relance_count": relance_count,
                            "email_send_count": initial_count + relance_count,
                            "last_email_kind": kind,
                        }
                    },
                )
            sent_batches += 1
        else:
            for it in items:
                rid = it.get("id")
                if not rid:
                    continue
                raw = it.get("_raw") or it
                hist = list(raw.get("email_history") or [])
                hist.append(
                    {
                        "sent_at": now_iso,
                        "to_email": to_email,
                        "status": "failed",
                        "kind": kind,
                        "label": "Relance automatique (échec)" if kind == "relance" else "E-mail de rappel (échec)",
                        "error": err,
                        "subject": subject,
                        "log_id": log_doc["id"],
                    }
                )
                await db.demandes.update_one(
                    {"id": rid},
                    {"$set": {"email_history": hist[-40:]}},
                )

    return sent_batches


async def _clients_hub_link_once():
    """Migration one-shot : rattache modules → hub Clients au démarrage."""
    import asyncio
    from client_hub import link_existing_module_records

    await asyncio.sleep(25)
    try:
        report = await link_existing_module_records(db, user_id=TENANT_USER_ID)
        logger.info(
            "Clients hub link: suivi_linked=%s suivi_created=%s offres_linked=%s offres_created=%s skipped=%s/%s",
            report.get("suivi_3p_linked"),
            report.get("suivi_3p_created"),
            report.get("offres_linked"),
            report.get("offres_created"),
            report.get("suivi_3p_skipped"),
            report.get("offres_skipped"),
        )
    except Exception:
        logger.exception("Clients hub link migration failed")

    # Fiches hub créées depuis Offres/Fiscalité : hors Kanban Dossiers (sauf déjà promu)
    try:
        res = await db.clients.update_many(
            {
                "user_id": TENANT_USER_ID,
                "in_dossiers": {"$ne": True},
                "$or": [
                    {"linked_from": {"$in": ["offres", "suivi_3p"]}},
                    {"source_modules": ["offres"]},
                    {"source_modules": ["suivi_3p"]},
                ],
            },
            {"$set": {"in_dossiers": False}},
        )
        logger.info(
            "Dossiers visibility: hub stubs marked in_dossiers=False matched=%s modified=%s",
            res.matched_count,
            res.modified_count,
        )
    except Exception:
        logger.exception("Dossiers visibility migration failed")


async def _demande_envoi_relance_loop():
    """Scan initial de tous les dossiers, puis contrôle horaire des relances Envoyé/Reçu."""
    import asyncio
    from demande_envoi_relances import scan_all_clients_for_relances

    await asyncio.sleep(20)
    # Premier scan au déploiement / redémarrage : anciens + nouveaux dossiers
    try:
        from demande_envoi_relances import list_missing_sent_at, scan_all_clients_for_relances

        report = await list_missing_sent_at(db)
        logger.info(
            "Relances — historique coche Envoyé: disponible=%s | avec date=%s | sans date (non récupérables)=%s",
            report.get("history_available_for_checkbox"),
            report.get("with_sent_at"),
            report.get("missing_sent_at"),
        )
        for row in (report.get("missing") or [])[:100]:
            logger.warning(
                "Envoyé sans sent_at (non récupérable): dossier=%s client=%s source=%s label=%s",
                row.get("numero_dossier"),
                row.get("client"),
                row.get("source"),
                row.get("label"),
            )
        stats = await scan_all_clients_for_relances(db)
        logger.info(
            "Relances demandes — scan initial: scanned=%s created=%s resolved=%s",
            stats.get("scanned"),
            stats.get("created"),
            stats.get("resolved"),
        )
    except Exception:
        logger.exception("Demande envoi relance — scan initial échoué")

    while True:
        await asyncio.sleep(3600)  # puis toutes les heures
        try:
            stats = await scan_all_clients_for_relances(db)
            if stats.get("created") or stats.get("resolved"):
                logger.info(
                    "Relances demandes: scanned=%s created=%s resolved=%s",
                    stats.get("scanned"),
                    stats.get("created"),
                    stats.get("resolved"),
                )
        except Exception:
            logger.exception("Demande envoi relance loop failed")


async def _rappel_email_loop():
    import asyncio

    await asyncio.sleep(15)
    while True:
        try:
            n = await _process_rappel_emails_once()
            if n:
                logger.info("Rappel emails sent: %s", n)
        except Exception:
            logger.exception("Rappel email loop failed")
        await asyncio.sleep(60)


async def _tech_audit_daily_loop():
    """Exécute le contrôle technique une fois par jour (après TECH_AUDIT_HOUR, Europe/Zurich)."""
    import asyncio

    from tech_audit import maybe_run_scheduled_audit

    await asyncio.sleep(45)
    while True:
        try:
            result = await maybe_run_scheduled_audit(db)
            if result and result.get("started"):
                logger.info("Tech audit scheduled task started day=%s", result.get("audit_day"))
        except Exception:
            logger.exception("Tech audit daily loop failed")
        await asyncio.sleep(3600)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )