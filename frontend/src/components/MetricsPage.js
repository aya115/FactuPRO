import React, { useEffect, useMemo, useState } from "react";
import api from "../api";
import "./MetricsPage.css";

export default function MetricsPage() {
  const [ocrDetails, setOcrDetails] = useState([]);
  const [invoiceId, setInvoiceId] = useState("");
  const [invoiceQuery, setInvoiceQuery] = useState("");
  const [invoiceQueryInput, setInvoiceQueryInput] = useState("");
  const [invoiceRows, setInvoiceRows] = useState([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  // ================= LOAD METRICS =================
  useEffect(() => {
    api
      .get("/metrics")
      .then((res) => {
        console.log("METRICS RESPONSE:", res.data);
      })
      .catch((err) =>
        setError(err.response?.data?.error || err.message)
      )
      .finally(() => setLoading(false));
  }, []);

  // ================= LOAD INVOICES (for dropdown) =================
  const groupInvoices = (rows) => {
    const grouped = {};
    (rows || []).forEach((row) => {
      const id = row.invoice_id;
      if (!id) return;
      if (!grouped[id]) {
        grouped[id] = {
          invoice_id: id,
          invoice_number: row.invoice_number,
          date_of_issue: row.date_of_issue,
          seller_name: row.seller_name,
          client_name: row.client_name,
          filename: row.filename,
        };
      }
    });
    return Object.values(grouped);
  };

  const fetchInvoices = async ({ q = invoiceQuery } = {}) => {
    setInvoicesLoading(true);
    try {
      const res = await api.get("/invoices", {
        params: { limit: 200, offset: 0, q: q || undefined },
      });
      setInvoiceRows(groupInvoices(res.data?.data || []));
    } catch (err) {
      // Ne bloque pas la page métriques si la liste facture échoue
      console.error("Invoices list error", err);
      setInvoiceRows([]);
    } finally {
      setInvoicesLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceQuery]);

  const invoiceOptions = useMemo(() => invoiceRows || [], [invoiceRows]);

  const formatInvoiceLabel = (inv) => {
    const num = inv.invoice_number ? `N° ${inv.invoice_number}` : "Sans numéro";
    const date = inv.date_of_issue ? ` • ${inv.date_of_issue}` : "";
    const seller = inv.seller_name ? ` • ${inv.seller_name}` : "";
    const client = inv.client_name ? ` → ${inv.client_name}` : "";
    return `${num}${date}${seller}${client}`;
  };

  // ================= LOAD OCR DETAILS =================
  const loadOCRDetails = () => {
    if (!invoiceId) return;

    setDetailLoading(true);

    api
      .get(`/metrics/ocr-details/${invoiceId}`)
      .then((res) => {
        console.log("OCR DETAILS:", res.data);
        setOcrDetails(res.data.details || []);
      })
      .catch((err) => console.error("OCR detail error", err))
      .finally(() => setDetailLoading(false));
  };

  // ================= FORMAT HELPERS =================
  const fmt = (v) => (v == null ? "—" : v);

  const pct = (v) =>
    v != null && typeof v === "number"
      ? `${v.toFixed(2)} %`
      : "—";

  const ocrPrecision = useMemo(() => {
    const details = Array.isArray(ocrDetails) ? ocrDetails : [];
    if (details.length === 0) return null;
    const correct = details.filter((d) => Boolean(d?.correct)).length;
    const total = details.length;
    const ratio = total > 0 ? correct / total : 0;
    return { correct, total, pct: ratio * 100 };
  }, [ocrDetails]);

  // ================= UI =================
  if (loading)
    return (
      <div className="metrics-page">
        <p>Chargement…</p>
      </div>
    );

  if (error)
    return (
      <div className="metrics-page metrics-page--error">
        {error}
      </div>
    );

  return (
    <section className="metrics-page">
      <div className="metrics-card">
        <h2 className="metrics-title">Métriques du pipeline</h2>

      
        {/* ================= OCR DETAIL ANALYSIS ================= */}

        <h3 className="metrics-subtitle">
          Analyse détaillée précision OCR
        </h3>

        <div style={{ marginBottom: "15px" }}>
          <div className="metrics-invoicePicker">
            <form
              className="metrics-invoiceSearch"
              onSubmit={(e) => {
                e.preventDefault();
                setInvoiceQuery(invoiceQueryInput.trim());
              }}
            >
              <input
                type="text"
                placeholder="Rechercher une facture (numéro, vendeur, client, fichier...)"
                value={invoiceQueryInput}
                onChange={(e) => setInvoiceQueryInput(e.target.value)}
                className="metrics-input"
                disabled={invoicesLoading}
              />
              <button
                type="submit"
                className="metrics-button metrics-button--ghost"
                disabled={invoicesLoading}
                title="Rechercher"
              >
                Rechercher
              </button>
              <button
                type="button"
                className="metrics-button metrics-button--ghost"
                onClick={() => {
                  setInvoiceQueryInput("");
                  setInvoiceQuery("");
                }}
                disabled={invoicesLoading}
                title="Réinitialiser"
              >
                Réinitialiser
              </button>
            </form>

            <select
              className="metrics-select"
              value={invoiceId}
              onChange={(e) => {
                setInvoiceId(e.target.value);
                setOcrDetails([]);
              }}
              disabled={invoicesLoading || invoiceOptions.length === 0}
            >
              <option value="">
                {invoicesLoading
                  ? "Chargement des factures…"
                  : invoiceOptions.length === 0
                  ? "Aucune facture trouvée"
                  : "Sélectionner une facture…"}
              </option>
              {invoiceOptions.map((inv) => (
                <option key={inv.invoice_id} value={String(inv.invoice_id)}>
                  {formatInvoiceLabel(inv)}
                </option>
              ))}
            </select>

            <div className="metrics-muted">
              {invoiceId ? (
                <span>Facture sélectionnée : ID {invoiceId}</span>
              ) : (
                <span>Sélectionne une facture pour afficher le détail OCR.</span>
              )}
            </div>
          </div>

          <button
            onClick={loadOCRDetails}
            className="metrics-button"
            disabled={!invoiceId || detailLoading}
          >
            Voir détail précision OCR
          </button>
        </div>

        {detailLoading && <p>Chargement détails OCR...</p>}

        {!detailLoading && ocrDetails.length > 0 && (
          <>
            {ocrPrecision && (
              <div className="metrics-info">
                <strong>Précision OCR (facture {invoiceId}) :</strong>{" "}
                {pct(ocrPrecision.pct)}{" "}
                <span className="metrics-muted">
                  ({ocrPrecision.correct}/{ocrPrecision.total} champs corrects)
                </span>
              </div>
            )}
            <table className="metrics-table">
              <thead>
                <tr>
                  <th>Champ</th>
                  <th>OCR extrait</th>
                  <th>Correct</th>
                  <th>Statut</th>
                </tr>
              </thead>

              <tbody>
                {ocrDetails.map((d, i) => (
                  <tr key={i}>
                    <td>{d.field}</td>
                    <td>{fmt(d.extracted)}</td>
                    <td>{fmt(d.corrected)}</td>
                    <td>{d.correct ? "✅" : "❌"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {ocrDetails.length === 0 && !detailLoading && (
          <p>Aucun détail disponible</p>
        )}
      </div>
    </section>
  );
}