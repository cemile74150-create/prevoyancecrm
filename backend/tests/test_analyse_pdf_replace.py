"""Remplacement d'un PDF d'analyse de même nom, pour le même client seulement."""
from datetime import date

from suivi_3p import (
    COLLECTION_CLIENTS,
    COLLECTION_DOCS,
    attach_computed_age,
    birth_date_for_analyse_import,
    commit_analyse_pdf_import,
    find_same_filename_docs,
    mongo_persist_analyse_import,
    normalize_analyse_filename,
    other_duplicate_reason,
)


NOW = "2026-10-05T12:00:00+00:00"
USER = "local-dev"


class MemStorage:
    def __init__(self):
        self.objects = {}

    def put(self, logical, data, content_type):
        path = "mem://" + logical
        self.objects[path] = bytes(data)
        return {"path": path, "size": len(data)}

    def delete(self, path):
        del self.objects[path]


def _client(**extra):
    base = {
        "id": "client-a",
        "user_id": USER,
        "prenom": "Jean",
        "nom": "Martin",
        "date_naissance": None,
        "notes": "note LeoSoft",
        "telephone": "0790000000",
        "email": "jean@example.ch",
        "statut_suivi": "À analyser",
        "conseiller": "Cemile",
        "adresse": "Rue du Test 1",
        "gain_fiscal_estime": 900,
    }
    base.update(extra)
    return base


def _doc(**extra):
    base = {
        "id": "doc-old",
        "user_id": USER,
        "suivi_3p_client_id": "client-a",
        "original_filename": "MARTIN Jean.pdf",
        "storage_path": "mem://old/martin.pdf",
        "size": 4,
        "content_sha256": "old",
        "extracted_gain_fiscal": 100,
        "extracted_date_naissance": "1970-01-01",
        "category": "Analyse 3e Pilier",
        "is_deleted": False,
        "created_at": "2024-01-01T00:00:00+00:00",
        "leosoft_note": "garder",
    }
    base.update(extra)
    return base


def _import(documents, client, storage, *, filename="MARTIN Jean.pdf", data=b"%PDF-new", gain=1500, birth="04.10.1976", **kwargs):
    return commit_analyse_pdf_import(
        documents,
        client,
        filename=filename,
        data=data,
        extracted_gain=gain,
        extracted_birth=birth,
        now=NOW,
        user_id=USER,
        put_object=storage.put,
        delete_object=storage.delete,
        source_folder="PDF - Analyse Fortune",
        display_label="Analyse optimisation fiscale",
        **kwargs,
    )


def _age(client, documents):
    active = [d for d in documents if isinstance(d, dict) and not d.get("is_deleted")]
    rows = attach_computed_age([client], {client["id"]: active}, today=date(2026, 10, 5))
    return rows[0]["age"]


def test_normalize_filename_is_basename_case_and_space_only():
    assert normalize_analyse_filename(r"C:\pdfs\MARTIN Jean.PDF") == normalize_analyse_filename("martin  jean.pdf")
    assert normalize_analyse_filename("MARTIN_Jean.pdf") != normalize_analyse_filename("MARTIN Jean.pdf")


def test_new_pdf_creates_one_document():
    storage = MemStorage()
    documents = []
    client = _client()
    result = _import(documents, client, storage, birth=None, gain=420)
    assert result["action"] == "created"
    assert len(documents) == 1
    assert documents[0]["suivi_3p_client_id"] == "client-a"
    assert documents[0]["extracted_gain_fiscal"] == 420
    assert len(storage.objects) == 1
    assert result["client"]["notes"] == "note LeoSoft"
    assert result["client"]["telephone"] == "0790000000"
    assert "date_naissance" not in result["client_updates"]


