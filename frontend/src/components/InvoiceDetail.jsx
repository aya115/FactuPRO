import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "../api";
import "./InvoiceDetail.css";

function formatMoney(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function InvoiceDetail() {
  const { id } = useParams(); // Récupère l'ID depuis l'URL
  const navigate = useNavigate();
  const [invoice, setInvoice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchInvoiceDetails = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/invoices/${id}/details`);
        setInvoice(res.data);
      } catch (err) {
        setError("Erreur lors du chargement de la facture");
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchInvoiceDetails();
  }, [id]);

  if (loading) {
    return (
      <div className="invoice-detail">
        <div className="invoice-detail__loading">
          Chargement des détails...
        </div>
      </div>
    );
  }

  if (error || !invoice) {
    return (
      <div className="invoice-detail">
        <div className="invoice-detail__error">
          {error || "Facture non trouvée"}
          <button onClick={() => navigate("/invoices")} className="invoice-detail__back-btn">
            Retour aux factures
          </button>
        </div>
      </div>

    );
  }

  return (
    <div className="invoice-detail">
      <div className="invoice-detail__container">
        <button onClick={() => navigate("/invoices")} className="invoice-detail__back-btn">
          ← Retour aux factures
        </button>

        <h1 className="invoice-detail__title">
          {invoice.filename || "Détails de la facture"}
        </h1>

        <div className="invoice-detail__summary">
          <div className="invoice-detail__row">
            <span className="invoice-detail__label">N° facture:</span>
            <span className="invoice-detail__value">{invoice.invoice_number || "—"}</span>
          </div>
          <div className="invoice-detail__row">
            <span className="invoice-detail__label">Date:</span>
            <span className="invoice-detail__value">{invoice.date_of_issue || "—"}</span>
          </div>
          <div className="invoice-detail__row">
            <span className="invoice-detail__label">Vendeur:</span>
            <span className="invoice-detail__value">{invoice.seller_name || "—"}</span>
          </div>
          <div className="invoice-detail__row">
            <span className="invoice-detail__label">Client:</span>
            <span className="invoice-detail__value">{invoice.client_name || "—"}</span>
          </div>
        </div>

        <div className="invoice-detail__table-wrapper">
          <table className="invoice-detail__table">
            <thead>
              <tr>
                <th>Description</th>
                <th className="invoice-detail__num">Qté</th>
                <th className="invoice-detail__num">PU HT</th>
                <th className="invoice-detail__num">Net</th>
                <th className="invoice-detail__num">% TVA</th>
                <th className="invoice-detail__num">TTC</th>
                <th>Catégorie</th>
                <th>Compte</th>
              </tr>
            </thead>
            <tbody>
              {invoice.items && invoice.items.length > 0 ? (
                invoice.items.map((item) => (
                  <tr key={item.item_id}>
                    <td className="invoice-detail__truncate" title={item.description || ""}>
                      {item.description || "—"}
                    </td>
                    <td className="invoice-detail__num">{item.quantity ?? "—"}</td>
                    <td className="invoice-detail__num">{formatMoney(item.net_price)}</td>
                    <td className="invoice-detail__num">{formatMoney(item.net)}</td>
                    <td className="invoice-detail__num">
                      {item.vat_percentage != null ? `${item.vat_percentage}%` : "—"}
                    </td>
                    <td className="invoice-detail__num">{formatMoney(item.gross)}</td>
                    <td className="invoice-detail__truncate" title={item.category || ""}>
                      {item.category || "—"}
                    </td>
                    <td className="invoice-detail__mono">{item.account || "—"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="invoice-detail__empty">
                    Aucun article dans cette facture
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="invoice-detail__totals">
          <div className="invoice-detail__total-row">
            <span>Total HT:</span>
            <span className="invoice-detail__total-value">{formatMoney(invoice.total_net)}</span>
          </div>
          <div className="invoice-detail__total-row">
            <span>TVA:</span>
            <span className="invoice-detail__total-value">{formatMoney(invoice.total_vat)}</span>
          </div>
          <div className="invoice-detail__total-row invoice-detail__total-row--grand">
            <span>Total TTC:</span>
            <span className="invoice-detail__total-value">{formatMoney(invoice.total_gross)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}