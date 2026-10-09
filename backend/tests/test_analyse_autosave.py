"""L'enregistrement automatique réécrit le brouillon sans empiler l'historique."""

from analyses_routes import (
    MAX_VERSIONS,
    plan_analyse_autosave,
    plan_analyse_versioned_save,
)


def _doc():
    return {
        "id": "analyse-courante",
        "client_id": "client-a",
        "status": "calculee",
        "version": 4,
        "results": {"lacune": {"revenuApres": 87196}},
        "input": {"client1": {"nom": "Helfer", "prenom": "Wiliam"}},
        "versions": [
            {"at": "2026-10-01T00:00:00+00:00", "status": "brouillon", "input": {"client1": {"nom": "origine"}}},
            {"at": "2026-10-02T00:00:00+00:00", "status": "calculee", "input": {"client1": {"nom": "precedent"}}},
        ],
    }


def _apply(doc, patch):
    """Simule un $set Mongo : les champs absents du patch ne sont pas effacés."""
    doc.update(patch)


def _autosave(doc, prenom, index):
    return plan_analyse_autosave(
        doc,
        saved_input={"client1": {"nom": "Helfer", "prenom": prenom}},
        snapshot={"at": f"snap-{index}", "status": doc["status"], "input": doc["input"], "results": doc["results"]},
        now=f"2026-10-08T12:00:{index:02d}+00:00",
    )


def test_repeated_autosave_keeps_history_and_same_document():
    doc = _doc()
    other = _doc()
    other["id"] = "autre-analyse"
    other["input"] = {"client1": {"nom": "Ne pas toucher"}}
    history = list(doc["versions"])

    first = _autosave(doc, "saisie-0", 0)
    assert "id" not in first
    assert "status" not in first
    assert "results" not in first
    _apply(doc, first)

    for index in range(1, 12):
        patch = _autosave(doc, f"saisie-{index}", index)
        assert "versions" not in patch
        assert "version" not in patch
        _apply(doc, patch)

    assert doc["id"] == "analyse-courante"
    assert doc["version"] == 5
    assert doc["status"] == "calculee"
    assert doc["results"]["lacune"]["revenuApres"] == 87196
    assert doc["versions"][:2] == history
    assert len(doc["versions"]) == 3
    assert doc["versions"][2]["input"]["client1"]["prenom"] == "Wiliam"
    assert doc["input"]["client1"]["prenom"] == "saisie-11"
    assert doc["autosaved"] is True
    assert other["id"] == "autre-analyse"
    assert other["input"]["client1"]["nom"] == "Ne pas toucher"


def test_explicit_save_adds_one_version_and_keeps_previous():
    doc = _doc()
    _apply(doc, _autosave(doc, "Wiliam", 1))
    before = len(doc["versions"])
    previous_first = doc["versions"][0]

    patch = plan_analyse_versioned_save(
        doc,
        saved_input=doc["input"],
        status="calculee",
        snapshot={"at": "t2", "status": doc["status"], "input": doc["input"], "results": doc["results"]},
        now="t2",
    )
    _apply(doc, patch)

    assert len(doc["versions"]) == before + 1
    assert doc["version"] == 6
    assert doc["autosaved"] is False
    assert doc["versions"][0] == previous_first
    assert doc["versions"][-1]["input"]["client1"]["prenom"] == "Wiliam"
    assert doc["id"] == "analyse-courante"


def test_explicit_save_still_caps_history():
    doc = _doc()
    doc["versions"] = [{"at": str(i), "input": {"n": i}} for i in range(MAX_VERSIONS)]
    patch = plan_analyse_versioned_save(
        doc,
        saved_input={"client1": {"nom": "nouveau"}},
        status="brouillon",
        snapshot={"at": "now", "input": {"client1": {"nom": "courant"}}},
        now="now",
    )
    assert len(patch["versions"]) == MAX_VERSIONS
    assert patch["versions"][-1]["input"]["client1"]["nom"] == "courant"
    assert patch["versions"][0]["input"]["n"] == 1
