"""API du comparateur LAMal. Chaque route exige lamal_module_access."""
from __future__ import annotations

import io
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from access_control import User, require_perm, PERM_LAMAL_MODULE_ACCESS
from lamal.engine import (
    SOURCES,
    accident_code,
    age_class_for_birth_year,
    birth_year_from_value,
    commit_delivery,
    load_catchment,
    load_localities_path,
    load_region_xlsx,
    load_tariff_names,
    money_str,
    parse_accident,
    parse_franchise_value,
    quote,
    render_email,
    resolve_residence,
    scan_premium_csv,
    valid_email,
    Catalog,
    Offer,
)
from lamal.people import (
    client_view,
    derive_status,
    is_opted_out,
    swiss_residence,
)
from lamal.store import COLLECTIONS, active_dataset, audit, ensure_indexes, new_id, now_iso

DATA_DIR_NAME = "data/ofsp"


class ProfileBody(BaseModel):
    birth_year: Optional[int] = None
    plz: Optional[str] = None
    commune: Optional[str] = None
    canton: Optional[str] = None
    with_accident: Optional[bool] = None
    franchise_chf: Optional[int] = None
    insurer_id: Optional[str] = None
    insurer_label: Optional[str] = None
    model_type: Optional[str] = None
    tarif_id: Optional[str] = None
    known_premium: Optional[str] = None
    known_premium_year: Optional[int] = None
    prospection_opposee: Optional[bool] = None
    notes: Optional[str] = None


class CompareBody(ProfileBody):
    client_id: Optional[str] = None
    year: int = 2027
    age_subgroup: Optional[str] = None
    save: bool = True


class EmailBody(BaseModel):
    comparison_id: str
    subject: Optional[str] = None
    body: Optional[str] = None


class CampaignBody(BaseModel):
    year: int = 2027
    client_ids: list[str] = Field(default_factory=list)
    minimum_saving_year: Optional[str] = None


class SendBody(BaseModel):
    confirm: str = ""


class StatusBody(BaseModel):
    status: str


