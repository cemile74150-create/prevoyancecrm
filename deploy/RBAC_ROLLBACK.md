# RBAC Phases 1–5 — sauvegarde & retour arrière

**Aucun déploiement depuis ce document.** Procédure pour un futur GO prod explicite.
**Interdit ici :** `railway up`, scripts Mongo prod, drop de collections, push `main`.

## Commits de référence (branche `feat/attribution-conseiller-account-id`)

| Phase | Commit | Contenu |
|---|---|---|
| P1 | `bb5fe46` | Seed `roles` + `resolve_effective_permissions` (accès inchangé) |
| P2 | `9d51794` | Modules admin scindés + backfill compat `users.manage` |
| P3 | `daa0d6d` | UI / API Rôles, propagation, `roles.manage` (admins only) |
| P4 | `832f7b7` | Exceptions individuelles (`permission_overrides`) + garde-fous |
| P5 | `9bb48fe` | Anti auto-élévation, trous routes, tests non-régression, doc rollback |

Hashes vérifiés sur `feat/attribution-conseiller-account-id` (`git log --oneline bb5fe46^..9bb48fe`).
Full P5 : `9bb48fe04cba3fd302fb73f5a3967920ba549ccc`.

## Avant tout déploiement futur

1. **Backup Infomaniak (pro)** de la base Mongo / snapshot hébergeur — conserver la date, le nom `.crmbak`, le préfixe S3 (`crm-backups/` sur bucket `prevoyancecrm-backups`) et le rapport `*.report.json` (`verify.ok` + `remote.verified`).
2. Noter `git rev-parse HEAD` déployé et le SHA GitHub de la branche.
3. Confirmer `ACCESS_MODE` (legacy / dual / strict) — voir `deploy/ATTRIBUTION_CUTOVER.md` (prod actuelle : `dual` via `app_settings.access_policy`).
4. Ne **pas** supprimer la collection `roles` ni les champs `permissions` / `permission_overrides` users.
5. Restauration données : procédure `deploy/infomaniak/BACKUP_RESTORE.md` (déchiffrer `.crmbak` → `verify_backup.py` → `restore_from_backup.py`). **Permissions + données** reviennent ensemble avec le restore ; un revert git seul ne droppe pas `roles`.

## Comportement au prochain démarrage prod (sans l’exécuter ici)

Au startup applicatif (idempotent, pas de suppression) :

1. `ensure_roles_seeded` — crée les templates système absents ; n’écrase pas un template déjà présent.
2. `backfill_phase2_admin_module_permissions` — ajoute les clés modules admin **absentes** ; hérite de `users.manage` ; pose `roles.manage=false` si absent.
3. `backfill_phase3_roles_manage` — `roles.manage=true` **uniquement** si `users.manage` déjà true (admins) ; ne pousse pas de droits sensibles aux non-admins.

Re-run = no-op si déjà backfillé.

## Feature flags / leviers sans revert code

| Levier | Effet |
|---|---|
| `PUT /api/access-policy/mode` → `legacy` | Revient à l’accès dossiers nom/e-mail (attribution) — **indépendant** du RBAC modules |
| Désactiver un rôle custom (`active=false`) | Soft ; ne drop pas la collection |
| Reset exceptions user | Réaligne sur le template rôle sans supprimer le compte |

## Retour arrière code (si GO deploy puis problème RBAC)

Ordre recommandé (du plus doux au plus dur) :

1. **Hotfix** sur la branche feat → redeploy ciblé (accord explicite).
2. **Revert du commit Phase 5 seulement** si le souci est anti-élévation / routes — les données `roles` / overrides restent valides.
3. Revert P4 → P3 → P2 → P1 **dans cet ordre** si nécessaire (`git revert <sha>` sur branche, pas force-push `main`).
4. Après revert P3+ : l’UI Rôles / `roles.manage` peut manquer ; les snapshots `permissions` users restent.
5. **Ne jamais** `dropCollection('roles')` sans plan de restore Infomaniak + validation Cemile.

## Ce que le rollback ne doit pas faire

- Écraser la prod avec une archive pré-migration d’attribution (perte notes/statuts post-deploy).
- Purger `permission_overrides` en masse.
- Accorder automatiquement des permissions sensibles aux non-admins « pour réparer ».
- Toucher Mongo prod depuis un script local hors procédure validée.

## Contrôles smoke post-deploy / post-rollback

- Login admin : Utilisateurs + Rôles (si P3+).
- Conseiller : pas d’accès Utilisateurs / Rôles / Messagerie admin.
- Offres process, Messagerie, Entreprises, LAMal, Congés, Suivi technique selon droits.
- Isolation dossiers dual/strict / `conseiller_account_id` inchangée.
- Self-edit admin : impossible de s’accorder `roles.manage` si absent.
