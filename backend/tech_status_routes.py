"""Routes admin : suivi technique (lecture seule + rapport PDF + contrôle quotidien)."""
from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import Depends, HTTPException, Query
from fastapi.responses import FileResponse

from access_control import PERM_SUIVI_TECHNIQUE_VIEW, User, require_perm
from tech_audit import build_tech_status_from_db, launch_manual_audit

logger = logging.getLogger(__name__)


def attach_tech_status_routes(api_router, db, get_current_user: Callable):
    @api_router.get("/admin/tech-status")
    async def get_tech_status(user: User = Depends(get_current_user)):
        require_perm(user, PERM_SUIVI_TECHNIQUE_VIEW)
        return await build_tech_status_from_db(db)

    @api_router.post("/admin/tech-status/run-audit")
    async def run_tech_audit(
        user: User = Depends(get_current_user),
        force: bool = Query(
            True,
            description="True = relance un contrôle complet ; False = ignore si déjà enregistré aujourd'hui",
        ),
    ):
        require_perm(user, PERM_SUIVI_TECHNIQUE_VIEW)
        try:
            return await launch_manual_audit(db, force=force)
        except Exception as exc:
            logger.exception("Contrôle technique manuel échoué")
            raise HTTPException(status_code=500, detail="Contrôle technique échoué") from exc

    @api_router.get("/admin/tech-status/audit-report.pdf")
    async def download_audit_report(user: User = Depends(get_current_user)):
        require_perm(user, PERM_SUIVI_TECHNIQUE_VIEW)
        try:
            from scripts.generate_audit_final_pdf import build_pdf
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="Générateur PDF indisponible") from exc

        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"Audit_LeoSoft_{stamp}.pdf"
        tmp = Path(tempfile.gettempdir()) / filename
        try:
            build_pdf(tmp)
        except Exception as exc:
            logger.exception("Génération PDF audit échouée")
            raise HTTPException(status_code=500, detail="Génération du rapport PDF échouée") from exc

        return FileResponse(
            path=str(tmp),
            media_type="application/pdf",
            filename=filename,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
