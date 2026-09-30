# Etat sauvegardes professionnelles

## Rétention Infomaniak (2026-08-27)
- `BACKUP_RETENTION_COUNT=7` : après chaque sauvegarde réussie, seules les **7** archives `.crmbak` les plus récentes sont conservées sur Object Storage ; les plus anciennes sont purgées automatiquement.
- Ne touche jamais aux données CRM (Mongo / fichiers live), uniquement aux archives `crm-backups/*.crmbak`.

## Correctif chemins Windows (2026-08-27)
- Cause des échecs depuis ~18–20 août : chemins Windows > 260 caractères pour 3 courriers
  Suivi 3P (noms de fichiers très longs) → `write_bytes` échouait, `BACKUP_STRICT` annulait toute la sauvegarde.
- Correctif : tronquer le nom local dans `backup_full.backup_local_filename` (+ préfixe `\\?\` si besoin).
- Logs Python conservés dans `backend/backups/backup_python_*_{out,err}.log`.

## Fait (2026-08-10)
- Pipeline `backup_professional.py` : dump Mongo + PDF, SHA256, tar.gz, AES-GCM, upload S3 **vérifié** (taille)
- Scripts PowerShell corrigés (stderr Python, wrapper Task Scheduler, chemins avec espaces)
- Tâche Windows `PrevoyanceCRM-DailyBackup` : **S4U + Highest**, quotidien 02:00, `WakeToRun`, `StartWhenAvailable`
- Rétention Infomaniak : **7** archives `.crmbak` les plus récentes (`BACKUP_RETENTION_COUNT=7`)
- Preuve : archives `20260810_073329` (manuel) et `20260810_074447` (tâche) présentes sur `prevoyancecrm-backups/crm-backups/`

## Optionnel
- Pour mode Password (accès réseau maximal hors session) : `BACKUP_TASK_PASSWORD` dans `backend/.env.backup` puis relancer `schedule_daily_backup.ps1` **en Administrateur**
