import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom"; // Importez useNavigate
import api from "../api";
import "./InvoicesCards.css";

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function InvoicesCards() {
  const navigate = useNavigate(); // Hook pour la navigation
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(12);
  const [offset, setOffset] = useState(0);

  const [invoices, setInvoices] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const page = useMemo(() => Math.floor(offset / limit) + 1, [offset, limit]);
  const pageCount = useMemo(() => Math.max(1, Math.ceil(total / limit)), [total, limit]);

  // Fonction pour grouper les items par facture
  const groupInvoices = (rows) => {
    const grouped = {};
    rows.forEach(row => {
      if (!grouped[row.invoice_id]) {
        grouped[row.invoice_id] = {
          id: row.invoice_id,
          filename: row.filename,
          invoice_number: row.invoice_number,
          date_of_issue: row.date_of_issue,
          seller_name: row.seller_name,
          client_name: row.client_name,
          total_net: row.total_net,
          total_vat: row.total_vat,
          total_gross: row.total_gross,
          user_id: row.user_id,
          items: []
        };
      }
      grouped[row.invoice_id].items.push({
        item_id: row.item_id,
        description: row.description,
        quantity: row.quantity,
        net_price: row.net_price,
        net: row.net,
        gross: row.gross,
        vat_percentage: row.vat_percentage,
        category: row.category,
        account: row.account
      });
    });
    return Object.values(grouped);
  };

  const fetchInvoices = async ({ nextOffset = offset, nextLimit = limit, nextQ = q } = {}) => {
    setLoading(true);
    setError("");
    try {
      const res = await api.get("/invoices", {
        params: { limit: nextLimit, offset: nextOffset, q: nextQ || undefined },
      });
      const groupedInvoices = groupInvoices(res.data?.data || []);
      setInvoices(groupedInvoices);
      setTotal(res.data?.total || 0);
    } catch (err) {
      setError("Erreur: " + (err.response?.data?.error || err.message));
      setInvoices([]);
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

  const handleCardClick = (invoiceId) => {
    // Naviguer vers la page de détails avec l'ID de la facture
    navigate(`/invoice/${invoiceId}`);
  };

  return (
    <section className="invoices-cards" id="invoices">
      <div className="invoices-cards__container">
        <div className="invoices-cards__header">
          <div>
            <h2 className="invoices-cards__title">Factures</h2>
            <p className="invoices-cards__subtitle">
              {loading ? "Chargement…" : `${total} facture(s)`}
            </p>
          </div>

          <form className="invoices-cards__search" onSubmit={onSearch}>
            <input
              className="invoices-cards__input"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              placeholder="Rechercher: numéro, vendeur, client, fichier…"
            />
            <button className="invoices-cards__btn" type="submit" disabled={loading}>
              Rechercher
            </button>
            <button
              className="invoices-cards__btn invoices-cards__btn--ghost"
              type="button"
              onClick={() => fetchInvoices()}
              disabled={loading}
              title="Rafraîchir"
            >
              Rafraîchir
            </button>
          </form>
        </div>

        <div className="invoices-cards__controls">
          <div className="invoices-cards__pager">
            <button
              className="invoices-cards__btn invoices-cards__btn--ghost"
              type="button"
              disabled={!canPrev}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Précédent
            </button>
            <span className="invoices-cards__page">
              Page {page} / {pageCount}
            </span>
            <button
              className="invoices-cards__btn invoices-cards__btn--ghost"
              type="button"
              disabled={!canNext}
              onClick={() => setOffset(offset + limit)}
            >
              Suivant
            </button>
          </div>

          <div className="invoices-cards__limit">
            <span>Afficher</span>
            <select
              className="invoices-cards__select"
              value={limit}
              disabled={loading}
              onChange={(e) => {
                const next = Number(e.target.value);
                setOffset(0);
                setLimit(next);
              }}
            >
              <option value={6}>6</option>
              <option value={12}>12</option>
              <option value={24}>24</option>
              <option value={48}>48</option>
            </select>
            <span>cartes / page</span>
          </div>
        </div>

        {error && <div className="invoices-cards__error">{error}</div>}

        <div className="invoices-cards__grid">
          {!loading && invoices.length === 0 ? (
            <div className="invoices-cards__empty">
              Aucune facture à afficher.
            </div>
          ) : (
            invoices.map((invoice) => (
              <div key={invoice.id} className="invoices-cards__card-wrapper">
                <div 
                  className="invoices-cards__card"
                  onClick={() => handleCardClick(invoice.id)}
                >
                  <div className="invoices-cards__card-header">
                    <h3 className="invoices-cards__card-title">
                      {invoice.filename || "Sans nom"}
                    </h3>
                    <span className="invoices-cards__card-badge">
                      {invoice.items?.length || 0} article(s)
                    </span>
                  </div>
                  
                  <div className="invoices-cards__card-body">
                    <div className="invoices-cards__card-row">
                      <span className="invoices-cards__card-label">Numéro:</span>
                      <span className="invoices-cards__card-value">{invoice.invoice_number || "—"}</span>
                    </div>
                    <div className="invoices-cards__card-row">
                      <span className="invoices-cards__card-label">Date:</span>
                      <span className="invoices-cards__card-value">{invoice.date_of_issue || "—"}</span>
                    </div>
                    <div className="invoices-cards__card-row">
                      <span className="invoices-cards__card-label">Vendeur:</span>
                      <span className="invoices-cards__card-value invoices-cards__card-value--truncate" title={invoice.seller_name || ""}>
                        {invoice.seller_name || "—"}
                      </span>
                    </div>
                    <div className="invoices-cards__card-row">
                      <span className="invoices-cards__card-label">Client:</span>
                      <span className="invoices-cards__card-value invoices-cards__card-value--truncate" title={invoice.client_name || ""}>
                        {invoice.client_name || "—"}
                      </span>
                    </div>
                  </div>
                  
                  <div className="invoices-cards__card-footer">
                    <div className="invoices-cards__card-total">
                      <span>Total TTC:</span>
                      <span className="invoices-cards__card-amount">{formatMoney(invoice.total_gross)}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </section>
  );
}