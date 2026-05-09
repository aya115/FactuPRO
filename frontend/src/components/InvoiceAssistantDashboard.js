import React, { useMemo, useState, useEffect, useRef } from "react";
import api from "../api";

import ReactMarkdown from "react-markdown";
import html2canvas from "html2canvas";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import "./InvoiceAssistantDashboard.css";

const CHART_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4", "#22c55e", "#e11d48"];

const HISTORY_KEY = "ia_question_history";
const CACHE_KEY = "ia_result_cache";
const MAX_HISTORY = 15;
const MAX_CACHE = 20;
const TABLE_PAGE_SIZE = 50;

const SUGGESTED_QUESTIONS = [
  "Total TTC par catégorie",
  "Top 5 clients par montant TTC",
  "Top 10 fournisseurs par nombre de factures",
  "Évolution mensuelle du total net",
  "Total TTC par mois et par catégorie",
  "Montant total par compte comptable",
  "Dépenses par vendeur",
  "Bottom 5 catégories par montant",
  "Nombre de factures par client",
  "Somme des montants HT par mois",
];

function isNumber(x) {
  return typeof x === "number" && Number.isFinite(x);
}

function guessVizType(question) {
  const q = (question || "").toLowerCase();
  if (q.includes("cat") || q.includes("catégorie") || q.includes("categorie")) return "pie";
  if (q.includes("top") || q.includes("bottom") || q.includes("fournisseur") || q.includes("vendor") || q.includes("vendeur"))
    return "bar";
  if (q.includes("évolution") || q.includes("evolution") || q.includes("par mois") || q.includes("par date") || q.includes("mensuel"))
    return "line";
  return "table";
}

function getTopBottomLimit(question) {
  const q = (question || "").toLowerCase();
  const topMatch = q.match(/\b(?:top|meilleurs?)\s*(\d+)/i);
  const bottomMatch = q.match(/\b(?:bottom|pires?|moins)\s*(\d+)/i);
  if (topMatch) return { limit: Math.min(parseInt(topMatch[1], 10) || 10, 20), reverse: false };
  if (bottomMatch) return { limit: Math.min(parseInt(bottomMatch[1], 10) || 10, 20), reverse: true };
  if (q.includes("top") || q.includes("meilleurs")) return { limit: 10, reverse: false };
  if (q.includes("bottom") || q.includes("pires")) return { limit: 10, reverse: true };
  return null;
}

function loadJson(key, fallback) {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch (_) {}
}

