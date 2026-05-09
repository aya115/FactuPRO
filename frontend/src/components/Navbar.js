import React, { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import "./Navbar.css";

const ROLE_LABELS = {
  comptable: "Comptable",
  superviseur: "Superviseur",
  admin: "Admin"
};

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAuthenticated, logout } = useAuth();

  const role = user?.role;

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const handleLogout = () => {
    logout();
    navigate("/", { replace: true });
  };

  const scrollToSection = (id) => {
    if (location.pathname !== "/") {
      navigate("/", { state: { scrollTo: id } });
      return;
    }
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <header className={`navbar ${scrolled ? "navbar--scrolled" : ""}`}>
      <div className="navbar__inner">

        <Link to="/" className="navbar__brand" aria-label="FactuPRO — accueil">
          <img
            src={`${process.env.PUBLIC_URL}/factupro-logo.png`}
            alt="FactuPRO"
            className="navbar__logo-img"
            width={220}
            height={49}
          />
        </Link>

        <nav className="navbar__links">

          {isAuthenticated ? (
            <>
              <Link
                className={`navbar__link ${location.pathname === "/dashboard" ? "navbar__link--active" : ""}`}
                to="/dashboard"
              >
                Tableau de bord
              </Link>

              {/* ===== MENU ACCESS GLOBAL POUR ADMIN ===== */}
              {(role === "comptable" || role === "admin") && (
                <>
                  <Link
                    className={`navbar__link ${location.pathname === "/invoices" ? "navbar__link--active" : ""}`}
                    to="/invoices"
                  >
                    Factures
                  </Link>

                  <Link
                    className={`navbar__link ${location.pathname === "/assistant" ? "navbar__link--active" : ""}`}
                    to="/assistant"
                  >
                    Assistant IA
                  </Link>
                </>
              )}

              {(role === "superviseur" || role === "admin") && (
                <>
                  <Link
                    className={`navbar__link ${location.pathname === "/metrics" ? "navbar__link--active" : ""}`}
                    to="/metrics"
                  >
                    Métriques
                  </Link>
                </>
              )}

              {/* Admin uniquement */}
              {role === "admin" && (
                <>
                  <Link
                    className={`navbar__link ${location.pathname === "/admin/users" ? "navbar__link--active" : ""}`}
                    to="/admin/users"
                  >
                    Utilisateurs
                  </Link>
                </>
              )}

              <span className="navbar__user">
                {user?.full_name || user?.email}
                <em>({ROLE_LABELS[role] || role})</em>
              </span>

              <button className="navbar__logout" onClick={handleLogout}>
                Déconnexion
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="navbar__link navbar__link--scroll"
                onClick={() => scrollToSection("fonctionnalites")}
              >
                Fonctionnalités
              </button>
              <button
                type="button"
                className="navbar__link navbar__link--scroll"
                onClick={() => scrollToSection("automatisation")}
              >
                Automatisation
              </button>
              <button
                type="button"
                className="navbar__link navbar__link--scroll"
                onClick={() => scrollToSection("demarrer")}
              >
                Démarrer
              </button>
              <button
  type="button"
  className="navbar__link navbar__link--scroll"
  onClick={() => scrollToSection("contact")}
>
  Contact
</button>
              <Link
                className={`navbar__btn-login ${location.pathname === "/signin" ? "navbar__btn-login--active" : ""}`}
                to="/signin"
              >
                Connexion
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}