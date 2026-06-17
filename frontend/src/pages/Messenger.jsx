import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import api from "../api";
import "./Messenger.css";

const ROLE_LABELS = {
  comptable: "Comptable",
  superviseur: "Superviseur",
};

const INTENT_ICONS = {
  question: "❓",
  correction: "✏️",
  approval: "✅",
  ack: "👍",
  info: "ℹ️",
};

function displayName(user) {
  return user?.full_name || user?.email?.split("@")[0] || "Utilisateur";
}

function initials(user) {
  const name = displayName(user);
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const sameDay =
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear();
  if (sameDay) {
    return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

function formatMessageTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function MessageContent({ text }) {
  const str = String(text || "");
  const parts = str.split(/(#\d+|facture\s+#?\d+)/gi).filter((p) => p !== "");
  return (
    <p>
      {parts.map((part, i) => {
        const idMatch = part.match(/#(\d+)/i);
        if (idMatch) {
          return (
            <Link key={i} to={`/invoice/${idMatch[1]}`} className="messenger__invoice-link">
              {part}
            </Link>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

function MessageTags({ metadata, isMine }) {
  if (isMine || !metadata) return null;
  const { priority, intent, intent_label, insight } = metadata;
  const showPriority = priority && priority !== "normal";
  const showIntent = intent && intent !== "info";
  if (!showPriority && !showIntent && !insight) return null;

  return (
    <div className="messenger__tags">
      {showPriority && (
        <span className={`messenger__tag messenger__tag--${priority}`}>
          {priority === "urgent" ? "Urgent" : "Prioritaire"}
        </span>
      )}
      {showIntent && (
        <span className="messenger__tag messenger__tag--intent">
          {INTENT_ICONS[intent] || "ℹ️"} {intent_label || intent}
        </span>
      )}
      {insight && <span className="messenger__tag-insight">{insight}</span>}
    </div>
  );
}

export default function Messenger() {
  const { user } = useAuth();
  const [conversations, setConversations] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [mobileShowChat, setMobileShowChat] = useState(false);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [context, setContext] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [actionItems, setActionItems] = useState([]);
  const [assistLoading, setAssistLoading] = useState(false);
  const [improveTone, setImproveTone] = useState("pro");
  const [isListening, setIsListening] = useState(false);
  const [voiceHint, setVoiceHint] = useState("");

  const messagesContainerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const stickToBottomRef = useRef(true);
  const pollRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const mediaChunksRef = useRef([]);

  const selectedContact = conversations.find((c) => c.user_id === selectedId);

  const loadConversations = useCallback(async (silent = false) => {
    if (!silent) setLoadingConversations(true);
    try {
      const res = await api.get("/chat/conversations");
      const list = res.data?.conversations || [];
      setConversations(list);
      setSelectedId((prev) => {
        if (prev && list.some((c) => c.user_id === prev)) return prev;
        return list[0]?.user_id ?? null;
      });
    } catch (e) {
      if (!silent) setError(e.response?.data?.error || "Impossible de charger les conversations.");
    } finally {
      if (!silent) setLoadingConversations(false);
    }
  }, []);

  const loadContext = useCallback(async () => {
    try {
      const res = await api.get("/chat/context");
      setContext(res.data || null);
    } catch {
      setContext(null);
    }
  }, []);

  const loadAssist = useCallback(async (partnerId) => {
    if (!partnerId) {
      setSuggestions([]);
      setSummary(null);
      setActionItems([]);
      return;
    }
    setAssistLoading(true);
    try {
      const [sugRes, sumRes] = await Promise.all([
        api.post("/chat/assist", { action: "suggest_replies", partner_id: partnerId }),
        api.post("/chat/assist", { action: "summarize", partner_id: partnerId }),
      ]);
      setSuggestions(sugRes.data?.suggestions || []);
      setSummary(sumRes.data?.summary || null);
      setActionItems(sumRes.data?.action_items || []);
    } catch {
      setSuggestions([]);
    } finally {
      setAssistLoading(false);
    }
  }, []);

  const loadMessages = useCallback(
    async (partnerId, silent = false) => {
      if (!partnerId) {
        setMessages([]);
        return;
      }
      if (!silent) setLoadingMessages(true);
      try {
        const res = await api.get("/chat/messages", { params: { user_id: partnerId, limit: 100 } });
        setMessages(res.data?.messages || []);
        if (silent) {
          loadConversations(true);
        } else {
          loadAssist(partnerId);
        }
      } catch (e) {
        if (!silent) setError(e.response?.data?.error || "Impossible de charger les messages.");
      } finally {
        if (!silent) setLoadingMessages(false);
      }
    },
    [loadConversations, loadAssist]
  );

  useEffect(() => {
    loadConversations();
    loadContext();
  }, [loadConversations, loadContext]);

  useEffect(() => {
    if (selectedId) {
      stickToBottomRef.current = true;
      loadMessages(selectedId);
      setMobileShowChat(true);
    } else {
      setMessages([]);
      setSuggestions([]);
      setSummary(null);
    }
  }, [selectedId, loadMessages]);

  const scrollMessagesToBottom = useCallback((smooth = true) => {
    const el = messagesContainerRef.current;
    if (!el) return;
    el.scrollTo({
      top: el.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  }, []);

  useEffect(() => {
    if (messages.length === 0) return;
    if (stickToBottomRef.current) {
      requestAnimationFrame(() => scrollMessagesToBottom(true));
    }
  }, [messages, scrollMessagesToBottom]);

  const handleMessagesScroll = () => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distanceFromBottom < 100;
  };

  useEffect(() => {
    pollRef.current = setInterval(() => {
      if (selectedId) loadMessages(selectedId, true);
      else loadConversations(true);
    }, 5000);
    return () => clearInterval(pollRef.current);
  }, [selectedId, loadMessages, loadConversations]);

  const handleSend = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    const text = draft.trim();
    if (!text || !selectedId || sending) return;

    setSending(true);
    setError("");
    try {
      const res = await api.post("/chat/messages", {
        receiver_id: selectedId,
        content: text,
      });
      const msg = res.data?.message;
      if (msg) {
        stickToBottomRef.current = true;
        setMessages((prev) => [...prev, msg]);
      }
      setDraft("");
      loadConversations(true);
      loadAssist(selectedId);
    } catch (e) {
      setError(e.response?.data?.error || "Envoi impossible.");
    } finally {
      setSending(false);
    }
  };

  const applySuggestion = (text) => {
    setDraft(text);
  };

  const insertInvoiceRef = (inv) => {
    const ref = inv.invoice_number
      ? `facture #${inv.id} (${inv.invoice_number})`
      : `facture #${inv.id}`;
    setDraft((prev) => (prev.trim() ? `${prev.trim()} ${ref}` : ref));
  };

  const handleImproveDraft = async () => {
    if (!draft.trim() || !selectedId) return;
    setAssistLoading(true);
    try {
      const res = await api.post("/chat/assist", {
        action: "improve_draft",
        partner_id: selectedId,
        draft,
        tone: improveTone,
      });
      if (res.data?.text) setDraft(res.data.text);
    } catch (e) {
      setError(e.response?.data?.error || "Reformulation impossible.");
    } finally {
      setAssistLoading(false);
    }
  };

  const refreshCopilot = () => {
    if (selectedId) loadAssist(selectedId);
  };

  const toggleListen = async () => {
    if (isListening) {
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        setIsListening(false);
        setVoiceHint("");
      }
      return;
    }

    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setError("Dictée vocale non supportée par ce navigateur.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;
      mediaChunksRef.current = [];
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const mr = new MediaRecorder(stream, { mimeType: mime });
      mediaRecorderRef.current = mr;

      mr.ondataavailable = (e) => {
        if (e.data?.size) mediaChunksRef.current.push(e.data);
      };

      mr.onstop = async () => {
        mediaStreamRef.current?.getTracks?.().forEach((t) => t.stop());
        mediaStreamRef.current = null;
        setIsListening(false);
        const blob = new Blob(mediaChunksRef.current, { type: mr.mimeType || "audio/webm" });
        mediaChunksRef.current = [];
        if (blob.size < 80) {
          setVoiceHint("");
          return;
        }
        setVoiceHint("Transcription en cours…");
        try {
          const fd = new FormData();
          fd.append("file", blob, "audio.webm");
          const { data } = await api.post("/audio/transcribe", fd, { timeout: 120000 });
          const t = (data?.text || "").trim();
          if (t) setDraft((prev) => (prev.trim() ? `${prev.trim()} ${t}` : t));
        } catch (err) {
          setError(err.response?.data?.error || "Transcription impossible.");
        } finally {
          setVoiceHint("");
        }
      };

      mr.onerror = () => {
        setIsListening(false);
        setVoiceHint("");
        mediaStreamRef.current?.getTracks?.().forEach((t) => t.stop());
        mediaStreamRef.current = null;
      };

      mr.start(400);
      setIsListening(true);
      setVoiceHint("Parlez… recliquez 🎙 pour transcrire.");
    } catch {
      setError("Microphone refusé ou indisponible.");
      setIsListening(false);
    }
  };

  const hasMediaRecorder =
    typeof window !== "undefined" &&
    typeof MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia;

  const partnerLabel = user?.role === "comptable" ? "Superviseurs" : "Comptables";

  return (
    <div className="messenger-page">
      <header className="messenger-page__header">
        <div>
          <h1 className="messenger-page__title">
            Messagerie intelligente
            <span className="messenger-page__ai-badge">IA</span>
          </h1>
          <p className="messenger-page__subtitle">
            Copilote OpenRouter, analyse des priorités et liens factures automatiques.
          </p>
        </div>
        <button
          type="button"
          className="messenger-page__copilot-toggle"
          onClick={() => setCopilotOpen((v) => !v)}
        >
          {copilotOpen ? "Masquer copilote" : "Copilote IA"}
        </button>
      </header>

      {error && (
        <div className="messenger-page__error" role="alert">
          {error}
          <button type="button" onClick={() => setError("")} aria-label="Fermer">
            ×
          </button>
        </div>
      )}

      <div className={`messenger messenger--smart${copilotOpen ? " messenger--with-copilot" : ""}`}>
        <aside
          className={`messenger__sidebar${mobileShowChat ? " messenger__sidebar--hidden-mobile" : ""}`}
        >
          <div className="messenger__sidebar-head">
            <span className="messenger__sidebar-title">{partnerLabel}</span>
          </div>
          {loadingConversations ? (
            <p className="messenger__placeholder">Chargement…</p>
          ) : conversations.length === 0 ? (
            <p className="messenger__placeholder">
              Aucun {partnerLabel.slice(0, -1).toLowerCase()} disponible pour le moment.
            </p>
          ) : (
            <ul className="messenger__contacts">
              {conversations.map((c) => (
                <li key={c.user_id}>
                  <button
                    type="button"
                    className={`messenger__contact${selectedId === c.user_id ? " messenger__contact--active" : ""}`}
                    onClick={() => {
                      setSelectedId(c.user_id);
                      setMobileShowChat(true);
                    }}
                  >
                    <span className="messenger__avatar" aria-hidden>
                      {initials(c)}
                    </span>
                    <span className="messenger__contact-body">
                      <span className="messenger__contact-top">
                        <span className="messenger__contact-name">{displayName(c)}</span>
                        <span className="messenger__contact-time">{formatTime(c.last_message_at)}</span>
                      </span>
                      <span className="messenger__contact-preview">
                        {c.last_message
                          ? `${c.last_message_is_mine ? "Vous : " : ""}${c.last_message}`
                          : "Nouvelle conversation"}
                      </span>
                      {c.last_priority === "urgent" && (
                        <span className="messenger__contact-priority">Priorité haute</span>
                      )}
                    </span>
                    {c.unread_count > 0 && (
                      <span className="messenger__badge">{c.unread_count}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section
          className={`messenger__chat${!mobileShowChat && conversations.length ? " messenger__chat--hidden-mobile" : ""}`}
        >
          {!selectedContact ? (
            <div className="messenger__empty">
              <span className="messenger__empty-icon" aria-hidden>🤖</span>
              <p>Sélectionnez une conversation — le copilote IA vous assiste.</p>
            </div>
          ) : (
            <>
              <header className="messenger__chat-header">
                <button
                  type="button"
                  className="messenger__back"
                  onClick={() => setMobileShowChat(false)}
                  aria-label="Retour aux conversations"
                >
                  ←
                </button>
                <span className="messenger__avatar messenger__avatar--header" aria-hidden>
                  {initials(selectedContact)}
                </span>
                <div className="messenger__chat-header-info">
                  <strong>{displayName(selectedContact)}</strong>
                  <span>{ROLE_LABELS[selectedContact.role] || selectedContact.role}</span>
                </div>
                <button
                  type="button"
                  className="messenger__header-ai"
                  onClick={() => setCopilotOpen(true)}
                  title="Ouvrir le copilote"
                >
                  ✨ Copilote
                </button>
              </header>

              <div
                className="messenger__messages"
                ref={messagesContainerRef}
                onScroll={handleMessagesScroll}
              >
                {loadingMessages ? (
                  <p className="messenger__placeholder">Chargement des messages…</p>
                ) : messages.length === 0 ? (
                  <p className="messenger__placeholder messenger__placeholder--center">
                    Aucun message — utilisez une suggestion IA ou écrivez le premier !
                  </p>
                ) : (
                  messages.map((m) => (
                    <div
                      key={m.id}
                      className={`messenger__bubble-row${m.is_mine ? " messenger__bubble-row--mine" : ""}`}
                    >
                      <div
                        className={`messenger__bubble${m.is_mine ? " messenger__bubble--mine" : ""}${m.metadata?.priority === "urgent" && !m.is_mine ? " messenger__bubble--urgent" : ""}`}
                      >
                        <MessageTags metadata={m.metadata} isMine={m.is_mine} />
                        <MessageContent text={m.content} />
                        <time dateTime={m.created_at}>{formatMessageTime(m.created_at)}</time>
                      </div>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>

              {suggestions.length > 0 && (
                <div className="messenger__quick-suggestions">
                  {suggestions.slice(0, 3).map((s, i) => (
                    <button
                      key={i}
                      type="button"
                      className="messenger__quick-chip"
                      onClick={() => applySuggestion(s.text)}
                      title={s.reason}
                    >
                      {s.text.length > 55 ? `${s.text.slice(0, 55)}…` : s.text}
                    </button>
                  ))}
                </div>
              )}

              <form className="messenger__composer" onSubmit={handleSend}>
                <div className="messenger__composer-tools">
                  {hasMediaRecorder && (
                    <button
                      type="button"
                      className={`messenger__tool-btn${isListening ? " messenger__tool-btn--active" : ""}`}
                      onClick={toggleListen}
                      title={isListening ? "Arrêter et transcrire" : "Dictée vocale"}
                    >
                      🎙
                    </button>
                  )}
                  <select
                    className="messenger__tone-select"
                    value={improveTone}
                    onChange={(e) => setImproveTone(e.target.value)}
                    title="Ton de reformulation"
                  >
                    <option value="pro">Pro</option>
                    <option value="concise">Concis</option>
                    <option value="friendly">Chaleureux</option>
                  </select>
                  <button
                    type="button"
                    className="messenger__tool-btn messenger__tool-btn--ai"
                    onClick={handleImproveDraft}
                    disabled={!draft.trim() || assistLoading}
                    title="Reformuler avec OpenRouter"
                  >
                    ✨
                  </button>
                </div>
                {voiceHint && <p className="messenger__voice-hint">{voiceHint}</p>}
                <div className="messenger__composer-row">
                  <textarea
                    className="messenger__input"
                    rows={1}
                    placeholder="Écrivez ou dictez votre message…"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSend(e);
                      }
                    }}
                    disabled={sending}
                  />
                  <button
                    type="submit"
                    className="messenger__send"
                    disabled={!draft.trim() || sending}
                    aria-label="Envoyer"
                  >
                    {sending ? "…" : "➤"}
                  </button>
                </div>
              </form>
            </>
          )}
        </section>

        {copilotOpen && (
          <aside className="messenger__copilot">
            <div className="messenger__copilot-head">
              <span>✨ Copilote OpenRouter</span>
              <button type="button" onClick={refreshCopilot} disabled={assistLoading || !selectedId}>
                ↻
              </button>
            </div>

            {assistLoading && !summary ? (
              <p className="messenger__placeholder">Analyse IA…</p>
            ) : (
              <>
                {summary && (
                  <section className="messenger__copilot-block">
                    <h3>Résumé intelligent</h3>
                    <p>{summary}</p>
                    {actionItems.length > 0 && (
                      <ul className="messenger__action-items">
                        {actionItems.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    )}
                  </section>
                )}

                {suggestions.length > 0 && (
                  <section className="messenger__copilot-block">
                    <h3>Réponses suggérées</h3>
                    <div className="messenger__copilot-suggestions">
                      {suggestions.map((s, i) => (
                        <button
                          key={i}
                          type="button"
                          className="messenger__copilot-suggestion"
                          onClick={() => applySuggestion(s.text)}
                        >
                          <span>{s.text}</span>
                          <em>{s.reason}</em>
                        </button>
                      ))}
                    </div>
                  </section>
                )}

                {context?.recent_invoices?.length > 0 && (
                  <section className="messenger__copilot-block">
                    <h3>Contexte factures</h3>
                    <div className="messenger__context-cards">
                      {context.recent_invoices.slice(0, 4).map((inv) => (
                        <button
                          key={inv.id}
                          type="button"
                          className="messenger__context-card"
                          onClick={() => insertInvoiceRef(inv)}
                        >
                          <strong>#{inv.id}</strong>
                          <span>{inv.invoice_number || inv.seller_name || "Facture"}</span>
                          {inv.total_gross != null && (
                            <em>{Number(inv.total_gross).toFixed(2)} €</em>
                          )}
                        </button>
                      ))}
                    </div>
                  </section>
                )}

                {context?.alerts?.length > 0 && (
                  <section className="messenger__copilot-block">
                    <h3>Alertes en cours</h3>
                    <ul className="messenger__alert-list">
                      {context.alerts.map((a) => (
                        <li key={`${a.invoice_id}-${a.message}`}>
                          <Link to={`/supervisor/review/${a.invoice_id}`}>
                            Facture #{a.invoice_id}
                          </Link>
                          <span>{a.message}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {context?.quick_templates?.length > 0 && (
                  <section className="messenger__copilot-block">
                    <h3>Modèles rapides</h3>
                    <div className="messenger__template-chips">
                      {context.quick_templates.map((tpl, i) => (
                        <button
                          key={i}
                          type="button"
                          className="messenger__quick-chip"
                          onClick={() => applySuggestion(tpl.replace("#{id}", "#…"))}
                        >
                          {tpl.replace("#{id}", "#…").slice(0, 48)}…
                        </button>
                      ))}
                    </div>
                  </section>
                )}
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}
