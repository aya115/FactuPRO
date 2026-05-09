import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import api from "../api";
import UploadInvoice from "../components/UploadInvoice";
import InvoicesCards from "../components/InvoicesCards"; // Changement ici
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
    <div className="dashboard dashboard--comptable">
      <header className="dashboard__header">
        <span className="dashboard__badge dashboard__badge--comptable">Comptable</span>
        <h1 className="dashboard__title">
          {greeting}, {displayName}
        </h1>
        <p className="dashboard__subtitle">
          Gérez vos factures au quotidien, déposez de nouveaux documents et
          suivez l’historique traité par le système.
        </p>

        {!loading && invoiceCount != null && (
          <div className="dashboard__stats">
            <div className="dashboard-stat">
              <div className="dashboard-stat__icon">📄</div>
              <div className="dashboard-stat__value">{invoiceCount}</div>
              <div className="dashboard-stat__label">
                Lignes de factures enregistrées
              </div>
            </div>
            <div className="dashboard-stat">
              <div className="dashboard-stat__icon">⚡</div>
              <div className="dashboard-stat__value">Temps réel</div>
              <div className="dashboard-stat__label">
                Mise à jour après chaque validation
              </div>
            </div>
          </div>
        )}
      </header>

      <section className="dashboard__section">
        <h2 className="dashboard__section-title">Importer une facture</h2>
        <UploadInvoice />
      </section>

      
    </div>
  );
}