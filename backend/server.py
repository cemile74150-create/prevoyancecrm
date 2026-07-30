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
    extract_3p_expiry_from_pdf,
    extract_3p_contracts_from_pdf,
    fill_pdf_bytes_with_client,
    prepare_library_form_pdf,
    render_pdf_page_png,
    repair_library_pdf_bytes,
    CRM_FIELD_SOURCES,
    DEMAND_PACKS,
    DOCUMENT_TYPES_3P,
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
    dossier_id: Optional[str] = None
    dossier_label: Optional[str] = None
    echeance_3p: Optional[str] = None
    # Multi-contrats 3e pilier : une ligne par contrat (compagnie + n° + échéance)
    echeances_3p: Optional[List[dict]] = None
    statut: str = "Nouveau"
    priorite: str = "normale"

class ClientCreate(ClientBase):
    pass

class NoteCreate(BaseModel):
    content: str

class DemandeCreate(BaseModel):
    titre: str
    description: Optional[str] = None
    priorite: Optional[str] = "normale"

class DemandeUpdate(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None
    priorite: Optional[str] = None
    done: Optional[bool] = None

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
    echeance_3p: Optional[str] = None
    company: Optional[str] = None
    policy_number: Optional[str] = None
    document_type: Optional[str] = None

class Echeance3PLineCreate(BaseModel):
    company: Optional[str] = None
    policy_number: Optional[str] = None
    echeance_3p: Optional[str] = None
    document_type: Optional[str] = None

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

async def _dossier_scope(user_id: str, client: dict) -> dict:
    """Retourne dossier_id + ids des membres du dossier familial."""
    dossier_id = client.get("dossier_id") or client["id"]
    members = await db.clients.find(
        {"user_id": user_id, "dossier_id": dossier_id}, {"id": 1, "linked_spouse_id": 1}
    ).to_list(100)
    member_ids = [m["id"] for m in members]
    if not member_ids:
        member_ids = [client["id"]]

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
        {"user_id": user_id, "linked_spouse_id": client["id"]}, {"id": 1}
    ).to_list(20)
    member_ids.extend(m["id"] for m in reverse)

    return {"dossier_id": dossier_id, "member_ids": list(dict.fromkeys(member_ids))}

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

def _lpp_tracking_from_funds(funds: List[dict], existing: Optional[List[dict]] = None) -> List[dict]:
    previous = {
        str(item.get("name") or "").strip().casefold(): item
        for item in (existing or []) if item.get("name")
    }
    tracking = []
    for fund in funds:
        name = str(fund.get("name") or fund.get("nom") or "").strip()
        if not name:
            continue
        prior = previous.get(name.casefold(), {})
        tracking.append({
            "id": prior.get("id") or str(uuid.uuid4()),
            "name": name,
            "address": fund.get("address") or fund.get("adresse") or "",
            "reference": fund.get("reference") or fund.get("ref") or "",
            "sent": bool(prior.get("sent")),
            "received": bool(prior.get("received")),
        })
    return tracking

# ---------------- Clients ----------------
@api_router.get("/clients")
async def list_clients(q: Optional[str] = None, statut: Optional[str] = None, user: User = Depends(get_current_user)):
    query = {"user_id": user.user_id}
    wanted = normalize_statut(statut) if statut else None
    # Inclure aussi les anciens libellés si le filtre correspond à un statut migré.
    if wanted:
        legacy_aliases = [old for old, new in STATUT_LEGACY_MAP.items() if new == wanted]
        query["statut"] = {"$in": [wanted, *legacy_aliases]} if legacy_aliases else wanted
    clients = await db.clients.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for c in clients:
        c["statut"] = normalize_statut(c.get("statut"))
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
    doc["statut"] = normalize_statut(doc.get("statut"))
    doc["numero_dossier"] = await next_dossier_number(user.user_id)
    doc["dossier_id"] = doc["id"]
    etat = (doc.get("etat_civil") or "").casefold()
    married = "mari" in etat or "partenariat" in etat
    doc["dossier_label"] = f"Famille {doc['nom']}" if married else f"{doc['prenom']} {doc['nom']}".strip()
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
    try:
        # Nettoyage "strict" côté lecture : évite que d'anciennes lignes erronées restent visibles
        # si l'utilisateur n'a pas re-upload/supprimé un document depuis.
        lines = c.get("echeances_3p")
        if isinstance(lines, list) and len(lines) > 0:
            await _reconcile_echeances_3p_lines(user.user_id, client_id)
            c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    except Exception:
        logger.exception("Reconciliation echeances_3p échouée (get_client)")
    if c:
        c["statut"] = normalize_statut(c.get("statut"))
    return c

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
        "members": members,
        "documents": docs,
        "notes": notes,
    }

