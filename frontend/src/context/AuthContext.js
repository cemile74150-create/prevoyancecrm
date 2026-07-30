import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const res = await api.get("/auth/me");
      setUser(res.data);
    } catch (e) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {
      /* ignore */
    }
    setUser(null);
    window.location.href = "/login";
  };

  const isAdmin = user?.role === "admin" || user?.can_manage_users;
  const isGlobal = user?.role === "admin" || user?.role === "ceo";

  return (
    <AuthContext.Provider
      value={{ user, setUser, loading, checkAuth, logout, isAdmin, isGlobal }}
    >
      {children}
    </AuthContext.Provider>
  );
};
