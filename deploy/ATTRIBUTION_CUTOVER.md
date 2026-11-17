# Déploiement progressif — attribution `conseiller_account_id`

**Source unique :** `leosoft-saisie-preneur` (branche à jour)  
**Interdit :** `railway up` depuis `prevoyancecrm` / copies bureau  
**Déployer uniquement** avec `deploy\leosoft-up.ps1` après accord explicite.

## Modes

| Mode | Comportement |
|---|---|
| `legacy` (défaut) | Accès nom / e-mail actuel — **aucun changement utilisateur** |
| `dual` | Si `conseiller_account_id` présent → account_id ; sinon fallback nom |
| `strict` | Uniquement `conseiller_account_id` (superviseurs `see_all` inchangés) |

Surcharge runtime : `PUT /api/access-policy/mode` (admin) → Mongo `app_settings` + journal `access_policy_journal`.  
Sinon variable d’environnement `ACCESS_MODE`.

## Nouveaux conseillers (150)

- Création API : `access_by_account_id_only=true` **forcé** pour `role=conseiller`.
- Impossible de repasser à `false` une fois `true`.
- Effet : mode strict **par compte**, même si l’instance est en `legacy` ou `dual`.

## Décisions dossiers (ne pas réattribuer automatiquement)

- Service Fiscal (43) : sans account_id — superviseurs only
- BONVESTING / Jordy (2) : exclus jusqu’à validation
- Pascal : accès dual/nom conservés pendant la transition
- Non attribués : superviseurs only

## État au 2026-11-13

- Code perf + permissions offres : déployé `c166089` en **legacy**
- Migration attributions : **245** en prod (journal `prod_243_2026-11-13`)
- Dual / strict / 150 comptes : **en attente GO explicite**

## Étapes restantes (chacune = accord Cemile)

1. Smoke post-deploy legacy (login + dossier + offres) — si pas déjà fait
2. **`ACCESS_MODE=dual`** via `PUT /api/access-policy/mode` (préféré) ou env — journaliser ; **ne pas créer les 150 comptes**
3. Contrôles dual ciblés : Pascal couples, Alberto, BONVESTING (nom), Fiscal protégé, collègue isolé
4. Création progressive des 150 comptes (`access_by_account_id_only=true`) — GO séparé
5. **`strict`** seulement après décisions métier Pascal + BONVESTING

## Retour arrière rapide (préserve le travail utilisateurs)

1. **Premier levier :** `PUT /api/access-policy/mode` → `legacy` (ou `dual`) — **aucune perte de notes/statuts/docs**
2. **Second levier :** retirer les `conseiller_account_id` via journal de migration (script ciblé) — les écritures métier restent
3. **Éviter** un restore full overwrite d’une archive pré-migration sur la prod (écraserait le travail post-déploiement)

## Contrôles post-étape

- Après code legacy : login + ouverture dossier inchangée
- Après migration 239 : compteurs `with_account_id` ; spot-check 5 conseillers
- Après dual : isolation collègue + Pascal/BONVESTING + Fiscal
- Après strict : liste d’impact (Pascal 2, BONVESTING 2) validée métier
