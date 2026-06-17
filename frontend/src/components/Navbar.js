import React, { useState, useEffect } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import api from "../api";
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
  const [unreadMessages, setUnreadMessages] = useState(0);

  const role = user?.role;

  useEffect(() => {
    if (!isAuthenticated || (role !== "comptable" && role !== "superviseur")) {
      setUnreadMessages(0);
      return undefined;
    }

    const fetchUnread = () => {
      api
        .get("/chat/unread-count")
        .then((res) => setUnreadMessages(res.data?.unread_count || 0))
        .catch(() => {});
    };

    fetchUnread();
    const id = setInterval(fetchUnread, 15000);
    return () => clearInterval(id);
  }, [isAuthenticated, role]);

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

  const onHero = location.pathname === "/" && !scrolled;

  return (
    <header
      className={`navbar ${scrolled ? "navbar--scrolled" : ""}${onHero ? " navbar--on-hero" : ""}`}
    >
      <div className="navbar__inner">

        <Link to="/" className="navbar__brand" aria-label="FactuPRO — accueil">
          <span className="navbar__wordmark" aria-label="FactuPRO">
            Factu<span>PRO</span>
          </span>
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

              {(role === "comptable" || role === "superviseur") && (
                <Link
                  className={`navbar__link ${location.pathname === "/messages" ? "navbar__link--active" : ""}`}
                  to="/messages"
                >
                  Messages
                  {unreadMessages > 0 && (
                    <span className="navbar__msg-badge">{unreadMessages > 99 ? "99+" : unreadMessages}</span>
                  )}
                </Link>
              )}

              {(role === "superviseur" || role === "admin") && (
                <>
                  <Link
                    className={`navbar__link ${location.pathname === "/metrics" ? "navbar__link--active" : ""}`}
                    to="/metrics"
                  >
                    Métriques
                  </Link>
                  <Link
                    className={`navbar__link ${location.pathname === "/analytics/bi" ? "navbar__link--active" : ""}`}
                    to="/analytics/bi"
                  >
                    Rapport BI
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