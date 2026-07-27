from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Query, Response, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import requests
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta

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
    statut: str = "Nouveau"
    priorite: str = "normale"

class ClientCreate(ClientBase):
    pass

class NoteCreate(BaseModel):
    content: str

class StatutUpdate(BaseModel):
    statut: str

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
@api_router.get("/clients/{client_id}/documents")
async def list_documents(client_id: str, user: User = Depends(get_current_user)):
    return await db.documents.find({"client_id": client_id, "user_id": user.user_id, "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(1000)

@api_router.post("/clients/{client_id}/documents")
async def upload_document(client_id: str, file: UploadFile = File(...), category: str = Form("Autre"), user: User = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client introuvable")
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/uploads/{user.user_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    ctype = file.content_type or MIME_TYPES.get(ext, "application/octet-stream")
    result = put_object(path, data, ctype)
    doc = {
        "id": str(uuid.uuid4()), "user_id": user.user_id, "client_id": client_id,
        "storage_path": result["path"], "original_filename": file.filename,
        "content_type": ctype, "size": result.get("size", len(data)),
        "category": category, "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.insert_one(doc)
    await log_action(user.user_id, client_id, f"Document ajouté: {file.filename} ({category})")
    doc.pop("_id", None)
    return doc

@api_router.get("/documents/{doc_id}/download")
async def download_document(doc_id: str, authorization: Optional[str] = Header(None), auth: Optional[str] = Query(None), request: Request = None):
    token = request.cookies.get("session_token") if request else None
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token and auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Session invalide")
    record = await db.documents.find_one({"id": doc_id, "user_id": session["user_id"], "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Document introuvable")
    data, content_type = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", content_type),
                    headers={"Content-Disposition": f'inline; filename="{record["original_filename"]}"'})

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