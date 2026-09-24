"""
Envoi d'e-mails CRM via SMTP Infomaniak (Railway → mail.infomaniak.com).

Variables d'environnement (Railway — secrets, jamais dans le code / Git) :
  SMTP_HOST       — mail.infomaniak.com
  SMTP_PORT       — 587 (STARTTLS)
  SMTP_TLS        — true (défaut)
  SMTP_USER       — noreply@leosoft.ch
  SMTP_PASSWORD   — mot de passe de la boîte (secret Railway uniquement)
  SMTP_FROM       — noreply@leosoft.ch (expéditeur)
  SMTP_FROM_NAME  — LeoSoft
  SMTP_REPLY_TO   — optionnel ; par défaut = SMTP_FROM
  OFFRES_EMAIL_TO — destinataire notifications offres (défaut : offres@agencemendes.ch)
  OFFRES_EMAIL_ENABLED — on/off/auto ; vide = activé si SMTP est configuré
  PUBLIC_APP_URL  — URL publique du CRM (liens fiche client / demande)

Ne jamais logger SMTP_PASSWORD.
"""
from __future__ import annotations

import html
import asyncio
import inspect
import logging
import os
import re
import smtplib
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("server")

DEFAULT_FROM_NAME = "LeoSoft"
DEFAULT_FROM_ADDRESS = "crm@agencemendes.ch"
DEFAULT_OFFRES_EMAIL_TO = "offres@agencemendes.ch"
DEFAULT_OFFICE_EMAIL_TO = "office@agencemendes.ch"

# Events that notify the conseiller (vs mailbox offres@)
CONSEILLER_OFFRE_EVENTS = frozenset(
    {
        "recue",
        "reçue",
        "offre_recue",
        "received",
        "incomplete",
        "incomplet",
        "incompletee",
        "incomplète",
        "complete",
        "offres_completes",
        "offres_complètes",
        "modifiee",
        "modification",
    }
)


def offre_notify_role(event: Optional[str]) -> str:
    """destinataire logique : createur | offres_mailbox"""
    key = (event or "envoyee").strip().lower()
    return "createur" if key in CONSEILLER_OFFRE_EVENTS else "offres_mailbox"


DEFAULT_SMTP_HOST = "mail.infomaniak.com"
DEFAULT_SMTP_PORT = 587
EMAIL_LOGS_COLLECTION = "email_logs"
MAIL_PROVIDER = "smtp_infomaniak"

MAIL_TYPE_RAPPEL = "rappel"
MAIL_TYPE_DEMANDE_OFFRE = "demande_offre"
MAIL_TYPE_DEMANDE_OFFRE_RECAP = "demande_offre_recap"
MAIL_TYPE_OFFRE_RECUE = "offre_recue"
MAIL_TYPE_OFFRES_COMPLETES = "offres_completes"
MAIL_TYPE_OFFRE_INCOMPLETE = "offre_incomplete"
MAIL_TYPE_OFFRE_SIGNEE = "offre_signee"
MAIL_TYPE_OFFRE_MODIFIEE = "offre_modifiee"
MAIL_TYPE_DOSSIER_PRESENTE = "dossier_presente"
MAIL_TYPE_TEST = "smtp_test"
MAIL_TYPE_NOTIFICATION = "notification"

# (filename, content_bytes, mime_type)
Attachment = Tuple[str, bytes, str]

BODY_TEXT_MAX = 12000
BODY_HTML_MAX = 20000

# Persist callback registered by the app (async or sync). Signature: (log_doc: dict) -> None | Awaitable
_email_log_persist = None
_pending_email_logs: List[dict] = []
_pending_lock = None  # lazy threading.Lock
_persist_tasks: set = set()  # strong refs for create_task


def _get_pending_lock():
    global _pending_lock
    if _pending_lock is None:
        import threading

        _pending_lock = threading.Lock()
    return _pending_lock


def set_email_log_persist(callback) -> None:
    """Enregistre le sink de journalisation (typiquement insert dans email_logs)."""
    global _email_log_persist
    _email_log_persist = callback


def _truncate(text: Optional[str], limit: int) -> Optional[str]:
    if text is None:
        return None
    s = str(text)
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)] + "…"


def _attachment_meta(attachments: Optional[Sequence[Attachment]]) -> List[dict]:
    out: List[dict] = []
    for att in attachments or []:
        if not att or len(att) < 1:
            continue
        name = str(att[0] or "piece-jointe")
        size = len(att[1]) if len(att) > 1 and isinstance(att[1], (bytes, bytearray)) else None
        mime = (att[2] if len(att) > 2 else None) or "application/octet-stream"
        out.append({"filename": name, "size": size, "mime": mime})
    return out


def enqueue_email_log(log_doc: dict) -> None:
    """Ajoute le log dans la file thread-safe (jamais perdu tant que le process vit)."""
    if not log_doc:
        return
    with _get_pending_lock():
        _pending_email_logs.append(log_doc)


def schedule_persist_email_log(log_doc: dict) -> None:
    """
    Persiste le journal de façon fiable :
    1) toujours enfilé (file mémoire) ;
    2) flush immédiat si une boucle asyncio tourne ;
    3) sinon flush sync si le sink est synchrone (tests / scripts).
    """
    if not log_doc:
        return
    enqueue_email_log(log_doc)
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(flush_pending_email_logs())
        _persist_tasks.add(task)
        task.add_done_callback(_persist_tasks.discard)
        return
    except RuntimeError:
        pass
    # Hors boucle asyncio : vider immédiatement si le sink est sync
    cb = _email_log_persist
    if not cb:
        return
    with _get_pending_lock():
        batch = list(_pending_email_logs)
        _pending_email_logs.clear()
    for doc in batch:
        try:
            result = cb(doc)
            if inspect.isawaitable(result):
                # Impossible d'await ici — remettre en file pour le worker startup
                enqueue_email_log(doc)
                logger.warning(
                    "email_log async sink hors boucle — remis en file id=%s",
                    doc.get("id"),
                )
        except Exception:
            logger.exception("schedule_persist sync flush failed id=%s", doc.get("id"))
            enqueue_email_log(doc)


async def _await_persist(awaitable, log_id: Optional[str]) -> None:
    try:
        await awaitable
    except Exception:
        logger.exception("Persist email_log async failed id=%s", log_id)


async def flush_pending_email_logs() -> int:
    """Vide la file d'attente vers Mongo/Postgres. Idempotent."""
    cb = _email_log_persist
    if not cb:
        return 0
    with _get_pending_lock():
        batch = list(_pending_email_logs)
        _pending_email_logs.clear()
    if not batch:
        return 0
    n = 0
    failed: List[dict] = []
    for doc in batch:
        try:
            result = cb(doc)
            if inspect.isawaitable(result):
                await result
            n += 1
        except Exception:
            logger.exception("flush pending email_log failed id=%s", doc.get("id"))
            failed.append(doc)
    if failed:
        with _get_pending_lock():
            # Remettre en tête pour retry
            _pending_email_logs[0:0] = failed
    return n


async def persist_email_log_now(log_doc: dict) -> bool:
    """Persistance immédiate et awaitée (insert ou upsert selon le sink)."""
    if not log_doc:
        return False
    cb = _email_log_persist
    if cb is None:
        enqueue_email_log(log_doc)
        logger.warning("email_logs sink non enregistré — log en file id=%s", log_doc.get("id"))
        return False
    try:
        result = cb(log_doc)
        if inspect.isawaitable(result):
            await result
        return True
    except Exception:
        logger.exception("persist_email_log_now failed id=%s", log_doc.get("id"))
        enqueue_email_log(log_doc)
        return False


async def email_log_flush_worker(stop_event: Optional[asyncio.Event] = None) -> None:
    """Worker périodique : garantit que la file est vidée même si create_task a échoué."""
    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            await flush_pending_email_logs()
        except Exception:
            logger.exception("email_log_flush_worker error")
        try:
            await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            break


def _env_flag(name: str) -> Optional[bool]:
    """None si non défini ; True/False si valeur explicite."""
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def smtp_host() -> str:
    return (os.environ.get("SMTP_HOST") or DEFAULT_SMTP_HOST).strip()


