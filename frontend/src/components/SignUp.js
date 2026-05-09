import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import api from "../api";
import "./Auth.css";

const ROLES = [
  { value: "comptable", label: "Comptable" },
  { value: "superviseur", label: "Superviseur" },
];

export default function SignUp() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState("comptable");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) navigate("/", { replace: true });
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Les mots de passe ne correspondent pas");
      return;
    }
    if (password.length < 6) {
      setError("Mot de passe minimum 6 caractères");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/signup", {
        email,
        password,
        full_name: fullName || null,
        role,
      });
      navigate("/signin", { replace: true });
    } catch (err) {
      setError(err.response?.data?.error || err.message || "Erreur d'inscription");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <img
          className="auth-brand-logo"
          src={`${process.env.PUBLIC_URL}/factupro-logo.png`}
          alt="FactuPRO"
          width={260}
          height={58}
        />
        <h1 className="auth-title">Inscription</h1>
        <p className="auth-subtitle">Créer un compte FactuPRO</p>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-label">Email</label>
          <input
            className="auth-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="vous@cabinet.fr"
            required
            autoComplete="email"
            disabled={loading}
          />

          <label className="auth-label">Nom complet (optionnel)</label>
          <input
            className="auth-input"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Jean Dupont"
            disabled={loading}
          />

          <label className="auth-label">Rôle</label>
          <select
            className="auth-input auth-select"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={loading}
          >
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>

          <label className="auth-label">Mot de passe (min. 6 caractères)</label>
          <input
            className="auth-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            minLength={6}
            autoComplete="new-password"
            disabled={loading}
          />

          <label className="auth-label">Confirmer le mot de passe</label>
          <input
            className="auth-input"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="••••••••"
            required
            autoComplete="new-password"
            disabled={loading}
          />

          {error && <div className="auth-error">{error}</div>}

          <button className="auth-btn" type="submit" disabled={loading}>
            {loading ? "Inscription…" : "S'inscrire"}
          </button>
        </form>

        <p className="auth-footer">
          Déjà inscrit ? <Link to="/signin">Se connecter</Link>
        </p>
      </div>
    </div>
  );
}
