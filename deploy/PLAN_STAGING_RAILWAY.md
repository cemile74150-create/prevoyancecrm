# Plan staging Railway — à exécuter seulement après GO-STAGING

**Ne pas créer tant que les protections GitHub ne sont pas confirmées.**

## Objectifs

| Exigence | Comment |
|----------|---------|
| App LeoSoft indépendante | Service Railway `leosoft-staging` (ou env `staging` séparé) — **pas** `production` |
| Mongo réservé tests | Nouveau plugin Mongo **ou** base `leosoft_staging` sur instance dédiée |
| S3 réservé tests | Bucket Infomaniak `leosoft-staging-docs` (préfixes `uploads/` `generated/` uniquement) |
| Aucune donnée client réelle | Seed fixtures / anonymisé uniquement — **interdit** de cloner prod |
| Aucun e-mail réel | `SMTP_*` absents **ou** Mailpit/Ethereal ; `OFFRES_EMAIL_ENABLED=false` |
| Aucun accès prod | Variables staging ≠ prod (Mongo URL, S3 keys, SMTP) |
| Aucun deploy `app.leosoft.ch` | Staging = autre service/URL ; `leosoft-up.ps1` refuse hors `main` + cible prod explicite |

## Architecture proposée

```
GitHub develop ──CI──► (optionnel) auto-deploy staging
GitHub main    ──GO──► app.leosoft.ch (production)
Local Cursor   ──────► Mongo/S3 locaux de test
```

### Services Railway (nouveau)

1. **Environment** `staging` (projet existant OK si isolation totale des variables)
2. **Service** `leosoft-staging` (même Dockerfile que prod)
3. **MongoDB** staging (nouveau)
4. **Variables** (noms seuls — valeurs staging) :
   - `MONGO_URL`, `DB_NAME=leosoft_staging`
   - `S3_*` → bucket staging
   - Pas de `SMTP_PASSWORD` prod ; mock ou service jetable
   - `PUBLIC_APP_URL=https://staging.…` (≠ app.leosoft.ch)
   - `TENANT_USER_ID=staging`
   - `ACCESS_MODE=legacy`
   - `RAILWAY_ENVIRONMENT=staging` (tag)

### Contrôles d’isolation (checklist avant 1er démarrage)

- [ ] Host Mongo staging ≠ host Mongo prod
- [ ] List S3 staging OK ; list bucket prod avec clés staging = échec
- [ ] Envoi mail test n’atteint aucune boîte conseiller/client
- [ ] URL publique ≠ `app.leosoft.ch`
- [ ] `railway up` staging ne cible jamais `--environment production`
- [ ] Script deploy prod (`leosoft-up.ps1`) refuse branche ≠ `main`

### Données

- Seed minimal : 1–2 users test, 0 dossier client réel
- Jamais `mongodump` prod → staging sans anonymisation + GO séparé

### Déploiement staging

- Script dédié futur : `deploy/leosoft-up-staging.ps1` (env staging only)
- **Interdit** de réutiliser `leosoft-up.ps1` pour staging (il est câblé production)

## Hors scope jusqu’à GO-STAGING

- Création env/service Railway
- Provisionnement Mongo/S3
- DNS staging
- Copie de données
