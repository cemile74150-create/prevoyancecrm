# Rollback code LeoSoft — procédure (GO Cemile obligatoire)

**Ne jamais exécuter ce document sans GO explicite.**  
**Ne jamais restaurer MongoDB pour un rollback code.**  
**Ne pas lancer `railway up` / rollback depuis Cursor sans accord.**  
**Mongo + documents S3 = opération SÉPARÉE** (jamais automatique avec un rollback code).

## Préparation seulement (dry-run autorisé sans GO prod)

Ces commandes **listent** ou **extraient en local hors prod** — elles ne rollbackent pas Railway :

```powershell
# Lister les déploiements (lecture seule)
railway deployment list --service prevoyance-frontend --environment production --limit 15

# Vérifier une archive locale (checksum)
Get-Content C:\LeoSoft\Versions\<version_id>\SHA256SUMS.txt
Get-FileHash C:\LeoSoft\Versions\<version_id>\leosoft-<version_id>.tar.gz -Algorithm SHA256

# Extraction dry-run hors prod (dossier temp) — ne pas pointer vers le dépôt de travail
$dest = Join-Path $env:TEMP ("leosoft-rollback-dryrun-" + [guid]::NewGuid().ToString("n"))
New-Item -ItemType Directory -Path $dest | Out-Null
tar -tzf C:\LeoSoft\Versions\<version_id>\leosoft-<version_id>.tar.gz | Select-Object -First 20
tar -xzf C:\LeoSoft\Versions\<version_id>\leosoft-<version_id>.tar.gz -C $dest
# Contrôler présence marqueur / wizard, puis supprimer $dest
Remove-Item -Recurse -Force $dest
```

## Principes

1. Un rollback **code** remet une version d’application précédente.
2. La base Mongo **reste** la base courante (sauf incident données traité à part via `deploy/infomaniak/BACKUP_RESTORE.md`).
3. Les archives code (`leosoft-versions/` ou `C:\LeoSoft\Versions`) ne contiennent ni `.env` ni données clients.
4. Restaurer un `.crmbak` ou des documents clients **n’est jamais** enchaîné automatiquement après un rollback code.

## Option A — Rollback Railway (préféré si déploiement encore listé)

1. Lister les déploiements :

```powershell
railway deployment list --service prevoyance-frontend --environment production --limit 15
```

2. Dans le **dashboard Railway** (service `prevoyance-frontend`, env `production`) : ouvrir un déploiement **SUCCESS** antérieur → **Rollback** / redeploy that image.
   - CLI actuelle : `railway deployment redeploy` = **dernier** déploiement seulement (pas un ID arbitraire).
   - Les déploiements marqués `REMOVED` peuvent ne plus être rollbackables ; dans ce cas → Option B.

3. Après rollback : tests post-rollback (ci-dessous).

4. Consigner : ID déploiement cible, date, GO Cemile, résultat des tests.

## Option B — Redéployer depuis archive / commit Git

### B1. Depuis GitHub (si le commit est connu)

1. Identifier le commit dans `version.json` ou tag (`leosoft-stable-…`).
2. Sur une **copie de travail dédiée** (pas un HEAD détaché improvisé sur la prod) : checkout du commit / branche figée.
3. Contrôles : `deploy\verifier-avant-deploiement.ps1`
4. **GO** puis `deploy\leosoft-up.ps1 -AutoriserDeploiement`
5. Archiver la version redeployée (local ± S3) avec l’ID Railway.

### B2. Depuis `C:\LeoSoft\Versions\<version_id>\`

1. Vérifier `SHA256SUMS.txt` / `version.json`.
2. Extraire le `.tar.gz` dans un dossier temporaire hors prod.
3. Restaurer les dépendances (`npm ci` / `pip`) depuis lockfiles.
4. Même contrôle + GO + `leosoft-up.ps1` que B1.

### B3. Depuis Infomaniak `leosoft-versions/`

1. Télécharger la clé `leosoft-versions/<version_id>/leosoft-….tar.gz` (mêmes credentials `BACKUP_S3_*`, **autre préfixe** que `crm-backups/`).
2. Vérifier checksum, puis comme B2.

## Checklist compatibilité Mongo (obligatoire avant rollback code)

Les migrations démarrage (`app_migrations`, chiffrement, couple dossiers, etc.) sont souvent **forward-only**.

- [ ] La version cible connaît-elle les champs / collections écrits par la version actuelle ?
- [ ] Y a-t-il eu une migration `app_migrations` entre les deux versions ? Si oui, rollback code **sans** rollback données = risque d’erreurs lecture/écriture.
- [ ] Fonctions sensibles à retester : login, ouverture client, PDF analyse, documents S3, suivi 3P, formulaires.
- [ ] Si incompatibilité schema : **ne pas** rollback code en prod ; corriger en forward-fix, ou préparer un plan données **séparé** (jamais automatique).

## Interdits

| Action | Statut |
|--------|--------|
| Restaurer un `.crmbak` pour « revenir en arrière » sur le code | Interdit |
| `push --force` sur `main` | Interdit |
| Rollback sans GO Cemile | Interdit |
| Supprimer les archives `leosoft-versions/` pour faire de la place | Manuel seulement, hors script |
| Déployer depuis `prevoyancecrm` / anciennes copies | Interdit |

## Tests post-rollback (minimum)

1. `GET /health` → ok  
2. Login  
3. Ouvrir un client existant  
4. Générer / ouvrir un PDF d’analyse (titre **COMPARATIF DES RENTES** toujours présent)  
5. Télécharger un document S3  
6. Parcours wizard 8 étapes intact  

## En cas d’échec du rollback

1. Revenir au dernier déploiement SUCCESS connu (Option A) ou dernier commit archivé stable.  
2. Ne pas toucher Mongo.  
3. Documenter l’écart et traiter en correctif forward.