def smtp_port() -> int:
    raw = (os.environ.get("SMTP_PORT") or str(DEFAULT_SMTP_PORT)).strip()
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_SMTP_PORT


def smtp_use_ssl() -> bool:
    """SSL implicite (port 465). Prioritaire sur STARTTLS si activé."""
    flag = _env_flag("SMTP_SSL")
    if flag is True:
        return True
    if flag is False:
        return False
    return smtp_port() == 465


def smtp_use_tls() -> bool:
    """STARTTLS sur le port 587 (défaut true si pas de SSL implicite)."""
    if smtp_use_ssl():
        return False
    flag = _env_flag("SMTP_TLS")
    if flag is None:
        return True
    return flag


def smtp_user() -> str:
    return (os.environ.get("SMTP_USER") or "").strip()


def smtp_password() -> str:
    """Mot de passe SMTP — ne jamais logger la valeur retournée."""
    return (os.environ.get("SMTP_PASSWORD") or "").strip()


def smtp_configured() -> bool:
    """Transport e-mail prêt (hôte + user + password + from)."""
    if not smtp_host():
        return False
    if not smtp_user():
        return False
    if not smtp_password():
        return False
    if not smtp_from_address():
        return False
    return True


def public_app_url() -> str:
    return (os.environ.get("PUBLIC_APP_URL") or os.environ.get("FRONTEND_URL") or "").rstrip("/")


def smtp_from_address() -> str:
    return (
        os.environ.get("SMTP_FROM")
        or os.environ.get("EMAIL_FROM")
        or DEFAULT_FROM_ADDRESS
    ).strip()


def smtp_from_header() -> str:
    """From visible : « LeoSoft <crm@…> »."""
    addr = smtp_from_address()
    name = (os.environ.get("SMTP_FROM_NAME") or DEFAULT_FROM_NAME).strip()
    if name and addr:
        return formataddr((name, addr))
    return addr


def smtp_reply_to() -> str:
    explicit = (os.environ.get("SMTP_REPLY_TO") or "").strip()
    return explicit or smtp_from_address()


def offres_email_to() -> str:
    """Destinataire des demandes d'offres — configurable via OFFRES_EMAIL_TO."""
    return (os.environ.get("OFFRES_EMAIL_TO") or DEFAULT_OFFRES_EMAIL_TO).strip()


def office_email_to() -> str:
    """Destinataire office (offres signées) — configurable via OFFICE_EMAIL_TO."""
    return (os.environ.get("OFFICE_EMAIL_TO") or DEFAULT_OFFICE_EMAIL_TO).strip()


def _clean_person_part(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_clean_person_part(v) for v in value).strip()
    return str(value).strip()


def resolve_offre_client_identity(doc: dict) -> Tuple[str, str]:
    """
    Retourne (nom, prenom) pour l'objet e-mail, depuis la demande.
    Ordre de priorité : colonnes CRM → form_payload synchronisé → client_label.
    """
    nom = _clean_person_part(doc.get("nom"))
    prenom = _clean_person_part(doc.get("prenom"))
    if nom or prenom:
        return nom, prenom

    # Extraire depuis le schéma GF si présent
    form_type_id = _clean_person_part(doc.get("form_type"))
    payload = doc.get("form_payload")
    if form_type_id and form_type_id != "pilier3_legacy" and isinstance(payload, dict):
        try:
            from offre_form_types import sync_crm_fields_from_payload

            tmp = {"form_type": form_type_id}
            sync_crm_fields_from_payload(tmp, form_type_id, payload)
            nom = _clean_person_part(tmp.get("nom"))
            prenom = _clean_person_part(tmp.get("prenom"))
            if nom or prenom:
                return nom, prenom
        except Exception:
            pass

    label = _clean_person_part(doc.get("client_label"))
    if label and label not in {"—", "-", "Client", "client"}:
        parts = label.split(None, 1)
        if len(parts) == 2:
            # client_label est souvent « Prénom Nom »
            return parts[1], parts[0]
        return label, ""
    return "", ""


def format_offre_client_subject_name(doc: dict) -> str:
    """« Nom Prénom » pour l'objet e-mail (dynamique par demande)."""
    nom, prenom = resolve_offre_client_identity(doc)
    if nom and prenom:
        return f"{nom} {prenom}".strip()
    if nom:
        return nom
    if prenom:
        return prenom
    return "Client"


def build_permanent_email_subject(doc: dict) -> str:
    """
    Objet permanent d'une offre :
    {NUMERO}-{Nom Prénom} -{TYPE}
    """
    numero = (doc.get("numero") or "").strip() or "OFF-????"
    client = format_offre_client_subject_name(doc)
    form_label = (
        (doc.get("form_type_label") or doc.get("type_pilier") or "Offre").strip() or "Offre"
    )
    return f"{numero}-{client} -{form_label}"


def subject_uses_placeholder_client(subject: str) -> bool:
    """True si l'objet figé contient encore le placeholder « Client »."""
    s = (subject or "").strip()
    if not s:
        return False
    return bool(re.search(r"(?:^|[\s–—-])Client(?:[\s–—-]|$)", s, flags=re.IGNORECASE))


def resolve_email_subject(doc: dict) -> str:
    """Retourne l'objet figé s'il existe (sauf placeholder Client), sinon le construit."""
    stored = (doc.get("email_subject") or "").strip()
    if stored and not subject_uses_placeholder_client(stored):
        return stored
    return build_permanent_email_subject(doc)


def offres_email_enabled() -> bool:
    """
    Activé automatiquement si SMTP est configuré.
    Désactivable explicitement avec OFFRES_EMAIL_ENABLED=0/false/off.
    """
    flag = _env_flag("OFFRES_EMAIL_ENABLED")
    if flag is False:
        return False
    if flag is True:
        return True
    return smtp_configured()


def mail_status_public() -> dict:
    """État mail sans secrets (UI / health)."""
    ready = smtp_configured()
    return {
        "smtp_configured": ready,
        "provider": MAIL_PROVIDER,
        "smtp_from": smtp_from_address() or None,
        "smtp_from_name": (os.environ.get("SMTP_FROM_NAME") or DEFAULT_FROM_NAME).strip() or None,
        "smtp_host": smtp_host() or None,
        "smtp_port": smtp_port(),
        "smtp_user": smtp_user() or None,
        "smtp_tls": smtp_use_tls(),
        "smtp_ssl": smtp_use_ssl(),
        "offres_email_to": offres_email_to(),
        "offres_email_enabled": offres_email_enabled(),
        "email_ready": ready and offres_email_enabled(),
        "public_app_url": public_app_url() or None,
    }


def _smtp_connect() -> smtplib.SMTP:
    """
    Ouvre une session SMTP Infomaniak (SSL 465 ou STARTTLS 587 + login).
    L'appelant doit fermer avec quit()/close(). Ne log jamais le mot de passe.
    """
    host = smtp_host()
    port = smtp_port()
    user = smtp_user()
    password = smtp_password()
    context = ssl.create_default_context()

    if smtp_use_ssl():
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        server.ehlo()
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        if smtp_use_tls():
            server.starttls(context=context)
            server.ehlo()
    server.login(user, password)
    return server


def _friendly_smtp_error(exc: BaseException) -> str:
    """Message d'erreur utilisable en UI — jamais de mot de passe."""
    name = type(exc).__name__
    msg = str(exc) or name
    lower = msg.lower()
    if isinstance(exc, (TimeoutError, OSError)) or "timed out" in lower or "timeout" in lower:
        return (
            "Timeout : le serveur Railway n'arrive pas à joindre mail.infomaniak.com "
            f"(port {smtp_port()}). Sur les plans Free/Hobby, Railway bloque le SMTP sortant "
            "(ports 465/587). Solution : passer le projet Railway en plan Pro, puis redéployer. "
            "Ce n'est pas un problème de mot de passe Infomaniak."
        )
    if "connection refused" in lower or "network is unreachable" in lower:
        return (
            "Connexion refusée vers le SMTP Infomaniak depuis Railway. "
            "Vérifiez que le plan Railway autorise le SMTP sortant (Pro ou supérieur)."
        )
    if isinstance(exc, smtplib.SMTPAuthenticationError) or "auth" in lower:
        return "Authentification SMTP échouée (vérifier SMTP_USER / SMTP_PASSWORD dans Railway)"
    return f"{name}: {msg}"[:500]


