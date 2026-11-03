"""Saisie du journal d'action d'un dossier client."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def normalize_journal_fields(
    libelle: Optional[str],
    date: Optional[str],
    note: Optional[str] = None,
) -> dict:
    label = (libelle or "").strip()
    if not label:
        raise ValueError("Indiquez ce qui a été fait.")
    if len(label) > 300:
        raise ValueError("Le libellé est trop long.")
    day = (date or "").strip()
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("La date doit être au format AAAA-MM-JJ.") from exc
    extra = (note or "").strip()
    if len(extra) > 4000:
        raise ValueError("La note est trop longue.")
    return {"libelle": label, "date": day, "note": extra or None}


def sort_journal_actions(rows: list[dict]) -> list[dict]:
    """La date d'action la plus récente en premier, puis la saisie la plus récente."""
    return sorted(
        rows,
        key=lambda row: (str(row.get("date") or ""), str(row.get("created_at") or "")),
        reverse=True,
    )


def assigned_journal_query(tenant_user_id: str, account_id: str, scope: dict) -> Optional[dict]:
    """Actions du dossier déjà attribuées à ce compte. None si le compte est vide."""
    account = _single_line(account_id)
    if not account:
        return None
    clauses = []
    members = [item for item in (scope.get("member_ids") or []) if item]
    if members:
        clauses.append({"client_id": {"$in": members}})
    dossier_id = scope.get("dossier_id")
    if dossier_id:
        clauses.append({"dossier_id": dossier_id})
    if not clauses:
        return None
    return {
        "user_id": tenant_user_id,
        "assignee_account_id": account,
        "$or": clauses,
    }


def journal_belongs_to_scope(row: dict, scope: dict) -> bool:
    members = set(scope.get("member_ids") or [])
    if row.get("client_id") in members:
        return True
    dossier_id = scope.get("dossier_id")
    return bool(dossier_id) and row.get("dossier_id") == dossier_id


def _single_line(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())


def person_display_name(source: Any) -> str:
    """Nom affiché d'un compte LeoSoft. Jamais un nom écrit en dur."""
    if source is None:
        return ""
    if isinstance(source, dict):
        read = source.get
    else:
        read = lambda key, default="": getattr(source, key, default)
    name = _single_line(read("name", "") or "")
    if name:
        return name
    return _single_line(f"{read('prenom', '') or ''} {read('nom', '') or ''}")


def journal_client_label(client: Optional[dict]) -> str:
    """Nom du dossier tel qu'il apparaît dans la notification : prénom et nom du client."""
    row = client or {}
    full = _single_line(f"{row.get('prenom') or ''} {row.get('nom') or ''}")
    if full:
        return full
    label = _single_line(row.get("dossier_label") or row.get("name") or "")
    return label or "Client"


def _usable_account_email(value: Any) -> str:
    """Adresse déjà enregistrée sur le compte. Vide si absente ou inutilisable."""
    email = str(value or "").strip()
    if not email or "@" not in email or any(ch.isspace() for ch in email):
        return ""
    return email


def assignee_identity(row: dict, requested_id: str = "") -> dict:
    name = person_display_name(row) or _single_line(row.get("conseiller"))
    account_id = _single_line(row.get("account_id") or row.get("user_id") or requested_id)
    return {
        "account_id": account_id,
        "name": name,
        "email": _usable_account_email(row.get("email")),
    }


def assignee_storage(identity: Optional[dict]) -> dict:
    if not identity or not _single_line(identity.get("account_id")):
        return {"assignee_account_id": None, "assignee_name": None}
    return {
        "assignee_account_id": _single_line(identity.get("account_id")),
        "assignee_name": _single_line(identity.get("name")) or None,
    }


def blank_treated_fields() -> dict:
    return {
        "treated": False,
        "treated_at": None,
        "treated_by_account_id": None,
        "treated_by_name": None,
    }


def mark_journal_treated(
    row: dict,
    *,
    treated: bool,
    actor_account_id: str,
    actor_name: str,
    now: str,
) -> dict:
    """Seul le collaborateur désigné peut cocher ou décocher Action traitée."""
    assignee = _single_line(row.get("assignee_account_id"))
    actor = _single_line(actor_account_id)
    if not assignee:
        raise ValueError("Cette action n'est attribuée à personne.")
    if actor != assignee:
        raise PermissionError("Seul le collaborateur désigné peut cocher Action traitée.")
    if treated:
        return {
            "treated": True,
            "treated_at": now,
            "treated_by_account_id": actor,
            "treated_by_name": _single_line(actor_name) or _single_line(row.get("assignee_name")) or None,
        }
    return blank_treated_fields()


def _format_journal_date(day: str) -> str:
    raw = (day or "").strip()[:10]
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        year, month, date = raw.split("-")
        return f"{date}/{month}/{year}"
    return raw


def plan_journal_assignment_mail(
    *,
    assigned: bool,
    author_name: str = "",
    client_name: str = "",
    action_date: str = "",
    libelle: str = "",
    note: Optional[str] = None,
    assignee_email: Optional[str] = None,
    dossier_url: str = "",
) -> dict:
    """
    Décide s'il faut un e-mail.
    Sans attribution : aucun message.
    Avec attribution mais sans adresse en base : reason=no_email, destinataire vide.
    """
    if not assigned:
        return {"send": False, "reason": None, "to": None}

    author = _single_line(author_name) or "Collaborateur"
    client = _single_line(client_name) or "Client"
    subject = f"Vous avez une notification de {author} sur le dossier {client}"
    lines = [
        subject,
        "",
        f"Date : {_format_journal_date(action_date)}",
        f"Ce qui a été fait : {_single_line(libelle)}",
    ]
    extra = str(note or "").strip()
    if extra:
        lines.append(f"Note : {extra}")
    lines.append(f"Dossier : {client}")
    lines.append("Ouvrez ce dossier et cochez « Action traitée » une fois l'action faite.")
    link = _single_line(dossier_url)
    if link:
        lines.append(link)
    email = _usable_account_email(assignee_email)
    return {
        "send": bool(email),
        "reason": None if email else "no_email",
        "to": email or None,
        "subject": subject,
        "body_text": "\n".join(lines),
        "from_name": author,
    }


async def send_planned_journal_mail(plan: Optional[dict], *, log_meta: Optional[dict] = None) -> dict:
    """Un seul envoi, tout de suite, via le transport SMTP déjà utilisé par LeoSoft."""
    if not plan or not plan.get("send"):
        return {"sent": False, "reason": None if not plan else plan.get("reason")}
    from email_service import MAIL_TYPE_NOTIFICATION, send_email_async

    ok, _err = await send_email_async(
        plan["to"],
        plan["subject"],
        plan["body_text"],
        from_name=plan.get("from_name"),
        mail_type=MAIL_TYPE_NOTIFICATION,
        log_meta=log_meta,
    )
    if not ok:
        return {"sent": False, "reason": "send_failed"}
    return {"sent": True, "reason": None}
