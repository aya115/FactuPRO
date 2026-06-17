// UploadInvoice.jsx
import React, { useState } from "react";
import api from "../api";
import InvoiceResult from "./InvoiceResult";
import "../App.css";

export default function UploadInvoice() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    setFile(selectedFile);
    setResult(null);
    setError("");
  };

  const handleUpload = async () => {
    if (!file) {
      setError("⚠️ Veuillez sélectionner un fichier !");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      // Plusieurs pages PDF + Groq + 1er chargement embeddings : peut dépasser 5 min sur machine modeste
      const res = await api.post("/upload", formData, { timeout: 900000 });
      setResult(res.data);
    } catch (err) {
      setError("Erreur: " + (err.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleExportMarkdown = () => {
    if (!result || !result.processed || !result.processed[0]?.raw_response) return;

    const blob = new Blob([result.processed[0].raw_response], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = (result.processed[0].filename || "facture") + ".md";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="upload-container">
      <h2>Upload Facture</h2>
      
      <div className="file-input-wrapper">
        <input
          type="file"
          id="file-input"
          accept=".pdf,.jpg,.jpeg,.png,.json,.xml"
          onChange={handleFileChange}
        />
        <label
          htmlFor="file-input"
          className={`file-input-label ${file ? "has-file" : ""}`}
        >  <div className="file-icon">{file ? "📄" : "📁"}</div>
          <div className="file-text">{file ? "Fichier sélectionné" : "Cliquez pour choisir un fichier"}</div>
          {file && <div className="file-name" title={file.name}>{file.name}</div>}
        </label>
        
      </div>

      <div className="button-group">
        <button onClick={handleUpload} disabled={loading || !file}>
          {loading && <span className="loading-spinner" aria-hidden />}
          {loading ? "Analyse en cours…" : "Traiter la facture"}
        </button>
        {result && (
          <button type="button" className="btn-export" onClick={handleExportMarkdown}>
            Exporter Markdown
          </button>
        )}
      </div>

      {loading && (
        <p className="upload-hint" role="status">
          PDF multi-pages, OCR et appel IA : le premier traitement peut prendre plusieurs minutes
          (chargement du modèle de classification). Ne fermez pas l’onglet.
        </p>
      )}

      {error && <div className="error-message">{error}</div>}
      {result && <InvoiceResult data={result} />}
    </div>
  );
}
