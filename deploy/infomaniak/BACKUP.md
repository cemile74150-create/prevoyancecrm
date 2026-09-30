# Sauvegardes professionnelles CRM (Railway + MongoDB conservés)

Objectif : **zéro perte**, copies **indépendantes de Railway**, chiffrées, vérifiées, restaurables.

## Architecture

```
Railway (prod)  --lecture-->  PC / serveur backup
                                 |
                                 +--> dump Mongo JSONL
                                 +--> tous PDF/docs (S3 Infomaniak)
                                 +--> SHA256 (manifest + verify)
                                 +--> tar.gz
                                 +--> AES-256-GCM (.crmbak)
                                 +--> Object Storage Infomaniak (privé)
                                 +--> (option) copie Swiss Backup manuelle du .crmbak
```

Railway n’est **jamais** la seule copie.

## Prérequis (une fois)

1. Copier [`env.backup.example`](env.backup.example) → `backend/.env.backup`
2. Définir `BACKUP_ENCRYPTION_PASSPHRASE` (min. 16 caractères, **hors chat**, hors Railway)
3. Créer un bucket Object Storage Infomaniak **privé** (ex. `prevoyance-crm-backups`) + clés S3
4. Remplir `BACKUP_S3_*` dans `.env.backup`
5. Enregistrer la tâche quotidienne :

```powershell
cd prevoyancecrm
.\deploy\infomaniak\schedule_daily_backup.ps1
```

## Lancer une sauvegarde maintenant

```powershell
cd prevoyancecrm
.\deploy\infomaniak\run_professional_backup.ps1
```

Sorties dans `backend/backups/` :
- `backups_full_YYYYMMDD_HHMMSS/` — dump brut + `manifest.csv` + `integrity.json`
- `prevoyancecrm_backup_*.tar.gz.crmbak` — archive **chiffrée**
- `prevoyancecrm_backup_*.report.json` — rapport (sans secrets)

## Vérifier l’intégrité

```powershell
cd prevoyancecrm\backend
# Dossier brut
python scripts\verify_backup.py backups\backups_full_YYYYMMDD_HHMMSS
# Archive chiffrée (nécessite BACKUP_ENCRYPTION_PASSPHRASE)
python scripts\verify_backup.py backups\prevoyancecrm_backup_XXXX.tar.gz.crmbak
```

## Restaurer après perte de Railway

Voir le guide détaillé : [`BACKUP_RESTORE.md`](BACKUP_RESTORE.md)

Résumé :
1. Nouveau Mongo (Atlas gratuit / VPS / nouveau Railway Mongo)
2. Déchiffrer + vérifier l’archive
3. `restore_from_backup.py` → métadonnées
4. `--files-to-s3` → PDF vers bucket privé
5. Redéployer le Dockerfile avec `MONGO_URL` + `S3_*`

## Swiss Backup

Si vous préférez Swiss Backup plutôt que (ou en plus de) Object Storage :
- Gardez le fichier `.crmbak` local produit chaque nuit
- Synchronisez le dossier `backend/backups/*.crmbak` vers Swiss Backup (client officiel Infomaniak)
- Object Storage reste recommandé pour l’automatisation S3 déjà câblée

## Rétention conseillée

- Distant Infomaniak : **7** jours / archives `.crmbak` les plus récentes (`BACKUP_RETENTION_COUNT=7`)
- Local : même valeur par défaut (surcharge possible via `BACKUP_RETENTION_LOCAL`)
- Test de restauration : tous les 3 mois (`--dry-run` puis restauration sur Mongo de staging)
