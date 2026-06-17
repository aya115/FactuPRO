import { useEffect, useMemo, useState } from "react";
import api from "../api";
import { useAuth } from "../contexts/AuthContext";
import { buildPowerBiEmbedUrl, getPowerBiViewUrl } from "../config/powerBi";
import "./PowerBIDashboard.css";

function PowerBiFrame({ title, embedUrl, supervisorView = false }) {
  const wrapClass = supervisorView
    ? "powerbi-page__frame-wrap powerbi-page__frame-wrap--supervisor"
    : "powerbi-page__frame-wrap";

  return (
    <div className={wrapClass}>
      {supervisorView && (
        <div
          className="powerbi-page__footer-shield"
          title="Barre Power BI masquée"
          aria-hidden
        />
      )}
      <iframe
        key={embedUrl}
        title={title}
        className="powerbi-page__frame"
        src={embedUrl}
        allowFullScreen
      />
    </div>
  );
}

function AdminPowerBIReport() {
  const { getAuthHeader } = useAuth();
  const [embedUrl, setEmbedUrl] = useState("");

  useEffect(() => {
    api
      .get("/admin/powerbi-pages", { headers: getAuthHeader() })
      .then((res) => {
        const url = res.data?.supervisor?.admin_embed_url;
        if (url) setEmbedUrl(url);
      })
      .catch(() => {
        setEmbedUrl(buildPowerBiEmbedUrl({ hideNavigation: false }));
      });
  }, [getAuthHeader]);

  const src = embedUrl || buildPowerBiEmbedUrl({ hideNavigation: false });

  return (
    <>
      <p className="powerbi-page__hint">
        Vue complète du rapport (pages 1 à 5).
      </p>
      <PowerBiFrame title="Rapport Power BI FactuPRO — admin" embedUrl={src} />
    </>
  );
}

function SupervisorPowerBIReport() {
  const { getAuthHeader } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [payload, setPayload] = useState(null);
  const [activeKey, setActiveKey] = useState("ocr");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const res = await api.get("/api/powerbi/supervisor-embed", {
          headers: getAuthHeader(),
        });
        if (!cancelled) {
          setPayload(res.data);
          setActiveKey(res.data?.pages?.[0]?.key || "ocr");
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err.response?.data?.error ||
              "Impossible de charger la configuration Power BI."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [getAuthHeader]);

  const activePage = payload?.pages?.find((p) => p.key === activeKey) || payload?.pages?.[0];
  const embedUrl = activePage?.embed_url || "";
  const externalUrl = activePage?.view_url || "";

  if (loading) {
    return <p className="powerbi-page__hint">Chargement du rapport…</p>;
  }

  if (error) {
    return <p className="powerbi-page__hint powerbi-page__hint--warn">{error}</p>;
  }

  return (
    <>
      <div className="powerbi-page__alert">
        <strong>Vue superviseur</strong> — onglets <strong>OCR</strong> et{" "}
        <strong>Alertes</strong> uniquement. La navigation des pages Power BI est
        masquée.
      </div>

      {!payload?.pages_configured && (
        <p className="powerbi-page__hint powerbi-page__hint--warn">
          Les pages OCR et Alertes ne sont pas encore configurées. Les identifiants
          Power BI (pages 3 et 5) doivent être définis dans le fichier de configuration
          serveur (<code>powerbi_pages.json</code>).
        </p>
      )}

      <div className="powerbi-page__tabs" role="tablist" aria-label="Pages du rapport">
        {(payload?.pages || []).map((page) => (
          <button
            key={page.key}
            type="button"
            role="tab"
            aria-selected={activeKey === page.key}
            className={`powerbi-page__tab ${
              activeKey === page.key ? "powerbi-page__tab--active" : ""
            }`}
            onClick={() => setActiveKey(page.key)}
          >
            {page.label}
          </button>
        ))}
        {externalUrl ? (
          <a
            className="powerbi-page__tab-external"
            href={externalUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            Ouvrir dans Power BI
          </a>
        ) : null}
      </div>

      {embedUrl ? (
        <PowerBiFrame
          key={activeKey}
          title={`Rapport Power BI — ${activePage?.label || ""}`}
          embedUrl={embedUrl}
          supervisorView
        />
      ) : null}
    </>
  );
}

export default function PowerBIDashboard() {
  const { user } = useAuth();
  const role = (user?.role || "").toLowerCase();
  const isSupervisor = role === "superviseur";
  const viewUrl = useMemo(() => getPowerBiViewUrl(), []);

  return (
    <div className="powerbi-page">
      <header className="powerbi-page__header">
        <div>
          <span className="powerbi-page__badge">Power BI</span>
          <h1 className="powerbi-page__title">
            {isSupervisor ? "Contrôle qualité" : "Analytique FactuPRO"}
          </h1>
          <p className="powerbi-page__subtitle">
            {isSupervisor
              ? "Indicateurs OCR, corrections, alertes et comptes PCG."
              : "Rapport complet publié sur Power BI Service (PostgreSQL)."}
          </p>
        </div>
        {!isSupervisor && (
          <a
            className="powerbi-page__external"
            href={viewUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            Ouvrir dans Power BI
          </a>
        )}
      </header>

      {isSupervisor ? <SupervisorPowerBIReport /> : <AdminPowerBIReport />}
    </div>
  );
}