def test_same_name_same_client_replaces_document_and_storage():
    storage = MemStorage()
    storage.objects["mem://old/martin.pdf"] = b"OLD"
    documents = [_doc()]
    original_id = documents[0]["id"]
    client = _client(date_naissance=None)
    result = _import(documents, client, storage, filename="martin  jean.PDF", data=b"%PDF-NEWER", gain=2222, birth="04.10.1976")

    active = [d for d in documents if not d.get("is_deleted")]
    assert result["action"] == "replaced"
    assert len(active) == 1
    assert active[0]["id"] == original_id
    assert active[0]["suivi_3p_client_id"] == "client-a"
    assert active[0]["extracted_gain_fiscal"] == 2222
    assert active[0]["extracted_date_naissance"] == "1976-10-04"
    assert active[0]["leosoft_note"] == "garder"
    assert "mem://old/martin.pdf" not in storage.objects
    assert list(storage.objects.values()) == [b"%PDF-NEWER"]
    assert result["client"]["notes"] == "note LeoSoft"
    assert result["client"]["conseiller"] == "Cemile"
    assert result["client"]["adresse"] == "Rue du Test 1"
    assert result["client"]["statut_suivi"] == "À analyser"
    assert result["client_updates"]["date_naissance"] == "1976-10-04"
    assert result["client_updates"]["gain_fiscal_estime"] == 2222


def test_same_name_other_client_is_not_replaced():
    storage = MemStorage()
    storage.objects["mem://old/martin.pdf"] = b"CLIENT-A"
    storage.objects["mem://other/martin.pdf"] = b"CLIENT-B"
    other = _doc(
        id="doc-b",
        suivi_3p_client_id="client-b",
        storage_path="mem://other/martin.pdf",
        extracted_gain_fiscal=5,
        extracted_date_naissance="1960-01-01",
        leosoft_note="fiche B",
    )
    documents = [_doc(), other]
    snapshot_b = dict(other)
    result = _import(documents, _client(), storage, data=b"%PDF-A-ONLY", gain=333, birth="04.10.1976")

    assert result["action"] == "replaced"
    assert result["document"]["suivi_3p_client_id"] == "client-a"
    assert other == snapshot_b
    assert storage.objects["mem://other/martin.pdf"] == b"CLIENT-B"
    assert find_same_filename_docs(documents, client_id="client-b", filename="MARTIN Jean.pdf")[0]["id"] == "doc-b"
    assert all(d.get("suivi_3p_client_id") != "client-b" or d["extracted_gain_fiscal"] == 5 for d in documents)


def test_no_birth_date_leaves_age_empty_and_does_not_wipe_fiche():
    storage = MemStorage()
    storage.objects["mem://old/martin.pdf"] = b"OLD"
    documents = [_doc(extracted_date_naissance="1976-10-04")]
    client = _client(date_naissance="", gain_fiscal_estime=900, notes="ne pas effacer", telephone="0220000000")
    result = _import(documents, client, storage, data=b"%PDF-SANS-DATE", gain=None, birth=None)

    assert "date_naissance" not in result["client_updates"]
    assert "gain_fiscal_estime" not in result["client_updates"]
    assert result["client"]["notes"] == "ne pas effacer"
    assert result["client"]["telephone"] == "0220000000"
    assert result["client"]["gain_fiscal_estime"] == 900
    assert result["client"]["email"] == "jean@example.ch"
    assert result["document"]["extracted_date_naissance"] is None
    assert _age(result["client"], documents) is None


def test_birth_date_found_on_replacement_fills_empty_fiche():
    storage = MemStorage()
    storage.objects["mem://old/martin.pdf"] = b"OLD"
    documents = [_doc(extracted_date_naissance=None)]
    client = _client(date_naissance=None)
    result = _import(documents, client, storage, birth="04.10.1976", gain=10)
    assert result["client_updates"]["date_naissance"] == "1976-10-04"
    assert result["client"]["notes"] == "note LeoSoft"
    assert _age(result["client"], documents) == 50


def test_manual_birth_date_different_from_old_extract_is_kept():
    storage = MemStorage()
    storage.objects["mem://old/martin.pdf"] = b"OLD"
    documents = [_doc(extracted_date_naissance="1976-10-04")]
    client = _client(date_naissance="1980-01-15", notes="saisie manuelle")
    result = _import(documents, client, storage, birth="01.02.1975", gain=80)
    assert "date_naissance" not in result["client_updates"]
    assert result["client"]["date_naissance"] == "1980-01-15"
    assert result["client"]["notes"] == "saisie manuelle"
    assert result["document"]["extracted_date_naissance"] == "1975-02-01"
    assert _age(result["client"], documents) == completed_age_of("1980-01-15")