def test_smtp_connection() -> Tuple[bool, Optional[str]]:
    """Vérifie connexion + auth SMTP Infomaniak (sans envoi)."""
    if not smtp_configured():
        return False, "SMTP non configuré (SMTP_HOST / SMTP_USER / SMTP_PASSWORD / SMTP_FROM)"
    try:
        logger.info(
            "SMTP: test connexion host=%s port=%s user=%s ssl=%s tls=%s",
            smtp_host(),
            smtp_port(),
            smtp_user(),
            smtp_use_ssl(),
            smtp_use_tls(),
        )
        server = _smtp_connect()
        try:
            server.noop()
        finally:
            try:
                server.quit()
            except Exception:
                server.close()
        logger.info("SMTP: connexion OK host=%s user=%s", smtp_host(), smtp_user())
        return True, None
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP: authentification échouée user=%s (mot de passe non loggé)", smtp_user())
        return False, "Authentification SMTP échouée (vérifier SMTP_USER / SMTP_PASSWORD)"
    except Exception as e:
        friendly = _friendly_smtp_error(e)
        logger.error("SMTP: test connexion échoué host=%s — %s", smtp_host(), friendly)
        return False, friendly


def rappel_email_grace_minutes() -> int:
    raw = (os.environ.get("RAPPEL_EMAIL_GRACE_MINUTES") or "120").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 120


_LOG_PROTECTED_KEYS = frozenset({
    "id", "type", "to", "to_email", "from", "cc", "bcc", "subject", "status", "error",
    "body_preview", "body_text", "body_html", "created_at", "sent_at", "provider",
    "attachments", "message_id",
})


def normalize_email_status(status: Optional[str]) -> str:
    """Normalise un statut journal : sent | pending | skipped | error."""
    status_norm = (status or "").strip().lower()
    if not status_norm:
        return ""
    if status_norm in {"sent", "ok", "success"}:
        return "sent"
    if status_norm in {"pending", "en_cours", "in_progress", "processing"}:
        return "pending"
    if status_norm in {"skipped", "skip"}:
        return "skipped"
    if status_norm in {"error", "failed", "fail"}:
        return "error"
    return "error"


def build_email_log(
    *,
    mail_type: str,
    to_email: str,
    subject: str,
    status: str,
    error: Optional[str] = None,
    body_preview: Optional[str] = None,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    client_id: Optional[str] = None,
    dossier_id: Optional[str] = None,
    ref_id: Optional[str] = None,
    ref_ids: Optional[List[str]] = None,
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    user_id: Optional[str] = None,
    created_by: Optional[str] = None,
    attachments: Optional[Sequence[Any]] = None,
    module: Optional[str] = None,
    message_id: Optional[str] = None,
    log_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Document journal unifié (collection email_logs)."""
    text_full = body_text if body_text is not None else body_preview
    preview_src = body_preview if body_preview is not None else text_full
    preview = _truncate((preview_src or "").strip(), 800)
    now_iso = datetime.now(timezone.utc).isoformat()
    status_out = normalize_email_status(status) or "error"
    doc = {
        "id": log_id or str(uuid.uuid4()),
        "type": mail_type or MAIL_TYPE_NOTIFICATION,
        "to": (to_email or "").strip(),
        "to_email": (to_email or "").strip(),
        "from": smtp_from_address() or None,
        "cc": list(cc or []),
        "bcc": list(bcc or []),
        "subject": (subject or "").strip(),
        "status": status_out,
        "error": error,
        "body_preview": preview or None,
        "body_text": _truncate(text_full, BODY_TEXT_MAX),
        "body_html": _truncate(body_html, BODY_HTML_MAX) if body_html else None,
        "client_id": client_id,
        "dossier_id": dossier_id,
        "ref_id": ref_id,
        "ref_ids": list(ref_ids or ([ref_id] if ref_id else [])),
        "user_id": user_id,
        "created_by": created_by,
        "created_at": now_iso,
        "sent_at": now_iso if status_out != "pending" else None,
        "provider": MAIL_PROVIDER,
        "module": module,
        "attachments": list(attachments or []),
        "message_id": (message_id or "").strip() or None,
    }
    if extra:
        for k, v in extra.items():
            if k in _LOG_PROTECTED_KEYS:
                continue
            if k in doc and doc[k] not in (None, "", [], {}):
                continue
            doc[k] = v
    return doc


def _compose_send_log_doc(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str],
    cc: Optional[Sequence[str]],
    bcc: Optional[Sequence[str]],
    attachments: Optional[Sequence[Attachment]],
    mail_type: Optional[str],
    log_meta: Optional[dict],
    status: str,
    error: Optional[str],
    message_id: Optional[str] = None,
    log_id: Optional[str] = None,
) -> dict:
    meta = dict(log_meta or {})
    type_key = (
        mail_type
        or meta.pop("type", None)
        or meta.pop("mail_type", None)
        or MAIL_TYPE_NOTIFICATION
    )
    log_doc = build_email_log(
        mail_type=str(type_key),
        to_email=to_email,
        subject=subject or "",
        status=status,
        error=error,
        body_text=body_text,
        body_html=body_html,
        body_preview=body_text,
        client_id=meta.get("client_id"),
        dossier_id=meta.get("dossier_id"),
        ref_id=meta.get("ref_id"),
        ref_ids=meta.get("ref_ids"),
        cc=cc,
        bcc=bcc,
        user_id=meta.get("user_id"),
        created_by=meta.get("created_by"),
        attachments=_attachment_meta(attachments),
        module=meta.get("module"),
        message_id=message_id,
        log_id=log_id,
        extra={
            k: v
            for k, v in meta.items()
            if k
            not in {
                "client_id",
                "dossier_id",
                "ref_id",
                "ref_ids",
                "user_id",
                "created_by",
                "module",
                "type",
                "mail_type",
                "status",
                "error",
                "subject",
                "bcc",
                "message_id",
            }
        },
    )
    if not (log_doc.get("subject") or "").strip():
        log_doc["subject"] = subject or ""
    return log_doc


def _smtp_deliver(
    to_email: str,
    subject: str,
    body_text: str,
    *,
    body_html: Optional[str] = None,
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    attachments: Optional[Sequence[Attachment]] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Envoi SMTP pur — sans journalisation. Retourne (ok, erreur, message_id)."""
    to_email = (to_email or "").strip()
    if not to_email:
        return False, "destinataire vide", None
    if not smtp_configured():
        return False, "SMTP non configuré", None

    msg, cc_clean, bcc_clean = _build_message(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )
    message_id = (msg.get("Message-ID") or "").strip() or None
    recipients = [to_email] + cc_clean + bcc_clean
    logger.info(
        "SMTP: tentative envoi to=%s from=%s subject=%r cc=%s host=%s",
        to_email,
        smtp_from_address(),
        subject,
        cc_clean or None,
        smtp_host(),
    )
    try:
        server = _smtp_connect()
        try:
            server.send_message(msg, from_addr=smtp_from_address(), to_addrs=recipients)
        finally:
            try:
                server.quit()
            except Exception:
                server.close()
        logger.info("SMTP: succès to=%s subject=%r message_id=%s", to_email, subject, message_id)
        return True, None, message_id
    except smtplib.SMTPAuthenticationError:
        err = "Authentification SMTP échouée (vérifier SMTP_USER / SMTP_PASSWORD)"
        logger.error("SMTP: erreur auth to=%s subject=%r — %s", to_email, subject, err)
        return False, err, message_id
    except Exception as e:
        err = _friendly_smtp_error(e)
        logger.error("SMTP: exception to=%s subject=%r — %s", to_email, subject, err)
        return False, err, message_id


def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    *,
    body_html: Optional[str] = None,
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    attachments: Optional[Sequence[Attachment]] = None,
    mail_type: Optional[str] = None,
    log_meta: Optional[dict] = None,
    persist_log: bool = True,
) -> Tuple[bool, Optional[str]]:
    """
    Envoie un e-mail via SMTP Infomaniak.
    Retourne (ok, erreur_ou_None).

    Le statut journalisé est STRICTEMENT le résultat SMTP :
    - sent  → send_message a réussi
    - error → échec réel (destinataire vide, SMTP down, exception)

    (Pas de statut « pending » ici : chemin sync — journal post-SMTP uniquement.)
    """
    to_email = (to_email or "").strip()
    ok, err, message_id = _smtp_deliver(
        to_email,
        subject,
        body_text,
        body_html=body_html,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )
    if persist_log:
        status = "sent" if ok else "error"
        log_doc = _compose_send_log_doc(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            mail_type=mail_type,
            log_meta=log_meta,
            status=status,
            error=err,
            message_id=message_id,
        )
        schedule_persist_email_log(log_doc)
    return ok, err


