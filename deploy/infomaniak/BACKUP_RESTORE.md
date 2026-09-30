# Procédure de restauration CRM (perte Railway)

Cette procédure reconstruit le CRM **sans dépendre** de l’ancien Railway, à partir d’une archive `.crmbak`.

## Ce dont vous avez besoin

1. Archive `prevoyancecrm_backup_YYYYMMDD_HHMMSS.tar.gz.crmbak` (locale ou téléchargée depuis Object Storage)
2. `BACKUP_ENCRYPTION_PASSPHRASE` (coffre / `.env.backup`)
3. Un MongoDB vide (ex. nouveau service Mongo Railway, MongoDB Atlas, ou VM)
4. (Recommandé) bucket S3 Infomaniak pour les PDF
5. Code source du CRM + `Dockerfile`

## A. Récupérer l’archive depuis Infomaniak Object Storage

```powershell
cd prevoyancecrm\backend
# .env.backup doit contenir BACKUP_S3_* et BACKUP_ENCRYPTION_PASSPHRASE
python -c "from scripts.backup_remote import list_remote_backups, download_backup; from pathlib import Path; print(list_remote_backups()); download_backup('crm-backups/NOM_DU_FICHIER.crmbak', Path('backups/restore.crmbak'))"
```

Ou via Cyberduck / aws-cli vers le bucket `prevoyance-crm-backups`.

## B. Vérifier l’intégrité (obligatoire)

```powershell
cd prevoyancecrm\backend
$env:BACKUP_ENCRYPTION_PASSPHRASE="..."  # ou chargé via .env.backup
python scripts\verify_backup.py backups\restore.crmbak
```

N’allez pas plus loin si `ok` est `false`.

## C. Restaurer les données Mongo

```powershell
$env:MONGO_URL="mongodb://...nouveau..."
$env:DB_NAME="prevoyancecrm"
python scripts\restore_from_backup.py backups\restore.crmbak
```

Cela réinjecte : users, clients, documents (métadonnées), notes, demandes, suivi 3P, etc.

## D. Restaurer les PDF / documents binaires

```powershell
# S3 Infomaniak configuré (S3_* dans l'environnement)
python scripts\restore_from_backup.py backups\restore.crmbak --files-to-s3
```

Les `storage_path` Mongo sont mis à jour en `s3://...`.

Sans S3 : les binaires restent dans l’archive déchiffrée (`files/`) ; vous pouvez les réimporter manuellement, mais S3 est la voie supportée.

## E. Relancer l’application

1. Build Docker : `docker build -t prevoyance-crm .`
2. Variables minimales :
   - `MONGO_URL`, `DB_NAME`
   - `S3_*` (documents sur Object Storage Infomaniak — obligatoire en prod)
   - `SMTP_*` Infomaniak
   - `ALLOW_LOCAL_STORAGE=false`
   - `PUBLIC_APP_URL`
3. Health : `GET /health` → `{"status":"ok"}`
4. Smoke : login, ouvrir un client, télécharger un PDF, générer un formulaire AVS

## F. Checklist anti-perte

- [ ] Au moins 1 `.crmbak` distant (Object Storage) datant de < 24 h
- [ ] Passphrase connue de 2 personnes de confiance / coffre
- [ ] Test `--dry-run` trimestriel
- [ ] Test restauration complète annuelle sur environnement staging

## Rollback partiel

Si seule une collection est corrompue, extraire le JSONL correspondant depuis l’archive déchiffrée et faire un `replace_one` ciblé (voir `restore_from_backup.py` / `PK_BY_COLLECTION`).
