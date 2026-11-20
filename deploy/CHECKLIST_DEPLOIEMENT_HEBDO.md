# Checklist déploiement hebdomadaire LeoSoft

À cocher **avant / pendant / après** la publication `app.leosoft.ch`.  
Une seule mise à jour prod par semaine sauf urgence + GO.

## Avant (staging / local)

- [ ] Branche issue de GitHub `main` (`git ls-remote origin refs/heads/main` + `merge-base --is-ancestor`)
- [ ] Dossier = `leosoft-saisie-preneur` (marqueur `.leosoft-release-source`)
- [ ] PR `develop` → `main` verte (si flux hebdo) **ou** GO explicite pour déployer depuis branche descendante
- [ ] `deploy\verifier-avant-deploiement.ps1` OK (tests moteur inclus)
- [ ] Smoke manuel local : wizard 8 étapes, PDF **COMPARATIF DES RENTES**, multi-LPP si concerné
- [ ] Plan de rollback noté : commit précédent + ID Railway SUCCESS antérieur (si encore listé)
- [ ] Sauvegarde données à jour ? (tâche `crm-backups/` — **séparée** de l’archive code)

## Pendant (GO prod)

- [ ] GO Cemile oral/écrit pour **déployer**
- [ ] `deploy\leosoft-up.ps1 -AutoriserDeploiement`
  - Archive **before-deploy** auto (local + S3 `leosoft-versions/`)
  - `railway up`
  - Archive **after-deploy** auto (même version_id si même jour/SHA ; `deploy-records.jsonl`)
- [ ] Noter le nouvel ID : `railway deployment list --service prevoyance-frontend --environment production --limit 3`
- [ ] Si ID connu après coup :  
  `.\deploy\archiver-version-code.ps1 -UploadS3 -AutoriserUploadS3 -Ensure -Phase after-deploy -RailwayDeploymentId "<id>"`

## Après publication

- [ ] Health prod + login + client + PDF + document
- [ ] Vérifier `C:\LeoSoft\Versions\<version_id>\` + clé S3 `leosoft-versions/<version_id>/…` + checksum
- [ ] Si `pending_local_sync` : suivre `VERSIONS.md` § Sync local
- [ ] Consigner version_id + commit + deployment id (carnet / note)
- [ ] Rollback Mongo/documents : **non** — seulement si incident données + GO séparé

## Ne pas faire

- [ ] Pas de `railway up` hors script autorisé
- [ ] Pas de restauration Mongo « au cas où »
- [ ] Pas de suppression auto d’archives code
- [ ] Pas de push `main` / `--force`
