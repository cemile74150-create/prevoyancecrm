"""Attribution des anciennes demandes d'offres d'après leur historique.

Logique pure, sans accès base : le script
``scripts/attribuer_historique_demandes_offres.py`` lit les données, appelle
``planifier`` puis, seulement avec ``--execute``, écrit les champs
d'attribution (mêmes champs que « M'attribuer »).

Règles :
- hors pilotage (brouillon, supprimée, annulée) : ignorée ;
- déjà attribuée (à la main ou par une migration précédente) : jamais écrasée ;
- gestionnaire = auteur de la dernière action de traitement d'offre
  (réception, transmission à l'agent) ; à défaut, auteur de la dernière
  autre action de traitement (soumission, relance, incomplet, en cours…) ;
- les actions de l'agent (création, envoi, décision client) ne comptent pas ;
- le candidat doit être un compte actif ayant le droit de traiter les offres,
  identifié sans ambiguïté (par identifiant, sinon par nom ou e-mail).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from demandes_offres_pilotage import _parse_iso, dans_pilotage, gestionnaire_info

SOURCE_MIGRATION = "migration_historique"
PAR_NOM_MIGRATION = "Migration historique"

DECISION_HORS_PILOTAGE = "hors_pilotage"
DECISION_DEJA_MANUELLE = "deja_attribuee_manuelle"
DECISION_DEJA_MIGREE = "deja_attribuee_migration"
DECISION_ATTRIBUABLE = "attribuable"
DECISION_AMBIGUE = "ambigue"
DECISION_NON_IDENTIFIEE = "non_identifiee"
DECISION_SANS_DROITS = "sans_droits_gestionnaire"
DECISION_SANS_TRAITEMENT = "sans_action_de_traitement"

NIVEAU_OFFRE = 1
NIVEAU_TRAITEMENT = 2


def normaliser(value: Any) -> str:
    """Minuscules, sans accents, apostrophes et espaces unifiés."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("`", "'").casefold()
    return re.sub(r"\s+", " ", text).strip()


def cle_nom(value: Any) -> str:
    """Clé indépendante de l'ordre prénom / nom : « PEREIRA Jordan » = « jordan pereira »."""
    tokens = re.split(r"[\s\-.,]+", normaliser(value))
    return " ".join(sorted(t for t in tokens if t))


# Actions de traitement d'offre (niveau 1), par préfixe normalisé.
ACTIONS_OFFRE = (
    "offre compagnie recue",
    "offres transmises a l'agent",
    "offre transmise a l'agent",
    "offres partiellement transmises a l'agent",
    "offres completes",
    "offre complete",
    "documents offre ajoutes",
)
# Autres actions du service Offre (niveau 2).
ACTIONS_TRAITEMENT = (
    "soumis a la compagnie",
    "non soumis a la compagnie",
    "en cours de traitement",
    "en attente de la compagnie",
    "relance effectuee aupres de la compagnie",
    "offre compagnie incomplete",
    "demande declaree incomplete",
    "compagnie marquee incomplete",
    "statut incomplet annule",
    "erreurs signalees",
    "document offre retire",
)


def niveau_action(action: Any) -> Optional[int]:
    label = normaliser(action)
    if not label:
        return None
    if any(label.startswith(p) for p in ACTIONS_OFFRE):
        return NIVEAU_OFFRE
    if any(label.startswith(p) for p in ACTIONS_TRAITEMENT):
        return NIVEAU_TRAITEMENT
    return None


@dataclass
class Trace:
    action: str
    at: str
    by_id: str
    by_name: str
    niveau: int
    ordre: int
    source: str


def _traces(doc: dict) -> list[Trace]:
    """Actions de traitement relevées dans l'historique, le suivi et les offres."""
    out: list[Trace] = []
    ordre = 0

    def add(action, at, by_id, by_name, source, niveau=None):
        nonlocal ordre
        lvl = niveau if niveau is not None else niveau_action(action)
        by_id = str(by_id or "").strip()
        by_name = str(by_name or "").strip()
        if lvl is None or not (by_id or by_name):
            return
        out.append(Trace(str(action or ""), str(at or ""), by_id, by_name, lvl, ordre, source))
        ordre += 1

    for h in doc.get("historique") or []:
        if isinstance(h, dict):
            add(h.get("action"), h.get("at"), h.get("by_id"), h.get("by_name"), "historique")
    for e in doc.get("suivi_evenements") or []:
        if isinstance(e, dict):
            add(e.get("label"), e.get("at"), e.get("auteur_id"), e.get("auteur"), "suivi")
    for offer in doc.get("offres") or []:
        if not isinstance(offer, dict):
            continue
        if offer.get("received_by"):
            add("Offre compagnie reçue", offer.get("received_at"), "", offer.get("received_by"), "offres", NIVEAU_OFFRE)
        for t in offer.get("transmissions") or []:
            if isinstance(t, dict):
                add("Offres transmises à l'agent", t.get("at"), t.get("by_id"), t.get("by"), "offres", NIVEAU_OFFRE)
    return out


def _cle_tri(trace: Trace):
    moment = _parse_iso(trace.at)
    return (moment.timestamp() if moment else float("-inf"), trace.ordre)


@dataclass
class Compte:
    id: str
    nom: str
    email: str
    actif: bool
    gestionnaire: bool


@dataclass
class Annuaire:
    """Comptes utilisateurs indexés par identifiant, nom et e-mail."""

    comptes: list[Compte]
    par_id: dict[str, Compte] = field(init=False)
    par_nom: dict[str, list[Compte]] = field(init=False)
    par_email: dict[str, list[Compte]] = field(init=False)

    def __post_init__(self):
        self.par_id, self.par_nom, self.par_email = {}, {}, {}
        for c in self.comptes:
            if c.id:
                self.par_id.setdefault(c.id, c)
            for key in {cle_nom(c.nom)} - {""}:
                self.par_nom.setdefault(key, []).append(c)
            if c.email:
                self.par_email.setdefault(normaliser(c.email), []).append(c)

    @classmethod
    def depuis_users(cls, rows: Iterable[dict], user_from_doc: Callable, can_process: Callable) -> "Annuaire":
        comptes = []
        for row in rows:
            try:
                account = user_from_doc(row)
            except Exception:
                continue
            nom = (account.name or f"{account.prenom} {account.nom}").strip()
            comptes.append(Compte(
                id=str(account.account_id or ""),
                nom=nom or str(row.get("email") or ""),
                email=str(row.get("email") or ""),
                actif=row.get("active", True) is not False,
                gestionnaire=bool(can_process(account)),
            ))
            alt = f"{row.get('prenom') or ''} {row.get('nom') or ''}".strip()
            if alt and cle_nom(alt) != cle_nom(nom):
                comptes.append(Compte(comptes[-1].id, alt, "", comptes[-1].actif, comptes[-1].gestionnaire))
        return cls(comptes)

    def resoudre(self, by_id: str, by_name: str) -> tuple[list[Compte], str]:
        """Comptes distincts correspondant à l'auteur, et méthode utilisée."""
        if by_id:
            found = self.par_id.get(by_id)
            return ([found], "id") if found else ([], "id_inconnu")
        key = normaliser(by_name)
        hits = self.par_email.get(key, []) if "@" in key else self.par_nom.get(cle_nom(by_name), [])
        uniques = [self.par_id.get(i, c) for i, c in {c.id: c for c in hits}.items()]
        return uniques, "email" if "@" in key else "nom"


def _est_agent(doc: dict, trace: Trace) -> bool:
    agent_ids = {str(doc.get(k) or "").strip() for k in ("agent_account_id", "created_by_account_id")} - {""}
    if trace.by_id and trace.by_id in agent_ids:
        return True
    agent_label = cle_nom(doc.get("agent_label"))
    return bool(not trace.by_id and agent_label and cle_nom(trace.by_name) == agent_label)


def _deja_migree(doc: dict) -> bool:
    if doc.get("gestionnaire_attribution_source") == SOURCE_MIGRATION:
        return True
    events = [e for e in (doc.get("attributions_historique") or []) if isinstance(e, dict)]
    return bool(events) and events[-1].get("type") == SOURCE_MIGRATION


@dataclass
class Decision:
    demande_id: str
    numero: str
    client: str
    agent: str
    statut: str
    decision: str
    raison: str = ""
    gestionnaire_id: Optional[str] = None
    gestionnaire_nom: Optional[str] = None
    action: Optional[str] = None
    action_at: Optional[str] = None
    gestionnaires_vus: list[str] = field(default_factory=list)
    candidats: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def analyser(doc: dict, annuaire: Annuaire) -> Decision:
    prenom, nom = str(doc.get("prenom") or "").strip(), str(doc.get("nom") or "").strip()
    d = Decision(
        demande_id=str(doc.get("id") or ""),
        numero=str(doc.get("numero") or ""),
        client=f"{prenom} {nom}".strip() or str(doc.get("client_label") or "").strip() or "—",
        agent=str(doc.get("agent_label") or "—"),
        statut=str(doc.get("statut") or ""),
        decision=DECISION_SANS_TRAITEMENT,
    )
    if not dans_pilotage(doc):
        d.decision, d.raison = DECISION_HORS_PILOTAGE, "brouillon, supprimée ou annulée"
        return d
    info = gestionnaire_info(doc)
    if info["id"]:
        d.gestionnaire_id, d.gestionnaire_nom = info["id"], info["nom"]
        d.decision = DECISION_DEJA_MIGREE if _deja_migree(doc) else DECISION_DEJA_MANUELLE
        return d

    traces = [t for t in _traces(doc) if not _est_agent(doc, t)]
    if not traces:
        d.raison = "aucune action de traitement d'un gestionnaire dans l'historique"
        return d
    niveau = min(t.niveau for t in traces)
    retenues = sorted((t for t in traces if t.niveau == niveau), key=_cle_tri)
    vus = []
    for t in retenues:
        hits, _ = annuaire.resoudre(t.by_id, t.by_name)
        vus.append(hits[0].nom if len(hits) == 1 else (t.by_name or t.by_id))
    d.gestionnaires_vus = list(dict.fromkeys(vus))
    derniere = retenues[-1]
    d.action, d.action_at = derniere.action, derniere.at or None

    comptes, methode = annuaire.resoudre(derniere.by_id, derniere.by_name)
    d.candidats = [{"id": c.id, "nom": c.nom, "actif": c.actif, "gestionnaire": c.gestionnaire} for c in comptes]
    auteur = derniere.by_name or derniere.by_id
    if not comptes:
        d.decision = DECISION_NON_IDENTIFIEE
        d.raison = f"auteur « {auteur} » sans compte utilisateur correspondant ({methode})"
        return d
    if len(comptes) > 1:
        d.decision = DECISION_AMBIGUE
        d.raison = f"« {auteur} » correspond à {len(comptes)} comptes ({methode})"
        return d
    compte = comptes[0]
    if not (compte.actif and compte.gestionnaire):
        d.decision = DECISION_SANS_DROITS
        d.raison = f"{compte.nom} : compte {'inactif' if not compte.actif else 'sans droit de traitement des offres'}"
        return d
    d.decision = DECISION_ATTRIBUABLE
    d.gestionnaire_id, d.gestionnaire_nom = compte.id, compte.nom
    d.raison = f"dernière action « {derniere.action} » ({methode})"
    return d


def planifier(docs: Iterable[dict], annuaire: Annuaire) -> list[Decision]:
    return [analyser(doc, annuaire) for doc in docs]


def patch_attribution(decision: Decision, *, stamp: str) -> dict:
    """Mise à jour Mongo : champs d'attribution seulement, sans toucher historique ni statut."""
    motif = f"Attribution d'après l'historique : « {decision.action} »"
    if decision.action_at:
        motif += f" du {decision.action_at[:10]}"
    event = {
        "type": SOURCE_MIGRATION,
        "at": stamp,
        "par_id": None,
        "par_nom": PAR_NOM_MIGRATION,
        "ancien_id": None,
        "ancien_nom": None,
        "nouveau_id": decision.gestionnaire_id,
        "nouveau_nom": decision.gestionnaire_nom,
        "motif": motif,
    }
    return {
        "$set": {
            "gestionnaire_id": decision.gestionnaire_id,
            "gestionnaire_nom": decision.gestionnaire_nom,
            "gestionnaire_attribue_at": decision.action_at if _parse_iso(decision.action_at) else stamp,
            "gestionnaire_attribue_par": PAR_NOM_MIGRATION,
            "gestionnaire_attribution_source": SOURCE_MIGRATION,
        },
        "$push": {"attributions_historique": event},
    }
