"""Routes LeoSoft du module Analyse de prévoyance.

Persistance Mongo, préremplissage clients, proxy d'exécution du moteur
Node existant (ESTV, ReportPayload, PDF). Le moteur n'est pas réécrit.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from access_control import User, can_access_client
from analyses_prefill import prefill_from_clients

logger = logging.getLogger(__name__)

ENGINE_DIR = Path(__file__).resolve().parent / "analyse_prevoyance_engine"
MAX_VERSIONS = 40
ACTIVE_STATUSES = ("brouillon", "calculee", "finalisee")


class AnalyseCreate(BaseModel):
    clientId: Optional[str] = None
    input: Optional[dict] = None


class AnalyseUpdate(BaseModel):
    input: Optional[dict] = None
    status: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _version_number(doc: dict) -> int:
    """Numéro de version courant. Une analyse = un document ; le numéro monte à chaque enregistrement."""
    raw = doc.get("version")
    try:
        number = int(raw)
    except (TypeError, ValueError):
        number = 0
    if number > 0:
        return number
    # Document ancien : les instantanés sont l'historique, la version courante est +1.
    count = doc.get("versionCount")
    if count is None:
        count = len(doc.get("versions") or [])
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 0
    return count + 1


def _summary(doc: dict) -> dict:
    data = doc.get("input") or {}
    person = data.get("client1") or {}
    name = f"{person.get('prenom') or ''} {person.get('nom') or ''}".strip()
    return {
        "id": doc.get("id"),
        "createdAt": doc.get("created_at"),
        "updatedAt": doc.get("updated_at"),
        "clientId": doc.get("client_id"),
        "clientName": name,
        "conseillerNom": data.get("conseillerNom") or "",
        "status": doc.get("status") or "brouillon",
        "ville": data.get("villeRecherche") or "",
        "hasResults": doc["hasResults"] if "hasResults" in doc else bool(doc.get("results")),
        "version": _version_number(doc),
        "versionCount": doc["versionCount"] if "versionCount" in doc else len(doc.get("versions") or []),
    }


def _public(doc: dict) -> dict:
    return {
        "id": doc.get("id"),
        "createdAt": doc.get("created_at"),
        "updatedAt": doc.get("updated_at"),
        "clientId": doc.get("client_id"),
        "status": doc.get("status") or "brouillon",
        "input": doc.get("input") or {},
        "results": doc.get("results"),
        "documentId": doc.get("document_id"),
        "version": _version_number(doc),
        "versionCount": len(doc.get("versions") or []),
    }


def _node_bin() -> str:
    node = shutil.which("node")
    if not node:
        raise HTTPException(status_code=503, detail="Node.js est requis pour le moteur d'analyse.")
    return node


def _tsx_cli() -> Path:
    cli = ENGINE_DIR / "node_modules" / "tsx" / "dist" / "cli.mjs"
    if not cli.is_file():
        raise HTTPException(
            status_code=503,
            detail="Moteur d'analyse non installé (tsx manquant dans backend/analyse_prevoyance_engine).",
        )
    return cli


def _engine_env() -> dict:
    env = os.environ.copy()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        browsers = Path(local) / "ms-playwright"
        if browsers.is_dir():
            env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    return env


def run_engine(command: str, payload: dict, *, pdf_path: Optional[str] = None, timeout: int = 120) -> str:
    args = [_node_bin(), str(_tsx_cli()), "runner.ts", command]
    if pdf_path:
        args.append(pdf_path)
    try:
        proc = subprocess.run(
            args,
            input=json.dumps(payload).encode("utf-8"),
            cwd=str(ENGINE_DIR),
            capture_output=True,
            timeout=timeout,
            check=False,
            env=_engine_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Le moteur d'analyse a dépassé le délai.") from exc
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        logger.error("analyse engine %s failed: %s", command, err[:2000])
        raise HTTPException(status_code=502, detail=err or "Échec du moteur d'analyse")
    return (proc.stdout or b"").decode("utf-8", errors="replace")


def attach_analyses_routes(
    api_router: APIRouter,
    *,
    db,
    get_current_user,
    decrypt_client,
    store_document,
):
    async def _client_or_403(client_id: str, user: User) -> dict:
        raw = await db.clients.find_one({"id": client_id, "user_id": user.user_id}, {"_id": 0})
        if not raw:
            raise HTTPException(status_code=404, detail="Client introuvable")
        client = decrypt_client(raw) or raw
        if not can_access_client(user, client):
            raise HTTPException(status_code=403, detail="Accès non autorisé à ce client")
        return client

    async def _get_owned(analyse_id: str, user: User) -> dict:
        doc = await db.analyses.find_one(
            {"id": analyse_id, "user_id": user.user_id},
            {"_id": 0},
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Analyse introuvable")
        if doc.get("client_id"):
            await _client_or_403(doc["client_id"], user)
        return doc

    async def _active_for_client(user: User, client_id: str, *, exclude_id: Optional[str] = None) -> list:
        rows = await db.analyses.find(
            {
                "user_id": user.user_id,
                "client_id": client_id,
                "status": {"$in": list(ACTIVE_STATUSES)},
            },
            {"_id": 0, "id": 1, "status": 1, "updated_at": 1, "results": 1},
        ).to_list(100)
        if exclude_id:
            rows = [row for row in rows if row.get("id") != exclude_id]
        return rows

    def _pick_primary(rows: list) -> Optional[dict]:
        """Analyse à ouvrir : la plus récente parmi Calculée/Finalisée, sinon le brouillon le plus récent."""
        if not rows:
            return None
        advanced = [row for row in rows if row.get("status") in ("calculee", "finalisee")]
        pool = advanced or list(rows)
        pool.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
        return pool[0]

    def _exists_conflict(primary: dict) -> HTTPException:
        return HTTPException(
            status_code=409,
            detail={
                "code": "ANALYSE_EXISTS",
                "message": "Une analyse existe déjà pour ce client.",
                "analyseId": primary.get("id"),
            },
        )

    def _snapshot(doc: dict, user: User) -> dict:
        return {
            "at": _now(),
            "by": user.account_id,
            "status": doc.get("status"),
            "input": doc.get("input"),
            "results": doc.get("results"),
        }

    @api_router.get("/analyses-prevoyance/locations")
    async def search_locations(q: str = "", taxYear: int = 2025, user: User = Depends(get_current_user)):
        if len((q or "").strip()) < 2:
            return {"locations": []}
        raw = run_engine("locations", {"q": q, "taxYear": taxYear}, timeout=30)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Réponse ESTV illisible") from exc
        return {"locations": data.get("locations") or []}

    @api_router.get("/analyses-prevoyance")
    async def list_analyses(clientId: Optional[str] = None, user: User = Depends(get_current_user)):
        query = {"user_id": user.user_id}
        if clientId:
            await _client_or_403(clientId, user)
            query["client_id"] = clientId
        rows = await db.analyses.aggregate([
            {"$match": query},
            {"$sort": {"updated_at": -1}},
            {"$limit": 200},
            {"$project": {
                "_id": 0,
                "id": 1,
                "created_at": 1,
                "updated_at": 1,
                "client_id": 1,
                "status": 1,
                "input": 1,
                "hasResults": {"$ne": [{"$ifNull": ["$results", None]}, None]},
                "version": 1,
                "versionCount": {"$size": {"$ifNull": ["$versions", []]}},
            }},
        ]).to_list(200)
        visible = []
        for row in rows:
            if row.get("client_id"):
                try:
                    await _client_or_403(row["client_id"], user)
                except HTTPException:
                    continue
            visible.append(_summary(row))
        return {"items": visible}

    @api_router.post("/analyses-prevoyance")
    async def create_analyse(payload: AnalyseCreate, user: User = Depends(get_current_user)):
        client = None
        spouse = None
        if payload.clientId:
            client = await _client_or_403(payload.clientId, user)
            spouse_id = client.get("linked_spouse_id")
            if spouse_id:
                try:
                    spouse = await _client_or_403(spouse_id, user)
                except HTTPException:
                    spouse = None
        if payload.input:
            data = payload.input
        elif client:
            from analyses_prefill import is_married
            spouse_arg = spouse if spouse and is_married(client) else None
            data = prefill_from_clients(client, spouse_arg, conseiller_nom=user.name or "")
        else:
            data = prefill_from_clients({}, conseiller_nom=user.name or "")
        if payload.clientId:
            active = await _active_for_client(user, payload.clientId)
            primary = _pick_primary(active)
            if primary:
                raise _exists_conflict(primary)
        now = _now()
        doc = {
            "id": str(uuid.uuid4()),
            "user_id": user.user_id,
            "created_by": user.account_id,
            "client_id": payload.clientId,
            "status": "brouillon",
            "input": data,
            "results": None,
            "version": 1,
            "versions": [],
            "created_at": now,
            "updated_at": now,
        }
        await db.analyses.insert_one(doc)
        doc.pop("_id", None)
        return _public(doc)

    @api_router.get("/analyses-prevoyance/{analyse_id}")
    async def get_analyse(analyse_id: str, user: User = Depends(get_current_user)):
        return _public(await _get_owned(analyse_id, user))

    @api_router.get("/analyses-prevoyance/{analyse_id}/versions")
    async def list_versions(analyse_id: str, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        versions = []
        for index, item in enumerate(doc.get("versions") or []):
            versions.append({
                "index": index,
                "at": item.get("at"),
                "status": item.get("status"),
            })
        return {"versions": versions, "current": {"status": doc.get("status"), "updatedAt": doc.get("updated_at")}}

    @api_router.post("/analyses-prevoyance/{analyse_id}/versions/{index}/restore")
    async def restore_version(analyse_id: str, index: int, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        versions = list(doc.get("versions") or [])
        if index < 0 or index >= len(versions):
            raise HTTPException(status_code=404, detail="Version introuvable")
        snap = versions[index] or {}
        versions.append(_snapshot(doc, user))
        updated = {
            "input": snap.get("input") if snap.get("input") is not None else doc.get("input"),
            "results": snap.get("results"),
            "status": snap.get("status") or "brouillon",
            "version": _version_number(doc) + 1,
            "versions": versions[-MAX_VERSIONS:],
            "updated_at": _now(),
        }
        await db.analyses.update_one({"id": analyse_id}, {"$set": updated})
        doc.update(updated)
        return _public(doc)

    @api_router.put("/analyses-prevoyance/{analyse_id}")
    async def save_analyse(analyse_id: str, payload: AnalyseUpdate, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        versions = list(doc.get("versions") or [])
        versions.append(_snapshot(doc, user))
        versions = versions[-MAX_VERSIONS:]
        status = payload.status or doc.get("status") or "brouillon"
        if (
            status in ACTIVE_STATUSES
            and doc.get("status") == "annulee"
            and doc.get("client_id")
        ):
            others = await _active_for_client(user, doc["client_id"], exclude_id=analyse_id)
            primary = _pick_primary(others)
            if primary:
                raise _exists_conflict(primary)
        updated = {
            "input": payload.input if payload.input is not None else doc.get("input"),
            "status": status,
            "version": _version_number(doc) + 1,
            "versions": versions,
            "updated_at": _now(),
        }
        await db.analyses.update_one({"id": analyse_id}, {"$set": updated})
        doc.update(updated)
        return _public(doc)

    @api_router.post("/analyses-prevoyance/{analyse_id}/calculate")
    async def calculate_analyse(analyse_id: str, payload: AnalyseUpdate, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        data = payload.input if payload.input is not None else doc.get("input")
        if not data:
            raise HTTPException(status_code=400, detail="input requis")
        raw = run_engine("calculate", {"input": data}, timeout=180)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="Résultat de calcul illisible") from exc
        results = parsed.get("results")
        if doc.get("status") == "annulee" and doc.get("client_id"):
            others = await _active_for_client(user, doc["client_id"], exclude_id=analyse_id)
            primary = _pick_primary(others)
            if primary:
                raise _exists_conflict(primary)
        versions = list(doc.get("versions") or [])
        versions.append(_snapshot(doc, user))
        updated = {
            "input": data,
            "results": results,
            "status": "calculee",
            "version": _version_number(doc) + 1,
            "versions": versions[-MAX_VERSIONS:],
            "updated_at": _now(),
        }
        await db.analyses.update_one({"id": analyse_id}, {"$set": updated})
        doc.update(updated)
        return _public(doc)

    @api_router.get("/analyses-prevoyance/{analyse_id}/report")
    async def preview_report(analyse_id: str, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        if not doc.get("results"):
            raise HTTPException(status_code=400, detail="Calculez l'analyse avant l'aperçu.")
        html = run_engine("html", {"record": _public(doc)}, timeout=60)
        return HTMLResponse(html)

    @api_router.get("/analyses-prevoyance/{analyse_id}/pdf")
    async def download_pdf(analyse_id: str, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        if not doc.get("results"):
            raise HTTPException(status_code=400, detail="Calculez l'analyse avant le PDF.")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "analyse.pdf")
            run_engine("pdf", {"record": _public(doc)}, pdf_path=path, timeout=180)
            data = Path(path).read_bytes()
        person = (doc.get("input") or {}).get("client1") or {}
        name = f"Analyse_{person.get('nom') or 'client'}.pdf"
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{name}"'},
        )

    @api_router.post("/analyses-prevoyance/{analyse_id}/enregistrer-dossier")
    async def save_into_client_folder(analyse_id: str, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        client_id = doc.get("client_id")
        if not client_id:
            raise HTTPException(status_code=400, detail="Cette analyse n'est pas liée à un client.")
        if not doc.get("results"):
            raise HTTPException(status_code=400, detail="Calculez l'analyse avant de l'enregistrer dans le dossier.")
        if doc.get("status") == "annulee" and client_id:
            others = await _active_for_client(user, client_id, exclude_id=analyse_id)
            primary = _pick_primary(others)
            if primary:
                raise _exists_conflict(primary)
        client = await _client_or_403(client_id, user)
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "analyse.pdf")
            run_engine("pdf", {"record": _public(doc)}, pdf_path=path, timeout=180)
            data = Path(path).read_bytes()
        person = (doc.get("input") or {}).get("client1") or {}
        filename = f"Analyse_prevoyance_{person.get('nom') or 'client'}_{person.get('prenom') or ''}.pdf".replace(" ", "_")
        stored = await store_document(
            client=client,
            client_id=client_id,
            user=user,
            filename=filename,
            data=data,
            content_type="application/pdf",
            category="Analyse de prévoyance",
            checklist_item="Analyse de prévoyance",
            title="Analyse de prévoyance",
        )
        await db.analyses.update_one(
            {"id": analyse_id},
            {"$set": {
                "status": "finalisee",
                "document_id": stored.get("id"),
                "updated_at": _now(),
            }},
        )
        return {"ok": True, "documentId": stored.get("id"), "status": "finalisee"}

    @api_router.post("/analyses-prevoyance/{analyse_id}/annuler")
    async def cancel_analyse(analyse_id: str, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        if doc.get("status") == "annulee":
            return _public(doc)
        versions = list(doc.get("versions") or [])
        versions.append(_snapshot(doc, user))
        updated = {
            "status": "annulee",
            "version": _version_number(doc) + 1,
            "versions": versions[-MAX_VERSIONS:],
            "updated_at": _now(),
        }
        await db.analyses.update_one({"id": analyse_id}, {"$set": updated})
        doc.update(updated)
        return _public(doc)

    @api_router.delete("/analyses-prevoyance/{analyse_id}")
    async def delete_analyse(analyse_id: str, user: User = Depends(get_current_user)):
        doc = await _get_owned(analyse_id, user)
        await db.analyses.delete_one({"id": analyse_id, "user_id": user.user_id})
        return {"ok": True, "id": doc.get("id"), "clientId": doc.get("client_id")}
