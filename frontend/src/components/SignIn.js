import React, { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import "./Auth.css";
export default function SignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { login, isAuthenticated } = useAuth();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/dashboard", { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    setError("");
    setLoading(true);

    try {
      const user = await login(email, password);

      console.log("LOGIN RESPONSE USER =", user);

      if (!user) {
        setError("Login failed");
        return;
      }

      navigate("/dashboard", { replace: true });

    } catch (err) {
      console.error("LOGIN ERROR FRONTEND:", err);

      setError(
        err.response?.data?.error ||
        "Erreur de connexion serveur"
      );
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
        <h1 className="auth-title">Connexion</h1>
        <p className="auth-subtitle">Plateforme de facturation intelligente</p>

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

          <label className="auth-label">Mot de passe</label>
          <input
            className="auth-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            autoComplete="current-password"
            disabled={loading}
          />

          {error && <div className="auth-error">{error}</div>}

          <button className="auth-btn" type="submit" disabled={loading}>
            {loading ? "Connexion…" : "Se connecter"}
          </button>
        </form>

        <p className="auth-footer">
          Pas de compte ? <Link to="/signup">S'inscrire</Link>
        </p>
      </div>
    </div>
  );
}
