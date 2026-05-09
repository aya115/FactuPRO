import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api from "../api";
import "../components/InvoiceDetail.css";

function fmt(v) {
  if (v === null || v === undefined || v === "") return "—";
  return String(v);
}

export default function InvoiceCorrectionReview() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [invoice, setInvoice] = useState(null);
  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const [invoiceRes, detailsRes] = await Promise.all([
          api.get(`/invoices/${id}/details`),
          api.get(`/metrics/ocr-details/${id}`),
        ]);
        if (!mounted) return;
        setInvoice(invoiceRes.data || null);
        setChanges(detailsRes.data?.details || []);
      } catch (e) {
        if (!mounted) return;
        setError(e?.response?.data?.error || "Erreur lors du chargement de la revue.");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    load();
    return () => {
      mounted = false;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="invoice-detail">
        <div className="invoice-detail__loading">Chargement de la revue…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="invoice-detail">
        <div className="invoice-detail__error">
          {error}
          <button onClick={() => navigate("/dashboard")} className="invoice-detail__back-btn">
            Retour au tableau de bord
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="invoice-detail">
      <div className="invoice-detail__container">
        <button onClick={() => navigate("/dashboard")} className="invoice-detail__back-btn">
          ← Retour au tableau de bord
        </button>

        <h1 className="invoice-detail__title">Revue correction facture #{id}</h1>

        <div className="invoice-detail__summary">
          <div className="invoice-detail__row">
            <span className="invoice-detail__label">Fichier</span>
            <span className="invoice-detail__value">{invoice?.filename || "—"}</span>
          </div>
          <div className="invoice-detail__row">
            <span className="invoice-detail__label">N° facture</span>
            <span className="invoice-detail__value">{invoice?.invoice_number || "—"}</span>
          </div>
          <div className="invoice-detail__row">
            <span className="invoice-detail__label">Vendeur</span>
            <span className="invoice-detail__value">{invoice?.seller_name || "—"}</span>
          </div>
          <div className="invoice-detail__row">
            <span className="invoice-detail__label">Date</span>
            <span className="invoice-detail__value">{invoice?.date_of_issue || "—"}</span>
          </div>
        </div>

        <div className="invoice-detail__table-wrapper">
          <table className="invoice-detail__table">
            <thead>
              <tr>
                <th>Champ</th>
                <th>Valeur extraite</th>
                <th>Valeur corrigée</th>
                <th>Statut</th>
              </tr>
            </thead>
            <tbody>
              {changes.length > 0 ? (
                changes.map((c, idx) => (
                  <tr
                    key={`${c.field}-${idx}`}
                    className={c.correct ? "invoice-detail__row-ok" : "invoice-detail__row-changed"}
                  >
                    <td>{fmt(c.field)}</td>
                    <td>{fmt(c.extracted)}</td>
                    <td>{fmt(c.corrected)}</td>
                    <td>
                      {c.correct ? (
                        <span className="invoice-detail__status invoice-detail__status--ok">Identique</span>
                      ) : (
                        <span className="invoice-detail__status invoice-detail__status--changed">Modifié</span>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4} className="invoice-detail__empty">
                    Aucune correction détaillée disponible pour cette facture.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
