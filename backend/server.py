from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Query, Response, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import re
import requests
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from pdf_generator import (
    list_templates,
    list_demand_packs,
    generate_document_pdf,
    generate_demand_pack,
    generate_decompte_letters,
    get_template,
    extract_pension_funds_from_pdf,
    fill_pdf_bytes_with_client,
    prepare_library_form_pdf,
    render_pdf_page_png,
    CRM_FIELD_SOURCES,
    DEMAND_PACKS,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

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

# ---------------- Object Storage ----------------
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "prevoyance-crm"
storage_key = None

MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    "json": "application/json", "csv": "text/csv", "txt": "text/plain",
    "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ---------------- Constants ----------------
STATUTS = [
    "Nouveau", "Documents demandés", "Documents reçus", "Analyse en cours",
    "Rapport en préparation", "À présenter au client", "Clôturé",
]

# ---------------- Models ----------------
class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None

class ClientBase(BaseModel):
    prenom: str = ""
    nom: str = ""
    date_naissance: Optional[str] = None
    sexe: Optional[str] = None
    nationalite: Optional[str] = None
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
    agent_apporteur: Optional[str] = None
    linked_spouse_id: Optional[str] = None
    echeance_3p: Optional[str] = None
    statut: str = "Nouveau"
    priorite: str = "normale"

class ClientCreate(ClientBase):
    pass

class NoteCreate(BaseModel):
    content: str

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
    return User(
        user_id="local-dev",
        email="demo@prevoyancecrm.local",
        name="Démonstration",
        picture=None
    )

@api_router.post("/auth/session")
async def process_session(response: Response, x_session_id: Optional[str] = Header(None)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="session_id manquant")
    resp = requests.get(
        "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
        headers={"X-Session-ID": x_session_id}, timeout=30,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Session invalide")
    data = resp.json()
    email = data["email"]
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": {"name": data.get("name"), "picture": data.get("picture")}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": data.get("name"),
            "picture": data.get("picture"), "created_at": datetime.now(timezone.utc).isoformat(),
        })
    session_token = data["session_token"]
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": expires_at.isoformat(), "created_at": datetime.now(timezone.utc).isoformat(),
    })
    response.set_cookie(key="session_token", value=session_token, httponly=True, secure=True, samesite="none", path="/", max_age=7*24*60*60)
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {"user": User(**user_doc)}

@api_router.get("/auth/me")
async def auth_me(user: User = Depends(get_current_user)):
    return user

@api_router.post("/auth/logout")
async def logout(response: Response, request: Request):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}

# ---------------- Helpers ----------------
async def log_action(user_id: str, client_id: str, description: str):
    await db.actions.insert_one({
        "id": str(uuid.uuid4()), "user_id": user_id, "client_id": client_id,
        "description": description, "created_at": datetime.now(timezone.utc).isoformat(),
    })

async def next_dossier_number(user_id: str) -> str:
    count = await db.clients.count_documents({"user_id": user_id})
    return f"DOS-{count + 1:04d}"

# ---------------- Clients ----------------
@api_router.get("/clients")
async def list_clients(q: Optional[str] = None, statut: Optional[str] = None, user: User = Depends(get_current_user)):
    query = {"user_id": user.user_id}
    if statut:
        query["statut"] = statut
    clients = await db.clients.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    if q:
        ql = q.lower()
        clients = [c for c in clients if ql in (c.get("prenom", "") + " " + c.get("nom", "")).lower()
                   or ql in (c.get("email") or "").lower()
                   or ql in (c.get("telephone") or "").lower()
                   or ql in (c.get("numero_dossier") or "").lower()]
    return clients

