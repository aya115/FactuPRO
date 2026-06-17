import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { useAuth } from "../contexts/AuthContext";
import "./PowerBIDashboard.css";
import "./Dashboards.css";

const EMPTY = {
  page_3_id: "",
  page_5_id: "",
  supervisor_report_id: "",
  page_3_name: "Page 3",
  page_5_name: "Page 5",
};

export default function PowerBiAdminSetup() {
  const { getAuthHeader } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/admin/powerbi-pages", { headers: getAuthHeader() })
      .then((res) => {
        const c = res.data?.config || {};
        setForm({
          page_3_id: c.page_3_id || "",
          page_5_id: c.page_5_id || "",
          supervisor_report_id: c.supervisor_report_id || "",
          page_3_name: c.page_3_name || "Page 3",
          page_5_name: c.page_5_name || "Page 5",
        });
      })
      .catch((err) => {
        setError(err.response?.data?.error || "Chargement impossible");
      })
      .finally(() => setLoading(false));
  }, [getAuthHeader]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const res = await api.put("/admin/powerbi-pages", form, {
        headers: getAuthHeader(),
      });
      setMessage(res.data?.message || "Enregistré.");
      const c = res.data?.config || {};
      setForm({
        page_3_id: c.page_3_id || "",
        page_5_id: c.page_5_id || "",
        supervisor_report_id: c.supervisor_report_id || "",
        page_3_name: c.page_3_name || "Page 3",
        page_5_name: c.page_5_name || "Page 5",
      });
    } catch (err) {
      setError(err.response?.data?.error || "Erreur lors de l’enregistrement");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="dashboard dashboard--admin powerbi-setup">
      <header className="dashboard__header">
        <span className="dashboard__badge dashboard__badge--admin">Admin</span>
        <h1 className="dashboard__title">Configuration Power BI — superviseur</h1>
        <p className="dashboard__subtitle">
          Définissez les pages 3 et 5 pour que le superviseur ne voie que l’OCR et
          les alertes. Aucun rebuild Docker nécessaire après enregistrement.
        </p>
      </header>

      <section className="dashboard__section">
        {loading ? (
          <p className="powerbi-page__hint">Chargement…</p>
        ) : (
          <form className="powerbi-setup__form" onSubmit={handleSubmit}>
            <ol className="powerbi-setup__steps">
              <li>
                Sur{" "}
                <a
                  href="https://app.powerbi.com"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  app.powerbi.com
                </a>
                , ouvrez le rapport <strong>hedha howa</strong>.
              </li>
              <li>
                Cliquez sur <strong>Page 3</strong> : copiez le code dans l’URL après{" "}
                <code>/reports/…/</code>
              </li>
              <li>
                Même chose pour <strong>Page 5</strong>.
              </li>
            </ol>

            <label className="powerbi-setup__label">
              ID page 3 (OCR)
              <input
                className="powerbi-setup__input"
                name="page_3_id"
                value={form.page_3_id}
                onChange={handleChange}
                placeholder="ex. a1b2c3d4e5f6..."
              />
            </label>

            <label className="powerbi-setup__label">
              ID page 5 (alertes)
              <input
                className="powerbi-setup__input"
                name="page_5_id"
                value={form.page_5_id}
                onChange={handleChange}
                placeholder="ex. f6e5d4c3b2a1..."
              />
            </label>

            <label className="powerbi-setup__label">
              Nom page 3 (si pas d’ID)
              <input
                className="powerbi-setup__input"
                name="page_3_name"
                value={form.page_3_name}
                onChange={handleChange}
              />
            </label>

            <label className="powerbi-setup__label">
              Nom page 5 (si pas d’ID)
              <input
                className="powerbi-setup__input"
                name="page_5_name"
                value={form.page_5_name}
                onChange={handleChange}
              />
            </label>

            <label className="powerbi-setup__label">
              Rapport superviseur dédié (optionnel — GUID complet)
              <input
                className="powerbi-setup__input"
                name="supervisor_report_id"
                value={form.supervisor_report_id}
                onChange={handleChange}
                placeholder="2e .pbix avec pages 3 et 5 seulement"
              />
            </label>

            {message && <p className="powerbi-setup__ok">{message}</p>}
            {error && <p className="powerbi-setup__err">{error}</p>}

            <div className="powerbi-setup__actions">
              <button type="submit" className="powerbi-setup__btn" disabled={saving}>
                {saving ? "Enregistrement…" : "Enregistrer"}
              </button>
              <Link to="/analytics/bi" className="powerbi-setup__link">
                Voir le rapport BI
              </Link>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
