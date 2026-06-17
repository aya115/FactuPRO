import React, { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import api from "../api";
import "./InvoiceResult.css";
import ReactJson from "react-json-view";

function extractFaiblessesRecommandations(markdown) {
  if (!markdown || typeof markdown !== "string") return "";
  const lower = markdown.toLowerCase();
  const idx = lower.search(/faiblesses\s*critiques|⚠️\s*faiblesses|###\s*remarques|###\s*recommandations|recommandations/);
  if (idx === -1) return "";
  let extract = markdown.slice(idx);
  const jsonBlock = extract.search(/```\s*json\s*\n/);
  if (jsonBlock !== -1) extract = extract.slice(0, jsonBlock);
  return extract.trim();
}

export default function InvoiceResult({ data }) {
  const [showRaw, setShowRaw] = useState(false);
  const [draftJson, setDraftJson] = useState({});
  const [validating, setValidating] = useState(false);
  const [validationMsg, setValidationMsg] = useState("");
  const [validationError, setValidationError] = useState("");

  // On dérive les données de la facture de façon sûre pour les hooks,
  // puis on gère les retours conditionnels plus bas.
  const processed = data?.processed || [];
  const invoice = processed[0];
  const hasError = !!invoice?.error;

  const readableJson = {
    filename: invoice?.filename,
    json: invoice?.json ?? invoice?.json_output ?? {},
    classification: invoice?.classification,
    anomalies: invoice?.anomalies,
  };

  const jsonData = useMemo(
    () => invoice?.json ?? invoice?.json_output ?? {},
    [invoice?.json, invoice?.json_output]
  );
  const anomalies = invoice?.anomalies ?? [];
  const classificationItems = invoice?.classification?.items ?? [];
  const faiblessesRecommandations = extractFaiblessesRecommandations(
    invoice?.raw_response || invoice?.markdown || ""
  );

  // Initialiser / synchroniser le brouillon avec les données extraites
  useEffect(() => {
    const j = jsonData || {};
    const sn = j.seller_name;
    const cn = j.client_name;
    setDraftJson({
      ...j,
      seller_name:
        typeof sn === "object" && sn !== null && !Array.isArray(sn)
          ? { name: "", address: "", tax_id: "", ...sn }
          : { name: typeof sn === "string" ? sn : "", address: "", tax_id: "" },
      client_name:
        typeof cn === "object" && cn !== null && !Array.isArray(cn)
          ? { name: "", address: "", tax_id: "", ...cn }
          : { name: typeof cn === "string" ? cn : "", address: "", tax_id: "" },
    });
    setValidationMsg("");
    setValidationError("");
  }, [invoice, jsonData]);

  const handleSellerChange = (e) => {
    const value = e.target.value;
    setDraftJson((prev) => ({
      ...prev,
      seller_name: { ...(prev.seller_name || {}), name: value },
    }));
  };

  const handleClientChange = (e) => {
    const value = e.target.value;
    setDraftJson((prev) => ({
      ...prev,
      client_name: { ...(prev.client_name || {}), name: value },
    }));
  };

  const handleItemChange = (idx, field, value) => {
    setDraftJson((prev) => {
      const prevItems = prev.items || [];
      const itemsCopy = prevItems.map((it, i) =>
        i === idx ? { ...(it || {}), [field]: value } : it
      );
      return { ...prev, items: itemsCopy };
    });
  };

  const handleValidate = async () => {
    try {
      setValidating(true);
      setValidationMsg("");
      setValidationError("");
  
      const payload = {
        invoice_id: invoice?.invoice_id || invoice?.id,
        extracted: jsonData,      // ← version originale (OCR)
        corrected: draftJson      // ← version corrigée
      };
  
      const res = await api.post("/invoices/confirm", payload);
  
      const pct = res.data?.ocr_precision_pct;
  
      setValidationMsg(
        pct != null
          ? `Facture validée. Précision OCR structurée: ${pct}%`
          : "Facture validée et enregistrée."
      );
  
    } catch (err) {
      setValidationError(
        "Erreur lors de la validation: " +
        (err.response?.data?.error || err.message || "Network Error")
      );
    } finally {
      setValidating(false);
    }
  };

  // Retours conditionnels APRÈS l'initialisation des hooks
  if (!data || !processed.length) return null;

  if (hasError) {
    return (
      <div className="invoice-result error-box">
        <div className="error-icon" aria-hidden>
          !
        </div>
        <h3>Erreur de traitement</h3>
        <p>{invoice.error}</p>
        {invoice.filename && (
          <span className="filename">{invoice.filename}</span>
        )}
      </div>
    );
  }

  return (
    <div className="invoice-result">
      <div className="result-header">
        <h3>Facture analysée</h3>

        <button
          type="button"
          className={`toggle-raw ${showRaw ? "active" : ""}`}
          onClick={() => setShowRaw(!showRaw)}
        >
          {showRaw ? "Vue JSON brute" : "Vue Markdown"}
        </button>
      </div>

      {showRaw ? (
        <ReactJson
        src={readableJson}
        theme="monokai"
        collapsed={2}
        displayDataTypes={false}
        enableClipboard={true}
      />
      ) : (
        <div className="markdown-content">
          {/* Seller & Client : toujours visibles pour compléter ce que l'OCR a raté */}
          <div className="invoice-result-seller-client">
            <h4 className="invoice-items-table-title">
              Détails du Seller et du Client (modifiable)
            </h4>
            <p className="invoice-ocr-hint">
              L’OCR et l’IA peuvent omettre des champs : complétez ici avant validation si besoin.
            </p>

            <p>
              <strong>Vendeur :</strong>{" "}
              <input
                type="text"
                value={draftJson?.seller_name?.name || ""}
                onChange={handleSellerChange}
                className="invoice-inline-input"
                placeholder="Nom issu de la facture ou saisie manuelle"
              />
            </p>

            <p>
              <strong>Acheteur :</strong>{" "}
              <input
                type="text"
                value={draftJson?.client_name?.name || ""}
                onChange={handleClientChange}
                className="invoice-inline-input"
                placeholder="Client / Bill to — souvent absent si mal lu par l’OCR"
              />
            </p>
          </div>

          {/* Items Table (éditable) */}
          {(draftJson.items || []).length > 0 && (
            <div className="invoice-table-container">
              <h4 className="invoice-items-table-title">Articles de facture</h4>
              <div className="invoice-items-table-scroll">
              <table className="invoice-items-table">
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Qté</th>
                    <th>Prix unit. net</th>
                    <th>Net</th>
                    <th>TVA %</th>
                    <th>TTC</th>
                    <th>Catégorie</th>
                  </tr>
                </thead>

                <tbody>
                  {(draftJson.items || []).map((row, idx) => {
                    const clItem = classificationItems[idx] || {};
                    const src = clItem.classification_source;
                    return (
                    <tr key={idx}>
                      <td>
                        <input
                          type="text"
                          value={row.description || ""}
                          onChange={(e) =>
                            handleItemChange(idx, "description", e.target.value)
                          }
                          className="invoice-inline-input"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={row.quantity ?? row.qty ?? ""}
                          onChange={(e) =>
                            handleItemChange(idx, "quantity", e.target.value)
                          }
                          className="invoice-inline-input invoice-inline-input--num"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={row.net_price ?? ""}
                          onChange={(e) =>
                            handleItemChange(idx, "net_price", e.target.value)
                          }
                          className="invoice-inline-input invoice-inline-input--num"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={row.net ?? row.net_worth ?? ""}
                          onChange={(e) =>
                            handleItemChange(idx, "net", e.target.value)
                          }
                          className="invoice-inline-input invoice-inline-input--num"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={row.vat_percentage ?? row.vat ?? ""}
                          onChange={(e) =>
                            handleItemChange(
                              idx,
                              "vat_percentage",
                              e.target.value
                            )
                          }
                          className="invoice-inline-input invoice-inline-input--num"
                        />
                      </td>
                      <td>
                        <input
                          type="text"
                          value={row.gross ?? row.gross_worth ?? ""}
                          onChange={(e) =>
                            handleItemChange(idx, "gross", e.target.value)
                          }
                          className="invoice-inline-input invoice-inline-input--num"
                        />
                      </td>
                      <td>
                        <span className="invoice-category">{clItem.category ?? "—"}</span>
                        {src && (
                          <span className={`invoice-source-badge invoice-source-badge--${src}`}>
                            {src === "rag_llm" ? "RAG" : "CSV"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                  })}
                </tbody>
              </table>
              </div>
            </div>
          )}

          {/* Résultats RAG (snippets web + exemples CSV envoyés au LLM) */}
          {classificationItems.some((it) => it.classification_source === "rag_llm") && (
            <div className="invoice-rag-results">
              <h4 className="invoice-items-table-title">Résultats RAG (contexte envoyé au LLM)</h4>
              {classificationItems.map((clItem, idx) => {
                if (clItem.classification_source !== "rag_llm") return null;
                const webSnippets = clItem.rag_web_snippets || [];
                const csvExamples = clItem.rag_csv_examples || [];
                return (
                  <div key={idx} className="invoice-rag-block">
                    <div className="invoice-rag-header">
                      <strong>{clItem.description || `Ligne ${idx + 1}`}</strong>
                      <span className="invoice-rag-category">→ {clItem.category}</span>
                      {clItem.similarity_score != null && (
                        <span className="invoice-rag-score">score: {clItem.similarity_score}</span>
                      )}
                    </div>
                    {webSnippets.length > 0 && (
                      <div className="invoice-rag-section">
                        <div className="invoice-rag-label">Snippets web (SerpAPI)</div>
                        <ul className="invoice-rag-list">
                          {webSnippets.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {webSnippets.length === 0 && (
                      <div className="invoice-rag-section invoice-rag-section--empty">
                        Aucun snippet SerpAPI (vérifier SERPAPI_API_KEY).
                      </div>
                    )}
                    {csvExamples.length > 0 && (
                      <div className="invoice-rag-section">
                        <div className="invoice-rag-label">Exemples CSV (top-k similaires)</div>
                        <ul className="invoice-rag-list">
                          {csvExamples.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Anomalies */}
          {anomalies.length > 0 && (
            <div className="invoice-result-anomalies">
              <h4 className="invoice-items-table-title">⚠️ Anomalies détectées</h4>
              <ul>
                {anomalies.map((a, i) => (
                  <li key={i} className={a.severity === "error" ? "anomaly-error" : "anomaly-warning"}>
                    {a.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Faiblesses critiques & Recommandations */}
          {faiblessesRecommandations && (
            <div className="invoice-result-faiblesses">
              <div className="markdown-faiblesses">
                <ReactMarkdown>{faiblessesRecommandations}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* Validation human-in-the-loop */}
          <div className="invoice-validate-bar">
            <button
              type="button"
              className="invoice-validate-btn"
              onClick={handleValidate}
              disabled={validating}
            >
              {validating ? "Validation en cours…" : "Valider et enregistrer la facture"}
            </button>
            {validationMsg && (
              <span className="invoice-validate-msg">{validationMsg}</span>
            )}
            {validationError && (
              <span className="invoice-validate-error">{validationError}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}