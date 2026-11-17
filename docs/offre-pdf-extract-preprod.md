# Import PDF intelligent — pré-production

Branche : `feat/offre-pdf-extract-structured`  
Aucun déploiement automatique. Contrôle : `deploy/verifier-avant-deploiement.ps1` (ne déploie pas).

## Feature flag (activation progressive)

| Mode | Variable / setting | Effet |
|------|-------------------|--------|
| **admin** (défaut) | `OFFRE_PDF_STRUCTURED_EXTRACT=admin` | Nouvel extract + mapping visibles **admins / ceo / users.manage** seulement |
| **on** | `OFFRE_PDF_STRUCTURED_EXTRACT=on` | Tous les utilisateurs édition offres |
| **off** (kill-switch) | `OFFRE_PDF_STRUCTURED_EXTRACT=off` | Ancien chemin `analyse-pdf` / `offre_pdf_form_fill` sans mapping structuré |

Surcharge runtime Mongo : `app_settings.key = offre_pdf_structured_extract`, `value` ∈ `admin|on|off`.

UI : `GET /demandes-offres/meta` expose `pdf_extract_structured_enabled` + `pdf_extract_structured_mode`.  
API : `POST .../modifier/analyse-pdf` respecte le flag pour chaque utilisateur.

### Rollback immédiat

1. Railway / env : `OFFRE_PDF_STRUCTURED_EXTRACT=off` **ou**
2. Mongo : `db.app_settings.updateOne({key:"offre_pdf_structured_extract"}, {$set:{value:"off"}}, {upsert:true})`

Pas besoin de redéployer une ancienne image si le flag est lu au runtime (settings) ; un redéploiement env suffit sinon.

## OCR Railway (fra / deu / eng)

Le `Dockerfile` installe déjà :

- `tesseract-ocr`
- `tesseract-ocr-fra`
- `tesseract-ocr-deu`
- `tesseract-ocr-eng`
- `TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata`
- `OCR_TESSDATA_CANDIDATES=...` (fallbacks distro)

Après GO prod, vérifier sans PDF client dans les logs :

```text
# dans le conteneur Railway
tesseract --list-langs
# doit lister fra, deu, eng
```

L’app loggue uniquement : `OCR pytesseract ok pages=… chars=… langs=… tessdata=…` (pas le contenu PDF).

## Tableaux scannés — limites

1. **PDF texte** : PyMuPDF `find_tables` → blocs `[table pN.M]`.
2. **PDF scan / image** : OCR Tesseract (images embarquées puis pixmap) + heuristiques lignes/colonnes `[ocr-table-heuristics]`.
3. **Limites** : pas de modèle vision ML ; colonnes mal OCR → ligne ignorée (pas d’invention) ; tableaux multi-pages complexes restent fragiles.

## Identité AXA — politique zéro faux positif

Si doute (Broker Service Center, Suisse Romande, date prise pour prénom, etc.) → champ vide / `to_verify`, **jamais** un faux prénom/nom prérempli.

## Confidentialité & coûts

- OCR **local** (Tesseract in-process) — **aucune API cloud** externe pour le PDF.
- Pas d’envoi des PDF clients hors infra LeoSoft / Railway.
- Ne pas committer de PDF clients ; ne pas logger le texte extrait (seulement métadonnées OCR).
- Coût = CPU conteneur pendant OCR (pas de facturation token LLM).

## Vérification perf locale (indicatif)

Sur machine de dev (Windows), harness `python scripts/_real_pdf_report.py --preset 3p` :

| Type PDF | Ordre de grandeur |
|----------|-------------------|
| ELVIA multi-véhicules (~12 p, texte) | ~5–15 s |
| AXA lettre / police (texte+OCR léger) | ~2–10 s |
| Zurich scan photo (OCR images) | ~10–40 s selon pages |
| Gros PDF multi-pages OCR | peut dépasser 60 s |

Mesurer à nouveau après GO sur Railway (CPU partagé).

## Mapping « Modifier une offre »

Champs CRM visibles/éditables alimentés depuis `fields` + `form_payload` + `montant_prime` (hors schéma si besoin). Badges trouvé / à vérifier / absent seulement si flag structuré actif.

## Parcours BDD

Import → préremplissage → correction → enregistrement (`montant_prime` persistée) → réouverture. Tests : `test_offre_form_isolation.py`, `test_offre_pdf_preprod_finalize.py`. Toujours sur DB **locale non-prod**.