async def send_email_async(
    to_email: str,
    subject: str,
    body_text: str,
    *,
    body_html: Optional[str] = None,
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    attachments: Optional[Sequence[Attachment]] = None,
    mail_type: Optional[str] = None,
    log_meta: Optional[dict] = None,
    persist_log: bool = True,
) -> Tuple[bool, Optional[str]]:
    """
    Variante async : journal « pending » avant SMTP, puis sent/error après acceptation SMTP.
    À utiliser depuis les routes FastAPI / jobs async.
    """
    to_email = (to_email or "").strip()
    log_id = str(uuid.uuid4()) if persist_log else None
    if persist_log:
        pending_doc = _compose_send_log_doc(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            mail_type=mail_type,
            log_meta=log_meta,
            status="pending",
            error=None,
            log_id=log_id,
        )
        await persist_email_log_now(pending_doc)

    ok, err, message_id = await asyncio.to_thread(
        _smtp_deliver,
        to_email,
        subject,
        body_text,
        body_html=body_html,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )
    if persist_log:
        status = "sent" if ok else "error"
        log_doc = _compose_send_log_doc(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            mail_type=mail_type,
            log_meta=log_meta,
            status=status,
            error=err,
            message_id=message_id,
            log_id=log_id,
        )
        # Conserver created_at du pending si déjà en base (via upsert $set partiel côté sink)
        await persist_email_log_now(log_doc)
    return ok, err


def _build_message(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    attachments: Optional[Sequence[Attachment]] = None,
) -> Tuple[EmailMessage, List[str], List[str]]:
    mail_from = smtp_from_address()
    from_header = smtp_from_header()
    reply_to = smtp_reply_to()

    cc_clean: List[str] = []
    for addr in cc or []:
        a = (addr or "").strip()
        if a and a.lower() != to_email.lower() and a not in cc_clean:
            cc_clean.append(a)

    bcc_clean: List[str] = []
    for addr in bcc or []:
        a = (addr or "").strip()
        if (
            a
            and a.lower() != to_email.lower()
            and a not in cc_clean
            and a not in bcc_clean
        ):
            bcc_clean.append(a)

    msg = EmailMessage()
    msg["Subject"] = subject or ""
    msg["From"] = from_header if "<" in from_header else formataddr((DEFAULT_FROM_NAME, mail_from))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=(mail_from.split("@")[-1] if mail_from and "@" in mail_from else "leosoft.ch"))
    if reply_to:
        msg["Reply-To"] = reply_to
    if cc_clean:
        msg["Cc"] = ", ".join(cc_clean)
    # Bcc n'est PAS mis dans les en-têtes visibles — uniquement dans to_addrs SMTP

    text = body_text or ""
    if body_html:
        msg.set_content(text)
        msg.add_alternative(body_html, subtype="html")
    else:
        msg.set_content(text)

    for att in attachments or []:
        if not att or len(att) < 2:
            continue
        filename = str(att[0] or "piece-jointe")
        data = att[1]
        mime = (att[2] if len(att) > 2 else None) or "application/octet-stream"
        if not isinstance(data, (bytes, bytearray)):
            continue
        maintype, _, subtype = mime.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(
            bytes(data),
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )

    return msg, cc_clean, bcc_clean


def _format_date_fr(date_str: str) -> str:
    raw = (date_str or "").strip()[:10]
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        y, m, d = raw.split("-")
        return f"{d}/{m}/{y}"
    return raw or "—"


def _client_url(client_id: Optional[str], *, tab: Optional[str] = None) -> Optional[str]:
    base = public_app_url()
    if base and client_id:
        url = f"{base}/clients/{client_id}"
        if tab:
            return f"{url}?tab={tab}"
        return url
    return None


def _analyse_prevoyance_url(client_id: Optional[str]) -> Optional[str]:
    """Lien absolu vers l'onglet « Analyse de prévoyance » (ClientDetail tab=analyse-prevoyance)."""
    return _client_url(client_id, tab="analyse-prevoyance")


def _demande_offre_url(demande_id: Optional[str]) -> Optional[str]:
    base = public_app_url()
    if base and demande_id:
        return f"{base}/demandes-offres/{demande_id}"
    return None


def _html_button(url: str, label: str = "Voir le dossier client") -> str:
    safe_url = html.escape(url, quote=True)
    safe_label = html.escape(label)
    return (
        f'<p style="margin:16px 0;">'
        f'<a href="{safe_url}" style="display:inline-block;background:#002FA7;color:#ffffff;'
        f"text-decoration:none;padding:10px 18px;border-radius:6px;font-weight:600;"
        f'font-family:Arial,sans-serif;font-size:14px;">{safe_label}</a></p>'
    )


def _when_label(date_str: str, heure: Optional[str]) -> str:
    date_fr = _format_date_fr(date_str)
    heure_txt = (heure or "").strip()
    return f"{date_fr} à {heure_txt}" if heure_txt else date_fr


def format_rappel_notification(
    *,
    client_name: str,
    titre: str,
    date_str: str,
    heure: Optional[str],
    client_id: Optional[str],
    description: Optional[str] = None,
    is_relance: bool = False,
) -> Tuple[str, str, str]:
    """
    Retourne (subject, body_text, body_html).
    Objet : 🔔 Rappel LeoSoft – {titre}  ou  🔁 Relance LeoSoft – {titre}
    """
    name = (client_name or "Client").strip() or "Client"
    titre_txt = (titre or "Rappel").strip() or "Rappel"
    when = _when_label(date_str, heure)
    if is_relance:
        subject = f"🔁 Relance LeoSoft – {titre_txt}"
        intro = "Ceci est une relance automatique : le rappel est toujours ouvert."
    else:
        subject = f"🔔 Rappel LeoSoft – {titre_txt}"
        intro = "Ceci est une notification automatique de LeoSoft."

    lines = [
        f"Client : {name}",
        f"Objet du rappel : {titre_txt}",
        f"Date et heure : {when}",
    ]
    if (description or "").strip():
        lines.extend(["", "Détails :", description.strip()])
    url = _client_url(client_id)
    if url:
        lines.extend(["", f"Voir le dossier client : {url}"])
    lines.extend(["", "—", intro])
    body_text = "\n".join(lines)

    html_parts = [
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;line-height:1.5;">',
    ]
    if is_relance:
        html_parts.append(
            '<p style="color:#b45309;font-weight:600;">Relance automatique — ce rappel n\'est pas encore effectué.</p>'
        )
    html_parts.extend([
        f"<p><strong>Client :</strong> {html.escape(name)}</p>",
        f"<p><strong>Objet du rappel :</strong> {html.escape(titre_txt)}</p>",
        f"<p><strong>Date et heure :</strong> {html.escape(when)}</p>",
    ])
    if (description or "").strip():
        html_parts.append(
            f"<p><strong>Détails :</strong><br/>{html.escape(description.strip()).replace(chr(10), '<br/>')}</p>"
        )
    if url:
        html_parts.append(_html_button(url))
    html_parts.append(f'<p style="color:#666;font-size:12px;margin-top:24px;">— {html.escape(intro)}</p>')
    html_parts.append("</div>")
    return subject, body_text, "".join(html_parts)


