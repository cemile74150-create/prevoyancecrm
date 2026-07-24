"""Backend API tests for Prévoyance CRM."""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://prevoyance-crm.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TOKEN = "test_session_fixed_001"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def client_id():
    """Create a TEST client for CRUD tests, return id. Cleaned up at teardown."""
    r = requests.post(f"{API}/clients", headers=HEADERS, json={
        "prenom": "TESTPrenom", "nom": "TESTNom", "email": "test_crud@example.com",
        "telephone": "+41791234567", "statut": "Nouveau", "priorite": "normale",
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    yield cid
    requests.delete(f"{API}/clients/{cid}", headers=HEADERS)


# ---------------- Auth ----------------
class TestAuth:
    def test_me_with_bearer(self):
        r = requests.get(f"{API}/auth/me", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == "user_testconseiller1"
        assert data["email"] == "conseiller@cabinet.ch"

    def test_me_without_auth(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_clients_without_auth(self):
        r = requests.get(f"{API}/clients")
        assert r.status_code == 401

    def test_invalid_token(self):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": "Bearer invalid_xxx"})
        assert r.status_code == 401


# ---------------- Clients CRUD ----------------
class TestClients:
    def test_list_clients(self):
        r = requests.get(f"{API}/clients", headers=HEADERS)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_client_dossier_number(self, client_id):
        # verify dossier number format via GET
        r = requests.get(f"{API}/clients/{client_id}", headers=HEADERS)
        assert r.status_code == 200
        c = r.json()
        assert c["numero_dossier"].startswith("DOS-")
        assert len(c["numero_dossier"]) == 8
        assert c["prenom"] == "TESTPrenom"

    def test_update_client(self, client_id):
        r = requests.put(f"{API}/clients/{client_id}", headers=HEADERS, json={
            "prenom": "TESTPrenom", "nom": "TESTNomUpdated", "email": "test_crud@example.com",
            "telephone": "+41791234567", "statut": "Nouveau", "priorite": "normale",
        })
        assert r.status_code == 200
        assert r.json()["nom"] == "TESTNomUpdated"
        # persistence
        g = requests.get(f"{API}/clients/{client_id}", headers=HEADERS)
        assert g.json()["nom"] == "TESTNomUpdated"

    def test_patch_statut(self, client_id):
        r = requests.patch(f"{API}/clients/{client_id}/statut", headers=HEADERS,
                           json={"statut": "Documents demandés"})
        assert r.status_code == 200
        assert r.json()["statut"] == "Documents demandés"

    def test_patch_statut_invalid(self, client_id):
        r = requests.patch(f"{API}/clients/{client_id}/statut", headers=HEADERS,
                           json={"statut": "InvalidStatus"})
        assert r.status_code == 400

    def test_search_by_name(self):
        r = requests.get(f"{API}/clients", headers=HEADERS, params={"q": "TESTPrenom"})
        assert r.status_code == 200
        assert any(c.get("prenom") == "TESTPrenom" for c in r.json())


# ---------------- Dashboard ----------------
class TestDashboard:
    def test_dashboard_stats(self):
        r = requests.get(f"{API}/dashboard/stats", headers=HEADERS)
        assert r.status_code == 200
        d = r.json()
        for k in ["by_statut", "total", "urgent", "today_appointments", "monthly", "pending_tasks"]:
            assert k in d
        assert isinstance(d["monthly"], list)
        assert len(d["monthly"]) == 6
        assert isinstance(d["by_statut"], dict)
        assert "Nouveau" in d["by_statut"]


# ---------------- Notes ----------------
class TestNotes:
    def test_add_and_list_note(self, client_id):
        r = requests.post(f"{API}/clients/{client_id}/notes", headers=HEADERS,
                          json={"content": "TEST note content"})
        assert r.status_code == 200
        assert r.json()["content"] == "TEST note content"
        g = requests.get(f"{API}/clients/{client_id}/notes", headers=HEADERS)
        assert g.status_code == 200
        assert any(n["content"] == "TEST note content" for n in g.json())


# ---------------- Documents ----------------
class TestDocuments:
    doc_id = None

    def test_upload_document(self, client_id):
        pdf_bytes = b"%PDF-1.4\n%test\n%%EOF"
        files = {"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        data = {"category": "Autre"}
        r = requests.post(f"{API}/clients/{client_id}/documents",
                          headers=HEADERS, files=files, data=data)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["original_filename"] == "test.pdf"
        assert j["category"] == "Autre"
        TestDocuments.doc_id = j["id"]

    def test_list_documents(self, client_id):
        r = requests.get(f"{API}/clients/{client_id}/documents", headers=HEADERS)
        assert r.status_code == 200
        assert any(d["id"] == TestDocuments.doc_id for d in r.json())

    def test_download_document(self):
        r = requests.get(f"{API}/documents/{TestDocuments.doc_id}/download", headers=HEADERS)
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

    def test_delete_document(self, client_id):
        r = requests.delete(f"{API}/documents/{TestDocuments.doc_id}", headers=HEADERS)
        assert r.status_code == 200
        g = requests.get(f"{API}/clients/{client_id}/documents", headers=HEADERS)
        assert not any(d["id"] == TestDocuments.doc_id for d in g.json())


# ---------------- Appointments ----------------
class TestAppointments:
    appt_id = None

    def test_create_appointment(self, client_id):
        r = requests.post(f"{API}/appointments", headers=HEADERS, json={
            "titre": "TEST Appointment", "date": "2026-12-15T10:00:00",
            "duree": 60, "type": "Rendez-vous", "client_id": client_id,
        })
        assert r.status_code == 200
        j = r.json()
        assert j["titre"] == "TEST Appointment"
        TestAppointments.appt_id = j["id"]

    def test_list_appointments(self):
        r = requests.get(f"{API}/appointments", headers=HEADERS)
        assert r.status_code == 200
        assert any(a["id"] == TestAppointments.appt_id for a in r.json())

    def test_toggle_appointment(self):
        r = requests.patch(f"{API}/appointments/{TestAppointments.appt_id}", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["done"] is True

    def test_delete_appointment(self):
        r = requests.delete(f"{API}/appointments/{TestAppointments.appt_id}", headers=HEADERS)
        assert r.status_code == 200


# ---------------- Tasks ----------------
class TestTasks:
    task_id = None

    def test_create_task(self):
        r = requests.post(f"{API}/tasks", headers=HEADERS, json={
            "titre": "TEST Task", "echeance": "2026-12-20", "priorite": "normale",
        })
        assert r.status_code == 200
        j = r.json()
        assert j["titre"] == "TEST Task"
        TestTasks.task_id = j["id"]

    def test_list_tasks(self):
        r = requests.get(f"{API}/tasks", headers=HEADERS)
        assert r.status_code == 200
        assert any(t["id"] == TestTasks.task_id for t in r.json())

    def test_toggle_task(self):
        r = requests.patch(f"{API}/tasks/{TestTasks.task_id}", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["done"] is True

    def test_delete_task(self):
        r = requests.delete(f"{API}/tasks/{TestTasks.task_id}", headers=HEADERS)
        assert r.status_code == 200


# ---------------- Actions history ----------------
class TestActions:
    def test_list_actions(self, client_id):
        r = requests.get(f"{API}/clients/{client_id}/actions", headers=HEADERS)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) > 0
