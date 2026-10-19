# Versionnement LeoSoft

Ouvrir dans Cursor le dossier `C:\Users\offic\Desktop\Cemile\Tableau suivi\leosoft-saisie-preneur`.

C'est la seule source de référence. Les autres dossiers du bureau sont des copies ou des archives. `prevoyancecrm` contient un ancien historique et des fichiers sensibles : ne pas le commiter, ne pas le pousser, ne pas le réinitialiser.

## Les quatre niveaux

| Niveau | Où | Rôle |
|---|---|---|
| Production | Railway, service `prevoyance-frontend` | Version en service. Un envoi `railway up` ne enregistre pas le commit Git. |
| GitHub `main` | `github.com/cemile74150-create/prevoyancecrm` | Version officielle, seulement après validation. |
| Développement | Une branche `feat/…` ou `fix/…` par fonctionnalité | Travail en cours, poussé sur GitHub sans fusion. |
| Archives | Anciennes branches et copies du bureau | Conservées. Elles ne servent pas de source. |

## Travailler

1. Ouvrir `leosoft-saisie-preneur`, ou le worktree déjà créé pour la branche (`leosoft-lamal-2027` pour `feat/lamal-comparateur-2027`).
2. Lire la branche : `git status -sb` et `git rev-parse --abbrev-ref HEAD`.
3. Lire GitHub `main` avec `git ls-remote origin refs/heads/main`. Ne pas se fier à `origin/main` local sans cette lecture.
4. Créer ou réutiliser une branche dédiée. Ne pas développer sur `main`.
5. Finir et tester la fonctionnalité.
6. Lancer `deploy\sauvegarder-branche.ps1 -Message "Pourquoi ce changement"`.
7. Le script refuse `main`, les fichiers `.env`, les clés et les fichiers `conflicted`. Il pousse uniquement la branche courante, puis compare le commit local et le commit distant.

Une simulation sans écriture : `deploy\sauvegarder-branche.ps1 -DryRun`.

## Vérifier GitHub

```powershell
git rev-parse HEAD
git ls-remote origin refs/heads/<branche>
```

Les deux identifiants doivent être identiques. Sinon, la fonctionnalité n'est pas sauvegardée.

## Préparer une fusion

La fusion dans `main` n'est pas automatique. Préparer seulement :

1. La branche de fonctionnalité est poussée et identique à GitHub.
2. Elle descend du `main` distant actuel.
3. Les tests du moteur passent : `deploy\verifier-avant-deploiement.ps1`.
4. Le rapport indique ce qui est déjà sur `main` et ce qui ne l'est pas.

L'accord explicite reste nécessaire avant toute fusion.

## Préparer un déploiement

1. Lancer `deploy\verifier-avant-deploiement.ps1`.
2. Le script vérifie le dossier, les 8 étapes du parcours, le titre `COMPARATIF DES RENTES`, la descendance de GitHub `main`, l'absence de fichiers sensibles suivis, et les tests du moteur.
3. Il s'arrête sans appeler Railway.
4. `deploy\leosoft-up.ps1` n'est pas versionné : il contient l'identifiant du projet. Il refuse de partir sans `-AutoriserDeploiement`.
5. Ne le lancer qu'après accord explicite, depuis `leosoft-saisie-preneur`.

Le retour arrière consiste à redéployer, après accord, un commit déjà identifié et poussé. Railway ne conserve pas le commit d'un envoi `railway up` : noter le commit dans le message d'accord avant l'envoi.

## Éviter une ancienne version

- Ne pas ouvrir `prevoyancecrm` pour développer.
- Ne pas lancer `railway up` depuis un dossier au hasard : Railway envoie le dossier ouvert, pas GitHub.
- Le `Dockerfile` de la source exige `.leosoft-release-source`. Les anciennes copies ne l'ont pas, leur image s'arrête.
- Comparer les commits, pas les dates des dossiers.