@api_router.post("/clients")
async def create_client(payload: ClientCreate, user: User = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["user_id"] = user.user_id
    doc["numero_dossier"] = await next_dossier_number(user.user_id)
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["updated_at"] = doc["created_at"]
    await db.clients.insert_one(doc)
    await log_action(user.user_id, doc["id"], f"Dossier créé ({doc['numero_dossier']})")
    doc.pop("_id", None)
    return doc

@api_router.get("/clients/{client_id}")
async def get_client(client_id: str, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return c

@api_router.put("/clients/{client_id}")
async def update_client(client_id: str, payload: ClientCreate, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    update = payload.model_dump()
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.clients.update_one({"id": client_id}, {"$set": update})
    await log_action(user.user_id, client_id, "Fiche client mise à jour")
    return await db.clients.find_one({"id": client_id}, {"_id": 0})

@api_router.patch("/clients/{client_id}/statut")
async def update_statut(client_id: str, payload: StatutUpdate, user: User = Depends(get_current_user)):
    if payload.statut not in STATUTS:
        raise HTTPException(status_code=400, detail="Statut invalide")
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    await db.clients.update_one({"id": client_id}, {"$set": {"statut": payload.statut, "updated_at": datetime.now(timezone.utc).isoformat()}})
    await log_action(user.user_id, client_id, f"Statut changé: {c.get('statut')} → {payload.statut}")
    return await db.clients.find_one({"id": client_id}, {"_id": 0})

@api_router.patch("/clients/{client_id}/document-checklist")
async def update_document_checklist(client_id: str, payload: DocumentChecklistUpdate, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {
            "document_checklist": payload.document_checklist,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})

@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: User = Depends(get_current_user)):
    res = await db.clients.delete_one({"id": client_id, "user_id": user.user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return {"ok": True}

# ---------------- Notes ----------------
@api_router.get("/clients/{client_id}/notes")
async def list_notes(client_id: str, user: User = Depends(get_current_user)):
    return await db.notes.find({"client_id": client_id, "user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)

@api_router.post("/clients/{client_id}/notes")
async def add_note(client_id: str, payload: NoteCreate, user: User = Depends(get_current_user)):
    doc = {"id": str(uuid.uuid4()), "client_id": client_id, "user_id": user.user_id,
           "content": payload.content, "author": user.name, "created_at": datetime.now(timezone.utc).isoformat()}
    await db.notes.insert_one(doc)
    await log_action(user.user_id, client_id, "Note interne ajoutée")
    doc.pop("_id", None)
    return doc

# ---------------- Actions history ----------------
@api_router.get("/clients/{client_id}/actions")
async def list_actions(client_id: str, user: User = Depends(get_current_user)):
    return await db.actions.find({"client_id": client_id, "user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)

# ---------------- Documents ----------------
# ---------------- Documents ----------------
async def _store_pdf_bytes(user_id: str, pdf_bytes: bytes, meta: dict, client_id: str, checklist_item: Optional[str] = None) -> dict:
    path = f"{APP_NAME}/generated/{user_id}/{uuid.uuid4()}.pdf"
    try:
        result = put_object(path, pdf_bytes, "application/pdf")
        storage_path = result["path"]
        size = result.get("size", len(pdf_bytes))
    except Exception as e:
        logger.error(f"Storage upload failed for generated PDF: {e}")
        local_dir = ROOT_DIR / "generated" / user_id
        local_dir.mkdir(parents=True, exist_ok=True)
        local_name = f"{uuid.uuid4()}.pdf"
        (local_dir / local_name).write_bytes(pdf_bytes)
        storage_path = f"local://generated/{user_id}/{local_name}"
        size = len(pdf_bytes)

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "client_id": client_id,
        "storage_path": storage_path,
        "original_filename": meta["original_filename"],
        "content_type": "application/pdf",
        "size": size,
        "category": meta.get("category") or "Autre",
        "template_id": meta.get("template_id"),
        "checklist_item": checklist_item or meta.get("checklist_item"),
        "caisse_name": meta.get("caisse_name"),
        "caisse_address": meta.get("caisse_address"),
        "caisse_reference": meta.get("caisse_reference"),
        "generated": True,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/clients/{client_id}/documents")
async def list_documents(client_id: str, user: User = Depends(get_current_user)):
    return await db.documents.find({"client_id": client_id, "user_id": user.user_id, "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(1000)

@api_router.post("/clients/{client_id}/documents")
async def upload_document(
    client_id: str,
    file: UploadFile = File(...),
    category: str = Form("Autre"),
    checklist_item: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/uploads/{user.user_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    ctype = file.content_type or MIME_TYPES.get(ext, "application/octet-stream")
    try:
        result = put_object(path, data, ctype)
        storage_path = result["path"]
        size = result.get("size", len(data))
    except Exception as e:
        logger.error(f"Storage upload failed: {e}")
        local_dir = ROOT_DIR / "generated" / user.user_id
        local_dir.mkdir(parents=True, exist_ok=True)
        local_name = f"{uuid.uuid4()}.{ext}"
        (local_dir / local_name).write_bytes(data)
        storage_path = f"local://generated/{user.user_id}/{local_name}"
        size = len(data)
    doc = {
        "id": str(uuid.uuid4()), "user_id": user.user_id, "client_id": client_id,
        "storage_path": storage_path, "original_filename": file.filename,
        "content_type": ctype, "size": size,
        "category": category,
        "checklist_item": checklist_item or category,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.insert_one(doc)
    await log_action(user.user_id, client_id, f"Document ajouté: {file.filename} ({category})")
    doc.pop("_id", None)
    return doc

@api_router.get("/document-templates")
async def document_templates(user: User = Depends(get_current_user)):
    return list_templates()

@api_router.get("/demand-packs")
async def demand_packs(user: User = Depends(get_current_user)):
    return list_demand_packs()

# ---------------- Bibliothèque de formulaires ----------------
def _read_storage_bytes(storage_path: str) -> bytes:
    if storage_path.startswith("local://"):
        local_path = ROOT_DIR / storage_path.replace("local://", "", 1)
        if not local_path.exists():
            raise FileNotFoundError(storage_path)
        return local_path.read_bytes()
    data, _ctype = get_object(storage_path)
    return data


def _write_storage_bytes(storage_path: str, data: bytes, content_type: str = "application/pdf") -> str:
    if storage_path.startswith("local://"):
        local_path = ROOT_DIR / storage_path.replace("local://", "", 1)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)
        return storage_path
    try:
        result = put_object(storage_path, data, content_type)
        return result["path"]
    except Exception:
        # Fallback local si object storage indisponible
        local_name = storage_path.replace("/", "_")
        local_dir = ROOT_DIR / "form_library_fallback"
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / local_name).write_bytes(data)
        return f"local://form_library_fallback/{local_name}"


async def _prepare_and_store_library_pdf(user_id: str, form_id: str, raw_pdf: bytes, existing_path: Optional[str] = None) -> dict:
    prepared = prepare_library_form_pdf(raw_pdf)
    path = existing_path or f"{APP_NAME}/form-library/{user_id}/{form_id}.pdf"
    try:
        if path.startswith("local://"):
            storage_path = _write_storage_bytes(path, prepared["pdf_bytes"])
            size = len(prepared["pdf_bytes"])
        else:
            result = put_object(path, prepared["pdf_bytes"], "application/pdf")
            storage_path = result["path"]
            size = result.get("size", len(prepared["pdf_bytes"]))
    except Exception:
        local_dir = ROOT_DIR / "form_library" / user_id
        local_dir.mkdir(parents=True, exist_ok=True)
        local_name = f"{form_id}.pdf"
        (local_dir / local_name).write_bytes(prepared["pdf_bytes"])
        storage_path = f"local://form_library/{user_id}/{local_name}"
        size = len(prepared["pdf_bytes"])
    return {
        "storage_path": storage_path,
        "size": size,
        "widgets": prepared["widgets"],
        "page_count": prepared["page_count"],
        "field_names": prepared["field_names"],
        "field_mapping": prepared["field_mapping"],
        "field_count": len(prepared["widgets"]),
        "widgets_prepared": True,
    }


async def _ensure_library_widgets(record: dict) -> dict:
    """Prépare les widgets uniques si le formulaire n'a pas encore été uniqueifié."""
    if record.get("widgets_prepared") and record.get("widgets"):
        return record
    try:
        raw = _read_storage_bytes(record["storage_path"])
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

    updates = {
        "storage_path": meta["storage_path"],
        "size": meta["size"],
        "widgets": meta["widgets"],
        "page_count": meta["page_count"],
        "field_names": meta["field_names"],
        "field_mapping": new_mapping,
        "field_count": meta["field_count"],
        "widgets_prepared": True,
    }
    await db.form_library.update_one({"id": record["id"]}, {"$set": updates})
    record.update(updates)
    return record


async def _appointment_date_for_client(user_id: str, client_id: str) -> str:
    appt = await db.appointments.find_one(
        {"user_id": user_id, "client_id": client_id},
        {"_id": 0},
        sort=[("date", 1)],
    )
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
        {"_id": 0},
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
    return doc


@api_router.get("/form-library/{form_id}")
async def get_form_library(form_id: str, user: User = Depends(get_current_user)):
    record = await db.form_library.find_one(
        {"id": form_id, "user_id": user.user_id, "is_deleted": {"$ne": True}},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="Formulaire introuvable")
    return await _ensure_library_widgets(record)


@api_router.patch("/form-library/{form_id}")
async def update_form_library(
    form_id: str,
    payload: UpdateFormLibraryRequest,
    user: User = Depends(get_current_user),
):
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
        return record

    await db.form_library.update_one(
        {"id": form_id, "user_id": user.user_id},
        {"$set": updates},
    )
    record.update(updates)
    return record


@api_router.delete("/form-library/{form_id}")
async def delete_form_library(form_id: str, user: User = Depends(get_current_user)):
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
        data = _read_storage_bytes(record["storage_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    fname = record.get("original_filename") or f"{record.get('name', 'formulaire')}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
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
        raw = _read_storage_bytes(record["storage_path"])
        png = render_pdf_page_png(raw, page_index=page_index, dpi=144)
    except IndexError:
        raise HTTPException(status_code=404, detail="Page introuvable")
    except Exception as e:
        logger.exception("Rendu page formulaire échoué")
        raise HTTPException(status_code=500, detail=f"Aperçu impossible: {e}")
    return Response(content=png, media_type="image/png")


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
    c = await db.clients.find_one({"id": payload.client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    spouse = None
    if c.get("linked_spouse_id"):
        spouse = await db.clients.find_one(
            {"id": c["linked_spouse_id"], "user_id": user.user_id},
            {"_id": 0},
        )
    mapping = payload.field_mapping if isinstance(payload.field_mapping, dict) else record.get("field_mapping")
    try:
        raw = _read_storage_bytes(record["storage_path"])
        agent = c.get("conseiller") or user.name or ""
        date_rdv = await _appointment_date_for_client(user.user_id, c["id"])
        pdf_bytes = fill_pdf_bytes_with_client(
            raw,
            c,
            agent_name=agent,
            field_mapping=mapping if isinstance(mapping, dict) else None,
            spouse=spouse,
            extra_values={"date_rdv": date_rdv},
            widgets=record.get("widgets"),
        )
    except Exception as e:
        logger.exception("Test fill formulaire échoué")
        raise HTTPException(status_code=500, detail=f"Test impossible: {e}")
    fname = f"TEST_{record.get('name', 'formulaire')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@api_router.post("/clients/{client_id}/generate-library-form")
async def generate_library_form_for_client(
    client_id: str,
    payload: GenerateLibraryFormRequest,
    user: User = Depends(get_current_user),
):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
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

    try:
        raw = _read_storage_bytes(form["storage_path"])
        agent = c.get("conseiller") or user.name or ""
        mapping = form.get("field_mapping")
        use_mapping = mapping if isinstance(mapping, dict) else None
        date_rdv = await _appointment_date_for_client(user.user_id, client_id)
        pdf_bytes = fill_pdf_bytes_with_client(
            raw,
            c,
            agent_name=agent,
            field_mapping=use_mapping,
            spouse=spouse,
            extra_values={"date_rdv": date_rdv},
            widgets=form.get("widgets"),
        )
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
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    try:
        get_template(payload.template_id)
    except KeyError:
        raise HTTPException(status_code=400, detail="Modèle de document inconnu")
    try:
        agent = c.get("conseiller") or user.name or ""
        pdf_bytes, meta = generate_document_pdf(
            payload.template_id,
            c,
            agent_name=agent,
            custom_filename=payload.custom_filename,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Génération PDF échouée")
        raise HTTPException(status_code=500, detail=f"Génération impossible: {e}")

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
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
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
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    data = await file.read()
    path = f"{APP_NAME}/uploads/{user.user_id}/{uuid.uuid4()}.pdf"
    try:
        result = put_object(path, data, "application/pdf")
        storage_path = result["path"]
        size = result.get("size", len(data))
    except Exception:
        local_dir = ROOT_DIR / "generated" / user.user_id
        local_dir.mkdir(parents=True, exist_ok=True)
        local_name = f"{uuid.uuid4()}.pdf"
        (local_dir / local_name).write_bytes(data)
        storage_path = f"local://generated/{user.user_id}/{local_name}"
        size = len(data)
    doc = {
        "id": str(uuid.uuid4()), "user_id": user.user_id, "client_id": client_id,
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
        funds = extract_pension_funds_from_pdf(data)
    except Exception as e:
        logger.exception("OCR / parse LPP échoué")
        funds = []
        await log_action(user.user_id, client_id, f"Réponse LPP enregistrée mais analyse échouée: {e}")
        return {"document": doc, "funds": [], "fund_count": 0, "error": str(e)}

    # Persister les caisses sur le document + fiche client (survit au refresh / timeout UI)
    await db.documents.update_one(
        {"id": doc["id"]},
        {"$set": {"detected_funds": funds, "fund_count": len(funds)}},
    )
    doc["detected_funds"] = funds
    doc["fund_count"] = len(funds)
    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {
            "lpp_detected_funds": funds,
            "lpp_response_doc_id": doc["id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    logger.info("parse-lpp-response client=%s funds=%s", client_id, len(funds))
    await log_action(user.user_id, client_id, f"Réponse LPP analysée: {len(funds)} caisse(s) détectée(s)")
    return {"document": doc, "funds": funds, "fund_count": len(funds)}

@api_router.post("/clients/{client_id}/reparse-lpp-response/{doc_id}")
async def reparse_lpp_response(client_id: str, doc_id: str, user: User = Depends(get_current_user)):
    """Relance l'OCR sur une réponse LPP déjà téléversée."""
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    doc = await db.documents.find_one(
        {"id": doc_id, "client_id": client_id, "user_id": user.user_id, "is_deleted": False},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")

    storage_path = doc.get("storage_path") or ""
    try:
        if storage_path.startswith("local://"):
            local_path = ROOT_DIR / storage_path.replace("local://", "", 1)
            data = local_path.read_bytes()
        else:
            data, _ctype = get_object(storage_path)
    except Exception as e:
        logger.exception("Lecture PDF pour reparse échouée")
        raise HTTPException(status_code=500, detail=f"Impossible de relire le PDF: {e}")

    funds = extract_pension_funds_from_pdf(data)
    await db.documents.update_one(
        {"id": doc_id},
        {"$set": {"detected_funds": funds, "fund_count": len(funds)}},
    )
    await db.clients.update_one(
        {"id": client_id},
        {"$set": {"lpp_detected_funds": funds, "lpp_response_doc_id": doc_id}},
    )
    doc["detected_funds"] = funds
    doc["fund_count"] = len(funds)
    await log_action(user.user_id, client_id, f"Réanalyse LPP: {len(funds)} caisse(s)")
    return {"document": doc, "funds": funds, "fund_count": len(funds)}

@api_router.post("/clients/{client_id}/generate-decompte-letters")
async def generate_decompte_for_funds(client_id: str, payload: GenerateDecompteRequest, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    if not payload.funds:
        raise HTTPException(status_code=400, detail="Sélectionnez au moins une caisse")
    try:
        agent = c.get("conseiller") or user.name or ""
        generated = generate_decompte_letters(c, payload.funds, agent_name=agent)
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
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    if c.get("linked_spouse_id"):
        existing = await db.clients.find_one({"id": c["linked_spouse_id"], "user_id": user.user_id}, {"_id": 0})
        if existing:
            return existing

    spouse_prenom = payload.prenom or (c.get("conjoint") or "").split(" ")[0]
    spouse_nom = payload.nom or " ".join((c.get("conjoint") or "").split(" ")[1:]) or c.get("nom", "")
    if not spouse_prenom or not spouse_nom:
        raise HTTPException(status_code=400, detail="Prénom et nom du conjoint requis")

    count = await db.clients.count_documents({"user_id": user.user_id})
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
        "numero_dossier": f"DOS-{count + 1:04d}",
        "document_checklist": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.clients.insert_one(spouse)
    await db.clients.update_one(
        {"id": client_id},
        {"$set": {
            "linked_spouse_id": spouse["id"],
            "conjoint": f"{spouse_prenom} {spouse_nom}".strip(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    await log_action(user.user_id, client_id, f"Fiche conjoint créée: {spouse_prenom} {spouse_nom}")
    spouse.pop("_id", None)
    return spouse

@api_router.patch("/clients/{client_id}/echeance-3p")
async def update_echeance_3p(client_id: str, payload: Echeance3PUpdate, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {"echeance_3p": payload.echeance_3p, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    # Create/update reminder task if within 1 year
    if payload.echeance_3p:
        try:
            due = datetime.fromisoformat(payload.echeance_3p[:10])
            days_left = (due - datetime.now()).days
            if 0 <= days_left <= 365:
                existing = await db.tasks.find_one({
                    "user_id": user.user_id,
                    "client_id": client_id,
                    "type": "echeance_3p",
                    "done": False,
                }, {"_id": 0})
                titre = f"Échéance 3e pilier — {c.get('prenom', '')} {c.get('nom', '')}".strip()
                if existing:
                    await db.tasks.update_one({"id": existing["id"]}, {"$set": {"echeance": payload.echeance_3p, "titre": titre}})
                else:
                    await db.tasks.insert_one({
                        "id": str(uuid.uuid4()),
                        "user_id": user.user_id,
                        "client_id": client_id,
                        "titre": titre,
                        "echeance": payload.echeance_3p,
                        "priorite": "haute",
                        "type": "echeance_3p",
                        "done": False,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
        except ValueError:
            pass
    await log_action(user.user_id, client_id, f"Échéance 3P mise à jour: {payload.echeance_3p or '—'}")
    return await db.clients.find_one({"id": client_id}, {"_id": 0})

@api_router.get("/echeances-3p")
async def list_echeances_3p(user: User = Depends(get_current_user)):
    clients = await db.clients.find(
        {"user_id": user.user_id, "echeance_3p": {"$ne": None, "$exists": True}},
        {"_id": 0, "id": 1, "prenom": 1, "nom": 1, "echeance_3p": 1, "numero_dossier": 1},
    ).to_list(1000)
    now = datetime.now()
    items = []
    for c in clients:
        try:
            due = datetime.fromisoformat(str(c["echeance_3p"])[:10])
        except Exception:
            continue
        days_left = (due - now).days
        items.append({
            **c,
            "days_left": days_left,
            "alert": 0 <= days_left <= 365,
        })
    items.sort(key=lambda x: x.get("days_left", 99999))
    return items

@api_router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, user: User = Depends(get_current_user)):
    record = await db.documents.find_one({"id": doc_id, "user_id": user.user_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    storage_path = record["storage_path"]
    if storage_path.startswith("local://"):
        local_path = ROOT_DIR / storage_path.replace("local://", "", 1)
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="Fichier introuvable")
        data = local_path.read_bytes()
        content_type = record.get("content_type", "application/pdf")
    else:
        data, content_type = get_object(storage_path)
    return Response(
        content=data,
        media_type=record.get("content_type", content_type),
        headers={"Content-Disposition": f'inline; filename="{record["original_filename"]}"'},
    )

@api_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: User = Depends(get_current_user)):
    res = await db.documents.update_one({"id": doc_id, "user_id": user.user_id}, {"$set": {"is_deleted": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return {"ok": True}

# ---------------- Appointments ----------------
@api_router.get("/appointments")
async def list_appointments(client_id: Optional[str] = None, user: User = Depends(get_current_user)):
    query = {"user_id": user.user_id}
    if client_id:
        query["client_id"] = client_id
    return await db.appointments.find(query, {"_id": 0}).sort("date", 1).to_list(1000)

@api_router.post("/appointments")
async def create_appointment(payload: AppointmentCreate, user: User = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["user_id"] = user.user_id
    doc["done"] = False
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    if doc.get("client_id"):
        c = await db.clients.find_one({"id": doc["client_id"], "user_id": user.user_id}, {"_id": 0})
        doc["client_name"] = f"{c.get('prenom','')} {c.get('nom','')}".strip() if c else None
        await log_action(user.user_id, doc["client_id"], f"Rendez-vous planifié: {doc['titre']}")
    await db.appointments.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.patch("/appointments/{appt_id}")
async def toggle_appointment(appt_id: str, user: User = Depends(get_current_user)):
    a = await db.appointments.find_one({"id": appt_id, "user_id": user.user_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Rendez-vous introuvable")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"done": not a.get("done", False)}})
    return await db.appointments.find_one({"id": appt_id}, {"_id": 0})

@api_router.delete("/appointments/{appt_id}")
async def delete_appointment(appt_id: str, user: User = Depends(get_current_user)):
    await db.appointments.delete_one({"id": appt_id, "user_id": user.user_id})
    return {"ok": True}

# ---------------- Tasks ----------------
@api_router.get("/tasks")
async def list_tasks(client_id: Optional[str] = None, user: User = Depends(get_current_user)):
    query = {"user_id": user.user_id}
    if client_id:
        query["client_id"] = client_id
    return await db.tasks.find(query, {"_id": 0}).sort("echeance", 1).to_list(1000)

@api_router.post("/tasks")
async def create_task(payload: TaskCreate, user: User = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["user_id"] = user.user_id
    doc["done"] = False
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.tasks.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.patch("/tasks/{task_id}")
async def toggle_task(task_id: str, user: User = Depends(get_current_user)):
    t = await db.tasks.find_one({"id": task_id, "user_id": user.user_id}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    await db.tasks.update_one({"id": task_id}, {"$set": {"done": not t.get("done", False)}})
    return await db.tasks.find_one({"id": task_id}, {"_id": 0})

@api_router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, user: User = Depends(get_current_user)):
    await db.tasks.delete_one({"id": task_id, "user_id": user.user_id})
    return {"ok": True}

# ---------------- Dashboard ----------------
@api_router.get("/dashboard/stats")
async def dashboard_stats(user: User = Depends(get_current_user)):
    clients = await db.clients.find({"user_id": user.user_id}, {"_id": 0}).to_list(5000)
    by_statut = {s: 0 for s in STATUTS}
    for c in clients:
        st = c.get("statut", "Nouveau")
        if st in by_statut:
            by_statut[st] += 1
    urgent = sum(1 for c in clients if c.get("priorite") == "urgent" and c.get("statut") != "Clôturé")

    today = datetime.now(timezone.utc).date().isoformat()
    appts = await db.appointments.find({"user_id": user.user_id}, {"_id": 0}).to_list(5000)
    today_appts = [a for a in appts if (a.get("date") or "").startswith(today)]
    today_appts.sort(key=lambda a: a.get("date", ""))

    # monthly stats last 6 months
    now = datetime.now(timezone.utc)
    monthly = []
    for i in range(5, -1, -1):
        ref = now - timedelta(days=30 * i)
        key = ref.strftime("%Y-%m")
        label = ref.strftime("%b")
        dossiers_count = sum(1 for c in clients if (c.get("created_at") or "").startswith(key))
        appt_count = sum(1 for a in appts if (a.get("date") or "").startswith(key))
        report_count = sum(1 for c in clients if c.get("statut") in ["À présenter au client", "Clôturé"] and (c.get("updated_at") or "").startswith(key))
        monthly.append({"mois": label, "dossiers": dossiers_count, "rendezvous": appt_count, "rapports": report_count})

    tasks = await db.tasks.find({"user_id": user.user_id, "done": False}, {"_id": 0}).to_list(1000)

    return {
        "by_statut": by_statut,
        "total": len(clients),
        "urgent": urgent,
        "nouveaux": by_statut.get("Nouveau", 0),
        "en_attente_docs": by_statut.get("Documents demandés", 0),
        "en_analyse": by_statut.get("Analyse en cours", 0),
        "a_presenter": by_statut.get("À présenter au client", 0),
        "termines": by_statut.get("Clôturé", 0),
        "today_appointments": today_appts,
        "monthly": monthly,
        "pending_tasks": len(tasks),
        "tasks": tasks,
        "statuts": STATUTS,
    }

@api_router.get("/")
async def root():
    return {"message": "Prévoyance CRM API"}

app.include_router(api_router)

cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve React production build (same origin as /api) when present
FRONTEND_BUILD = Path(__file__).resolve().parent.parent / "frontend" / "build"
if FRONTEND_BUILD.exists():
    static_dir = FRONTEND_BUILD / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # API and health already registered above; this catches frontend routes
        candidate = FRONTEND_BUILD / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_BUILD / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend non déployé")
else:
    logger.warning("Frontend build introuvable à %s", FRONTEND_BUILD)

@app.on_event("startup")
async def startup():
    # #region agent log
    try:
        logger.info("DEBUG_STARTUP frontend_build_exists=%s mongo_set=%s", FRONTEND_BUILD.exists(), bool(os.environ.get("MONGO_URL")))
    except Exception:
        pass
    # #endregion
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")

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