def attach_lamal_routes(api_router: APIRouter, *, db, get_current_user, decrypt_client: Callable):
    router = APIRouter(prefix="/lamal", tags=["lamal"])

    def guard(user: User):
        require_perm(user, PERM_LAMAL_MODULE_ACCESS, "Accès au comparateur LAMal refusé")

    async def geo_catalog(dataset) -> Catalog:
        localities = []
        async for row in db[COLLECTIONS["regions"]].find({"dataset_id": dataset["id"], "kind": "locality"}, {"_id": 0}):
            localities.append(row)
        regions = {}
        async for row in db[COLLECTIONS["regions"]].find({"dataset_id": dataset["id"], "kind": "region"}, {"_id": 0}):
            regions[int(row["bfs"])] = row
        return Catalog(year=dataset["year"], offers={}, localities=localities, regions_by_bfs=regions, source=dataset.get("source") or {})

    async def offers_for(dataset_id: str, **filters) -> dict:
        query = {"dataset_id": dataset_id}
        bfs = filters.pop("bfs", None)
        for key, value in filters.items():
            if value is not None:
                query[key] = value
        offers = {}
        cursor = db[COLLECTIONS["premiums"]].find(query, {"_id": 0})
        async for row in cursor:
            if row.get("catchment_bfs") and bfs not in set(row["catchment_bfs"]):
                continue
            offer = Offer(
                insurer_id=row["insurer_id"],
                canton=row["canton"],
                region=row["region"],
                age_class=row["age_class"],
                age_subgroup=row["age_subgroup"],
                accident=row["accident"],
                franchise_code=row["franchise_code"],
                franchise_chf=int(row["franchise_chf"]),
                ordinary_franchise=bool(row.get("ordinary_franchise")),
                tarif_id=row["tarif_id"],
                tariftyp=row["tariftyp"],
                premium_month=__import__("decimal").Decimal(row["premium_month"]),
                base_tariff=bool(row.get("base_tariff")),
                tarif_name_de=row.get("tarif_name_de") or "",
                tarif_name_fr=row.get("product_name") or "",
                insurer_name=row.get("insurer_name") or "",
            )
            offers[offer.key] = offer
        return offers

    @router.get("/meta")
    async def meta(user: User = Depends(get_current_user)):
        guard(user)
        dataset = await active_dataset(db, 2027)
        return {"sources": SOURCES, "dataset": dataset, "send_enabled": False}

    @router.post("/datasets/import")
    async def import_dataset(user: User = Depends(get_current_user)):
        guard(user)
        from pathlib import Path
        directory = Path(__file__).resolve().parents[1] / "data" / "ofsp"
        premiums = directory / "Praemien_CH.csv"
        regions_path = directory / "Praemienregionen_2027.xlsx"
        localities_path = directory / "ortschaften.zip"
        tariffs_path = directory / "Tarife.csv"
        catchment_path = directory / "Einzugsgebiete.csv"
        missing = [path.name for path in (premiums, regions_path, localities_path, tariffs_path, catchment_path) if not path.exists()]
        if missing:
            raise HTTPException(status_code=400, detail="Fichiers officiels manquants : " + ", ".join(missing))
        report, offers = scan_premium_csv(premiums, tariff_year=2027)
        if not report.ok:
            await db[COLLECTIONS["datasets"]].insert_one({
                "id": new_id(),
                "year": 2027,
                "active": False,
                "status": "rejected",
                "errors": report.errors,
                "warnings": report.warnings,
                "created_at": now_iso(),
            })
            raise HTTPException(status_code=422, detail={"errors": report.errors, "warnings": report.warnings})
        existing = await db[COLLECTIONS["datasets"]].find_one({"sha256": report.sha256, "status": "active"}, {"_id": 0})
        if existing:
            return {"dataset": existing, "idempotent": True}
        try:
            region_rows = load_region_xlsx(regions_path)
            locality_rows = load_localities_path(localities_path)
            names = load_tariff_names(tariffs_path)
            catchment = load_catchment(catchment_path)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Fichier officiel illisible : {exc}") from exc
        if len(locality_rows) < 1000 or len(region_rows) < 500:
            raise HTTPException(status_code=422, detail="Annuaire des communes ou régions incomplet")
        dataset_id = new_id()
        await ensure_indexes(db)
        batch = []
        for offer in offers.values():
            french = names.get((offer.insurer_id, offer.tarif_id), "")
            key = (offer.insurer_id, offer.canton, offer.region, offer.tarif_id)
            if key not in catchment:
                continue
            allowed = catchment[key]
            public = offer.public()
            public.update({
                "dataset_id": dataset_id,
                "product_name": french or public["product_name"],
                "franchise_code": offer.franchise_code,
                "tarif_name_de": offer.tarif_name_de,
                "catchment_bfs": None if allowed is None else sorted(allowed),
            })
            batch.append(public)
            if len(batch) >= 2000:
                await db[COLLECTIONS["premiums"]].insert_many(batch)
                batch = []
        if batch:
            await db[COLLECTIONS["premiums"]].insert_many(batch)
        region_docs = [{"dataset_id": dataset_id, "kind": "region", **row} for row in region_rows.values()]
        locality_docs = [{"dataset_id": dataset_id, "kind": "locality", **row} for row in locality_rows]
        if region_docs:
            await db[COLLECTIONS["regions"]].insert_many(region_docs)
        for start in range(0, len(locality_docs), 2000):
            await db[COLLECTIONS["regions"]].insert_many(locality_docs[start:start + 2000])
        await db[COLLECTIONS["datasets"]].update_many({"year": 2027, "active": True}, {"$set": {"active": False}})
        document = {
            "id": dataset_id,
            "year": 2027,
            "active": True,
            "status": "active",
            "sha256": report.sha256,
            "row_count": report.row_count,
            "offer_count": len(offers),
            "stored_offers": report.offer_count,
            "warnings": report.warnings,
            "source": SOURCES,
            "imported_at": now_iso(),
            "imported_by": user.email,
        }
        await db[COLLECTIONS["datasets"]].insert_one(document)
        await audit(db, user.email, "import_dataset", {"id": dataset_id, "sha256": report.sha256})
        document.pop("_id", None)
        return {"dataset": {k: v for k, v in document.items() if k != "_id"}, "idempotent": False}

    @router.get("/clients")
    async def list_clients(
        q: Optional[str] = None,
        canton: Optional[str] = None,
        status: Optional[str] = None,
        year: int = 2027,
        user: User = Depends(get_current_user),
    ):
        guard(user)
        rows = await _client_rows(q=q, canton=canton, status=status, year=year)
        return {"items": rows, "count": len(rows)}

    async def _client_rows(*, q: Optional[str], canton: Optional[str], status: Optional[str], year: int):
        profiles = {}
        async for row in db[COLLECTIONS["profiles"]].find({}, {"_id": 0}):
            profiles[row["client_id"]] = row
        latest = {}
        async for row in db[COLLECTIONS["comparisons"]].find({"year": year}, {"_id": 0}).sort("created_at", -1):
            latest.setdefault(row.get("client_id"), row)
        items = []
        query = {"user_id": user.user_id}
        cursor = db.clients.find(query, {"_id": 0})
        async for raw in cursor:
            client = decrypt_client(raw) or raw
            residence = swiss_residence(client)
            if residence is not True:
                continue
            profile = profiles.get(client.get("id"), {})
            comparison = latest.get(client.get("id"))
            view = client_view(client, profile, comparison)
            if q:
                blob = " ".join(str(view.get(key) or "") for key in ("nom", "prenom", "commune", "id", "npa")).casefold()
                if q.casefold() not in blob:
                    continue
            if canton and view.get("canton") != canton.upper():
                continue
            if status and view.get("status") != status:
                continue
            items.append(view)
        return items

    @router.get("/dashboard")
    async def dashboard(year: int = 2027, user: User = Depends(get_current_user)):
        guard(user)
        rows = await _client_rows(q=None, canton=None, status=None, year=year)
        analysed = [row for row in rows if row.get("comparison_id")]
        incomplete = [row for row in rows if row.get("status") == "informations_manquantes"]
        savings = [row for row in rows if row.get("savings_reliable")]
        total = 0
        from decimal import Decimal
        for row in savings:
            if row.get("savings_year"):
                total += Decimal(row["savings_year"])
        ready = await db[COLLECTIONS["emails"]].count_documents({"year": year, "status": "a_valider"})
        sent = await db[COLLECTIONS["emails"]].count_documents({"year": year, "status": "envoye"})
        followed = [row for row in rows if row.get("status") in {"client_interesse", "changement_en_cours", "termine"}]
        return {
            "year": year,
            "swiss_clients": len(rows),
            "analysed": len(analysed),
            "incomplete": len(incomplete),
            "with_savings": len(savings),
            "savings_year_total": money_str(total) if savings else None,
            "emails_ready": ready,
            "emails_sent": sent,
            "followed": len(followed),
            "items": rows[:200],
        }

    @router.get("/clients/{client_id}")
    async def one_client(client_id: str, user: User = Depends(get_current_user)):
        guard(user)
        client = await _load_client(client_id)
        profile = await db[COLLECTIONS["profiles"]].find_one({"client_id": client_id}, {"_id": 0}) or {}
        comparison = await db[COLLECTIONS["comparisons"]].find_one({"client_id": client_id}, {"_id": 0}, sort=[("created_at", -1)])
        return {"client": client_view(client, profile, comparison), "profile": profile}

    async def _load_client(client_id: str) -> dict:
        raw = await db.clients.find_one({"id": client_id}, {"_id": 0})
        if not raw:
            raise HTTPException(status_code=404, detail="Client introuvable")
        client = decrypt_client(raw) or raw
        if swiss_residence(client) is False:
            raise HTTPException(status_code=422, detail="Ce client n'est pas domicilié en Suisse et est exclu du comparateur LAMal.")
        return client

    @router.put("/clients/{client_id}/profile")
    async def save_profile(client_id: str, body: ProfileBody, user: User = Depends(get_current_user)):
        guard(user)
        await _load_client(client_id)
        payload = {k: v for k, v in body.model_dump().items() if v is not None}
        payload.update({"client_id": client_id, "updated_at": now_iso(), "updated_by": user.email})
        await db[COLLECTIONS["profiles"]].update_one({"client_id": client_id}, {"$set": payload}, upsert=True)
        await audit(db, user.email, "profile_update", {"client_id": client_id})
        stored = await db[COLLECTIONS["profiles"]].find_one({"client_id": client_id}, {"_id": 0})
        return {"profile": stored}

    @router.post("/comparisons")
    async def create_comparison(body: CompareBody, user: User = Depends(get_current_user)):
        guard(user)
        dataset = await active_dataset(db, body.year)
        if not dataset:
            raise HTTPException(status_code=409, detail="Aucun jeu de primes officiel actif. Importez les fichiers OFSP.")
        client = await _load_client(body.client_id) if body.client_id else {}
        profile_doc = {}
        if body.client_id:
            profile_doc = await db[COLLECTIONS["profiles"]].find_one({"client_id": body.client_id}, {"_id": 0}) or {}
        merged = _merge_profile(client, profile_doc, body)
        geo = await geo_catalog(dataset)
        residence = resolve_residence(geo, plz=merged.get("plz"), commune=merged.get("commune"), canton=merged.get("canton"))
        offers = {}
        if residence.get("ok") and merged.get("birth_year") and merged.get("with_accident") is not None:
            age_class = age_class_for_birth_year(int(merged["birth_year"]), body.year)
            offers = await offers_for(
                dataset["id"],
                canton=residence["canton"],
                region=residence["region"],
                age_class=age_class,
                accident=accident_code(bool(merged["with_accident"])),
                bfs=residence.get("bfs"),
            )
        catalog = Catalog(
            year=body.year,
            offers=offers,
            localities=geo.localities,
            regions_by_bfs=geo.regions_by_bfs,
            source=geo.source,
        )
        result = quote(catalog, {**merged, "residence": residence, "year": body.year})
        result["dataset"] = {"id": dataset["id"], "sha256": dataset.get("sha256"), "source": dataset.get("source"), "year": dataset.get("year")}
        result["calculated_at"] = now_iso()
        if body.client_id and body.save and result.get("ok"):
            document = {
                "id": new_id(),
                "client_id": body.client_id,
                "year": body.year,
                "created_at": result["calculated_at"],
                "created_by": user.email,
                "parameters": merged,
                "result": _jsonable(result),
                "dataset_id": dataset["id"],
            }
            await db[COLLECTIONS["comparisons"]].insert_one(document)
            result["comparison_id"] = document["id"]
            await audit(db, user.email, "comparison", {"client_id": body.client_id, "id": document["id"]})
        return _jsonable(result)

    @router.get("/clients/{client_id}/history")
    async def history(client_id: str, user: User = Depends(get_current_user)):
        guard(user)
        await _load_client(client_id)
        rows = []
        cursor = db[COLLECTIONS["comparisons"]].find({"client_id": client_id}, {"_id": 0}).sort("created_at", -1)
        async for row in cursor:
            rows.append(row)
        return {"items": rows}

    @router.post("/emails/preview")
    async def preview_email(body: EmailBody, user: User = Depends(get_current_user)):
        guard(user)
        comparison = await db[COLLECTIONS["comparisons"]].find_one({"id": body.comparison_id}, {"_id": 0})
        if not comparison:
            raise HTTPException(status_code=404, detail="Comparaison introuvable")
        client = await _load_client(comparison["client_id"])
        message = render_email(client, comparison.get("result") or {})
        if body.subject:
            message["subject"] = body.subject
        if body.body:
            message["body"] = body.body
        message["to"] = client.get("email")
        message["to_valid"] = valid_email(client.get("email"))
        message["opt_out"] = is_opted_out(client, await db[COLLECTIONS["profiles"]].find_one({"client_id": client.get("id")}, {"_id": 0}) or {})
        return message

    @router.post("/emails")
    async def prepare_email(body: EmailBody, user: User = Depends(get_current_user)):
        guard(user)
        preview = await preview_email(body, user)
        if preview.get("opt_out"):
            raise HTTPException(status_code=422, detail="Opposition à la prospection : aucun e-mail ne sera préparé.")
        if not preview.get("to_valid"):
            raise HTTPException(status_code=422, detail="Adresse e-mail absente ou invalide.")
        comparison = await db[COLLECTIONS["comparisons"]].find_one({"id": body.comparison_id}, {"_id": 0})
        document = {
            "id": new_id(),
            "client_id": comparison["client_id"],
            "comparison_id": body.comparison_id,
            "campaign_id": None,
            "year": comparison.get("year"),
            "to": preview["to"],
            "subject": preview["subject"],
            "body": preview["body"],
            "kind": preview["kind"],
            "status": "a_valider",
            "created_at": now_iso(),
            "created_by": user.email,
        }
        await db[COLLECTIONS["emails"]].insert_one(document)
        await audit(db, user.email, "email_draft", {"id": document["id"], "client_id": document["client_id"]})
        document.pop("_id", None)
        return document

    @router.post("/emails/{email_id}/send")
    async def send_email_route(email_id: str, body: SendBody, user: User = Depends(get_current_user)):
        guard(user)
        email = await db[COLLECTIONS["emails"]].find_one({"id": email_id}, {"_id": 0})
        if not email:
            raise HTTPException(status_code=404, detail="E-mail introuvable")
        if email.get("status") == "envoye":
            raise HTTPException(status_code=409, detail="Cet e-mail a déjà été envoyé.")
        outcome = commit_delivery(email, confirm=body.confirm, transport=None)
        await db[COLLECTIONS["emails"]].update_one({"id": email_id}, {"$set": {"status": outcome["status"], "send_attempt_at": now_iso()}})
        await audit(db, user.email, "email_send_blocked", {"id": email_id, "status": outcome["status"]})
        raise HTTPException(status_code=409, detail=outcome["detail"])

    @router.post("/campaigns")
    async def create_campaign(body: CampaignBody, user: User = Depends(get_current_user)):
        guard(user)
        dataset = await active_dataset(db, body.year)
        if not dataset:
            raise HTTPException(status_code=409, detail="Jeu de primes inactif ou absent.")
        campaign_id = new_id()
        rows = await _client_rows(q=None, canton=None, status=None, year=body.year)
        selected = []
        for row in rows:
            if body.client_ids and row["id"] not in body.client_ids:
                continue
            if row.get("opt_out") or not row.get("email_valid"):
                row["campaign_eligible"] = False
                continue
            if not row.get("savings_reliable"):
                row["campaign_eligible"] = False
                continue
            if body.minimum_saving_year and row.get("savings_year") and float(row["savings_year"]) < float(body.minimum_saving_year):
                row["campaign_eligible"] = False
                continue
            row["campaign_eligible"] = True
            selected.append(row["id"])
        document = {
            "id": campaign_id,
            "year": body.year,
            "dataset_id": dataset["id"],
            "status": "preparation",
            "created_at": now_iso(),
            "created_by": user.email,
            "recipient_ids": selected,
            "progress": {"total": len(rows), "selected": len(selected), "done": len(selected)},
        }
        await db[COLLECTIONS["campaigns"]].insert_one(document)
        for client_id in selected:
            comparison = await db[COLLECTIONS["comparisons"]].find_one({"client_id": client_id, "year": body.year}, {"_id": 0}, sort=[("created_at", -1)])
            if not comparison:
                continue
            existing = await db[COLLECTIONS["emails"]].find_one({"campaign_id": campaign_id, "client_id": client_id})
            if existing:
                continue
            client = await _load_client(client_id)
            message = render_email(client, comparison.get("result") or {})
            if message["kind"] != "economies":
                continue
            await db[COLLECTIONS["emails"]].insert_one({
                "id": new_id(),
                "campaign_id": campaign_id,
                "client_id": client_id,
                "comparison_id": comparison["id"],
                "year": body.year,
                "to": client.get("email"),
                "subject": message["subject"],
                "body": message["body"],
                "kind": message["kind"],
                "status": "a_valider",
                "created_at": now_iso(),
                "created_by": user.email,
            })
        await audit(db, user.email, "campaign_prepare", {"id": campaign_id, "recipients": len(selected)})
        document.pop("_id", None)
        return document

    @router.post("/campaigns/{campaign_id}/send")
    async def send_campaign(campaign_id: str, body: SendBody, user: User = Depends(get_current_user)):
        guard(user)
        outcome = commit_delivery({"campaign_id": campaign_id}, confirm=body.confirm, transport=None)
        await audit(db, user.email, "campaign_send_blocked", {"id": campaign_id})
        raise HTTPException(status_code=409, detail=outcome["detail"])

    @router.get("/campaigns")
    async def list_campaigns(user: User = Depends(get_current_user)):
        guard(user)
        rows = []
        async for row in db[COLLECTIONS["campaigns"]].find({}, {"_id": 0}).sort("created_at", -1):
            rows.append(row)
        return {"items": rows}

    @router.get("/campaigns/{campaign_id}")
    async def get_campaign(campaign_id: str, user: User = Depends(get_current_user)):
        guard(user)
        campaign = await db[COLLECTIONS["campaigns"]].find_one({"id": campaign_id}, {"_id": 0})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campagne introuvable")
        emails = []
        async for row in db[COLLECTIONS["emails"]].find({"campaign_id": campaign_id}, {"_id": 0}):
            emails.append(row)
        return {"campaign": campaign, "emails": emails}

    @router.delete("/campaigns/{campaign_id}/recipients/{client_id}")
    async def remove_recipient(campaign_id: str, client_id: str, user: User = Depends(get_current_user)):
        guard(user)
        await db[COLLECTIONS["emails"]].delete_one({"campaign_id": campaign_id, "client_id": client_id, "status": "a_valider"})
        await db[COLLECTIONS["campaigns"]].update_one({"id": campaign_id}, {"$pull": {"recipient_ids": client_id}})
        return {"ok": True}

    @router.post("/clients/{client_id}/status")
    async def set_status(client_id: str, body: StatusBody, user: User = Depends(get_current_user)):
        guard(user)
        allowed = {"client_interesse", "changement_en_cours", "termine", "email_a_valider"}
        if body.status not in allowed:
            raise HTTPException(status_code=422, detail="Statut de suivi non autorisé")
        await _load_client(client_id)
        await db[COLLECTIONS["profiles"]].update_one(
            {"client_id": client_id},
            {"$set": {"client_id": client_id, "suivi": body.status, "updated_at": now_iso()}},
            upsert=True,
        )
        return {"ok": True, "status": body.status}

    @router.get("/export.xlsx")
    async def export_xlsx(year: int = 2027, user: User = Depends(get_current_user)):
        guard(user)
        from openpyxl import Workbook
        rows = await _client_rows(q=None, canton=None, status=None, year=year)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Comparaisons"
        sheet.append(["Client", "Commune", "Canton", "Caisse actuelle", "Économie annuelle CHF", "Statut", "E-mail"])
        for row in rows:
            sheet.append([
                f"{row.get('prenom') or ''} {row.get('nom') or ''}".strip(),
                row.get("commune") or "À compléter",
                row.get("canton") or "",
                row.get("insurer") or "À compléter",
                row.get("savings_year") or "",
                row.get("status_label") or "",
                row.get("email") or "",
            ])
        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=lamal-comparaisons-{year}.xlsx"},
        )

    @router.get("/communes")
    async def search_communes(q: str = Query("", min_length=2), user: User = Depends(get_current_user)):
        guard(user)
        dataset = await active_dataset(db, 2027)
        if not dataset:
            return {"items": []}
        expression = {"$regex": q, "$options": "i"}
        cursor = db[COLLECTIONS["regions"]].find(
            {"dataset_id": dataset["id"], "kind": "locality", "$or": [{"commune": expression}, {"locality": expression}, {"plz": q}]},
            {"_id": 0},
        ).limit(20)
        return {"items": [row async for row in cursor]}

    @router.post("/comparisons/{comparison_id}/recommendation")
    async def recommend(comparison_id: str, body: ProfileBody, user: User = Depends(get_current_user)):
        guard(user)
        insurer_id = body.insurer_id
        tarif_id = body.tarif_id
        if not insurer_id or not tarif_id:
            raise HTTPException(status_code=422, detail="Offre incomplète")
        updated = await db[COLLECTIONS["comparisons"]].update_one(
            {"id": comparison_id},
            {"$set": {"selected_offer": {"insurer_id": insurer_id, "tarif_id": tarif_id}, "selected_at": now_iso()}},
        )
        if updated.matched_count == 0:
            raise HTTPException(status_code=404, detail="Comparaison introuvable")
        await audit(db, user.email, "recommendation", {"comparison_id": comparison_id, "tarif_id": tarif_id})
        return {"ok": True}

    api_router.include_router(router)


