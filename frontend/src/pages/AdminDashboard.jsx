import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { useAuth } from "../contexts/AuthContext";
import "./Dashboards.css";

const GRAFANA_URL =
  process.env.REACT_APP_GRAFANA_URL || "http://localhost:3030";

const SHORTCUTS = [
  {
    to: "/analytics/bi",
    title: "Rapport Power BI",
    desc: "Analyses métier : clients, catégories, tendances",
    icon: "📊",
    variant: "primary",
  },
  {
    href: `${GRAFANA_URL}/d/factupro-tech`,
    title: "Grafana (monitoring)",
    desc: "Perf pipeline, alertes, uploads — temps réel",
    icon: "📈",
    variant: "default",
    external: true,
  },
  {
    to: "/admin/users",
    title: "Utilisateurs",
    desc: "Comptes, rôles et accès",
    icon: "👥",
    variant: "default",
  },
  {
    to: "/metrics",
    title: "Détail OCR par facture",
    desc: "Champs extraits vs corrigés (facture par facture)",
    icon: "⚙️",
    variant: "default",
  },
];

export default function AdminDashboard() {
  const { user, getAuthHeader } = useAuth();

  const [stats, setStats] = useState({ users: 0, precision: 0 });
  const [totals, setTotals] = useState({
    invoices: 0,
    sellers: 0,
    clients: 0,
    categories: 0,
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
          precision:
            metricsRes.data.ocr_precision ??
            metricsRes.data.ocr_precision_pct ??
            0,
        });

        setTotals(
          analyticsRes.data.totals || {
            invoices: 0,
            sellers: 0,
            clients: 0,
            categories: 0,
          }
        );
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

  const metrics = [
    { key: "users", label: "Utilisateurs", value: stats.users, icon: "👥", tone: "blue" },
    {
      key: "invoices",
      label: "Factures",
      value: loading ? "…" : totals.invoices,
      icon: "📄",
      tone: "teal",
    },
    {
      key: "precision",
      label: "Précision OCR",
      value: precisionDisplay,
      icon: "🎯",
      tone: "violet",
    },
    {
      key: "categories",
      label: "Catégories",
      value: loading ? "…" : totals.categories,
      icon: "🏷️",
      tone: "amber",
    },
    {
      key: "sellers",
      label: "Vendeurs",
      value: loading ? "…" : totals.sellers,
      icon: "🏢",
      tone: "blue",
    },
    {
      key: "clients",
      label: "Clients",
      value: loading ? "…" : totals.clients,
      icon: "🤝",
      tone: "teal",
    },
  ];

  return (
    <div className="dashboard dashboard--admin dashboard--modern">
      <header className="dashboard-hero">
        <div className="dashboard-hero__content">
          <span className="dashboard__badge dashboard__badge--admin">
            Administrateur
          </span>
          <h1 className="dashboard-hero__title">
            {greeting}, <span>{displayName}</span>
          </h1>
          <p className="dashboard-hero__subtitle">
            Pilotez la plateforme en un coup d’œil. Les analyses visuelles détaillées
            sont dans Power BI.
          </p>
        </div>
        <div className="dashboard-hero__glow" aria-hidden />
      </header>

      <section className="dashboard-block">
        <h2 className="dashboard-block__title">Indicateurs clés</h2>
        <div className="metric-grid">
          {metrics.map((m) => (
            <article
              key={m.key}
              className={`metric-card metric-card--${m.tone}`}
            >
              <div className="metric-card__icon" aria-hidden>
                {m.icon}
              </div>
              <div className="metric-card__body">
                <p className="metric-card__value">{m.value}</p>
                <p className="metric-card__label">{m.label}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="dashboard-block">
        <h2 className="dashboard-block__title">Accès rapide</h2>
        <div className="shortcut-grid">
          {SHORTCUTS.map((s) => {
            const className = `shortcut-card shortcut-card--${s.variant}`;
            const inner = (
              <>
                <span className="shortcut-card__icon" aria-hidden>
                  {s.icon}
                </span>
                <span className="shortcut-card__text">
                  <span className="shortcut-card__title">{s.title}</span>
                  <span className="shortcut-card__desc">{s.desc}</span>
                </span>
                <span className="shortcut-card__arrow" aria-hidden>
                  {s.external ? "↗" : "→"}
                </span>
              </>
            );
            if (s.external && s.href) {
              return (
                <a
                  key={s.href}
                  href={s.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={className}
                >
                  {inner}
                </a>
              );
            }
            return (
              <Link key={s.to} to={s.to} className={className}>
                {inner}
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}
