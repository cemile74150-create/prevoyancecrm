# PRD — PrévoyanceCRM (CRM prévoyance & retraite suisse)

## Problem statement
Application web CRM (type Salesforce simplifié) pour cabinets de prévoyance/retraite/conseil en Suisse. Centraliser les infos clients et suivre chaque dossier visuellement, de la prise de contact au rapport final. UI en français.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), routes préfixées `/api`, MongoDB via motor.
- Frontend: React 19 + Tailwind + shadcn/ui + Recharts. Pages sous `/app/frontend/src/pages`.
- Auth: Emergent-managed Google OAuth (cookie httpOnly `session_token`, 7 jours).
- Stockage documentaire: Emergent Object Storage (EMERGENT_LLM_KEY).
- Design: "Swiss Modern", accent bleu #002FA7, polices Chivo (titres) / IBM Plex Sans (corps).

## User personas
- Conseiller en prévoyance: gère ses dossiers clients, RDV, documents et analyses.

## Core requirements (static)
Tableau de bord, gestion des dossiers (Kanban 7 statuts), fiche client complète, gestion documentaire, agenda/rappels/tâches, recherche globale, interface responsive.

## Implemented (2026-07-20)
- Connexion Google (Emergent) + sessions + routes protégées.
- Tableau de bord: 8 KPI (nouveaux, attente docs, analyse, à présenter, terminés, urgents, total, tâches), graphique mensuel (dossiers/RDV/rapports), répartition par statut, RDV du jour.
- Dossiers: Kanban glisser-déposer sur les 7 statuts, badges priorité/urgent.
- Clients: liste + recherche/filtre, création/édition (infos perso, coordonnées, familiale, pro, statut, priorité), n° dossier auto (DOS-XXXX).
- Fiche client: onglets Infos, Rendez-vous, Notes internes, Documents, Historique des actions.
- Documents: upload/téléchargement/suppression PDF catégorisés (Certificat LPP, Déclaration d'impôt, Pièce d'identité, Fiches de salaire, Contrats, Autre) via object storage.
- Agenda: RDV groupés par jour + tâches/rappels (échéance, priorité, cochage).
- Recherche globale dans le header (nom, tél, email, n° dossier).
- Tests: 25/25 backend, frontend vérifié.

## Backlog / futures
- P1: Calculateurs (AVS, LPP, fiscal, départ anticipé, gains fiscaux).
- P1: Génération de rapports PDF professionnels depuis le dossier.
- P2 (IA): analyse automatique des certificats LPP, extraction PDF, préremplissage, recommandations.
- P2: vue calendrier mensuelle, notifications d'échéances.

## Next tasks
- Implémenter les calculateurs de retraite.
- Générateur de rapport PDF.
