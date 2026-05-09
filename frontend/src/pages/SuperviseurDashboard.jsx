import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import api from "../api";
import InvoicesCards from "../components/InvoicesCards"; // Changement ici
import MetricsPage from "../components/MetricsPage";
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
  const ocrPrecision =
    metrics?.ocr_precision != null || metrics?.ocr_precision_pct != null
      ? Number(
          metrics.ocr_precision ?? metrics.ocr_precision_pct
        ).toFixed(1)
      : "—";

  const markAsRead = async (alertId) => {
    try {
      await api.put(`/supervisor/alerts/${alertId}/read`);
      setAlerts((prev) => prev.filter((a) => a.id !== alertId));
    } catch (_) {}
  };

  return (
    <div className="dashboard dashboard--superviseur">
      <header className="dashboard__header">
        <span className="dashboard__badge dashboard__badge--superviseur">Superviseur</span>
        <h1 className="dashboard__title">
          {greeting}, {displayName}
        </h1>
        <p className="dashboard__subtitle">
          Surveillez la qualité du pipeline OCR et la cohérence des données
          extraites, et intervenez en cas d’anomalies.
        </p>

        {!loading && (
          <div className="dashboard__stats">
            <div className="dashboard-stat">
              <div className="dashboard-stat__icon">📄</div>
              <div className="dashboard-stat__value">{nbInvoices}</div>
              <div className="dashboard-stat__label">
                Factures présentes dans le système
              </div>
            </div>
            
          </div>
        )}
      </header>

 

      <section className="dashboard__section">
        <h2 className="dashboard__section-title">Alertes de correction manuelle</h2>
        {alertsLoading ? (
          <p className="admin-grid__placeholder">Chargement des alertes…</p>
        ) : alerts.length === 0 ? (
          <p className="admin-grid__placeholder">Aucune alerte non lue.</p>
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
                    className="invoices-cards__btn invoices-cards__btn--ghost"
                    onClick={() => navigate(`/supervisor/review/${a.invoice_id}`)}
                  >
                    Voir facture
                  </button>
                  <button
                    type="button"
                    className="invoices-cards__btn"
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