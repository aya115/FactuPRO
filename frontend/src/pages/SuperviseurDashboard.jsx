import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import api from "../api";
import "./Dashboards.css";

export default function SuperviseurDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [alerts, setAlerts] = useState([]);
  const [alertsLoading, setAlertsLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get("/metrics").then((res) => setMetrics(res.data || {})).catch(() => setMetrics({})),
      api
        .get("/supervisor/alerts", { params: { unread: 1, limit: 10 } })
        .then((res) => setAlerts(res.data?.alerts || []))
        .catch(() => setAlerts([]))
        .finally(() => setAlertsLoading(false)),
    ]).finally(() => setLoading(false));
  }, []);

  const displayName = user?.full_name || user?.email?.split("@")[0] || "Superviseur";
  const greeting = new Date().getHours() < 12 ? "Bonjour" : "Bonsoir";

  const nbInvoices = metrics?.nb_invoices ?? metrics?.nb_invoices_processed ?? 0;
  const ocrPrecisionLabel =
    metrics?.ocr_precision != null || metrics?.ocr_precision_pct != null
      ? `${Number(metrics.ocr_precision ?? metrics.ocr_precision_pct).toFixed(1)}%`
      : "—";

  const markAsRead = async (alertId) => {
    try {
      await api.put(`/supervisor/alerts/${alertId}/read`);
      setAlerts((prev) => prev.filter((a) => a.id !== alertId));
    } catch (_) {}
  };

  return (
    <div className="dashboard dashboard--superviseur dashboard--modern">
      <header className="dashboard-hero dashboard-hero--superviseur">
        <div className="dashboard-hero__content">
          <span className="dashboard__badge dashboard__badge--superviseur">Superviseur</span>
          <h1 className="dashboard-hero__title">
            {greeting}, <span>{displayName}</span>
          </h1>
          <p className="dashboard-hero__subtitle">
            Contrôle qualité OCR, alertes et rapport Power BI.
          </p>
        </div>
        <div className="dashboard-hero__glow" aria-hidden />
      </header>
      {!loading && (
        <section className="dashboard-block">
          <h2 className="dashboard-block__title">Indicateurs</h2>
          <div className="metric-grid metric-grid--compact">
            <article className="metric-card metric-card--blue">
              <div className="metric-card__icon" aria-hidden>📄</div>
              <div className="metric-card__body">
                <p className="metric-card__value">{nbInvoices}</p>
                <p className="metric-card__label">Factures en base</p>
              </div>
            </article>
            <article className="metric-card metric-card--violet">
              <div className="metric-card__icon" aria-hidden>🎯</div>
              <div className="metric-card__body">
                <p className="metric-card__value">{ocrPrecisionLabel}</p>
                <p className="metric-card__label">Précision OCR</p>
              </div>
            </article>
          </div>
        </section>
      )}

      <section className="dashboard-block">
        <h2 className="dashboard-block__title">Accès rapide</h2>
        <div className="shortcut-grid">
          <Link to="/analytics/bi" className="shortcut-card shortcut-card--primary">
            <span className="shortcut-card__icon" aria-hidden>📊</span>
            <span className="shortcut-card__text">
              <span className="shortcut-card__title">Rapport Power BI</span>
              <span className="shortcut-card__desc">OCR, alertes et analyses</span>
            </span>
            <span className="shortcut-card__arrow" aria-hidden>→</span>
          </Link>
          <a
            href={`${process.env.REACT_APP_GRAFANA_URL || "http://localhost:3030"}/d/factupro-tech`}
            target="_blank"
            rel="noopener noreferrer"
            className="shortcut-card shortcut-card--default"
          >
            <span className="shortcut-card__icon" aria-hidden>📈</span>
            <span className="shortcut-card__text">
              <span className="shortcut-card__title">Grafana (monitoring)</span>
              <span className="shortcut-card__desc">Alertes non lues, perf pipeline</span>
            </span>
            <span className="shortcut-card__arrow" aria-hidden>↗</span>
          </a>
          <Link to="/metrics" className="shortcut-card shortcut-card--default">
            <span className="shortcut-card__icon" aria-hidden>⚙️</span>
            <span className="shortcut-card__text">
              <span className="shortcut-card__title">Métriques</span>
              <span className="shortcut-card__desc">Détail technique du pipeline</span>
            </span>
            <span className="shortcut-card__arrow" aria-hidden>→</span>
          </Link>
          <Link to="/messages" className="shortcut-card shortcut-card--default">
            <span className="shortcut-card__icon" aria-hidden>💬</span>
            <span className="shortcut-card__text">
              <span className="shortcut-card__title">Messagerie</span>
              <span className="shortcut-card__desc">Échanger avec les comptables</span>
            </span>
            <span className="shortcut-card__arrow" aria-hidden>→</span>
          </Link>
        </div>
      </section>

      <section className="dashboard-block">
        <h2 className="dashboard-block__title">Alertes de correction</h2>
        {alertsLoading ? (
          <p className="admin-grid__placeholder">Chargement des alertes…</p>
        ) : alerts.length === 0 ? (
          <p className="dashboard-empty">Aucune alerte non lue — tout est à jour.</p>
        ) : (
          <div className="supervisor-alerts">
            {alerts.map((a) => (
              <div key={a.id} className="supervisor-alerts__item">
                <div className="supervisor-alerts__main">
                  <div className="supervisor-alerts__title">Facture #{a.invoice_id}</div>
                  <div className="supervisor-alerts__message">{a.message}</div>
                </div>
                <div className="supervisor-alerts__actions">
                  <button
                    type="button"
                    className="dashboard-btn dashboard-btn--ghost"
                    onClick={() => navigate(`/supervisor/review/${a.invoice_id}`)}
                  >
                    Voir facture
                  </button>
                  <button
                    type="button"
                    className="dashboard-btn dashboard-btn--primary"
                    onClick={() => markAsRead(a.id)}
                  >
                    Marquer lu
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
