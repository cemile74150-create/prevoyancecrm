# Architecture économique — Railway + MongoDB + sauvegardes Infomaniak

**Pas de migration** PostgreSQL / Jelastic. Le CRM reste sur Railway + MongoDB.

## Docs sauvegarde (prioritaire)

- Guide ops : [`BACKUP.md`](BACKUP.md)
- Restauration complète : [`BACKUP_RESTORE.md`](BACKUP_RESTORE.md)
- Variables : [`env.backup.example`](env.backup.example) → `backend/.env.backup`

## Lancer / planifier

```powershell
.\deploy\infomaniak\run_professional_backup.ps1
.\deploy\infomaniak\schedule_daily_backup.ps1
```

## Rappel architecture

| Composant | Où |
|-----------|-----|
| App + Mongo | Railway |
| SMTP | Infomaniak mail |
| Copies de secours chiffrées | Object Storage Infomaniak (+ Swiss Backup optionnel) |
| PHP / MySQL / FTP | Hors périmètre CRM |
