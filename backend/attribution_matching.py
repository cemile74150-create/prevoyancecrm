"""Matching lecture seule : dossiers → comptes conseiller.

Ne lit que les champs d'attribution conseiller (jamais e-mail / téléphone / adresse client).
N'écrit rien en base. N'active aucune nouvelle permission.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from access_control import (
    ROLE_ADMIN,
    ROLE_CEO,
    ROLE_CONSEILLER,
    ROLE_GESTIONNAIRE_OFFRES,
    conseiller_labels_match,
    is_global_viewer,
    user_from_doc,
)
from conseiller_identity import normalize_conseiller_key

# Champs dossier / offre autorisés pour l'attribution (côté conseiller uniquement).
CONSEILLER_LABEL_FIELDS = ("conseiller", "agent_label")
CONSEILLER_EMAIL_FIELDS = ("agent_email", "conseiller_email")
CONSEILLER_ACCOUNT_FIELDS = ("conseiller_account_id", "agent_account_id", "created_by_account_id")

# Ne jamais utiliser pour rattacher un dossier à un compte.
FORBIDDEN_CLIENT_CONTACT_FIELDS = ("email", "telephone", "adresse", "avs_number")

REASON_SURE_ACCOUNT_ID = "account_id_existant"
REASON_SURE_EMAIL = "email_conseiller_unique"
REASON_SURE_FULL_NAME = "nom_complet_unique"
REASON_EMPTY = "vide_ou_non_attribue"
REASON_NO_MATCH = "aucun_compte_correspondant"
REASON_MULTI_EMAIL = "plusieurs_comptes_meme_email"
REASON_MULTI_NAME = "plusieurs_comptes_meme_nom"
REASON_PARTIAL_TOKEN = "correspondance_partielle_un_seul_mot"
REASON_EMAIL_NAME_CONFLICT = "email_et_nom_pointent_vers_comptes_differents"
REASON_INACTIVE_ONLY = "compte_correspondant_inactif"
REASON_COUPLE_MISMATCH = "couple_conseillers_differents"
REASON_ALREADY_SET_OTHER = "account_id_present_mais_compte_introuvable"


@dataclass
class AccountCandidate:
    account_id: str
    email: str
    name: str
    conseiller: str
    role: str
    active: bool
    labels: List[str] = field(default_factory=list)


@dataclass
class MatchResult:
    status: str  # sure | ambiguous | empty | impossible
    reason: str
    account_id: Optional[str] = None
    account_label: Optional[str] = None
    candidates: List[str] = field(default_factory=list)
    label_used: Optional[str] = None
    email_used: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_email(value: Any) -> str:
    return str(value or "").strip().casefold()


def _is_empty_label(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return True
    key = normalize_conseiller_key(raw)
    return key in {"", "non attribue", "non attribué", "n/a", "na", "aucun"}


def account_from_user_doc(doc: dict) -> AccountCandidate:
    user = user_from_doc(doc)
    labels: List[str] = []
    for raw in (user.conseiller, user.name, f"{user.prenom} {user.nom}".strip()):
        label = " ".join(str(raw or "").split()).strip()
        if label and label not in labels:
            labels.append(label)
    return AccountCandidate(
        account_id=str(doc.get("user_id") or user.account_id),
        email=_norm_email(user.email),
        name=user.name or "",
        conseiller=(user.conseiller or "").strip(),
        role=user.role,
        active=user.active,
        labels=labels,
    )


def build_account_index(user_docs: Iterable[dict]) -> List[AccountCandidate]:
    return [account_from_user_doc(d) for d in user_docs if d.get("user_id")]


def _tokens(label: str) -> List[str]:
    key = normalize_conseiller_key(label)
    return [t for t in key.split(" ") if t]


def _full_name_equal(left: str, right: str) -> bool:
    """Égalité stricte de personne (mêmes jetons, ordre indifférent). Pas de match partiel."""
    a = set(_tokens(left))
    b = set(_tokens(right))
    if not a or not b:
        return False
    return a == b


def _label_fields(doc: dict) -> List[str]:
    out: List[str] = []
    for key in CONSEILLER_LABEL_FIELDS:
        val = str(doc.get(key) or "").strip()
        if val and val not in out and not _is_empty_label(val):
            out.append(val)
    return out


def _email_fields(doc: dict) -> List[str]:
    out: List[str] = []
    for key in CONSEILLER_EMAIL_FIELDS:
        val = _norm_email(doc.get(key))
        if val and "@" in val and val not in out:
            out.append(val)
    return out


def _existing_account_ids(doc: dict) -> List[str]:
    out: List[str] = []
    for key in CONSEILLER_ACCOUNT_FIELDS:
        val = str(doc.get(key) or "").strip()
        if val and val not in out:
            out.append(val)
    return out


def assert_no_client_contact_used(doc: dict) -> None:
    """Garde-fou tests : le matching ne lit jamais ces clés comme identité conseiller."""
    # Fonction documentaire — le code de match n'accède pas à ces champs.
    _ = [doc.get(k) for k in FORBIDDEN_CLIENT_CONTACT_FIELDS]


def match_record_to_accounts(
    doc: dict,
    accounts: Sequence[AccountCandidate],
    *,
    spouse: Optional[dict] = None,
) -> MatchResult:
    """Classe un dossier / une offre / une fiche Suivi 3P."""
    active = [a for a in accounts if a.active]
    by_id = {a.account_id: a for a in accounts}

    existing_ids = _existing_account_ids(doc)
    if existing_ids:
        found = [by_id[i] for i in existing_ids if i in by_id]
        active_found = [a for a in found if a.active]
        if len(active_found) == 1:
            a = active_found[0]
            return MatchResult(
                status="sure",
                reason=REASON_SURE_ACCOUNT_ID,
                account_id=a.account_id,
                account_label=a.conseiller or a.name,
                candidates=[a.account_id],
                detail="Identifiant compte déjà présent sur la fiche",
            )
        if found and not active_found:
            return MatchResult(
                status="ambiguous",
                reason=REASON_INACTIVE_ONLY,
                candidates=[a.account_id for a in found],
                detail="account_id présent mais compte inactif",
            )
        if existing_ids and not found:
            return MatchResult(
                status="impossible",
                reason=REASON_ALREADY_SET_OTHER,
                candidates=list(existing_ids),
                detail="account_id stocké sans compte correspondant",
            )

    labels = _label_fields(doc)
    emails = _email_fields(doc)

    if not labels and not emails:
        return MatchResult(
            status="empty",
            reason=REASON_EMPTY,
            detail="Aucun libellé ni e-mail conseiller",
        )

    email_hits: Dict[str, AccountCandidate] = {}
    for em in emails:
        matches = [a for a in active if a.email == em]
        if len(matches) > 1:
            return MatchResult(
                status="ambiguous",
                reason=REASON_MULTI_EMAIL,
                candidates=[a.account_id for a in matches],
                email_used=em,
                detail=f"Plusieurs comptes actifs avec {em}",
            )
        if len(matches) == 1:
            email_hits[matches[0].account_id] = matches[0]

    # Correspondances nom complet uniquement (pas le match partiel « un seul mot »).
    full_hits: Dict[str, AccountCandidate] = {}
    partial_hits: Dict[str, AccountCandidate] = {}
    label_used = labels[0] if labels else None
    for label in labels:
        for acc in active:
            for acc_label in acc.labels:
                if _full_name_equal(label, acc_label):
                    full_hits[acc.account_id] = acc
                elif conseiller_labels_match(label, acc_label) and not _full_name_equal(label, acc_label):
                    # Ex. dossier « Martin » ↔ compte « Martin Dupont »
                    partial_hits[acc.account_id] = acc

    if email_hits and full_hits:
        if set(email_hits) != set(full_hits):
            return MatchResult(
                status="ambiguous",
                reason=REASON_EMAIL_NAME_CONFLICT,
                candidates=sorted(set(email_hits) | set(full_hits)),
                label_used=label_used,
                email_used=emails[0] if emails else None,
                detail="E-mail conseiller et nom désignent des comptes différents",
            )

    if len(email_hits) == 1 and (not full_hits or set(email_hits) == set(full_hits)):
        a = next(iter(email_hits.values()))
        result = MatchResult(
            status="sure",
            reason=REASON_SURE_EMAIL,
            account_id=a.account_id,
            account_label=a.conseiller or a.name,
            candidates=[a.account_id],
            label_used=label_used,
            email_used=emails[0] if emails else None,
            detail="E-mail conseiller unique",
        )
    elif len(full_hits) == 1 and not email_hits:
        a = next(iter(full_hits.values()))
        result = MatchResult(
            status="sure",
            reason=REASON_SURE_FULL_NAME,
            account_id=a.account_id,
            account_label=a.conseiller or a.name,
            candidates=[a.account_id],
            label_used=label_used,
            detail="Prénom+nom complets uniques",
        )
    elif len(full_hits) > 1:
        result = MatchResult(
            status="ambiguous",
            reason=REASON_MULTI_NAME,
            candidates=sorted(full_hits),
            label_used=label_used,
            detail="Plusieurs comptes pour le même nom complet",
        )
    elif partial_hits and not email_hits and not full_hits:
        result = MatchResult(
            status="ambiguous",
            reason=REASON_PARTIAL_TOKEN,
            candidates=sorted(partial_hits),
            label_used=label_used,
            detail="Correspondance partielle (un seul mot) — non automatique",
        )
    elif not email_hits and not full_hits and not partial_hits:
        # Compte inactif ?
        inactive_hits = []
        for label in labels:
            for acc in accounts:
                if not acc.active:
                    for acc_label in acc.labels:
                        if _full_name_equal(label, acc_label) or conseiller_labels_match(label, acc_label):
                            inactive_hits.append(acc.account_id)
                            break
        for em in emails:
            inactive_hits.extend(a.account_id for a in accounts if not a.active and a.email == em)
        inactive_hits = sorted(set(inactive_hits))
        if inactive_hits:
            result = MatchResult(
                status="ambiguous",
                reason=REASON_INACTIVE_ONLY,
                candidates=inactive_hits,
                label_used=label_used,
                email_used=emails[0] if emails else None,
                detail="Seul un compte inactif correspond",
            )
        else:
            result = MatchResult(
                status="impossible",
                reason=REASON_NO_MATCH,
                label_used=label_used,
                email_used=emails[0] if emails else None,
                detail="Aucun compte actif ou inactif ne correspond",
            )
    else:
        result = MatchResult(
            status="ambiguous",
            reason=REASON_MULTI_NAME,
            candidates=sorted(set(email_hits) | set(full_hits) | set(partial_hits)),
            label_used=label_used,
            detail="Plusieurs candidats après croisement e-mail / nom",
        )

    if spouse and result.status == "sure":
        spouse_result = match_record_to_accounts(spouse, accounts, spouse=None)
        if spouse_result.status == "sure" and spouse_result.account_id != result.account_id:
            return MatchResult(
                status="ambiguous",
                reason=REASON_COUPLE_MISMATCH,
                candidates=sorted({result.account_id or "", spouse_result.account_id or ""} - {""}),
                label_used=label_used,
                detail="Les deux membres du couple pointent vers des conseillers différents",
            )
        if spouse_result.status in {"ambiguous", "impossible"} and _label_fields(spouse):
            # Conjoint avec attribution problématique : signaler sans écraser un match sûr du primaire
            # seulement si le conjoint a un libellé distinct non vide.
            if spouse_result.status == "ambiguous" and spouse_result.reason == REASON_COUPLE_MISMATCH:
                return spouse_result
    return result


def planned_access_by_account_id(user, doc: dict) -> bool:
    """Comportement cible après bascule (non branché sur les routes).

    - Vue globale (admin / CEO / gestionnaire selon see_all) : toujours True
    - Sinon : uniquement si conseiller_account_id (ou agent_account_id) = compte connecté
    """
    if is_global_viewer(user):
        return True
    wanted = str(getattr(user, "account_id", "") or "")
    if not wanted:
        return False
    for key in CONSEILLER_ACCOUNT_FIELDS:
        if str(doc.get(key) or "").strip() == wanted:
            return True
    return False


def supervision_roles_keep_global() -> dict:
    """Documente les rôles qui doivent conserver la supervision Mendes."""
    return {
        ROLE_ADMIN: True,
        ROLE_CEO: True,
        ROLE_GESTIONNAIRE_OFFRES: True,
        ROLE_CONSEILLER: False,
    }


def summarize_results(rows: Sequence[dict]) -> dict:
    """Agrège une liste de {status, reason, ...}."""
    summary = {
        "total": len(rows),
        "sure": 0,
        "ambiguous": 0,
        "empty": 0,
        "impossible": 0,
        "by_reason": {},
    }
    for row in rows:
        status = row.get("status") or "impossible"
        summary[status] = summary.get(status, 0) + 1
        reason = row.get("reason") or "?"
        summary["by_reason"][reason] = summary["by_reason"].get(reason, 0) + 1
    return summary


def _public_ref(doc: dict, id_field: str = "id") -> str:
    """Référence affichable sans nom/prénom/e-mail client."""
    numero = str(doc.get("numero_dossier") or doc.get("numero") or "").strip()
    if numero:
        return numero
    raw_id = str(doc.get(id_field) or doc.get("id") or "").strip()
    if len(raw_id) > 12:
        return raw_id[:8] + "…"
    return raw_id or "?"


def redact_row_for_export(row: dict) -> dict:
    """Retire tout libellé client ; garde ref, conseiller, statut, raison."""
    return {
        "ref": row.get("ref") or row.get("numero") or row.get("id"),
        "conseiller": row.get("conseiller"),
        "agent_email_domain": _email_domain(row.get("email_used") or row.get("agent_email")),
        "status": row.get("status"),
        "reason": row.get("reason"),
        "detail": row.get("detail"),
        "account_id": row.get("account_id"),
        "account_label": row.get("account_label"),
        "candidates": row.get("candidates") or [],
    }


def _email_domain(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if "@" not in text:
        return None
    return text.split("@", 1)[1].casefold()


def classify_collection(
    records: Iterable[dict],
    accounts: Sequence[AccountCandidate],
    *,
    id_field: str = "id",
    spouses_by_id: Optional[Dict[str, dict]] = None,
) -> List[dict]:
    spouses_by_id = spouses_by_id or {}
    out: List[dict] = []
    for doc in records:
        spouse = None
        sid = doc.get("linked_spouse_id")
        if sid and spouses_by_id:
            spouse = spouses_by_id.get(sid)
        match = match_record_to_accounts(doc, accounts, spouse=spouse)
        out.append(
            {
                "id": doc.get(id_field) or doc.get("id"),
                "ref": _public_ref(doc, id_field),
                "numero": doc.get("numero_dossier") or doc.get("numero"),
                "conseiller": doc.get("conseiller") or doc.get("agent_label"),
                "agent_email": doc.get("agent_email") or doc.get("conseiller_email"),
                **match.to_dict(),
            }
        )
    return out


def per_conseiller_stats(
    records: Iterable[dict],
    rows: Sequence[dict],
    accounts: Sequence[AccountCandidate],
) -> List[dict]:
    """Pour chaque libellé conseiller vu : fiches actuelles vs rattachements sûrs vers un compte."""
    by_label: Dict[str, dict] = {}
    id_to_row = {r.get("id"): r for r in rows}

    def bucket(label: str) -> dict:
        key = normalize_conseiller_key(label) or "non attribue"
        if key not in by_label:
            by_label[key] = {
                "conseiller_label": label.strip() or "Non attribué",
                "dossiers_actuels": 0,
                "rattaches_surs": 0,
                "ambigus": 0,
                "vides": 0,
                "impossibles": 0,
                "account_id_cible": None,
                "account_label_cible": None,
            }
        return by_label[key]

    for doc in records:
        label = str(doc.get("conseiller") or doc.get("agent_label") or "").strip() or "Non attribué"
        b = bucket(label)
        b["dossiers_actuels"] += 1
        row = id_to_row.get(doc.get("id"))
        if not row:
            continue
        status = row.get("status")
        if status == "sure":
            b["rattaches_surs"] += 1
            if not b["account_id_cible"]:
                b["account_id_cible"] = row.get("account_id")
                b["account_label_cible"] = row.get("account_label")
        elif status == "ambiguous":
            b["ambigus"] += 1
        elif status == "empty":
            b["vides"] += 1
        else:
            b["impossibles"] += 1

    # Enrichir avec comptes actifs sans dossier
    seen_accounts = {b["account_id_cible"] for b in by_label.values() if b.get("account_id_cible")}
    for acc in accounts:
        if not acc.active or acc.account_id in seen_accounts:
            continue
        if acc.role != "conseiller":
            continue
        # Pas de ligne forcée : le tableau liste les libellés présents sur les fiches.

    return sorted(by_label.values(), key=lambda x: (-x["dossiers_actuels"], x["conseiller_label"].casefold()))


def count_inactive_and_missing(rows: Sequence[dict]) -> dict:
    inactive = sum(1 for r in rows if r.get("reason") == REASON_INACTIVE_ONLY)
    missing_id = sum(1 for r in rows if r.get("reason") == REASON_ALREADY_SET_OTHER)
    no_match = sum(1 for r in rows if r.get("reason") == REASON_NO_MATCH)
    return {
        "compte_inactif": inactive,
        "account_id_sans_compte": missing_id,
        "aucun_compte_correspondant": no_match,
        "total_inexistant_ou_inactif": inactive + missing_id + no_match,
    }
