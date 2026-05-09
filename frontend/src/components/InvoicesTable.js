import React, { useEffect, useMemo, useState } from "react";
import api from "../api";
import "./InvoicesTable.css";

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function InvoicesTable() {
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);

  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const page = useMemo(() => Math.floor(offset / limit) + 1, [offset, limit]);
  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / limit)), [total, limit]);

  const fetchInvoices = async ({ nextOffset = offset, nextLimit = limit, nextQ = q } = {}) => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/invoices", {
        params: { limit: nextLimit, offset: nextOffset, q: nextQ || undefined },
      });
      setRows(res.data?.data || []);
      setTotal(res.data?.total || 0);
    } catch (err) {
      setError("Erreur: " + (err.response?.data?.error || err.message));
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit, offset, q]);

  const onSearch = (e) => {
    e.preventDefault();
    setOffset(0);
    setQ(qInput.trim());
  };

  const canPrev = offset > 0 && !loading;
  const canNext = offset + limit < total && !loading;

  return (
    <section className="invoices" id="invoices">
      <div className="invoices__card">
        <div className="invoices__header">
          <div>
            <h2 className="invoices__title">Lignes de factures (Postgres)</h2>
            <p className="invoices__subtitle">
              {loading ? "Chargement…" : `${total} ligne(s) d'articles`}
            </p>
          </div>

          <form className="invoices__search" onSubmit={onSearch}>
            <input
              className="invoices__input"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="Rechercher: numéro, vendeur, client, fichier, description…"
            />
            <button className="invoices__btn" type="submit" disabled={loading}>
              Rechercher
            </button>
            <button
              className="invoices__btn invoices__btn--ghost"
              type="button"
              onClick={() => fetchInvoices()}
              disabled={loading}
              title="Rafraîchir"
            >
              Rafraîchir
            </button>
          </form>
        </div>

        <div className="invoices__controls">
          <div className="invoices__pager">
            <button
              className="invoices__btn invoices__btn--ghost"
              type="button"
              disabled={!canPrev}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Précédent
            </button>
            <span className="invoices__page">
              Page {page} / {pageCount}
            </span>
            <button
              className="invoices__btn invoices__btn--ghost"
              type="button"
              disabled={!canNext}
              onClick={() => setOffset(offset + limit)}
            >
              Suivant
            </button>
          </div>

          <div className="invoices__limit">
            <span>Afficher</span>
            <select
              className="invoices__select"
              value={limit}
              disabled={loading}
              onChange={(e) => {
                const next = Number(e.target.value);
                setOffset(0);
                setLimit(next);
              }}
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
            <span>/ page</span>
          </div>
        </div>

        {error && <div className="invoices__error">{error}</div>}

        <div className="invoices__tableWrap" role="region" aria-label="Table des factures">
          <table className="invoices__table">
            <thead>
              <tr>
                <th>Facture</th>
                <th>Numéro</th>
                <th>Date</th>
                <th>Vendeur</th>
                <th>Client</th>
                <th>Description</th>
                <th className="invoices__num">Qté</th>
                <th className="invoices__num">PU HT</th>
                <th className="invoices__num">Net</th>
                <th className="invoices__num">% TVA</th>
                <th className="invoices__num">TTC</th>
                <th>Catégorie</th>
                <th>Compte</th>
              </tr>
            </thead>
            <tbody>
              {!loading && rows.length === 0 ? (
                <tr>
                  <td colSpan={13} className="invoices__empty">
                    Aucune ligne de facture à afficher.
                  </td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.item_id}>
                    <td className="invoices__truncate" title={r.filename || ""}>
                      {r.filename || "—"}
                    </td>
                    <td className="invoices__mono">{r.invoice_number || "—"}</td>
                    <td className="invoices__mono">{r.date_of_issue || "—"}</td>
                    <td className="invoices__truncate" title={r.seller_name || ""}>
                      {r.seller_name || "—"}
                    </td>
                    <td className="invoices__truncate" title={r.client_name || ""}>
                      {r.client_name || "—"}
                    </td>
                    <td className="invoices__truncate" title={r.description || ""}>
                      {r.description || "—"}
                    </td>
                    <td className="invoices__num">{r.quantity ?? "—"}</td>
                    <td className="invoices__num">{formatMoney(r.net_price)}</td>
                    <td className="invoices__num">{formatMoney(r.net)}</td>
                    <td className="invoices__num">
                      {r.vat_percentage != null ? `${r.vat_percentage}%` : "—"}
                    </td>
                    <td className="invoices__num">{formatMoney(r.gross)}</td>
                    <td className="invoices__truncate" title={r.category || ""}>
                      {r.category || "—"}
                    </td>
                    <td className="invoices__mono">{r.account || "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

