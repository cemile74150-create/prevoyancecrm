# Sources Gravity Forms (conditions d’affichage)

Artefacts récupérés depuis les dumps intranet DOT / Chrome view-source, utilisés pour renseigner `show_when` dans `offre_form_schemas/`.

## Contenu

| Fichier / dossier | Rôle |
|-------------------|------|
| `manifest.json` | Inventaire des dumps lus + couverture par schéma |
| `conditional_logic/{gid}.json` | Règles extraites de `gf_form_conditional_logic[gid]` |
| `import_show_when_report.json` | Dernier rapport d’import (added/updated/gaps) |
| `GAPS.md` | Conditions impossibles à retrouver avec les dumps actuels |

## Pipeline

```bash
cd backend
python scripts/extract_gf_conditional_logic.py
python scripts/import_show_when_from_gf.py          # écrit les schémas
python scripts/import_show_when_from_gf.py --dry-run
```

Le script d’import **ne modifie que** `show_when` (+ tampon `show_when_import`). Labels, types, options, pages et design UI sont préservés.

## Fiabilité

1. **Fiable** : blob JS `window['gf_form_conditional_logic'][id]`
2. **Insuffisant seul** : `data-conditional-logic="hidden|visible"` (état initial, sans parent/valeur)
3. **Manquant** : formulaires sans dump JS → voir `GAPS.md` (export admin GF nécessaire)