function rowsToCSV(columns, rows) {
  const head = columns.join(";");
  const body = rows.map((r) => columns.map((c) => {
    const v = r[c];
    if (v == null) return "";
    const s = String(v).replace(/"/g, '""');
    return s.includes(";") || s.includes('"') || s.includes("\n") ? `"${s}"` : s;
  }).join(";"));
  return "\uFEFF" + [head, ...body].join("\r\n");
}

function stripMarkdown(text) {
  if (!text || typeof text !== "string") return "";
  return text
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/#{1,6}\s*/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\n+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export default function InvoiceAssistantDashboard() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [vizOverride, setVizOverride] = useState("");
  const [tablePage, setTablePage] = useState(1);
  const [theme, setTheme] = useState(() => loadJson("ia_theme", "dark"));
  const [history, setHistory] = useState(() => loadJson(HISTORY_KEY, []));
  const [cache, setCache] = useState(() => loadJson(CACHE_KEY, {}));
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [chartFilterOpen, setChartFilterOpen] = useState(false);
  const [chartFilterLabels, setChartFilterLabels] = useState(() => new Set());
  const [chartFilterValueMin, setChartFilterValueMin] = useState("");
  const [chartFilterValueMax, setChartFilterValueMax] = useState("");
  const [chartFilterApplyLabel, setChartFilterApplyLabel] = useState(true);
  const [chartFilterApplyValue, setChartFilterApplyValue] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceTranscript, setVoiceTranscript] = useState("");
  const chartRef = useRef(null);
  const chartContainerRef = useRef(null);
  const formRef = useRef(null);
  const chartFilterPanelRef = useRef(null);
  const speechSynthRef = useRef(null);
  const ttsObjectUrlRef = useRef(null);
  /** @type {React.MutableRefObject<MediaRecorder | null>} */
  const mediaRecorderRef = useRef(null);
  const mediaChunksRef = useRef([]);
  const mediaStreamRef = useRef(null);
//Sauvegarde thème dark/light
  useEffect(() => {
    saveJson("ia_theme", theme);
  }, [theme]);

  useEffect(() => {
    setChartFilterLabels(new Set());
    setChartFilterValueMin("");
    setChartFilterValueMax("");
    setChartFilterApplyLabel(true);
    setChartFilterApplyValue(false);
    setChartFilterOpen(false);
  }, [result?.question]);

  useEffect(() => {
    if (!chartFilterOpen) return;
    const close = (e) => {
      const el = chartFilterPanelRef.current;
      if (el && !el.contains(e.target)) setChartFilterOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [chartFilterOpen]);

  const speakResponseWithBrowser = (text) => {
    if (!text.trim() || !window.speechSynthesis) {
      setIsSpeaking(false);
      return;
    }
    window.speechSynthesis.cancel();
    const u = new window.SpeechSynthesisUtterance(text);
    u.lang = "fr-FR";
    u.rate = 0.95;
    const voices = window.speechSynthesis.getVoices?.() || [];
    const fr = voices.find((v) => v.lang.startsWith("fr"));
    if (fr) u.voice = fr;
    u.onstart = () => setIsSpeaking(true);
    u.onend = u.onerror = () => {
      setIsSpeaking(false);
      speechSynthRef.current = null;
    };
    speechSynthRef.current = u;
    window.speechSynthesis.speak(u);
  };
//Fonction lecture vocale :
  const speakResponse = async () => {
    if (!result || result?.clarification) return;
    const parts = [];
    if (result.commentaire) parts.push(stripMarkdown(result.commentaire));
    if (result.explanation) parts.push(result.explanation);
    if (result.kpis?.length) {
      const kpiText = result.kpis.slice(0, 4).map((k) => `${k.label} : ${k.value}`).join(". ");
      parts.push("Résumé : " + kpiText);
    }
    const text = parts.join(" ");
    if (!text.trim()) return;

    stopSpeaking();

    try {
      setIsSpeaking(true);
      const res = await api.post(//Backend génère audio
        "/audio/speak",
        { text: text.slice(0, 4000) },
        { responseType: "blob", timeout: 120000 }
      );
      const url = URL.createObjectURL(res.data);
      ttsObjectUrlRef.current = url;
      const audio = new Audio(url);
      speechSynthRef.current = audio;
      audio.onended = () => {
        if (ttsObjectUrlRef.current) {
          URL.revokeObjectURL(ttsObjectUrlRef.current);
          ttsObjectUrlRef.current = null;
        }
        setIsSpeaking(false);
        speechSynthRef.current = null;
      };
      audio.onerror = () => {
        if (ttsObjectUrlRef.current) {
          URL.revokeObjectURL(ttsObjectUrlRef.current);
          ttsObjectUrlRef.current = null;
        }
        setIsSpeaking(false);
        speechSynthRef.current = null;
        speakResponseWithBrowser(text);
      };
      await audio.play();
    } catch {
      setIsSpeaking(false);
      speechSynthRef.current = null;
      speakResponseWithBrowser(text);
    }
  };

  const stopSpeaking = () => {
    if (ttsObjectUrlRef.current) {
      URL.revokeObjectURL(ttsObjectUrlRef.current);
      ttsObjectUrlRef.current = null;
    }
    const ref = speechSynthRef.current;
    if (ref && typeof ref.pause === "function") {
      ref.pause();
      if (ref.src) ref.src = "";
    }
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
    speechSynthRef.current = null;
  };

  useEffect(() => {
    const voices = () => window.speechSynthesis?.getVoices?.();
    if (window.speechSynthesis && !voices()?.length) {
      window.speechSynthesis.onvoiceschanged = voices;
    }
    return () => {
      window.speechSynthesis?.cancel();
      const ref = speechSynthRef.current;
      if (ref && typeof ref.pause === "function") ref.pause();
    };
  }, []);
//Micro IA
  const toggleListen = async () => {
    if (isListening) {
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        setIsListening(false);
        setVoiceTranscript("");
      }
      return;
    }

    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setError("Enregistrement audio non supporté par ce navigateur.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      mediaChunksRef.current = [];
      const mime =
        MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
      const mr = new MediaRecorder(stream, { mimeType: mime });
      mediaRecorderRef.current = mr;

      mr.ondataavailable = (e) => {
        if (e.data?.size) mediaChunksRef.current.push(e.data);
      };

      mr.onstop = async () => {
        const s = mediaStreamRef.current;
        if (s) {
          s.getTracks().forEach((t) => t.stop());
          mediaStreamRef.current = null;
        }
        setIsListening(false);
        const chunks = mediaChunksRef.current;
        mediaChunksRef.current = [];
        const blob = new Blob(chunks, { type: mr.mimeType || "audio/webm" });
        if (blob.size < 80) {
          setVoiceTranscript("");
          return;
        }
        setVoiceTranscript("Transcription…");
        try {
          const fd = new FormData();
          fd.append("file", blob, "audio.webm");
          const { data } = await api.post("/audio/transcribe", fd, { timeout: 120000 });
          const t = (data?.text || "").trim();
          if (t) setQuestion((prev) => (prev + (prev.trim() ? " " : "") + t).trim());
        } catch (err) {
          const msg =
            err.response?.data?.error ||
            (typeof err.response?.data === "string" ? err.response.data : null) ||
            err.message ||
            "Transcription impossible";
          setError(typeof msg === "string" ? msg : "Transcription impossible");
        } finally {
          setVoiceTranscript("");
        }
      };

      mr.onerror = () => {
        setIsListening(false);
        setVoiceTranscript("");
        mediaStreamRef.current?.getTracks?.().forEach((t) => t.stop());
        mediaStreamRef.current = null;
      };

      mr.start(400);
      setIsListening(true);
      setVoiceTranscript("Enregistrement… Parlez, puis recliquez pour envoyer.");
    } catch {
      setError("Microphone refusé ou indisponible.");
      setIsListening(false);
      setVoiceTranscript("");
    }
  };

  const hasMediaRecorder =
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    typeof MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia;

  const canReadAloud =
    !result?.clarification && !!(result?.commentaire || result?.explanation || result?.kpis?.length);

  const suggestionsFiltered = useMemo(() => {
    const q = (question || "").trim().toLowerCase();
    if (q.length < 2) return SUGGESTED_QUESTIONS.slice(0, 5);
    return SUGGESTED_QUESTIONS.filter((s) => s.toLowerCase().includes(q)).slice(0, 8);
  }, [question]);

  const columns = result?.columns || [];
  const rows = result?.rows || [];
  const kpis = result?.kpis || [];
  const viz = result?.viz || {};

  const { labelColumn, valueColumn, chartData, chartType } = useMemo(() => {
    const cols = columns;
    const rs = rows;
    const explicitType = typeof viz.type === "string" ? viz.type.toLowerCase() : "";
    const requestedType = (vizOverride || explicitType || guessVizType(question)).toLowerCase();
    const explicitLabel = typeof viz.labelColumn === "string" ? viz.labelColumn : "";
    const explicitValue = typeof viz.valueColumn === "string" ? viz.valueColumn : "";

    let labelCol = explicitLabel && cols.includes(explicitLabel) ? explicitLabel : "";
    let valueCol = explicitValue && cols.includes(explicitValue) ? explicitValue : "";

    if (!valueCol && rs.length > 0) {
      for (const c of cols) {
        const v = rs[0]?.[c];
        if (isNumber(v)) { valueCol = c; break; }
      }
    }
    if (!labelCol && rs.length > 0) {
      for (const c of cols) {
        const v = rs[0]?.[c];
        if (!isNumber(v) && !/id$/i.test(c)) { labelCol = c; break; }
      }
    }

    const canChart = Boolean(labelCol && valueCol) && rs.length > 0;
    const type = canChart ? requestedType : "table";

    let data = canChart
      ? rs.slice(0, 30).map((r) => ({
          name: r[labelCol] === null || r[labelCol] === undefined || r[labelCol] === "" ? "—" : String(r[labelCol]),
          value: isNumber(r[valueCol]) ? r[valueCol] : Number(r[valueCol]) || 0,
        }))
      : [];

    const topBottom = getTopBottomLimit(question);
    if (topBottom && data.length > 0) {
      if (topBottom.reverse) data = [...data].sort((a, b) => a.value - b.value).slice(0, topBottom.limit);
      else data = [...data].sort((a, b) => b.value - a.value).slice(0, topBottom.limit);
    }

    return { labelColumn: labelCol, valueColumn: valueCol, chartData: data, chartType: type };
  }, [columns, rows, viz.type, viz.labelColumn, viz.valueColumn, vizOverride, question]);

  const filteredChartData = useMemo(() => {
    let data = chartData;
    if (chartFilterApplyLabel) {
      if (chartFilterLabels.size > 0 && !chartFilterLabels.has("\u200b")) {
        data = data.filter((d) => chartFilterLabels.has(d.name));
      } else if (chartFilterLabels.has("\u200b")) {
        data = [];
      }
    }
    if (chartFilterApplyValue) {
      const minVal = chartFilterValueMin !== "" && Number.isFinite(Number(chartFilterValueMin)) ? Number(chartFilterValueMin) : null;
      const maxVal = chartFilterValueMax !== "" && Number.isFinite(Number(chartFilterValueMax)) ? Number(chartFilterValueMax) : null;
      if (minVal != null) data = data.filter((d) => d.value >= minVal);
      if (maxVal != null) data = data.filter((d) => d.value <= maxVal);
    }
    return data;
  }, [chartData, chartFilterLabels, chartFilterValueMin, chartFilterValueMax, chartFilterApplyLabel, chartFilterApplyValue]);

  const paginatedRows = useMemo(() => {
    const start = (tablePage - 1) * TABLE_PAGE_SIZE;
    return rows.slice(start, start + TABLE_PAGE_SIZE);
  }, [rows, tablePage]);
  const totalPages = Math.max(1, Math.ceil(rows.length / TABLE_PAGE_SIZE));

  const handleAsk = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (!q) {
      setError("Merci de saisir une question.");
      return;
    }
    const cacheKey = q.toLowerCase();
    if (cache[cacheKey]) {
      setResult(cache[cacheKey]);
      setError("");
      setTablePage(1);
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    setTablePage(1);
    try {
      const res = await api.post("/qa", { question: q }, { timeout: 90000 });
      const data = res.data;
      setResult(data);
      const nextHistory = [q, ...(history.filter((h) => h !== q))].slice(0, MAX_HISTORY);
      setHistory(nextHistory);
      saveJson(HISTORY_KEY, nextHistory);
      const nextCache = { [cacheKey]: data, ...cache };
      const keys = Object.keys(nextCache).slice(0, MAX_CACHE);
      const trimmed = keys.reduce((acc, k) => ({ ...acc, [k]: nextCache[k] }), {});
      setCache(trimmed);
      saveJson(CACHE_KEY, trimmed);
    } catch (err) {
      setError("Erreur: " + (err.response?.data?.error || err.message));
    } finally {
      setLoading(false);
    }
  };

  const setQuestionAndHide = (q) => {
    setQuestion(q);
    setShowSuggestions(false);
  };

  const setQuestionAndSubmit = (q) => {
    setQuestion(q);
    setShowSuggestions(false);
    setTimeout(() => formRef.current?.requestSubmit(), 100);
  };

  const exportCSV = () => {
    if (!columns.length || !rows.length) return;
    const csv = rowsToCSV(columns, rows);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "resultats-factures-ia.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggleChartFilterLabel = (name) => {
    setChartFilterLabels((prev) => {
      const allNames = chartData.map((d) => d.name);
      const isChecked = prev.size === 0 || prev.has(name);
      if (isChecked) {
        const next = prev.size === 0 ? new Set(allNames) : new Set(prev);
        next.delete(name);
        return next.size === 0 ? new Set() : next;
      }
      const next = new Set(prev.size === 0 ? allNames : prev);
      next.add(name);
      return next.size === chartData.length ? new Set() : next;
    });
  };

  const selectAllChartFilterLabels = () => setChartFilterLabels(new Set());
  const selectNoneChartFilterLabels = () => setChartFilterLabels(new Set(["\u200b"]));

  const exportChartPNG = async () => {
    const el = chartContainerRef.current;
    if (!el) return;
    try {
      const canvas = await html2canvas(el, { backgroundColor: "#020617", scale: 2 });
      const url = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = url;
      a.download = "graphique-factures-ia.png";
      a.click();
    } catch (err) {
      console.error(err);
    }
  };

  const quickFilters = [
    { label: "Cette année", append: " pour cette année" },
    { label: "Par catégorie", append: " par catégorie" },
    { label: "Par client", append: " par client" },
    { label: "Par fournisseur", append: " par fournisseur (vendeur)" },
    { label: "Par mois", append: " par mois" },
  ];

  return (
    <section className={`ia ia--${theme}`}>
      <div className="ia__layout">
        <div className="ia__left">
          <div className="ia__card">
            <div className="ia__cardHead">
              <h2 className="ia__title">Assistant IA factures</h2>
              <button
                type="button"
                className="ia__themeToggle"
                onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
                title={theme === "dark" ? "Mode clair" : "Mode sombre"}
                aria-label="Changer le thème"
              >
                {theme === "dark" ? "☀️" : "🌙"}
              </button>
            </div>
            <p className="ia__subtitle">
              Pose une question libre sur tes factures : totaux, clients, catégories, comptes, etc.
            </p>

            <form ref={formRef} className="ia__form" onSubmit={handleAsk}>
              <div className="ia__inputWrap">
                <div className="ia__textareaRow">
                  <textarea
                    className="ia__textarea"
                    rows={3}
                    placeholder="Ex: total TTC par catégorie, top 5 clients par montant, évolution mensuelle..."
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onFocus={() => setShowSuggestions(true)}
                    onBlur={() => setTimeout(() => setShowSuggestions(false), 180)}
                    disabled={loading}
                  />
                  {hasMediaRecorder && (
                    <button
                      type="button"
                      className={`ia__voiceBtn ia__voiceBtn--mic ${isListening ? "ia__voiceBtn--active" : ""}`}
                      onClick={() => toggleListen()}
                      title={
                        isListening
                          ? "Arrêter et transcrire (Whisper)"
                          : "Enregistrer la question (Whisper — recliquer pour envoyer)"
                      }
                      aria-label={isListening ? "Arrêter l'enregistrement" : "Enregistrer la question"}
                    >
                      <span className="ia__voiceIcon" aria-hidden>
                        {isListening ? (
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11v2a7 7 0 0 0 14 0v-2M12 19v4M8 23h8"/></svg>
                        ) : (
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/></svg>
                        )}
                      </span>
                      <span className="ia__voiceLabel">{isListening ? "Stop → Whisper" : "Micro"}</span>
                    </button>
                  )}
                </div>
                {isListening && voiceTranscript && (
                  <p className="ia__voiceTranscript">{voiceTranscript}</p>
                )}
                {showSuggestions && suggestionsFiltered.length > 0 && (
                  <ul className="ia__suggestions">
                    {suggestionsFiltered.map((s) => (
                      <li key={s}>
                        <button type="button" className="ia__suggestionBtn" onClick={() => setQuestionAndHide(s)}>
                          {s}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="ia__quickFilters">
                <span className="ia__quickFiltersLabel">Filtres rapides :</span>
                {quickFilters.map((f) => (
                  <button
                    key={f.label}
                    type="button"
                    className="ia__chip"
                    onClick={() => setQuestion((prev) => (prev.trim() ? prev.trim() + f.append : f.label.toLowerCase()))}
                    disabled={loading}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              {history.length > 0 && (
                <div className="ia__history">
                  <span className="ia__historyLabel">Dernières questions :</span>
                  <div className="ia__historyChips">
                    {history.slice(0, 8).map((h) => (
                      <button
                        key={h}
                        type="button"
                        className="ia__chip ia__chip--history"
                        onClick={() => setQuestionAndHide(h)}
                      >
                        {h.length > 40 ? h.slice(0, 37) + "…" : h}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="ia__actions">
                <div className="ia__vizPick">
                  <span className="ia__vizLabel">Graphique</span>
                  <select
                    className="ia__select"
                    value={vizOverride}
                    onChange={(e) => setVizOverride(e.target.value)}
                    disabled={loading}
                  >
                    <option value="">Auto</option>
                    <option value="pie">Camembert</option>
                    <option value="bar">Barres</option>
                    <option value="line">Ligne</option>
                    <option value="area">Aire</option>
                    <option value="table">Tableau seul</option>
                  </select>
                </div>
                <button className="ia__btn" type="submit" disabled={loading}>
                  {loading ? "Analyse en cours…" : "Poser la question"}
                </button>
              </div>
            </form>

            {error && <div className="ia__error">{error}</div>}
            {result?.clarification && (
              <div className="ia__clarification">
                <p className="ia__clarificationText">{result.clarification}</p>
                {(result.clarification_suggestions || []).length > 0 && (
                  <div className="ia__clarificationChips">
                    {(result.clarification_suggestions || []).map((s) => (
                      <button key={s} type="button" className="ia__chip ia__chip--clarify" onClick={() => setQuestionAndSubmit(s)}>
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {result?.commentaire && !result?.clarification && (
              <div className="ia__answer">
                <ReactMarkdown>{result.commentaire}</ReactMarkdown>
              </div>
            )}
            {canReadAloud && (
              <div className="ia__readAloud">
                {isSpeaking ? (
                  <button type="button" className="ia__voiceBtn ia__voiceBtn--stop" onClick={stopSpeaking} title="Arrêter la lecture">
                    <span className="ia__voiceIcon" aria-hidden><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg></span>
                    <span>Arrêter la lecture</span>
                  </button>
                ) : (
                  <button type="button" className="ia__voiceBtn ia__voiceBtn--speaker" onClick={speakResponse} title="Lire la réponse à haute voix">
                    <span className="ia__voiceIcon" aria-hidden><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07M19.07 4.93a10 10 0 0 1 0 14.14"/></svg></span>
                    <span>Lire la réponse</span>
                  </button>
                )}
              </div>
            )}
            {result?.explanation && !result?.clarification && (
              <div className="ia__explanation">
                <strong>Résumé :</strong> {result.explanation}
              </div>
            )}
            {result?.suggestions?.length > 0 && !result?.clarification && (
              <div className="ia__followUp">
                <span className="ia__followUpLabel">Suggestions de suivi :</span>
                <div className="ia__followUpChips">
                  {result.suggestions.map((s) => (
                    <button key={s} type="button" className="ia__chip ia__chip--followUp" onClick={() => setQuestionAndSubmit(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {result?.sql && !result?.clarification && (
              <details className="ia__sql">
                <summary>Requête SQL générée</summary>
                <pre><code>{result.sql}</code></pre>
              </details>
            )}
          </div>
        </div>

        <div className="ia__right">
          {result?.clarification && (
            <div className="ia__card ia__card--clarificationHelp">
              <p className="ia__muted">Précisez votre question en cliquant sur une suggestion à gauche, puis recliquez sur « Poser la question ».</p>
            </div>
          )}
          <div className="ia__card ia__card--metrics">
            <h3 className="ia__sectionTitle">KPIs</h3>
            {kpis.length === 0 && !result?.clarification ? (
              <p className="ia__muted">Aucun résultat pour l'instant.</p>
            ) : kpis.length > 0 ? (
              <div className="ia__kpis">
                {kpis.map((kpi, idx) => (
                  <div key={idx} className="ia__kpi">
                    <span className="ia__kpiLabel">{kpi.label}</span>
                    <span className="ia__kpiValue">{typeof kpi.value === "number" && Number.isFinite(kpi.value) ? Number(kpi.value).toLocaleString("fr-FR") : kpi.value}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="ia__card ia__card--chart" ref={chartRef}>
            <div className="ia__chartHeader">
              <h3 className="ia__sectionTitle">{viz.title || "Graphique"}</h3>
              <div className="ia__chartHeaderActions">
                {labelColumn && valueColumn && (
                  <span className="ia__mutedSmall">{labelColumn} / {valueColumn}</span>
                )}
                {(chartType === "pie" || chartType === "bar" || chartType === "line" || chartType === "area") && chartData.length > 0 && (
                  <>
                    <div className="ia__chartFilterWrap" ref={chartFilterPanelRef}>
                      <button
                        type="button"
                        className={`ia__chartFilterBtn ${(chartFilterApplyLabel && (chartFilterLabels.size > 0 || chartFilterLabels.has("\u200b"))) || (chartFilterApplyValue && (chartFilterValueMin !== "" || chartFilterValueMax !== "")) ? "ia__chartFilterBtn--active" : ""}`}
                        onClick={() => setChartFilterOpen((o) => !o)}
                        title="Filtrer le graphique"
                        aria-label="Filtrer le graphique"
                      >
                        <span className="ia__chartFilterIcon" aria-hidden>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
                        </span>
                        <span className="ia__chartFilterIconLabel">Filtrer</span>
                      </button>
                      {chartFilterOpen && (
                        <div className="ia__chartFilterPanel">
                          <div className="ia__chartFilterAxisChoice">
                            <span className="ia__chartFilterSectionTitle">Appliquer le filtre sur :</span>
                            <label className="ia__chartFilterAxisOption">
                              <input type="checkbox" checked={chartFilterApplyLabel} onChange={(e) => setChartFilterApplyLabel(e.target.checked)} />
                              <span>Axe catégorie ({labelColumn})</span>
                            </label>
                            <label className="ia__chartFilterAxisOption">
                              <input type="checkbox" checked={chartFilterApplyValue} onChange={(e) => setChartFilterApplyValue(e.target.checked)} />
                              <span>Axe valeur ({valueColumn})</span>
                            </label>
                          </div>
                          <div className="ia__chartFilterSection">
                            <span className="ia__chartFilterSectionTitle">Axe catégorie — {labelColumn}</span>
                            <div className="ia__chartFilterCheckAll">
                              <button type="button" className="ia__chartFilterLink" onClick={selectAllChartFilterLabels}>Tout</button>
                              <span> · </span>
                              <button type="button" className="ia__chartFilterLink" onClick={selectNoneChartFilterLabels}>Aucun</button>
                            </div>
                            <div className={`ia__chartFilterCheckboxes ${!chartFilterApplyLabel ? "ia__chartFilterCheckboxes--disabled" : ""}`}>
                              {chartData.map((d) => {
                                const checked = chartFilterLabels.size === 0 || chartFilterLabels.has(d.name);
                                return (
                                  <label key={d.name} className="ia__chartFilterCheck">
                                    <input type="checkbox" checked={checked} onChange={() => toggleChartFilterLabel(d.name)} disabled={!chartFilterApplyLabel} />
                                    <span className="ia__chartFilterCheckLabel">{d.name}</span>
                                  </label>
                                );
                              })}
                            </div>
                          </div>
                          <div className="ia__chartFilterSection">
                            <span className="ia__chartFilterSectionTitle">Axe valeur — {valueColumn}</span>
                            <div className={`ia__chartFilterRange ${!chartFilterApplyValue ? "ia__chartFilterRange--disabled" : ""}`}>
                              <input type="number" placeholder="Min" value={chartFilterValueMin} onChange={(e) => setChartFilterValueMin(e.target.value)} className="ia__chartFilterInput" disabled={!chartFilterApplyValue} />
                              <span> – </span>
                              <input type="number" placeholder="Max" value={chartFilterValueMax} onChange={(e) => setChartFilterValueMax(e.target.value)} className="ia__chartFilterInput" disabled={!chartFilterApplyValue} />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                    <button type="button" className="ia__btn ia__btn--small" onClick={exportChartPNG}>
                      Télécharger PNG
                    </button>
                  </>
                )}
              </div>
            </div>
            <div className="ia__chart" ref={chartContainerRef}>
              {chartData.length > 0 && filteredChartData.length === 0 && (
                <div className="ia__chartFilterEmpty">Aucune donnée après filtre. Cliquez sur « Tout » dans le filtre.</div>
              )}
              {chartType === "pie" && chartData.length > 0 && filteredChartData.length > 0 && (
                <ResponsiveContainer width="100%" height={280}>
                  <PieChart>
                    <Pie data={filteredChartData} dataKey="value" nameKey="name" innerRadius={70} outerRadius={100} paddingAngle={2} isAnimationActive>
                      {filteredChartData.map((_, i) => (
                        <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v) => [Number(v).toLocaleString("fr-FR"), valueColumn]} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
              {chartType === "bar" && chartData.length > 0 && filteredChartData.length > 0 && (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={filteredChartData} margin={{ bottom: 30 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-18} textAnchor="end" height={70} />
                    <YAxis tickFormatter={(v) => Number(v).toLocaleString("fr-FR")} />
                    <Tooltip formatter={(v) => [Number(v).toLocaleString("fr-FR"), valueColumn]} />
                    <Bar dataKey="value" radius={[6, 6, 0, 0]} isAnimationActive animationDuration={600}>
                      {filteredChartData.map((_, i) => (
                        <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
              {chartType === "line" && chartData.length > 0 && filteredChartData.length > 0 && (
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={filteredChartData} margin={{ bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tickFormatter={(v) => Number(v).toLocaleString("fr-FR")} />
                    <Tooltip formatter={(v) => [Number(v).toLocaleString("fr-FR"), valueColumn]} />
                    <Line type="monotone" dataKey="value" stroke={CHART_COLORS[0]} strokeWidth={2} dot={{ r: 4 }} isAnimationActive animationDuration={600} name={valueColumn} />
                  </LineChart>
                </ResponsiveContainer>
              )}
              {chartType === "area" && chartData.length > 0 && filteredChartData.length > 0 && (
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={filteredChartData} margin={{ bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.25} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tickFormatter={(v) => Number(v).toLocaleString("fr-FR")} />
                    <Tooltip formatter={(v) => [Number(v).toLocaleString("fr-FR"), valueColumn]} />
                    <Area type="monotone" dataKey="value" stroke={CHART_COLORS[0]} fill={CHART_COLORS[0]} fillOpacity={0.4} isAnimationActive animationDuration={600} name={valueColumn} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
              {chartType !== "pie" && chartType !== "bar" && chartType !== "line" && chartType !== "area" && (
                <div className="ia__chartEmpty">
                  Pose une question du type <b>label + valeur</b> (ex. total TTC par catégorie, top 5 clients, évolution par mois).
                </div>
              )}
            </div>
          </div>

          <div className="ia__card ia__card--table">
            <div className="ia__tableToolbar">
              <h3 className="ia__sectionTitle">Résultats détaillés</h3>
              {rows.length > 0 && (
                <button type="button" className="ia__btn ia__btn--small" onClick={exportCSV}>
                  Exporter CSV
                </button>
              )}
            </div>
            <div className="ia__tableWrap">
              <table className="ia__table">
                <thead>
                  <tr>
                    {columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paginatedRows.length === 0 ? (
                    <tr>
                      <td colSpan={columns.length || 1} className="ia__empty">
                        Aucun résultat à afficher.
                      </td>
                    </tr>
                  ) : (
                    paginatedRows.map((row, idx) => (
                      <tr key={(tablePage - 1) * TABLE_PAGE_SIZE + idx}>
                        {columns.map((c) => (
                          <td key={c}>
                            {row[c] === null || row[c] === undefined || row[c] === ""
                              ? "—"
                              : typeof row[c] === "number" && Number.isFinite(row[c])
                                ? Number(row[c]).toLocaleString("fr-FR")
                                : String(row[c])}
                          </td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <div className="ia__pagination">
                <button type="button" className="ia__pageBtn" disabled={tablePage <= 1} onClick={() => setTablePage((p) => p - 1)}>
                  ← Précédent
                </button>
                <span className="ia__pageInfo">
                  Page {tablePage} / {totalPages} ({rows.length} lignes)
                </span>
                <button type="button" className="ia__pageBtn" disabled={tablePage >= totalPages} onClick={() => setTablePage((p) => p + 1)}>
                  Suivant →
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