@api_router.put("/clients/{client_id}")
async def update_client(client_id: str, payload: ClientCreate, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    update = payload.model_dump()
    update["statut"] = normalize_statut(update.get("statut"))
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.clients.update_one({"id": client_id}, {"$set": update})
    await log_action(user.user_id, client_id, "Fiche client mise à jour")
    return await db.clients.find_one({"id": client_id}, {"_id": 0})

@api_router.patch("/clients/{client_id}/statut")
async def update_statut(client_id: str, payload: StatutUpdate, user: User = Depends(get_current_user)):
    statut = normalize_statut(payload.statut)
    if statut not in STATUTS:
        raise HTTPException(status_code=400, detail="Statut invalide")
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")

    # Statut commun au dossier familial : tous les membres avancent ensemble.
    scope = await _dossier_scope(user.user_id, c)
    member_ids = scope.get("member_ids") or [client_id]
    now_iso = datetime.now(timezone.utc).isoformat()
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

@api_router.patch("/clients/{client_id}/lpp-caisse-tracking")
async def update_lpp_caisse_tracking(client_id: str, payload: LppCaisseTrackingUpdate, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    tracking = [
        {**entry, "id": entry.get("id") or str(uuid.uuid4()), "sent": bool(entry.get("sent")), "received": bool(entry.get("received"))}
        for entry in payload.lpp_caisse_tracking if entry.get("name")
    ]
    await db.clients.update_one({"id": client_id, "user_id": user.user_id}, {"$set": {
        "lpp_caisse_tracking": tracking, "updated_at": datetime.now(timezone.utc).isoformat(),
    }})
    return {"lpp_caisse_tracking": tracking}

@api_router.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
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
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
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
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
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

# ---------------- Demandes à faire (to-do conseiller) ----------------
def _normalize_demande_priorite(value: Optional[str]) -> str:
    raw = (value or "normale").strip().lower()
    if raw in {"haute", "high", "urgent", "urgente"}:
        return "haute"
    return "normale"


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
    return demande


@api_router.get("/demandes")
async def list_all_demandes(
    done: Optional[bool] = Query(False),
    user: User = Depends(get_current_user),
):
    """Liste globale des demandes. Par défaut : non traitées uniquement."""
    query: dict = {"user_id": user.user_id}
    if done is not None:
        query["done"] = bool(done)
    demandes = await db.demandes.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    # Tri stable : plus récentes d'abord, puis haute priorité en tête
    demandes.sort(key=lambda d: d.get("created_at") or "", reverse=True)
    demandes.sort(key=lambda d: 0 if d.get("priorite") == "haute" else 1)
    enriched = []
    for d in demandes:
        enriched.append(await _enrich_demande_with_client(d))
    return enriched


@api_router.get("/clients/{client_id}/demandes")
async def list_client_demandes(client_id: str, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    scope = await _dossier_scope(user.user_id, c)
    query = {
        "user_id": user.user_id,
        "$or": [
            {"client_id": {"$in": scope["member_ids"]}},
            {"dossier_id": scope["dossier_id"]},
        ],
    }
    # Ouvertes d'abord, puis traitées (historique)
    demandes = await db.demandes.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    open_ones = [d for d in demandes if not d.get("done")]
    done_ones = [d for d in demandes if d.get("done")]
    open_ones.sort(key=lambda d: (0 if d.get("priorite") == "haute" else 1, d.get("created_at") or ""))
    return open_ones + done_ones


@api_router.post("/clients/{client_id}/demandes")
async def create_demande(client_id: str, payload: DemandeCreate, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    titre = (payload.titre or "").strip()
    if not titre:
        raise HTTPException(status_code=400, detail="Titre obligatoire")
    scope = await _dossier_scope(user.user_id, c)
    now_iso = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "client_id": client_id,
        "dossier_id": scope["dossier_id"],
        "titre": titre,
        "description": (payload.description or "").strip() or None,
        "priorite": _normalize_demande_priorite(payload.priorite),
        "done": False,
        "author": getattr(user, "name", None) or None,
        "created_by": getattr(user, "user_id", None) or None,
        "created_at": now_iso,
        "done_at": None,
        "done_by": None,
        "done_by_name": None,
    }
    await db.demandes.insert_one(doc)
    await log_action(user.user_id, client_id, f"Demande créée: {titre}", dossier_id=scope["dossier_id"])
    doc.pop("_id", None)
    return doc


@api_router.patch("/demandes/{demande_id}")
async def update_demande(demande_id: str, payload: DemandeUpdate, user: User = Depends(get_current_user)):
    d = await db.demandes.find_one({"id": demande_id, "user_id": user.user_id}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Demande introuvable")

    updates: dict = {}
    if payload.titre is not None:
        titre = payload.titre.strip()
        if not titre:
            raise HTTPException(status_code=400, detail="Titre obligatoire")
        updates["titre"] = titre
    if payload.description is not None:
        updates["description"] = payload.description.strip() or None
    if payload.priorite is not None:
        updates["priorite"] = _normalize_demande_priorite(payload.priorite)

    if payload.done is not None:
        new_done = bool(payload.done)
        was_done = bool(d.get("done"))
        updates["done"] = new_done
        if new_done and not was_done:
            updates["done_at"] = datetime.now(timezone.utc).isoformat()
            updates["done_by"] = getattr(user, "user_id", None) or None
            updates["done_by_name"] = getattr(user, "name", None) or None
        elif not new_done and was_done:
            updates["done_at"] = None
            updates["done_by"] = None
            updates["done_by_name"] = None

    if updates:
        await db.demandes.update_one({"id": demande_id, "user_id": user.user_id}, {"$set": updates})

    updated = await db.demandes.find_one({"id": demande_id}, {"_id": 0})
    return await _enrich_demande_with_client(updated)


@api_router.delete("/demandes/{demande_id}")
async def delete_demande(demande_id: str, user: User = Depends(get_current_user)):
    res = await db.demandes.delete_one({"id": demande_id, "user_id": user.user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Demande introuvable")
    return {"ok": True}

# ---------------- Actions history ----------------
@api_router.get("/clients/{client_id}/actions")
async def list_actions(client_id: str, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
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

    client = await db.clients.find_one({"id": client_id, "user_id": user_id}, {"_id": 0, "dossier_id": 1})
    dossier_id = (client or {}).get("dossier_id") or meta.get("dossier_id") or client_id

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "client_id": client_id,
        "dossier_id": dossier_id,
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
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    scope = await _dossier_scope(user.user_id, c)
    query = {
        "user_id": user.user_id,
        "is_deleted": False,
        "$or": [
            {"client_id": {"$in": scope["member_ids"]}},
            {"dossier_id": scope["dossier_id"]},
        ],
    }
    return await db.documents.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)


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
    docs = await db.documents.find(
        {
            "user_id": user_id,
            "client_id": client_id,
            "is_deleted": False,
            "$or": [
                {"checklist_item": {"$in": three_p_labels}},
                {"category": {"$in": three_p_labels}},
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
        "dossier_id": c.get("dossier_id"),
        "storage_path": storage_path, "original_filename": file.filename,
        "content_type": ctype, "size": size,
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
    is_3p_police = checklist_item in {"Police 3e pilier", "Police de 3e pilier"} or category in {"Police 3e pilier", "Police de 3e pilier"}
    if is_3p_police and (ext == "pdf" or ctype == "application/pdf"):
        try:
            detected_echeances = extract_3p_contracts_from_pdf(data) or []
        except Exception:
            logger.exception("Extraction contrats 3P échouée")
            detected_echeances = []

        # Règle stricte : 1 document PDF = 1 ligne (prendre le meilleur candidat uniquement).
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = detected_echeances[0] if detected_echeances else {}
        new_line = _echeance_line_from_extraction(entry, doc["id"], now_iso)
        new_lines = [new_line]

        existing_lines = c.get("echeances_3p") or []
        merged_lines = _merge_echeances_3p_lines(existing_lines, new_lines)

        detected_dates = [l.get("echeance_3p") for l in merged_lines if l.get("echeance_3p")]
        if detected_dates:
            detected_first_echeance = min(detected_dates)

        await db.clients.update_one(
            {"id": client_id, "user_id": user.user_id},
            {"$set": {
                "echeances_3p": merged_lines,
                "echeance_3p": detected_first_echeance,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )

        await _upsert_echeance_3p_line_reminder(user.user_id, c, new_line)

        await db.documents.update_one(
            {"id": doc["id"]},
            {"$set": {
                "extracted_echeances_3p": detected_echeances[:1] if detected_echeances else [entry],
                "extracted_echeance_3p": new_line.get("echeance_3p"),
                "extracted_document_type": new_line.get("document_type"),
                "extracted_expiry_engine": "v2-robust",
            }},
        )
        doc["extracted_echeance_3p"] = new_line.get("echeance_3p")
        doc["document_type"] = new_line.get("document_type")
        await _reconcile_echeances_3p_lines(user.user_id, client_id)
    await log_action(user.user_id, client_id, f"Document ajouté: {file.filename} ({category})")
    doc.pop("_id", None)
    doc["echeance_3p"] = detected_first_echeance
    doc["echeance_3p_detected"] = bool(detected_first_echeance)
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
        "checkboxes_scrubbed": True,
    }


async def _ensure_library_widgets(record: dict) -> dict:
    """Prépare les widgets uniques si besoin, et nettoie les ronds dans les cases."""
    if record.get("widgets_prepared") and record.get("widgets"):
        # Nettoyer les PDF déjà préparés (artefacts cercles sur cases)
        if not record.get("checkboxes_scrubbed"):
            try:
                raw = _read_storage_bytes(record["storage_path"])
                cleaned = repair_library_pdf_bytes(raw)
                storage_path = _write_storage_bytes(record["storage_path"], cleaned)
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
    tracking = _lpp_tracking_from_funds(funds, c.get("lpp_caisse_tracking"))
    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {
            "lpp_detected_funds": funds,
            "lpp_caisse_tracking": tracking,
            "lpp_response_doc_id": doc["id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    logger.info("parse-lpp-response client=%s funds=%s", client_id, len(funds))
    await log_action(user.user_id, client_id, f"Réponse LPP analysée: {len(funds)} caisse(s) détectée(s)")
    return {"document": doc, "funds": funds, "fund_count": len(funds), "lpp_caisse_tracking": tracking}

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
    tracking = _lpp_tracking_from_funds(funds, c.get("lpp_caisse_tracking"))
    await db.clients.update_one(
        {"id": client_id},
        {"$set": {
            "lpp_detected_funds": funds, "lpp_response_doc_id": doc_id,
            "lpp_caisse_tracking": tracking, "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    doc["detected_funds"] = funds
    doc["fund_count"] = len(funds)
    await log_action(user.user_id, client_id, f"Réanalyse LPP: {len(funds)} caisse(s)")
    return {"document": doc, "funds": funds, "fund_count": len(funds), "lpp_caisse_tracking": tracking}

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
            "dossier_id": dossier_id,
            "dossier_label": dossier_label,
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
    await _upsert_echeance_3p_reminder(user.user_id, c, payload.echeance_3p)
    await log_action(user.user_id, client_id, f"Échéance 3P mise à jour: {payload.echeance_3p or '—'}")
    return await db.clients.find_one({"id": client_id}, {"_id": 0})

@api_router.post("/clients/{client_id}/echeances-3p")
async def create_echeance_3p_line(client_id: str, payload: Echeance3PLineCreate, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")

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
    return await db.clients.find_one({"id": client_id}, {"_id": 0})


@api_router.patch("/clients/{client_id}/echeances-3p/{line_id}")
async def update_echeance_3p_line(client_id: str, line_id: str, payload: Echeance3PLineUpdate, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")

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
    old_date = target.get("echeance_3p")
    old_company = target.get("company")
    old_policy_number = target.get("policy_number")

    new_date = payload.echeance_3p or None

    # Conversion : '' -> None (clear)
    new_company = payload.company.strip() if isinstance(payload.company, str) and payload.company.strip() else None
    new_policy_number = payload.policy_number.strip() if isinstance(payload.policy_number, str) and payload.policy_number.strip() else None

    target["company"] = new_company
    target["policy_number"] = new_policy_number
    target["echeance_3p"] = new_date
    if payload.document_type is not None:
        target["document_type"] = _normalize_document_type_3p(payload.document_type)
    elif not target.get("document_type"):
        target["document_type"] = "Autre document"
    target["detected"] = bool(new_date) if target.get("manual") else bool(new_date)
    target["updated_at"] = now_iso

    detected_dates = [l.get("echeance_3p") for l in lines if isinstance(l, dict) and l.get("echeance_3p")]
    new_first = min(detected_dates) if detected_dates else None

    await db.clients.update_one(
        {"id": client_id, "user_id": user.user_id},
        {"$set": {"echeances_3p": lines, "echeance_3p": new_first, "updated_at": now_iso}},
    )

    # Recalcul des rappels : fermer l'ancien rappel (si présent) puis recréer (si < 1 an)
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
    return await db.clients.find_one({"id": client_id}, {"_id": 0})


@api_router.delete("/clients/{client_id}/echeances-3p/{line_id}")
async def delete_echeance_3p_line(client_id: str, line_id: str, user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")

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
    return await db.clients.find_one({"id": client_id}, {"_id": 0})


@api_router.get("/echeances-3p")
async def list_echeances_3p(user: User = Depends(get_current_user)):
    clients = await db.clients.find(
        {
            "user_id": user.user_id,
            "$or": [
                {"echeances_3p": {"$exists": True}},
                {"echeance_3p": {"$ne": None, "$exists": True}},
            ],
        },
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
    record = await db.documents.find_one(
        {"id": doc_id, "user_id": user.user_id, "is_deleted": False},
        {"_id": 0},
    )
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")

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

    removed_lines = [l for l in lines if isinstance(l, dict) and l.get("source_doc_id") == doc_id]
    if not removed_lines:
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
    by_conseiller: dict = {}  # name -> { total, by_statut }

    dossier_statut_map = {}
    dossier_created_map = {}
    dossier_updated_map = {}

    def pick_dossier_conseiller(members: list) -> str:
        names = [(m.get("conseiller") or "").strip() for m in members]
        names = [n for n in names if n]
        if not names:
            return "Non attribué"
        counts = {}
        for n in names:
            counts[n] = counts.get(n, 0) + 1
        return sorted(counts.items(), key=lambda x: (-x[1], x[0].lower()))[0][0]

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
        entry = by_conseiller.setdefault(
            cons,
            {"name": cons, "total": 0, "by_statut": {s: 0 for s in STATUTS}},
        )
        entry["total"] += 1
        if dossier_statut in entry["by_statut"]:
            entry["by_statut"][dossier_statut] += 1

    conseiller_list = sorted(
        by_conseiller.values(),
        key=lambda x: (x["name"] == "Non attribué", -x["total"], x["name"].lower()),
    )
    today = datetime.now(timezone.utc).date().isoformat()
    appts = await db.appointments.find({"user_id": user.user_id}, {"_id": 0}).to_list(5000)
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

    tasks = await db.tasks.find({"user_id": user.user_id, "done": False}, {"_id": 0}).to_list(1000)

    return {
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
        "by_conseiller": conseiller_list,
    }

@api_router.get("/")
async def root():
    return {"message": "Prévoyance CRM API"}

@api_router.post("/admin/merge-couple-dossiers")
async def merge_couple_dossiers(user: User = Depends(get_current_user)):
    """Migration manuelle : fusionne tous les dossiers couple de l'utilisateur."""
    merged = await _migrate_couple_dossiers(user_id=user.user_id)
    return {"merged": merged, "message": f"{merged} couple(s) fusionné(s)"}

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


@app.on_event("startup")
async def startup():
    try:
        logger.info("startup frontend_build_exists=%s mongo_set=%s", FRONTEND_BUILD.exists(), bool(os.environ.get("MONGO_URL")))
    except Exception:
        pass
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    # Migration automatique des dossiers couple au démarrage
    try:
        merged = await _migrate_couple_dossiers()
        if merged:
            logger.info("Startup migration: %d couple dossier(s) merged", merged)
    except Exception as e:
        logger.error("Startup couple migration failed: %s", e)
    try:
        migrated = await _migrate_simplified_statuts()
        if migrated:
            logger.info("Startup migration: %d statut(s) simplifié(s)", migrated)
    except Exception as e:
        logger.error("Startup statut migration failed: %s", e)

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