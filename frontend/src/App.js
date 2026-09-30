import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Kanban from "@/pages/Kanban";
import Clients from "@/pages/Clients";
import ClientDetail from "@/pages/ClientDetail";
import DossierHub from "@/pages/DossierHub";
import Agenda from "@/pages/Agenda";
import Rappels from "@/pages/Rappels";
import Formulaires from "@/pages/Formulaires";
import Utilisateurs from "@/pages/Utilisateurs";
import Echeances3P from "@/pages/Echeances3P";
import Suivi3P from "@/pages/Suivi3P";
import Suivi3PFiche from "@/pages/Suivi3PFiche";
import DemandesOffres from "@/pages/DemandesOffres";
import GestionReponsesOffres from "@/pages/GestionReponsesOffres";
import DemandeOffreFiche from "@/pages/DemandeOffreFiche";
import ModifierOffre from "@/pages/ModifierOffre";
import HistoriqueEmails from "@/pages/HistoriqueEmails";
import SuiviTechnique from "@/pages/SuiviTechnique";

function Protected({ children, perm, anyOf }) {
  const { user, loading, hasPerm } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-muted-foreground">
        Chargement…
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  const allowed = perm
    ? hasPerm(perm)
    : anyOf
      ? anyOf.some((k) => hasPerm(k))
      : true;
  if (!allowed) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  return (
    <Routes>
      <Route
        path="/login"
        element={loading ? null : user ? <Navigate to="/dashboard" replace /> : <Login />}
      />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
      <Route path="/dossiers" element={<Protected perm="dossiers.view"><Kanban /></Protected>} />
      <Route path="/clients" element={<Protected perm="clients.view"><Clients /></Protected>} />
      <Route path="/clients/:id" element={<Protected anyOf={["clients.view", "dossiers.view"]}><ClientDetail /></Protected>} />
      <Route path="/dossiers/:dossierId" element={<Protected perm="dossiers.view"><DossierHub /></Protected>} />
      <Route path="/suivi-3p" element={<Protected perm="suivi_3p.view"><Suivi3P /></Protected>} />
      <Route path="/suivi-3p/:clientId" element={<Protected perm="suivi_3p.view"><Suivi3PFiche /></Protected>} />
      <Route path="/demandes-offres" element={<Protected perm="demandes_offres.view"><DemandesOffres /></Protected>} />
      <Route path="/gestion-reponses-offres" element={<Protected perm="demandes_offres.process"><GestionReponsesOffres /></Protected>} />
      <Route path="/modifier-offre" element={<Protected perm="demandes_offres.edit"><ModifierOffre /></Protected>} />
      <Route path="/demandes-offres/:demandeId" element={<Protected perm="demandes_offres.view"><DemandeOffreFiche /></Protected>} />
      <Route path="/historique-emails" element={<Protected anyOf={["users.manage"]}><HistoriqueEmails /></Protected>} />
      <Route path="/rappels" element={<Protected perm="rappels.view"><Rappels /></Protected>} />
      <Route path="/demandes" element={<Navigate to="/rappels" replace />} />
      <Route path="/agenda" element={<Protected perm="agenda.view"><Agenda /></Protected>} />
      <Route path="/echeances-3p" element={<Protected anyOf={["agenda.view", "suivi_3p.view", "dossiers.view"]}><Echeances3P /></Protected>} />
      <Route path="/formulaires" element={<Protected perm="formulaires.view"><Formulaires /></Protected>} />
      <Route path="/utilisateurs" element={<Protected perm="users.manage"><Utilisateurs /></Protected>} />
      <Route path="/suivi-technique" element={<Protected perm="users.manage"><SuiviTechnique /></Protected>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
          <Toaster position="top-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}
export default App;
