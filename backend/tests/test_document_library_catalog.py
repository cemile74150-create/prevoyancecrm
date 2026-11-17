"""Catalogue bibliothèque documentaire : PDF système hors lettres/courriers."""

from pathlib import Path

from pdf_generator import (
    DOCUMENT_TEMPLATES,
    is_letter_or_courrier_template,
    list_blank_pdf_forms_for_library,
    read_blank_system_pdf,
)

SERVER_PY = Path(__file__).resolve().parents[1] / "server.py"


def test_letters_and_courriers_are_detected():
    letters = [t for t in DOCUMENT_TEMPLATES if is_letter_or_courrier_template(t)]
    ids = {t["id"] for t in letters}
    assert "lettre_lpp" in ids
    assert "lettre_avs" in ids
    assert "lettre_decompte_lpp" in ids


def test_blank_pdf_catalog_excludes_letters_and_keeps_forms():
    rows = list_blank_pdf_forms_for_library()
    ids = {r["system_template_id"] for r in rows}
    assert "mandat_de_gestion" in ids
    assert "procuration_avs_lpp" in ids
    assert "recherche_avoirs_lpp" in ids
    assert "calcul_rente_future" in ids
    assert "fiche_client" in ids
    assert "lettre_lpp" not in ids
    assert "lettre_avs" not in ids
    assert "lettre_decompte_lpp" not in ids
    filenames = [r["original_filename"].lower() for r in rows]
    assert len(filenames) == len(set(filenames))
    for row in rows:
        assert row["source"] == "system"
        assert row["can_map"] is False
        assert row["can_delete"] is False
        assert str(row["original_filename"]).lower().endswith(".pdf")


def test_read_blank_system_pdf_returns_pdf_bytes():
    data, filename, label = read_blank_system_pdf("mandat_de_gestion")
    assert data[:4] == b"%PDF"
    assert filename.lower().endswith(".pdf")
    assert "mandat" in label.lower()


def test_blank_system_pdfs_match_template_files_on_disk():
    """Chaque téléchargement vierge = fichier modèle brut, sans données client."""
    from pdf_generator import TEMPLATES_DIR, list_blank_pdf_forms_for_library, read_blank_system_pdf

    for row in list_blank_pdf_forms_for_library():
        tid = row["system_template_id"]
        data, filename, _label = read_blank_system_pdf(tid)
        disk = (TEMPLATES_DIR / filename).read_bytes()
        assert data == disk
        # Heuristique : pas de nom client typique dans le binaire vierge
        lowered = data.lower()
        assert b"miozza" not in lowered
        assert b"imeri" not in lowered


def test_list_form_library_must_not_filter_by_caller_user_id():
    """
    Régression : le code déployé filtrait form_library par user.user_id.
    Les PDF importés (TENANT / local-dev) disparaissaient pour un admin user_*.
    """
    src = SERVER_PY.read_text(encoding="utf-8")
    start = src.index("async def list_form_library")
    end = src.index("@api_router.get(\"/form-library/field-sources\")", start)
    body = src[start:end]
    assert "user.user_id" not in body
    assert "_form_library_active_query" in body
    assert "list_blank_pdf_forms_for_library" in body
    assert "_merge_library_catalog" in body


def test_form_library_lookups_are_cabinet_scoped_not_per_user():
    src = SERVER_PY.read_text(encoding="utf-8")
    helper_start = src.index("async def _find_library_form_record")
    helper_end = src.index("def _dedupe_library_items", helper_start)
    helper = src[helper_start:helper_end]
    assert "user_id" not in helper
    assert "_form_library_active_query" in helper


def test_merge_catalog_keeps_imports_and_system_without_duplicate_names():
    # Logique miroir de _merge_library_catalog / _dedupe (sans importer server.py).
    def name_key(v):
        return str(v or "").strip().lower()

    def dedupe(items):
        out, seen_fn, seen_nm = [], set(), set()
        for item in items:
            fn, nm = name_key(item.get("original_filename")), name_key(item.get("name"))
            if fn and fn in seen_fn:
                continue
            if nm and nm in seen_nm:
                continue
            if fn:
                seen_fn.add(fn)
            if nm:
                seen_nm.add(nm)
            out.append(item)
        return out

    def merge(imported, system):
        items = dedupe(imported)
        fns = {name_key(i.get("original_filename")) for i in items if name_key(i.get("original_filename"))}
        nms = {name_key(i.get("name")) for i in items if name_key(i.get("name"))}
        extras = [
            r for r in system
            if not (
                (name_key(r.get("original_filename")) and name_key(r.get("original_filename")) in fns)
                or (name_key(r.get("name")) and name_key(r.get("name")) in nms)
            )
        ]
        return [*extras, *items]

    imported = [
        {"id": "a", "name": "Mandat de gestion", "original_filename": "custom_mandat.pdf"},
        {"id": "b", "name": "Compte libre passage Pictet", "original_filename": "Pictet.pdf"},
    ]
    system = list_blank_pdf_forms_for_library()
    merged = merge(imported, system)
    ids = {row["id"] for row in merged}
    assert "a" in ids
    assert "b" in ids
    # Doublon de nom avec un PDF système → on garde l'import, pas le system:mandat
    assert "system:mandat_de_gestion" not in ids
    assert any(str(i).startswith("system:") for i in ids)
