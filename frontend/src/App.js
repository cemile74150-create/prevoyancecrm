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
import Demandes from "@/pages/Demandes";
import Formulaires from "@/pages/Formulaires";
import Utilisateurs from "@/pages/Utilisateurs";

function Protected({ children }) {
  const { user, loading } = useAuth();
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
      <Route path="/dossiers" element={<Protected><Kanban /></Protected>} />
      <Route path="/clients" element={<Protected><Clients /></Protected>} />
      <Route path="/clients/:id" element={<Protected><ClientDetail /></Protected>} />
      <Route path="/dossiers/:dossierId" element={<Protected><DossierHub /></Protected>} />
      <Route path="/demandes" element={<Protected><Demandes /></Protected>} />
      <Route path="/agenda" element={<Protected><Agenda /></Protected>} />
      <Route path="/formulaires" element={<Protected><Formulaires /></Protected>} />
      <Route path="/utilisateurs" element={<Protected><Utilisateurs /></Protected>} />
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
