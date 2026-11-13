"""Import Excel de conseillers — aperçu, doublons, entreprises inconnues."""
from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from openpyxl import Workbook, load_workbook

from access_control import (
    ROLE_CONSEILLER,
    display_name,
    force_access_by_account_id_only_on_create,
    permission_storage_fields,
)
from entreprises import match_entreprise_by_name, normalize_domain

HEADERS = ("Prenom", "Nom", "Email", "Nom de l'entreprise")
HEADER_ALIASES = {
    "prenom": "prenom",
    "prénom": "prenom",
    "nom": "nom",
    "email": "email",
    "e-mail": "email",
    "mail": "email",
    "nom de l'entreprise": "entreprise",
    "nom entreprise": "entreprise",
    "entreprise": "entreprise",
    "societe": "entreprise",
    "société": "entreprise",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_import_template_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Conseillers"
    for i, h in enumerate(HEADERS, start=1):
        ws.cell(1, i, h)
    # Ligne d'exemple (à remplacer)
    ws.cell(2, 1, "Jean")
    ws.cell(2, 2, "Dupont")
    ws.cell(2, 3, "jean.dupont@exemple.ch")
    ws.cell(2, 4, "Agence Mendes")
    ws2 = wb.create_sheet("Instructions")
    ws2["A1"] = "Remplissez l'onglet Conseillers (une ligne = un utilisateur)."
    ws2["A2"] = "Colonnes obligatoires : Prénom, Nom, Email, Nom de l'entreprise."
    ws2["A3"] = "L'entreprise doit exister dans LeoSoft (ou sera signalée comme inconnue)."
    ws2["A4"] = "Rôle imposé : Conseiller. Accès : uniquement dossiers attribués (account_id)."
    ws2["A5"] = "Ne mettez aucun mot de passe dans ce fichier."
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _norm_header(cell: Any) -> str:
    s = str(cell or "").strip().casefold()
    s = re.sub(r"\s+", " ", s)
    return HEADER_ALIASES.get(s, "")


def parse_excel_rows(content: bytes) -> tuple[list[dict], Optional[str]]:
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        return [], "Fichier Excel illisible"
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return [], "Fichier vide"
    mapping: dict[int, str] = {}
    for idx, cell in enumerate(header_row):
        key = _norm_header(cell)
        if key:
            mapping[idx] = key
    needed = {"prenom", "nom", "email", "entreprise"}
    if not needed.issubset(set(mapping.values())):
        return [], "Colonnes requises manquantes (Prénom, Nom, Email, Nom de l'entreprise)"
    out: list[dict] = []
    for line_no, row in enumerate(rows_iter, start=2):
        if row is None or all(c is None or str(c).strip() == "" for c in row):
            continue
        item = {"ligne": line_no, "prenom": "", "nom": "", "email": "", "entreprise": ""}
        for idx, key in mapping.items():
            if idx >= len(row):
                continue
            val = row[idx]
            item[key] = str(val).strip() if val is not None else ""
        item["email"] = item["email"].strip().lower()
        out.append(item)
    return out, None


def preview_import(
    rows: list[dict],
    *,
    existing_emails: set[str],
    entreprises: list[dict],
) -> dict[str, Any]:
    """Aperçu sans écriture."""
    seen_in_file: set[str] = set()
    preview_rows = []
    unknown_entreprises: dict[str, int] = {}
    counts = {
        "total": len(rows),
        "ok": 0,
        "duplicate_email_db": 0,
        "duplicate_email_file": 0,
        "unknown_entreprise": 0,
        "invalid": 0,
    }
    for raw in rows:
        prenom = (raw.get("prenom") or "").strip()
        nom = (raw.get("nom") or "").strip()
        email = (raw.get("email") or "").strip().lower()
        ent_nom = (raw.get("entreprise") or "").strip()
        status = "ok"
        errors: list[str] = []
        ent = match_entreprise_by_name(entreprises, ent_nom) if ent_nom else None

        if not prenom or not nom:
            status = "invalid"
            errors.append("Prénom/Nom manquant")
        if not email or "@" not in email:
            status = "invalid"
            errors.append("E-mail invalide")
        if not ent_nom:
            status = "invalid"
            errors.append("Entreprise manquante")
        elif not ent:
            if status == "ok":
                status = "unknown_entreprise"
            errors.append("Entreprise inconnue")
            unknown_entreprises[ent_nom] = unknown_entreprises.get(ent_nom, 0) + 1

        if email and email in existing_emails:
            status = "duplicate_email_db"
            errors.append("E-mail déjà présent")
        elif email and email in seen_in_file:
            status = "duplicate_email_file"
            errors.append("E-mail en doublon dans le fichier")
        if email:
            seen_in_file.add(email)

        if status == "ok":
            counts["ok"] += 1
        elif status == "duplicate_email_db":
            counts["duplicate_email_db"] += 1
        elif status == "duplicate_email_file":
            counts["duplicate_email_file"] += 1
        elif status == "unknown_entreprise":
            counts["unknown_entreprise"] += 1
        else:
            counts["invalid"] += 1

        preview_rows.append(
            {
                "ligne": raw.get("ligne"),
                "prenom": prenom,
                "nom": nom,
                "email": email,
                "entreprise": ent_nom,
                "entreprise_id": (ent or {}).get("id"),
                "entreprise_finma": (ent or {}).get("finma_number") if ent else None,
                "status": status,
                "errors": errors,
                "role": ROLE_CONSEILLER,
                "access_by_account_id_only": True,
            }
        )

    return {
        "rows": preview_rows,
        "counts": counts,
        "unknown_entreprises": [
            {"nom": n, "occurrences": c} for n, c in sorted(unknown_entreprises.items())
        ],
        "can_apply": counts["ok"] > 0
        and counts["invalid"] == 0
        and counts["duplicate_email_db"] == 0
        and counts["duplicate_email_file"] == 0
        and counts["unknown_entreprise"] == 0,
    }


def build_user_docs_from_preview(ok_rows: list[dict]) -> list[dict]:
    """Documents utilisateurs prêts à insérer (sans password_hash — activation)."""
    docs = []
    for row in ok_rows:
        if row.get("status") != "ok":
            continue
        prenom = row["prenom"]
        nom = row["nom"]
        name = display_name(prenom, nom)
        account_id = f"user_{uuid.uuid4().hex[:12]}"
        access_only = force_access_by_account_id_only_on_create(ROLE_CONSEILLER)
        doc = {
            "user_id": account_id,
            "email": row["email"],
            "prenom": prenom,
            "nom": nom,
            "name": name,
            "telephone": None,
            "picture": None,
            "role": ROLE_CONSEILLER,
            "conseiller": name,
            "finma_number": None,
            "entreprise_id": row.get("entreprise_id"),
            "active": True,
            "password_hash": "",
            "must_set_password": True,
            "activation_pending": True,
            "created_at": _now(),
            "access_by_account_id_only": access_only,
            "receive_conseiller_rappel_copies": False,
            **permission_storage_fields(
                ROLE_CONSEILLER,
                None,
                False,
                access_by_account_id_only=access_only,
            ),
        }
        docs.append(doc)
    return docs
