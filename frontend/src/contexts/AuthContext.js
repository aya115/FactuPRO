import React, { createContext, useContext, useState, useEffect } from "react";
import api from "../api";
const STORAGE_KEY = "invoice_auth";

function readStoredAuth() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.token) return null;
    return parsed;
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = readStoredAuth();

    if (!stored) {
      setLoading(false);
      return;
    }

    setToken(stored.token);
    if (stored.user) {
      setUser(stored.user);
    }

    api
      .get("/auth/me", {
        headers: { Authorization: `Bearer ${stored.token}` },
      })
      .then((res) => {
        const freshUser = res.data?.user || stored.user || null;
        setUser(freshUser);
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ token: stored.token, user: freshUser })
        );
      })
      .catch((err) => {
        if (err.response?.status === 401) {
          localStorage.removeItem(STORAGE_KEY);
          setToken(null);
          setUser(null);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const saveAuth = (newToken, newUser) => {
    setToken(newToken);
    setUser(newUser);
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ token: newToken, user: newUser })
    );
  };

  const login = async (email, password) => {
    const res = await api.post("/auth/signin", {
      email,
      password,
    });

    const { token: newToken, user: newUser } = res.data;

    saveAuth(newToken, newUser);

    return newUser;
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