def _merge_profile(client: dict, stored: dict, body: CompareBody) -> dict:
    explicit = {k: v for k, v in body.model_dump().items() if v is not None and k not in {"client_id", "save"}}
    birth = explicit.get("birth_year") or stored.get("birth_year") or birth_year_from_value(client.get("date_naissance"))
    accident = explicit.get("with_accident")
    if accident is None:
        accident = stored.get("with_accident")
    if accident is None:
        accident = parse_accident(client.get("couverture_accidents") or client.get("accident") or client.get("avec_accident"))
    franchise = explicit.get("franchise_chf")
    if franchise is None:
        franchise = parse_franchise_value(stored.get("franchise_chf") if stored.get("franchise_chf") is not None else client.get("franchise") or client.get("franchise_lamal"))
    return {
        "birth_year": birth,
        "plz": explicit.get("plz") or stored.get("plz") or client.get("npa"),
        "commune": explicit.get("commune") or stored.get("commune") or client.get("ville") or client.get("commune"),
        "canton": explicit.get("canton") or stored.get("canton") or client.get("canton"),
        "with_accident": accident,
        "franchise_chf": franchise,
        "insurer_id": explicit.get("insurer_id") or stored.get("insurer_id") or client.get("caisse_lamal_id"),
        "insurer_label": explicit.get("insurer_label") or stored.get("insurer_label") or client.get("caisse_maladie") or client.get("caisse"),
        "model_type": explicit.get("model_type") or stored.get("model_type") or client.get("modele_lamal"),
        "tarif_id": explicit.get("tarif_id") or stored.get("tarif_id"),
        "known_premium": explicit.get("known_premium") or stored.get("known_premium") or client.get("prime_lamal"),
        "known_premium_year": explicit.get("known_premium_year") or stored.get("known_premium_year"),
        "age_subgroup": explicit.get("age_subgroup") or stored.get("age_subgroup"),
        "year": body.year,
    }


def _jsonable(value):
    from decimal import Decimal
    if isinstance(value, Decimal):
        return money_str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
