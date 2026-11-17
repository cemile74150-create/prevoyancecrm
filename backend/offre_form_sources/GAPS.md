# Gaps — conditions d’affichage DOT → LeoSoft

Généré par `scripts/report_show_when_gaps.py`.

## Résumé import

- Ajoutés : **47**
- Mis à jour : **240**
- Inchangés : **322**
- Sans export JS utilisable : **5**

## Formulaires sans `gf_form_conditional_logic` récupérable

Ces schémas conservent leurs `show_when` déjà présents (s’il y en a).
Pour les compléter : export JSON Gravity Forms (admin WP) ou nouveau dump HTML contenant le blob JS.

- `laa_employee_maison` (GF 37) — champs=28, show_when existants=0, règles extraites=0, marqueurs HTML=0
- `pilier3` (GF 6) — champs=104, show_when existants=51, règles extraites=0, marqueurs HTML=0
- `pilier3_autre` (GF 58) — champs=11, show_when existants=0, règles extraites=0, marqueurs HTML=0
- `pilier3_standard` (GF 37) — champs=16, show_when existants=0, règles extraites=0, marqueurs HTML=0
- `protection_juridique_entreprise` (GF 36) — champs=49, show_when existants=0, règles extraites=0, marqueurs HTML=0

## Conditionnels GF orphelins (id présent dans le blob, absent du schéma LeoSoft)

- `assurances_particulier_var` : gf_field_id [38]

## Ce qui reste impossible sans nouvel export DOT

1. Toute règle absente du blob JS **et** absente du JSON LeoSoft actuel.
2. Les stubs `gf_*.json` / `menage.json` sans champs.
3. Reconstruction heuristique « champ suivant un Oui/Non » sans marqueur GF — volontairement non appliquée.

## Correctifs post-audit (pré-déploiement)

- `assurances_particulier_var` : 3 `show_when` importés depuis GF47 (animaux) référencent des parents absents (`input_15`, `input_21`, `input_45`) → **retirés** pour éviter des champs définitivement masqués.
- Opérateurs numériques `>` / `<` (seuils 500000) : désormais évalués correctement côté backend + frontend (sinon traités à tort comme égalité de chaînes).
- Effacement des valeurs masquées : uniquement si le **parent a une réponse explicite** (Oui/Non/etc.). Réouverture d’un dossier avec parent vide **conserve** les valeurs déjà enregistrées.

## Schémas actifs — couverture `show_when`

| Schéma | GF | Champs | show_when |
|--------|----|--------|-----------|
| `animaux` | 47 | 52 | 10 |
| `assurances_particulier` | 11 | 68 | 8 |
| `assurances_particulier_var` | 47 | 26 | 0 |
| `attestation_vehicule` | 110 | 31 | 2 |
| `entreprise` | 13 | 129 | 90 |
| `entreprise_27` | 27 | 52 | 16 |
| `entreprise_28` | 28 | 51 | 15 |
| `entreprise_29` | 29 | 53 | 13 |
| `entreprise_31` | 31 | 49 | 13 |
| `entreprise_32` | 32 | 74 | 32 |
| `entreprise_33` | 33 | 67 | 11 |
| `entreprise_46` | 46 | 35 | 7 |
| `entreprise_50` | 50 | 131 | 33 |
| `entreprise_offres` | 14 | 88 | 24 |
| `formulaire_complet` | 94 | 155 | 109 |
| `laa_employee_maison` | 37 | 28 | 0 |
| `menage_rc` | 1 | 109 | 57 |
| `motocycle` | 9 | 91 | 21 |
| `pilier3` | 6 | 104 | 51 |
| `pilier3_autre` | 58 | 11 | 0 |
| `pilier3_parent_enfant` | 41 | 78 | 19 |
| `pilier3_risque_pur` | 42 | 118 | 67 |
| `pilier3_standard` | 37 | 16 | 0 |
| `protection_juridique_entreprise` | 36 | 49 | 0 |
| `protection_juridique_entreprise_2` | 38 | 44 | 1 |
| `protection_juridique_particulier` | 35 | 48 | 11 |
| `rc_entreprise` | 30 | 50 | 9 |
| `vehicule` | 8 | 110 | 37 |
| `voyage` | 12 | 137 | 34 |
