import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import api from "../api";
import UploadInvoice from "../components/UploadInvoice";
import "./Dashboards.css";

export default function ComptableDashboard() {
  const { user } = useAuth();
  const [invoiceCount, setInvoiceCount] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/invoices", { params: { limit: 1 } })
      .then((res) => setInvoiceCount(res.data?.total ?? 0))
      .catch(() => setInvoiceCount(0))
      .finally(() => setLoading(false));
  }, []);

  const displayName = user?.full_name || user?.email?.split("@")[0] || "Comptable";
  const greeting = new Date().getHours() < 12 ? "Bonjour" : "Bonsoir";

  return (
    <div className="dashboard dashboard--comptable dashboard--modern">
      <header className="dashboard-hero dashboard-hero--comptable">
        <div className="dashboard-hero__content">
          <span className="dashboard__badge dashboard__badge--comptable">Comptable</span>
          <h1 className="dashboard-hero__title">
            {greeting}, <span>{displayName}</span>
          </h1>
          <p className="dashboard-hero__subtitle">
            Déposez vos factures, consultez l’historique et interrogez l’assistant IA.
          </p>
        </div>
        <div className="dashboard-hero__glow" aria-hidden />
      </header>

      {!loading && invoiceCount != null && (
        <section className="dashboard-block">
          <h2 className="dashboard-block__title">Aperçu</h2>
          <div className="metric-grid metric-grid--compact">
            <article className="metric-card metric-card--teal">
              <div className="metric-card__icon" aria-hidden>📄</div>
              <div className="metric-card__body">
                <p className="metric-card__value">{invoiceCount}</p>
                <p className="metric-card__label">Lignes enregistrées</p>
              </div>
            </article>
            <article className="metric-card metric-card--blue">
              <div className="metric-card__icon" aria-hidden>⚡</div>
              <div className="metric-card__body">
                <p className="metric-card__value">Live</p>
                <p className="metric-card__label">Mise à jour temps réel</p>
              </div>
            </article>
          </div>
        </section>
      )}

      <section className="dashboard-block">
        <h2 className="dashboard-block__title">Accès rapide</h2>
        <div className="shortcut-grid">
          <Link to="/messages" className="shortcut-card shortcut-card--primary">
            <span className="shortcut-card__icon" aria-hidden>💬</span>
            <span className="shortcut-card__text">
              <span className="shortcut-card__title">Messagerie</span>
              <span className="shortcut-card__desc">Échanger avec le superviseur</span>
            </span>
            <span className="shortcut-card__arrow" aria-hidden>→</span>
          </Link>
          <Link to="/invoices" className="shortcut-card shortcut-card--default">
            <span className="shortcut-card__icon" aria-hidden>📋</span>
            <span className="shortcut-card__text">
              <span className="shortcut-card__title">Mes factures</span>
              <span className="shortcut-card__desc">Historique et détail</span>
            </span>
            <span className="shortcut-card__arrow" aria-hidden>→</span>
          </Link>
          <Link to="/assistant" className="shortcut-card shortcut-card--default">
            <span className="shortcut-card__icon" aria-hidden>🤖</span>
            <span className="shortcut-card__text">
              <span className="shortcut-card__title">Assistant IA</span>
              <span className="shortcut-card__desc">Questions sur vos données</span>
            </span>
            <span className="shortcut-card__arrow" aria-hidden>→</span>
          </Link>
        </div>
      </section>

      <section className="dashboard-block dashboard-block--upload">
        <div className="dashboard-block__head">
          <h2 className="dashboard-block__title">Importer une facture</h2>
          <Link to="/invoices" className="dashboard-block__link">
            Voir toutes les factures →
          </Link>
        </div>
        <UploadInvoice />
      </section>
    </div>
  );
}