def format_rappels_batch(
    items: List[Dict[str, Any]],
    *,
    when_label: str,
    is_relance: bool = False,
) -> Tuple[str, str, str]:
    """
    E-mail récapitulatif pour plusieurs rappels à la même heure.
    items: dicts avec client_name, titre, description, client_id, date, heure
    """
    n = len(items)
    if n == 1:
        it = items[0]
        return format_rappel_notification(
            client_name=it.get("client_name") or "Client",
            titre=it.get("titre") or "Rappel",
            date_str=it.get("date") or "",
            heure=it.get("heure"),
            client_id=it.get("client_id"),
            description=it.get("description"),
            is_relance=is_relance,
        )

    if is_relance:
        subject = f"🔁 Relance LeoSoft – {n} rappels encore ouverts"
        text_lines = [
            f"Relance automatique : {n} rappel(s) toujours ouverts ({when_label}) :",
            "",
        ]
        html_parts = [
            '<div style="font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;line-height:1.5;">',
            f"<p style=\"color:#b45309;font-weight:600;\">Relance automatique — {n} rappel(s) encore ouverts ({html.escape(when_label)}) :</p>",
        ]
    else:
        subject = f"🔔 Rappel LeoSoft – {n} rappels à {when_label}"
        text_lines = [
            f"Vous avez {n} rappels prévus ({when_label}) :",
            "",
        ]
        html_parts = [
            '<div style="font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;line-height:1.5;">',
            f"<p>Vous avez <strong>{n}</strong> rappels prévus (<strong>{html.escape(when_label)}</strong>) :</p>",
        ]

    for i, it in enumerate(items, 1):
        name = (it.get("client_name") or "Client").strip() or "Client"
        titre = (it.get("titre") or "Rappel").strip() or "Rappel"
        desc = (it.get("description") or "").strip()
        url = _client_url(it.get("client_id"))
        text_lines.append(f"{i}. {name} — {titre}")
        if desc:
            text_lines.append(f"   Détails : {desc}")
        if url:
            text_lines.append(f"   Voir le dossier : {url}")
        text_lines.append("")

        html_parts.append(
            '<div style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;margin:12px 0;">'
            f"<p style='margin:0 0 6px;'><strong>{i}. {html.escape(name)}</strong></p>"
            f"<p style='margin:0 0 6px;'>{html.escape(titre)}</p>"
        )
        if desc:
            html_parts.append(
                f"<p style='margin:0 0 8px;color:#555;'>{html.escape(desc).replace(chr(10), '<br/>')}</p>"
            )
        if url:
            html_parts.append(_html_button(url))
        html_parts.append("</div>")

    text_lines.extend(["—", "Ceci est une notification automatique de LeoSoft."])
    html_parts.append('<p style="color:#666;font-size:12px;margin-top:24px;">— Ceci est une notification automatique de LeoSoft.</p>')
    html_parts.append("</div>")
    return subject, "\n".join(text_lines), "".join(html_parts)


def _agent_greeting_prenom(doc: dict) -> str:
    """Prénom du conseiller pour la salutation e-mail."""
    prenom = _clean_person_part(doc.get("agent_prenom"))
    if prenom:
        return prenom
    label = _clean_person_part(doc.get("agent_label"))
    if label:
        return label.split(None, 1)[0]
    return ""


def format_demande_offre_email(doc: dict) -> Tuple[str, str, str]:
    """
    E-mail récapitulatif à l'envoi d'une demande d'offre (boîte offres@).
    Objet permanent : {NUMERO}-{CLIENT} -{TYPE}
    """
    client = _offre_client_name(doc)
    form_label = (doc.get("form_type_label") or doc.get("type_pilier") or "Offre").strip() or "Offre"
    numero = (doc.get("numero") or "").strip()
    subject = resolve_email_subject(doc)

    intro_lines = [
        "Une nouvelle offre a été envoyée depuis le CRM.",
        "",
        f"N° / référence : {numero or '—'}",
        f"Client : {client}",
        f"Type d'offre : {form_label}",
        f"Statut : {doc.get('statut') or 'Demande envoyée'}",
    ]
    field_rows = _collect_filled_offre_fields(doc)
    body_text, body_html = _compose_offre_email(
        intro_lines=intro_lines,
        intro_html="<p><strong>Une nouvelle offre a été envoyée depuis le CRM.</strong></p>",
        field_rows=field_rows,
        doc=doc,
        highlight_rows=None,
    )
    return subject, body_text, body_html


def format_demande_offre_recap_conseiller_email(doc: dict) -> Tuple[str, str, str]:
    """
    Copie récapitulative destinée au conseiller qui a créé / envoyé la demande.
    Objet : Récapitulatif de votre demande d'offre – [Client] – [N°]
    """
    client = _offre_client_name(doc)
    form_label = (doc.get("form_type_label") or doc.get("type_pilier") or "Offre").strip() or "Offre"
    numero = (doc.get("numero") or "").strip()
    subject = f"Récapitulatif de votre demande d’offre – {client} – {numero or '—'}"

    prenom = _agent_greeting_prenom(doc)
    greeting = f"Bonjour {prenom}," if prenom else "Bonjour,"
    intro_lines = [
        greeting,
        "",
        "Voici le récapitulatif de votre demande d’offre envoyée depuis Leosoft.",
        "",
        f"N° / référence : {numero or '—'}",
        f"Client : {client}",
        f"Type d'offre : {form_label}",
        f"Statut : {doc.get('statut') or 'Demande envoyée'}",
    ]
    field_rows = _collect_filled_offre_fields(doc)
    greeting_html = html.escape(greeting)
    body_text, body_html = _compose_offre_email(
        intro_lines=intro_lines,
        intro_html=(
            f"<p>{greeting_html}</p>"
            "<p>Voici le récapitulatif de votre demande d’offre envoyée depuis Leosoft.</p>"
        ),
        field_rows=field_rows,
        doc=doc,
        highlight_rows=None,
    )
    return subject, body_text, body_html


def format_offre_recue_email(doc: dict, offer: Optional[dict] = None) -> Tuple[str, str, str]:
    """
    Notification conseiller : une offre compagnie a été enregistrée (« Offre reçue »).
    Inclut le récapitulatif complet schéma-driven de la demande + deep link fiche.
    """
    client = _offre_client_name(doc)
    numero = (doc.get("numero") or "").strip()
    form_label = (doc.get("form_type_label") or doc.get("type_pilier") or "Offre").strip() or "Offre"
    subject = f"Offre reçue – {client} – {numero or '—'}"

    prenom = _agent_greeting_prenom(doc)
    greeting = f"Bonjour {prenom}," if prenom else "Bonjour,"
    intro_lines = [
        greeting,
        "",
        f"Vous avez reçu une offre pour {client}.",
        "",
        f"N° / référence : {numero or '—'}",
        f"Client : {client}",
        f"Type d'offre : {form_label}",
        f"Statut : {doc.get('statut') or 'Offre reçue'}",
    ]
    offer = offer if isinstance(offer, dict) else {}
    if offer.get("compagnie"):
        intro_lines.append(f"Compagnie : {offer.get('compagnie')}")
    if offer.get("reference"):
        intro_lines.append(f"Référence compagnie : {offer.get('reference')}")
    if offer.get("date_reception"):
        try:
            from swiss_dates import format_swiss_date

            dr = format_swiss_date(offer.get("date_reception")) or str(offer.get("date_reception"))
        except Exception:
            dr = str(offer.get("date_reception"))
        intro_lines.append(f"Date de réception : {dr}")

    field_rows = _collect_filled_offre_fields(doc, include_empty=True)
    greeting_html = html.escape(greeting)
    safe_client = html.escape(client)
    body_text, body_html = _compose_offre_email(
        intro_lines=intro_lines,
        intro_html=(
            f"<p>{greeting_html}</p>"
            f"<p>Vous avez reçu une offre pour <strong>{safe_client}</strong>.</p>"
        ),
        field_rows=field_rows,
        doc=doc,
        highlight_rows=None,
    )
    return subject, body_text, body_html


