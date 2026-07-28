import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import Dashboard from "@/pages/Dashboard";
import Kanban from "@/pages/Kanban";
import Clients from "@/pages/Clients";
import ClientDetail from "@/pages/ClientDetail";
import DossierHub from "@/pages/DossierHub";
import Agenda from "@/pages/Agenda";
import Formulaires from "@/pages/Formulaires";
// Visual PDF field mapping editor (FormMappingEditor) — 2026-07-28

function Protected({ children }) {
  return children;
}

function AppRoutes() {
  const location = useLocation();
  // Handle OAuth callback: session_id arrives in URL fragment
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
      <Route path="/dossiers" element={<Protected><Kanban /></Protected>} />
      <Route path="/clients" element={<Protected><Clients /></Protected>} />
      <Route path="/clients/:id" element={<Protected><ClientDetail /></Protected>} />
      <Route path="/dossiers/:dossierId" element={<Protected><DossierHub /></Protected>} />
      <Route path="/agenda" element={<Protected><Agenda /></Protected>} />
      <Route path="/formulaires" element={<Protected><Formulaires /></Protected>} />
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