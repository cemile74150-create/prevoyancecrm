# PRD — PrévoyanceCRM (extrait technique)

## Stack

- Frontend : React (CRA + craco), shadcn/ui
- Backend : FastAPI + MongoDB
- Hébergement : Railway (app + MongoDB volume)
- Stockage documentaire : **Infomaniak S3** (`S3_*`)
- Auth : email/mot de passe + sessions (`user_sessions`)

## Fonctionnalités cœur

- Gestion clients / dossiers / pipeline
- Documents PDF (upload, génération courriers, proxy S3)
- Suivi 3P, demandes d'offres, rappels, agenda
- Sauvegardes chiffrées vers Infomaniak (hors Railway)