def format_offres_completes_email(
    doc: dict,
    *,
    note: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Notification conseiller : toutes les offres demandées sont complètes et disponibles.
    Inclut une note optionnelle du gestionnaire + lien profond fiche demande.
    """
    client = _offre_client_name(doc)
    subject = f"Vos offres sont complètes – {client}"

    prenom = _agent_greeting_prenom(doc)
    greeting = f"Bonjour {prenom}," if prenom else "Bonjour,"
    url = _demande_offre_url(doc.get("id"))
    link_label = "Voir les offres dans LeoSoft"
    note_text = (note or doc.get("message_conseiller") or "").strip()

    text_lines = [
        greeting,
        "",
        f"Les offres concernant {client} sont maintenant complètes et disponibles dans LeoSoft.",
    ]
    if note_text:
        text_lines.extend(["", "Note du gestionnaire :", note_text])
    text_lines.extend(["", "Vous pouvez consulter les offres directement ici :"])
    if url:
        text_lines.extend(["", f"{link_label} :", url])
    else:
        text_lines.extend(["", "(Lien indisponible — ouvrez la demande dans LeoSoft.)"])
    text_lines.extend(["", "Cordialement,", "LeoSoft"])
    body_text = "\n".join(text_lines)

    safe_client = html.escape(client)
    safe_greeting = html.escape(greeting)
    html_parts = [
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;line-height:1.5;">',
        f"<p>{safe_greeting}</p>",
        f"<p>Les offres concernant <strong>{safe_client}</strong> sont maintenant complètes et disponibles dans LeoSoft.</p>",
    ]
    if note_text:
        html_parts.append(
            "<p><strong>Note du gestionnaire :</strong><br/>"
            + html.escape(note_text).replace("\n", "<br/>")
            + "</p>"
        )
    html_parts.append("<p>Vous pouvez consulter les offres directement ici :</p>")
    if url:
        html_parts.append(_html_button(url, link_label))
    html_parts.append("<p>Cordialement,<br/>LeoSoft</p></div>")
    return subject, body_text, "".join(html_parts)


def format_demande_incomplete_email(
    doc: dict,
    *,
    comment: Optional[str] = None,
) -> Tuple[str, str, str]:
    """
    Notification : offre déclarée incomplète → conseiller de la demande.
    Objet = objet permanent (inchangé).
    """
    client = _offre_client_name(doc)
    numero = (doc.get("numero") or "").strip()
    form_label = (doc.get("form_type_label") or doc.get("type_pilier") or "").strip()
    reason = (comment or doc.get("incomplete_comment") or "").strip() or "Non précisée"
    extra_comment = (
        (doc.get("incomplete_notes") or doc.get("incomplete_extra_comment") or "").strip()
    )
    if extra_comment and extra_comment == reason:
        extra_comment = ""
    signaled_by = (doc.get("incomplete_by") or "—").strip() or "—"
    signaled_at_raw = (doc.get("incomplete_at") or "").strip()
    signaled_at = signaled_at_raw
    try:
        if signaled_at_raw:
            dt = datetime.fromisoformat(signaled_at_raw.replace("Z", "+00:00"))
            signaled_at = dt.astimezone().strftime("%d.%m.%Y à %H:%M")
    except Exception:
        signaled_at = signaled_at_raw or "—"

    subject = resolve_email_subject(doc)

    erreurs = list(doc.get("erreurs_incomplete") or [])
    erreurs_lines = []
    for err in erreurs:
        code = (err.get("label") or err.get("code") or "").strip()
        detail = (err.get("detail") or "").strip()
        if code and detail:
            erreurs_lines.append(f"- {code} : {detail}")
        elif code or detail:
            erreurs_lines.append(f"- {code or detail}")

    intro_lines = [
        "Votre demande d'offre nécessite des informations complémentaires.",
        "",
        f"Client : {client}",
        f"Référence : {numero or '—'}",
    ]
    if form_label:
        intro_lines.append(f"Type d'offre : {form_label}")
    intro_lines.extend(
        [
            "Statut : Demande incomplète",
            f"Motif : {reason}",
        ]
    )
    if erreurs_lines:
        intro_lines.append("Éléments manquants / incorrects :")
        intro_lines.extend(erreurs_lines)
    if extra_comment:
        intro_lines.append(f"Commentaire : {extra_comment}")
    intro_lines.extend(
        [
            f"Signalée par : {signaled_by}",
            f"Date et heure : {signaled_at or '—'}",
        ]
    )

    reason_html = html.escape(reason).replace("\n", "<br/>")
    intro_html = (
        "<p><strong>Votre demande d'offre nécessite des informations complémentaires.</strong></p>"
        f"<p><strong>Client</strong> : {html.escape(client)}<br/>"
        f"<strong>Référence</strong> : {html.escape(numero or '—')}<br/>"
    )
    if form_label:
        intro_html += f"<strong>Type d'offre</strong> : {html.escape(form_label)}<br/>"
    intro_html += (
        "<strong>Statut</strong> : Demande incomplète<br/>"
        f"<strong>Motif</strong> : {reason_html}<br/>"
    )
    if erreurs_lines:
        intro_html += "<strong>Éléments manquants / incorrects</strong> :<ul>"
        for line in erreurs_lines:
            intro_html += f"<li>{html.escape(line.lstrip('- ').strip())}</li>"
        intro_html += "</ul>"
    if extra_comment:
        intro_html += (
            f"<strong>Commentaire</strong> : "
            f"{html.escape(extra_comment).replace(chr(10), '<br/>')}<br/>"
        )
    intro_html += (
        f"<strong>Signalée par</strong> : {html.escape(signaled_by)}<br/>"
        f"<strong>Date et heure</strong> : {html.escape(signaled_at or '—')}</p>"
    )

    field_rows = _collect_filled_offre_fields(doc)
    body_text, body_html = _compose_offre_email(
        intro_lines=intro_lines,
        intro_html=intro_html,
        field_rows=field_rows,
        doc=doc,
    )
    return subject, body_text, body_html


def format_offre_signee_email(doc: dict, *, signature: Optional[dict] = None) -> Tuple[str, str, str]:
    """Offre signée — même objet permanent, corps spécifique."""
    client = _offre_client_name(doc)
    numero = (doc.get("numero") or "").strip()
    subject = resolve_email_subject(doc)
    sig = signature if isinstance(signature, dict) else (doc.get("signature") or {})
    intro_lines = [
        "Une offre a été signée par le client.",
        "",
        f"N° / référence : {numero or '—'}",
        f"Client : {client}",
        f"Date de signature : {(sig.get('date_signature') or '—')}",
        f"Enregistrée par : {(sig.get('recorded_by') or '—')}",
    ]
    if sig.get("commentaire"):
        intro_lines.append(f"Commentaire : {sig.get('commentaire')}")
    body_text, body_html = _compose_offre_email(
        intro_lines=intro_lines,
        intro_html="<p><strong>Une offre a été signée par le client.</strong></p>",
        field_rows=_collect_filled_offre_fields(doc),
        doc=doc,
    )
    return subject, body_text, body_html


def format_offre_modifiee_email(
    doc: dict,
    *,
    changes: Optional[list] = None,
    note: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Demande de modification d'une offre existante — même objet permanent."""
    client = _offre_client_name(doc)
    numero = (doc.get("numero") or "").strip()
    subject = resolve_email_subject(doc)
    changes = changes or doc.get("modifications") or []
    note = (note or doc.get("note_service_offre") or "").strip()
    intro_lines = [
        "Une demande de modification d'offre a été envoyée depuis le CRM.",
        "",
        f"N° / référence : {numero or '—'}",
        f"Client : {client}",
        "Événement : Offre à modifier",
    ]
    if changes:
        intro_lines.append("")
        intro_lines.append("Modifications :")
        for ch in changes:
            field = ch.get("label") or ch.get("field") or "Champ"
            old = ch.get("old")
            new = ch.get("new")
            intro_lines.append(f"- {field} : {old!s} → {new!s}")
    if note:
        intro_lines.extend(["", f"Note au service Offre : {note}"])
    body_text, body_html = _compose_offre_email(
        intro_lines=intro_lines,
        intro_html="<p><strong>Une demande de modification d'offre a été envoyée.</strong></p>",
        field_rows=_collect_filled_offre_fields(doc),
        doc=doc,
    )
    return subject, body_text, body_html


def format_client_prenom_nom(client: Optional[dict]) -> str:
    """Affichage « Prénom NOM » pour notifications dossier."""
    c = client or {}
    prenom = (c.get("prenom") or "").strip()
    nom = (c.get("nom") or "").strip()
    if prenom or nom:
        return f"{prenom} {nom.upper()}".strip()
    label = (c.get("dossier_label") or c.get("name") or "").strip()
    return label or "Client"


def format_dossier_presente_email(client: dict) -> Tuple[str, str, str]:
    """
    Notification conseiller : dossier marqué « À présenter » avec analyse disponible.
    Formulation : dossier prêt à être présenté (pas déjà présenté).
    """
    client_name = format_client_prenom_nom(client)
    subject = f"Dossier prêt à être présenté – {client_name}"
    url = _analyse_prevoyance_url((client or {}).get("id"))
    btn_label = "👉 Ouvrir l’analyse de prévoyance"
    body_text = (
        "Bonjour,\n"
        "\n"
        f"Le dossier de {client_name} est prêt à être présenté.\n"
        "\n"
        "L’analyse de prévoyance est disponible dans son dossier sur Leosoft.\n"
    )
    if url:
        body_text += f"\n{btn_label} :\n{url}\n"
    body_text += (
        "\n"
        "Bonne journée,\n"
        "Leosoft\n"
    )
    safe = html.escape(client_name)
    body_html = (
        "<p>Bonjour,</p>"
        f"<p>Le dossier de <strong>{safe}</strong> est prêt à être présenté.</p>"
        "<p>L’analyse de prévoyance est disponible dans son dossier sur Leosoft.</p>"
    )
    if url:
        body_html += _html_button(url, btn_label)
    body_html += "<p>Bonne journée,<br/>Leosoft</p>"
    return subject, body_text, body_html


# --- Labels & dump dynamique des champs d'offre ---

_OFFRE_FIELD_LABELS: Dict[str, str] = {
    "numero": "N° demande",
    "statut": "Statut",
    "form_type_label": "Type d'offre",
    "form_type": "Code formulaire",
    "form_category": "Catégorie",
    "civilite": "Civilité",
    "nom": "Nom",
    "prenom": "Prénom",
    "sexe": "Sexe",
    "date_naissance": "Date de naissance",
    "nationalite": "Nationalité",
    "permis": "Permis",
    "adresse": "Adresse",
    "ville": "Ville",
    "npa": "NPA",
    "pays": "Pays",
    "statut_professionnel": "Statut professionnel",
    "profession": "Profession",
    "travail_bureau_80": "Travail de bureau ≥ 80 %",
    "affilie_lpp": "Affilié LPP",
    "fumeur": "Fumeur",
    "situation": "Situation",
    "activites_risque": "Activités à risque",
    "activites_risque_liste": "Liste activités à risque",
    "type_pilier": "Type de pilier",
    "date_debut": "Date de début",
    "periodicite_prime": "Périodicité de prime",
    "montant_prime": "Montant de prime",
    "deja_piliers_pax": "Déjà des piliers Pax",
    "type_paiement": "Type de paiement",
    "duree_contrat": "Durée du contrat",
    "age_terme": "Âge terme",
    "exoneration_primes": "Exonération de primes",
    "rente_invalidite": "Rente invalidité",
    "diplome": "Diplôme",
    "adaptation_auto_primes": "Adaptation auto des primes",
    "risque_pur": "Risque pur",
    "taille": "Taille",
    "poids": "Poids",
    "renseignements_complementaires": "Renseignements complémentaires",
    "compagnies": "Compagnies",
    "commentaires": "Commentaires / informations complémentaires",
    "inclure_cga": "Inclure CGA",
    "date_prochain_rdv": "Date prochain RDV",
    "langue_offre": "Langue de l'offre",
    "mandat_gestion": "Mandat de gestion",
    "agent_label": "Agent",
    "agent_prenom": "Agent — prénom",
    "agent_nom": "Agent — nom",
    "agent_email": "Agent — e-mail",
    "agent_finma": "Agent — FINMA",
    "date_envoi": "Date d'envoi",
    "incomplete_comment": "Raison incomplète",
    "incomplete_by": "Signalée incomplète par",
    "incomplete_at": "Signalée incomplète le",
}

_OFFRE_SKIP_KEYS = frozenset({
    "_id", "id", "user_id", "created_by", "created_at", "updated_at",
    "historique", "is_deleted", "form_payload", "offres", "offre",
    "offre_choisie_id", "envoi_client", "conclusion", "signature", "annulation",
    "email_sent", "email_error", "documents", "docs", "client_id",
    "incomplete_status", "storage_path", "docx_storage_path",
    "email_subject", "created_by_account_id", "created_by_email",
    "created_by_name", "tenant_id", "client_label",
})

# Infos générales toujours utiles (indépendantes du type de formulaire)
_OFFRE_GENERAL_KEYS: Tuple[str, ...] = (
    "numero",
    "form_type_label",
    "form_category",
    "statut",
    "civilite",
    "prenom",
    "nom",
    "langue_offre",
    "agent_label",
    "agent_prenom",
    "agent_nom",
    "agent_email",
    "agent_finma",
    "date_envoi",
    "compagnies",
    "commentaires",
)

# Champs CRM du wizard legacy 3P uniquement (jamais injectés sur les formulaires schéma)
_OFFRE_LEGACY_EXTRA_KEYS: Tuple[str, ...] = (
    "sexe",
    "date_naissance",
    "nationalite",
    "permis",
    "adresse",
    "ville",
    "npa",
    "pays",
    "statut_professionnel",
    "profession",
    "travail_bureau_80",
    "affilie_lpp",
    "fumeur",
    "situation",
    "activites_risque",
    "activites_risque_liste",
    "type_pilier",
    "date_debut",
    "periodicite_prime",
    "montant_prime",
    "deja_piliers_pax",
    "type_paiement",
    "duree_contrat",
    "age_terme",
    "exoneration_primes",
    "rente_invalidite",
    "diplome",
    "adaptation_auto_primes",
    "risque_pur",
    "taille",
    "poids",
    "renseignements_complementaires",
    "inclure_cga",
    "date_prochain_rdv",
    "mandat_gestion",
)


def _offre_client_name(doc: dict) -> str:
    """Nom affiché dans le corps des e-mails (Prénom Nom), sans changer le format du corps."""
    nom, prenom = resolve_offre_client_identity(doc)
    name = f"{prenom} {nom}".strip()
    if name:
        return name
    label = _clean_person_part(doc.get("client_label"))
    if label and label not in {"—", "-", "Client", "client"}:
        return label
    return "Client"


_OFFRE_DATE_KEYS = frozenset({
    "date_naissance",
    "date_debut",
    "date_envoi",
    "date_prochain_rdv",
    "incomplete_at",
    "date_reception",
    "date_signature",
    "date_relance",
})


def _format_offre_field_value(value: Any, *, key: Optional[str] = None) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, (list, tuple)):
        parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
        return ", ".join(parts)
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            fv = _format_offre_field_value(v, key=str(k))
            if fv:
                parts.append(f"{k}: {fv}")
        return "; ".join(parts)
    text = str(value).strip()
    if key and key in _OFFRE_DATE_KEYS:
        try:
            from swiss_dates import format_swiss_date

            return format_swiss_date(text) or text
        except Exception:
            return text
    return text


