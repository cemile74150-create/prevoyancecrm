# Versions code LeoSoft — schéma et archivage

## Schéma de version

Format : `YYYY-MM-DD_<shortSHA12>`

Exemple : `2026-11-20_c81daf185154`

| Champ (`version.json`) | Contenu |
|------------------------|---------|
| `version_id` | Identifiant ci-dessus |
| `date` | Horodatage local ISO |
| `github_commit` | SHA complet Git |
| `github_branch` | Branche au moment de l’archive |
| `railway_deployment_id` | Optionnel (si fourni au script) |
| `archive_sha256` | Empreinte de l’archive `.tar.gz` |
| `s3_key` | Clé Infomaniak si uploadé |

L’archive reflète **l’arbre Git du commit** (pas les fichiers non commités).

Un même `version_id` (même jour + même SHA) n’est **jamais écrasé**.  
Avant/après déploiement : même archive ; événements consignés dans `deploy-records.jsonl`.

## Emplacements

| Destination | Chemin / préfixe | Rôle |
|-------------|------------------|------|
| PC | `C:\LeoSoft\Versions\<version_id>\` | Copie vérifiée + `version.json` + `SHA256SUMS.txt` |
| Infomaniak S3 | `leosoft-versions/<version_id>/…` | Miroir distant **code** |
| (historique) | `leosoft-code-backups/` | Anciennes archives (script legacy) |
| (données) | `crm-backups/*.crmbak` | Mongo + PDF — **séparé** |

Ne jamais mélanger code et `.crmbak`.  
Ne jamais supprimer/modifier `crm-backups/`, `leosoft-code-backups/`, Mongo, ni documents clients.

## Contenu de l’archive

**Inclus** : `frontend/` (sources + lockfiles), `backend/` (sources + requirements), `deploy/` (scripts/docs non secrets), Dockerfile / configs suivies par Git, `.leosoft-release-source`.

**Exclus** : `.env*`, secrets, `node_modules`, `frontend/build`, `backend/backups`, `*.crmbak`, uploads, données clients, `prevoyancecrm/`.

`node_modules` se reconstruit via les lockfiles.

## Scripts

```powershell
# Plan + construction temporaire + vérif (rien d’écrit durable)
.\deploy\archiver-version-code.ps1 -DryRun

# Copie locale vérifiée sous C:\LeoSoft\Versions
.\deploy\archiver-version-code.ps1 -LocalOnly

# Local + S3 (GO explicite obligatoire) + vérif SHA-256 re-téléchargée
.\deploy\archiver-version-code.ps1 -UploadS3 -AutoriserUploadS3

# Upload S3 d’une archive locale déjà présente (pas de rebuild)
.\deploy\archiver-version-code.ps1 -UploadExisting -AutoriserUploadS3 -VersionId "2026-11-20_c81daf185154"

# Assure présence (skip si déjà là) — utilisé par leosoft-up.ps1
.\deploy\archiver-version-code.ps1 -UploadS3 -AutoriserUploadS3 -Ensure -Phase before-deploy
```

Self-test exclusions :

```powershell
python deploy\archive_code_version.py --self-test
```

## Lien avec le déploiement (`leosoft-up.ps1`)

**Uniquement** si `-AutoriserDeploiement` (jamais au simple démarrage local de l’app) :

1. Contrôles `verifier-avant-deploiement.ps1`
2. **Archivage `before-deploy`** → local + S3 (`--ensure`, `--allow-s3-without-local`)
3. `railway up` (production — seulement avec GO déploiement)
4. **Archivage `after-deploy`** → même `version_id` si même jour/SHA ; ajoute une ligne dans `deploy-records.jsonl`

Si l’écriture locale échoue (PC Versions hors ligne / disque indisponible) mais les credentials `BACKUP_S3_*` sont présents : **S3 doit réussir** ; l’archivage signale `pending_local_sync`.

Échec clair si S3 échoue quand l’upload est requis.  
Échec clair si local échoue sans `-AllowS3WithoutLocal`.

## Sync local (PC de retour)

Quand `pending_local_sync` ou PC Versions à nouveau disponible :

1. Télécharger `leosoft-versions/<version_id>/leosoft-<version_id>.tar.gz` (mêmes `BACKUP_S3_*`, **autre préfixe** que `crm-backups/`).
2. Placer sous `C:\LeoSoft\Versions\<version_id>\` avec `version.json` + `SHA256SUMS.txt`.
3. Vérifier : `Get-FileHash … -Algorithm SHA256` = `archive_sha256`.
4. Ne pas écraser une archive locale déjà présente avec un checksum différent — signaler l’écart.

Ou, si l’archive locale existe déjà sans S3 :

```powershell
.\deploy\archiver-version-code.ps1 -UploadExisting -AutoriserUploadS3 -VersionId "<id>"
```

## Règles de sécurité

- Aucune suppression automatique d’archives anciennes.
- Pas d’écrasement si le dossier version ou la clé S3 tar.gz existe déjà.
- Credentials : `backend/.env.backup` (`BACKUP_S3_*`) gitignored — ne pas créer/rotationner de clés ici, ne pas modifier Railway env.
- Rollback code ≠ restauration Mongo (voir `ROLLBACK_CODE.md`).
