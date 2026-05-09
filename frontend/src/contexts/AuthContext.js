import React, { createContext, useContext, useState, useEffect } from "react";
import api from "../api";
const STORAGE_KEY = "invoice_auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
  
    if (!stored) {
      setLoading(false);
      return;
    }
  
    try {
      const { token: t } = JSON.parse(stored);
  
      setToken(t);
  
      api
        .get("/auth/me", {
          headers: {
            Authorization: `Bearer ${t}`
          }
        })
        .then((res) => {
          setUser(res.data?.user || null);
        })
        .catch(() => {
          localStorage.removeItem(STORAGE_KEY);
          setToken(null);
          setUser(null);
        })
        .finally(() => setLoading(false));
  
    } catch {
      localStorage.removeItem(STORAGE_KEY);
      setLoading(false);
    }
  }, []);

  const saveAuth = (newToken, newUser) => {
    setToken(newToken);
    setUser(newUser);
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: newToken, user: newUser }));
  };

  const login = async (email, password) => {
    const res = await api.post("/auth/signin", {
      email,
      password,
    });
  
    const { token, user } = res.data;
  
    saveAuth(token, user);
  
    return user;   // ✅ retourne bien l’utilisateur
  };

  const signup = async (email, password, fullName, role) => {
    const res = await api.post("/auth/signup", {
      email,
      password,
      full_name: fullName,
      role,
    });
    const { token: t, user: u } = res.data;
    saveAuth(t, u);
    return u;
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  };

  const getAuthHeader = () => (token ? { Authorization: `Bearer ${token}` } : {});

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        login,
        signup,
        logout,
        isAuthenticated: !!token,
        getAuthHeader,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