def _humanize_payload_key(key: str) -> str:
    """Libellé de secours pour une clé payload non technique (legacy / hors schéma)."""
    text = (key or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else key


def _collect_filled_offre_fields(
    doc: dict,
    *,
    include_empty: bool = False,
    empty_label: str = "Non renseigné",
) -> List[Tuple[str, Optional[str]]]:
    """
    Extrait les champs pour l'e-mail d'offre.

    - Infos générales CRM (n°, type, catégorie, agent, langue, statut, date…)
    - Puis champs du formulaire via le schéma (`form_type`) : labels + ordre / sections
    - Jamais d'IDs techniques (`input_124`, « Formulaire — input … »)
    - Isolation stricte par formulaire (pas de champs 3a sur véhicule entreprise)
    - Dates : JJ.MM.AAAA exact, sans double-expansion d'année
    - include_empty=True : champs schéma vides → empty_label (récap « Offre reçue »)
    """
    rows: List[Tuple[str, Optional[str]]] = []
    seen_labels: set = set()
    empty_text = (empty_label or "Non renseigné").strip() or "Non renseigné"

    def add(label: str, value: Any, *, allow_empty_section: bool = False, key: Optional[str] = None):
        if allow_empty_section:
            if not label or label in seen_labels:
                return
            seen_labels.add(label)
            rows.append((label, None))
            return
        if key and key in _OFFRE_DATE_KEYS:
            formatted = _format_offre_field_value(value, key=key)
        elif isinstance(value, str):
            formatted = value.strip()
        else:
            formatted = _format_offre_field_value(value, key=key)
        if not formatted or formatted in {"—", "-", "None"}:
            if include_empty:
                formatted = empty_text
            else:
                return
        if label in seen_labels:
            return
        seen_labels.add(label)
        rows.append((label, formatted))

    form_type_id = ((doc or {}).get("form_type") or "").strip() or "pilier3_legacy"
    is_schema_form = form_type_id != "pilier3_legacy"

    # 1) Infos générales (toujours, cohérentes avec la demande)
    for key in _OFFRE_GENERAL_KEYS:
        if key not in (doc or {}):
            continue
        label = _OFFRE_FIELD_LABELS.get(key) or _humanize_payload_key(key)
        add(label, doc.get(key), key=key)

    # Adresse CRM (hub / sync) — bloc lisible avant le détail schéma
    adresse_composee = ", ".join(
        part for part in (
            (doc or {}).get("adresse") or "",
            " ".join(
                p for p in ((doc or {}).get("npa") or "", (doc or {}).get("ville") or "") if p
            ).strip(),
            (doc or {}).get("pays") or "",
        ) if part
    )
    if adresse_composee:
        add("Adresse", adresse_composee)

    # 2a) Formulaires schéma GF : uniquement les champs de CE form_type
    if is_schema_form:
        try:
            from offre_form_types import (
                is_technical_input_id,
                iter_schema_filled_fields,
                resolve_field_label,
            )
        except Exception:
            is_technical_input_id = None  # type: ignore
            iter_schema_filled_fields = None  # type: ignore
            resolve_field_label = None  # type: ignore

        payload = doc.get("form_payload") if isinstance(doc.get("form_payload"), dict) else {}
        schema_rows: List[Tuple[str, Optional[str]]] = []
        if callable(iter_schema_filled_fields):
            schema_rows = iter_schema_filled_fields(
                form_type_id,
                payload,
                include_empty=include_empty,
                empty_label=empty_text,
            )

        if schema_rows:
            for label, value in schema_rows:
                if value is None:
                    add(label, None, allow_empty_section=True)
                else:
                    add(label, value)
        else:
            # Schéma vide / introuvable : tenter une résolution label par clé, sans IDs bruts
            for key, value in payload.items():
                if key in _OFFRE_SKIP_KEYS or str(key).startswith("_"):
                    continue
                if callable(is_technical_input_id) and is_technical_input_id(str(key)):
                    label = resolve_field_label(form_type_id, str(key)) if callable(resolve_field_label) else None
                    if not label:
                        continue
                else:
                    label = (
                        (resolve_field_label(form_type_id, str(key)) if callable(resolve_field_label) else None)
                        or _OFFRE_FIELD_LABELS.get(key)
                        or _humanize_payload_key(str(key))
                    )
                if callable(is_technical_input_id) and is_technical_input_id(label):
                    continue
                add(label, value)
        return rows

    # 2b) Wizard CRM legacy 3P : colonnes CRM + payload non technique
    for key in _OFFRE_LEGACY_EXTRA_KEYS:
        if key not in (doc or {}):
            continue
        label = _OFFRE_FIELD_LABELS.get(key) or _humanize_payload_key(key)
        add(label, doc.get(key), key=key)

    # Autres colonnes CRM connues (hors skip / déjà listées)
    already = set(_OFFRE_GENERAL_KEYS) | set(_OFFRE_LEGACY_EXTRA_KEYS)
    for key, value in (doc or {}).items():
        if key in _OFFRE_SKIP_KEYS or key in already or key.startswith("_"):
            continue
        if key == "form_type":
            continue
        label = _OFFRE_FIELD_LABELS.get(key) or _humanize_payload_key(key)
        add(label, value, key=key)

    payload = doc.get("form_payload") if isinstance(doc.get("form_payload"), dict) else {}
    try:
        from offre_form_types import is_technical_input_id as _is_tech
    except Exception:
        def _is_tech(k: str) -> bool:  # type: ignore
            return str(k).lower().startswith("input")

    for key, value in payload.items():
        if key in _OFFRE_SKIP_KEYS or str(key).startswith("_"):
            continue
        if _is_tech(str(key)):
            # Legacy : ne jamais afficher input_* brut
            continue
        label = _OFFRE_FIELD_LABELS.get(key) or _humanize_payload_key(str(key))
        add(label, value)

    return rows


def _compose_offre_email(
    *,
    intro_lines: List[str],
    intro_html: str,
    field_rows: List[Tuple[str, Optional[str]]],
    doc: dict,
    highlight_rows: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[str, str]:
    del highlight_rows  # reserved
    lines = list(intro_lines)
    if field_rows:
        lines.extend(["", "Détails de l'offre :", ""])
        for label, value in field_rows:
            if value is None:
                lines.append("")
                lines.append(f"— {label} —")
                continue
            lines.append(f"{label} : {value}")

    url = _demande_offre_url(doc.get("id"))
    client_url = _client_url(doc.get("client_id"))
    if url:
        lines.extend(["", f"Ouvrir dans le CRM : {url}"])
    if client_url:
        lines.append(f"Fiche client : {client_url}")
    lines.extend(["", "—", "Notification automatique de LeoSoft."])
    body_text = "\n".join(lines)

    html_parts = [
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;line-height:1.5;">',
        intro_html,
    ]
    if field_rows:
        html_parts.append("<p><strong>Détails de l'offre</strong></p>")
        html_parts.append(
            '<table style="border-collapse:collapse;width:100%;max-width:640px;font-size:13px;">'
        )
        for label, value in field_rows:
            if value is None:
                html_parts.append(
                    "<tr>"
                    f'<td colspan="2" style="border:1px solid #e5e7eb;padding:8px 10px;'
                    f'background:#eef2ff;font-weight:600;">{html.escape(label)}</td>'
                    "</tr>"
                )
                continue
            html_parts.append(
                "<tr>"
                f'<td style="border:1px solid #e5e7eb;padding:6px 8px;width:38%;'
                f'background:#f8fafc;vertical-align:top;"><strong>{html.escape(label)}</strong></td>'
                f'<td style="border:1px solid #e5e7eb;padding:6px 8px;vertical-align:top;">'
                f'{html.escape(value).replace(chr(10), "<br/>")}</td>'
                "</tr>"
            )
        html_parts.append("</table>")
    if url:
        html_parts.append(_html_button(url, "Ouvrir la demande d'offre"))
    if client_url:
        html_parts.append(_html_button(client_url, "Voir la fiche client"))
    html_parts.append(
        '<p style="color:#666;font-size:12px;margin-top:24px;">'
        "— Notification automatique de LeoSoft.</p></div>"
    )
    return body_text, "".join(html_parts)


# --- Compat anciens imports (offsets) ---
def parse_notify_offsets():
    return [0]


def offset_label(minutes: int) -> str:
    return "0"
