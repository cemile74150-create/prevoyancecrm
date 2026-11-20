# Flux GitHub LeoSoft — local → develop → main → GO prod

## Branches

| Branche | Rôle |
|---------|------|
| `feat/*` / local | Travail libre avec Cursor |
| `develop` | Intégration hebdomadaire + CI |
| `main` | Versions production uniquement (protégée) |

`main` GitHub est la référence de déploiement. Ne jamais `push --force` ni déployer hors GO.

## Flux hebdomadaire

1. **Lundi–vendredi** : développer en local (`leosoft-saisie-preneur`), commits sur `feat/…` ou directement PR vers `develop`.
2. **PR → `develop`** : CI obligatoire (tests + build). Fusion après vert.
3. **Fin de semaine** : PR `develop` → `main` (CI verte).
4. **GO explicite** : `deploy\verifier-avant-deploiement.ps1` puis `deploy\leosoft-up.ps1 -AutoriserDeploiement`.
5. **Une seule** mise à jour `app.leosoft.ch` par semaine sauf urgence + GO.

## Protections attendues sur GitHub

### `main`
- Require a pull request before merging
- Require status checks: `backend-unit`, `frontend-build`, `guard-no-railway-deploy`
- Require conversation resolution
- Do not allow force pushes
- Do not allow deletions
- Restrict who can push (idéalement personne hors PR)

### `develop`
- Require a pull request before merging (recommandé)
- Require same CI checks
- Do not allow force pushes
- Do not allow deletions

Script d’application (nécessite `gh auth login`) :

```powershell
deploy\proteger-branches-github.ps1
```

## CI

Fichier : `.github/workflows/ci.yml`

- Aucun `railway up`
- Aucun secret production
- Backend : pytest ciblés
- Frontend : `npm run build`

## Staging

Environnement Railway **séparé** — à créer seulement après validation de cette étape GitHub (GO staging).  
Isolation : Mongo / S3 / SMTP distincts de la prod.

## Interdits

- Push direct sur `main`
- Déploiement Railway depuis CI
- Copier des secrets prod dans GitHub Actions
- Fusionner dans `main` sans GO de publication (la fusion code ≠ déploiement)
