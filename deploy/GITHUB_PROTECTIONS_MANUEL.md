# Actions manuelles GitHub — protections (solo Cemile)

## Prérequis

1. `gh auth login` (navigateur) **ou** appliquer via l’UI GitHub.
2. Branche `develop` déjà poussée (fait).
3. Attendre un run CI **vert** sur `develop` (sinon les status checks requis peuvent bloquer les PR).

## Option A — Script (recommandé)

```powershell
gh auth login
cd "C:\Users\offic\Desktop\Cemile\Tableau suivi\leosoft-develop-setup"
git pull origin develop
.\deploy\proteger-branches-github.ps1
```

Effet :
- `main` et `develop` : PR obligatoire, CI obligatoire, pas de force-push, pas de suppression
- **0 review** tierce (tu n’es pas bloquée en solo)
- `enforce_admins` : même toi, pas de push direct sur `main`

## Option B — Interface GitHub

1. Ouvre https://github.com/cemile74150-create/prevoyancecrm/settings/branches  
2. **Add rule** → Branch name pattern : `main`
   - Require a pull request before merging ✅
   - Required approvals : **0** (solo)
   - Require status checks to pass ✅  
     Ajoute (après 1er CI vert) : `backend-unit`, `frontend-build`, `guard-no-railway-deploy`
   - Require conversation resolution ✅
   - Do not allow bypassing the above settings ✅ (si dispo)
   - Allow force pushes : **off**
   - Allow deletions : **off**
3. Répète pour `develop` (mêmes checks, 0 approval).

## Ce qui ne te bloque PAS

- Travailler et pousser `feat/offre-pdf-extract-structured`
- Ouvrir des PR vers `develop`
- Merger tes propres PR (0 approval)
- Développer en local librement

## Ce qui est bloqué (voulu)

- Push direct sur `main`
- Force-push / suppression de `main` (et `develop`)
- Merger une PR sans CI verte (une fois les checks requis activés)
- Déployer `app.leosoft.ch` depuis une branche ≠ `main` (`leosoft-up.ps1`)

## Pour que CI tourne aussi sur PR → main

Le fichier `.github/workflows/ci.yml` doit être **sur main**.  
Après CI verte sur develop : ouvrir une PR `develop` → `main` **uniquement** pour CI + garde-fous deploy (pas de features métier), puis merger.  
Sans cela, les PR vers `main` n’exécutent pas encore le workflow.