def completed_age_of(iso):
    from suivi_3p import completed_age

    return completed_age(iso, today=date(2026, 10, 5))


def test_fiche_birth_equal_to_previous_extract_is_updated_from_new_pdf():
    storage = MemStorage()
    storage.objects["mem://old/martin.pdf"] = b"OLD"
    documents = [_doc(extracted_date_naissance="04.10.1976")]
    client = _client(date_naissance="1976-10-04", telephone="0791111111")
    result = _import(documents, client, storage, birth="15.06.1981", gain=50)
    assert result["client_updates"]["date_naissance"] == "1981-06-15"
    assert result["client"]["telephone"] == "0791111111"
    assert result["client"]["conseiller"] == "Cemile"
    assert _age(result["client"], documents) == completed_age_of("1981-06-15")


def test_encrypted_birth_date_is_not_overwritten():
    assert birth_date_for_analyse_import(
        "enc:v1:secret",
        "1981-06-15",
        previous_extracted="1976-10-04",
    ) is None


def test_different_filename_stays_a_new_document():
    storage = MemStorage()
    storage.objects["mem://old/martin.pdf"] = b"OLD"
    documents = [_doc()]
    result = _import(documents, _client(), storage, filename="MARTIN_Jean.pdf", data=b"%PDF-OTHER", gain=7, birth=None)
    assert result["action"] == "created"
    assert len([d for d in documents if not d.get("is_deleted")]) == 2
    assert storage.objects["mem://old/martin.pdf"] == b"OLD"


def test_same_stem_and_size_under_another_name_is_still_a_skip_not_a_replace():
    docs = [_doc(original_filename="MARTIN Jean.docx", size=8)]
    reason = other_duplicate_reason(docs, client_id="client-a", filename="MARTIN Jean.pdf", data=b"12345678")
    assert reason == "deja_importe_stem_size"
    assert find_same_filename_docs(docs, client_id="client-a", filename="MARTIN Jean.pdf") == []


class _Coll:
    def __init__(self, docs):
        self.docs = docs
        self.ops = []

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        self.ops.append(("insert", dict(doc)))

    def update_one(self, filt, update):
        self.ops.append(("update", dict(filt), dict(update["$set"])))
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in filt.items()):
                doc.update(update["$set"])
                return


class _DB:
    def __init__(self):
        self.docs = _Coll([
            _doc(),
            _doc(id="doc-b", suivi_3p_client_id="client-b", storage_path="mem://other/martin.pdf", extracted_gain_fiscal=5),
        ])
        self.clients = _Coll([
            _client(),
            _client(id="client-b", prenom="Paul", notes="autre client"),
        ])

    def __getitem__(self, name):
        if name == COLLECTION_DOCS:
            return self.docs
        if name == COLLECTION_CLIENTS:
            return self.clients
        raise KeyError(name)


def test_mongo_persist_updates_only_the_matching_client():
    storage = MemStorage()
    storage.objects["mem://old/martin.pdf"] = b"OLD"
    documents = [_doc(), _doc(id="doc-b", suivi_3p_client_id="client-b", storage_path="mem://other/martin.pdf")]
    db = _DB()

    def persist(plan, document):
        mongo_persist_analyse_import(db, plan)

    result = _import(documents, _client(), storage, data=b"%PDF-A", gain=77, birth=None, persist=persist)
    assert result["action"] == "replaced"
    updated = [op for op in db.docs.ops if op[0] == "update"]
    assert updated
    assert all(op[1].get("suivi_3p_client_id") == "client-a" for op in updated)
    other = next(d for d in db.docs.docs if d["id"] == "doc-b")
    assert other["extracted_gain_fiscal"] == 5
    assert other["storage_path"] == "mem://other/martin.pdf"
    client_b = next(c for c in db.clients.docs if c["id"] == "client-b")
    assert client_b["notes"] == "autre client"
    client_a = next(c for c in db.clients.docs if c["id"] == "client-a")
    assert client_a["notes"] == "note LeoSoft"
    assert client_a["telephone"] == "0790000000"
    assert "date_naissance" not in client_a or client_a.get("date_naissance") in (None, "")
