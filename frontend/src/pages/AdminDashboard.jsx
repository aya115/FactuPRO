import { useEffect, useMemo, useState } from "react";
import api from "../api";
import { useAuth } from "../contexts/AuthContext";
import "./Dashboards.css";

export default function AdminDashboard() {
  const { user, getAuthHeader } = useAuth();

  const [stats, setStats] = useState({
    users: 0,
    invoices: 0,
    precision: 0,
  });

  const [analytics, setAnalytics] = useState({
    totals: { invoices: 0, sellers: 0, clients: 0, categories: 0 },
    invoices_per_category: [],
    invoices_per_client: [],
  });

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [metricsRes, usersRes, analyticsRes] = await Promise.all([
          api.get("/metrics", { headers: getAuthHeader() }),
          api.get("/admin/users", { headers: getAuthHeader() }),
          api.get("/admin/analytics", { headers: getAuthHeader() }),
        ]);

        setStats({
          users: usersRes.data.users?.length || 0,
          invoices: metricsRes.data.nb_invoices || metricsRes.data.nb_invoices_processed || 0,
          precision:
            metricsRes.data.ocr_precision ??
            metricsRes.data.ocr_precision_pct ??
            0,
        });

        setAnalytics({
          totals: analyticsRes.data.totals || {
            invoices: 0,
            sellers: 0,
            clients: 0,
            categories: 0,
          },
          invoices_per_category: analyticsRes.data.invoices_per_category || [],
          invoices_per_client: analyticsRes.data.invoices_per_client || [],
        });
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    loadDashboard();
  }, [getAuthHeader]);

  const displayName = user?.full_name || user?.email?.split("@")[0] || "Admin";
  const greeting = new Date().getHours() < 12 ? "Bonjour" : "Bonsoir";
  const precisionDisplay =
    typeof stats.precision === "number"
      ? `${stats.precision.toFixed(1)}%`
      : stats.precision ?? "—";

  const categoryPieConfig = useMemo(() => {
    const data = analytics.invoices_per_category || [];
    if (!data.length) return { segments: [], total: 0 };

    const total = data.reduce(
      (sum, item) => sum + (item.invoice_count || 0),
      0
    );
    if (!total) return { segments: [], total: 0 };

    const palette = [
      "#38bdf8",
      "#22c55e",
      "#f97316",
      "#eab308",
      "#a855f7",
      "#f43f5e",
      "#0ea5e9",
      "#10b981",
    ];

    let currentAngle = 0;
    const segments = data.map((item, index) => {
      const value = item.invoice_count || 0;
      const sliceAngle = (value / total) * 360;
      const start = currentAngle;
      const end = currentAngle + sliceAngle;
      currentAngle = end;

      return {
        color: palette[index % palette.length],
        start,
        end,
        label: item.category || "Non définie",
        value,
      };
    });

    return { segments, total };
  }, [analytics.invoices_per_category]);

  const pieBackground = useMemo(() => {
    if (!categoryPieConfig.segments.length) {
      return "radial-gradient(circle at 30% 30%, #1f2937 0, #020617 60%)";
    }

    const parts = categoryPieConfig.segments.map((seg) => {
      return `${seg.color} ${seg.start.toFixed(2)}deg ${seg.end.toFixed(
        2
      )}deg`;
    });
    return `conic-gradient(${parts.join(", ")})`;
  }, [categoryPieConfig]);

  const categoryBars = useMemo(() => {
    const data = analytics.invoices_per_category || [];
    if (!data.length) return [];
    const max = Math.max(...data.map((d) => d.invoice_count || 0)) || 1;
    return data.map((d) => {
      const value = d.invoice_count || 0;
      const pct = (value / max) * 100;
      return {
        label: d.category || "Non définie",
        value,
        widthPct: Math.max(pct, 10),
      };
    });
  }, [analytics.invoices_per_category]);

  const clientBars = useMemo(() => {
    const data = analytics.invoices_per_client || [];
    if (!data.length) return [];

    const sorted = [...data].sort(
      (a, b) => (b.invoice_count || 0) - (a.invoice_count || 0)
    );
    const top = sorted.slice(0, 6);
    const max = Math.max(...top.map((d) => d.invoice_count || 0)) || 1;

    return top.map((d) => {
      const value = d.invoice_count || 0;
      const pct = (value / max) * 100;
      return {
        label: d.client_name || "Client inconnu",
        value,
        widthPct: Math.max(pct, 10),
      };
    });
  }, [analytics.invoices_per_client]);

  return (
    <div className="dashboard dashboard--admin">
      <header className="dashboard__header">
        <span className="dashboard__badge dashboard__badge--admin">
          Administrateur
        </span>
        <h1 className="dashboard__title">
          {greeting}, {displayName}
        </h1>
        <p className="dashboard__subtitle">
          Vue d’ensemble du système, gestion des utilisateurs et des paramètres.
        </p>

       
      </header>

      <section className="dashboard__section">
        <h2 className="dashboard__section-title">
          Synthèse base de données factures
        </h2>

        <div className="admin-grid">
          <div className="admin-grid__card">
            <h3 className="admin-grid__title">Totaux clés</h3>
            <div className="admin-grid__kpis">
              <div className="admin-kpi">
                <span className="admin-kpi__label">Factures</span>
                <span className="admin-kpi__value">
                  {analytics.totals.invoices}
                </span>
              </div>
              <div className="admin-kpi">
                <span className="admin-kpi__label">Catégories</span>
                <span className="admin-kpi__value">
                  {analytics.totals.categories}
                </span>
              </div>
              <div className="admin-kpi">
                <span className="admin-kpi__label">Vendeurs</span>
                <span className="admin-kpi__value">
                  {analytics.totals.sellers}
                </span>
              </div>
              <div className="admin-kpi">
                <span className="admin-kpi__label">Clients</span>
                <span className="admin-kpi__value">
                  {analytics.totals.clients}
                </span>
              </div>
            </div>
          </div>

          <div className="admin-grid__card">
            <h3 className="admin-grid__title">
              Répartition des factures par catégorie
            </h3>
            {loading ? (
              <p className="admin-grid__placeholder">Chargement…</p>
            ) : !categoryPieConfig.segments.length ? (
              <p className="admin-grid__placeholder">
                Aucune donnée de catégorie disponible.
              </p>
            ) : (
              <div className="admin-chart admin-chart--pie">
                <div
                  className="admin-chart__pie"
                  style={{ backgroundImage: pieBackground }}
                  aria-label="Répartition des factures par catégorie"
                />
                <ul className="admin-chart__legend">
                  {categoryPieConfig.segments.map((seg, index) => (
                    <li key={seg.label + index}>
                      <span
                        className="admin-chart__legend-color"
                        style={{ backgroundColor: seg.color }}
                      />
                      <span className="admin-chart__legend-label">
                        {seg.label}
                      </span>
                      <span className="admin-chart__legend-value">
                        {seg.value}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="admin-grid__card">
            <h3 className="admin-grid__title">
              Top clients par nombre de factures
            </h3>
            {loading ? (
              <p className="admin-grid__placeholder">Chargement…</p>
            ) : !clientBars.length ? (
              <p className="admin-grid__placeholder">
                Aucune donnée client disponible.
              </p>
            ) : (
              <div className="admin-chart admin-chart--bars">
                <div className="admin-chart__bars">
                  {clientBars.map((bar) => (
                    <div
                      key={bar.label}
                      className="admin-chart__bar-wrapper"
                      title={`${bar.label} — ${bar.value} facture(s)`}
                    >
                      <span className="admin-chart__bar-label">
                        {bar.label}
                      </span>
                      <div className="admin-chart__bar-track">
                        <div
                          className="admin-chart__bar admin-chart__bar--green"
                          style={{ width: `${bar.widthPct}%` }}
                        />
                      </div>
                      <span className="admin-chart__bar-value">
                        {bar.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="admin-grid__card admin-grid__card--wide">
            <h3 className="admin-grid__title">
              Top catégories par nombre de factures
            </h3>
            {loading ? (
              <p className="admin-grid__placeholder">Chargement…</p>
            ) : !categoryBars.length ? (
              <p className="admin-grid__placeholder">
                Aucune donnée de catégorie disponible.
              </p>
            ) : (
              <div className="admin-chart admin-chart--bars">
                <div className="admin-chart__bars">
                  {categoryBars.map((bar) => (
                    <div
                      key={bar.label}
                      className="admin-chart__bar-wrapper"
                      title={`${bar.label} — ${bar.value} facture(s)`}
                    >
                      <span className="admin-chart__bar-label">
                        {bar.label}
                      </span>
                      <div className="admin-chart__bar-track">
                        <div
                          className="admin-chart__bar"
                          style={{ width: `${bar.widthPct}%` }}
                        />
                      </div>
                      <span className="admin-chart__bar-value">
                        {bar.value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
