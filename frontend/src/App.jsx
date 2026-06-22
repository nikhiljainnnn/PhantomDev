import { useState, useEffect, useRef, useCallback } from "react";

/* ── Environment detection ───────────────────────────────────────────────── */
const isProduction = window.location.port === "" || window.location.port === "80";
const API      = isProduction ? "/api" : "http://localhost:8000";
const WS_BASE  = isProduction ? `ws://${window.location.host}` : "ws://localhost:8000";

/* ── Design tokens (Stitch PhantomDev system) ───────────────────────────── */
const C = {
  bg:          "#020817",
  sidebar:     "#060e1d",
  surface:     "#0b1323",
  surfaceLow:  "#131c2b",
  surfaceMid:  "#18202f",
  surfaceHigh: "#222a3a",
  surfaceTop:  "#2d3546",
  border:      "rgba(255,255,255,0.07)",
  borderBright:"rgba(255,255,255,0.14)",
  text:        "#dbe2f8",
  textMuted:   "#c7c4d7",
  textDim:     "#64748b",
  primary:     "#6366f1",
  primaryDim:  "#4f46e5",
  primaryGlow: "rgba(99,102,241,0.25)",
  violet:      "#a855f7",
  violetGlow:  "rgba(168,85,247,0.2)",
  emerald:     "#10b981",
  emeraldGlow: "rgba(16,185,129,0.15)",
  amber:       "#f59e0b",
  red:         "#ef4444",
  pink:        "#ec4899",
  pinkGlow:    "rgba(236,72,153,0.2)",
  gray:        "#64748b",
};

/* ── Agent definitions (fully dynamic - no hardcoding) ──────────────────── */
const AGENT_DEFS = {
  PhantomDev:      { label: "PhantomDev",   abbr: "PD", color: C.primary,  glyph: "⚡" },
  PMAgent:         { label: "PM Agent",      abbr: "PM", color: "#818cf8",  glyph: "📋" },
  ArchitectAgent:  { label: "Architect",     abbr: "AR", color: "#38bdf8",  glyph: "🏗" },
  EngineerAgent:   { label: "Engineer",      abbr: "EN", color: C.emerald,  glyph: "💻" },
  EngineerAgent_0: { label: "Engineer #1",   abbr: "E1", color: C.emerald,  glyph: "💻" },
  EngineerAgent_1: { label: "Engineer #2",   abbr: "E2", color: "#34d399",  glyph: "💻" },
  EngineerAgent_2: { label: "Engineer #3",   abbr: "E3", color: "#6ee7b7",  glyph: "💻" },
  QAAgent:         { label: "QA Agent",      abbr: "QA", color: C.amber,    glyph: "🧪" },
  SecurityAgent:   { label: "Security",      abbr: "SC", color: C.red,      glyph: "🛡" },
  WriterAgent:     { label: "Tech Writer",   abbr: "TW", color: C.violet,   glyph: "✍" },
  PRAgent:         { label: "PR Agent",      abbr: "PR", color: C.pink,     glyph: "🔀" },
  HumanProxy:      { label: "System",        abbr: "SY", color: C.gray,     glyph: "⚙" },
};

const PIPELINE_STEPS = [
  { key: "PMAgent",        label: "PM Agent",     icon: "📋" },
  { key: "ArchitectAgent", label: "Architect",    icon: "🏗" },
  { key: "EngineerAgent_0",label: "Engineer #1",  icon: "💻" },
  { key: "EngineerAgent_1",label: "Engineer #2",  icon: "💻" },
  { key: "EngineerAgent_2",label: "Engineer #3",  icon: "💻" },
  { key: "QAAgent",        label: "QA",           icon: "🧪" },
  { key: "SecurityAgent",  label: "Security",     icon: "🛡" },
  { key: "WriterAgent",    label: "Writer",       icon: "✍" },
  { key: "PRAgent",        label: "PR Agent",     icon: "🔀" },
];

const STATUS_META = {
  pending:      { label: "Pending",       color: C.gray,    bg: "rgba(100,116,139,0.15)" },
  planning:     { label: "Planning",      color: "#818cf8", bg: "rgba(129,140,248,0.15)" },
  architecting: { label: "Architecting",  color: "#38bdf8", bg: "rgba(56,189,248,0.15)"  },
  coding:       { label: "Coding",        color: C.emerald, bg: "rgba(16,185,129,0.15)"  },
  testing:      { label: "Testing",       color: C.amber,   bg: "rgba(245,158,11,0.15)"  },
  securing:     { label: "Securing",      color: C.red,     bg: "rgba(239,68,68,0.15)"   },
  documenting:  { label: "Documenting",   color: C.violet,  bg: "rgba(168,85,247,0.15)"  },
  pr_open:      { label: "PR Ready",      color: C.pink,    bg: "rgba(236,72,153,0.15)"  },
  approved:     { label: "Approved ✓",    color: C.emerald, bg: "rgba(16,185,129,0.15)"  },
  rejected:     { label: "Rejected",      color: C.red,     bg: "rgba(239,68,68,0.15)"   },
  failed:       { label: "Failed",        color: "#94a3b8", bg: "rgba(148,163,184,0.1)"  },
};

const STATUS_STEP = {
  planning: 0, architecting: 1, coding: 2, testing: 5,
  securing: 6, documenting: 7, pr_open: 8, approved: 8,
};

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.floor((Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z"))) / 1000);
  if (s < 5)   return "just now";
  if (s < 60)  return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function getAgent(name) {
  return AGENT_DEFS[name] || { label: name, abbr: (name||"?").slice(0,2).toUpperCase(), color: C.gray, glyph: "🤖" };
}

function extractFiles(messages) {
  const files = new Set();
  if (!messages) return [];
  messages.forEach(m => {
    const content = m.content || "";
    const matches = content.match(/(?:file_path|Completed|Created|Updated|Writing)[\s:]+([^\s,\n"'`]+\.[a-z]{2,6})/gi);
    if (matches) matches.forEach(match => {
      const file = match.split(/[\s:]+/).pop().replace(/[`"']/g, "");
      if (file.includes(".") && !file.startsWith("http")) files.add(file);
    });
  });
  return [...files];
}

/* ── CSS-in-JS helpers ───────────────────────────────────────────────────── */
const glass = (extra = {}) => ({
  background: "rgba(11,19,35,0.7)",
  backdropFilter: "blur(16px)",
  WebkitBackdropFilter: "blur(16px)",
  border: `1px solid ${C.border}`,
  borderRadius: 12,
  ...extra,
});

const gradBtn = {
  background: `linear-gradient(135deg, ${C.primary} 0%, ${C.violet} 100%)`,
  border: "none",
  borderRadius: 8,
  color: "#fff",
  cursor: "pointer",
  fontWeight: 600,
  padding: "10px 18px",
  fontSize: 14,
  display: "flex",
  alignItems: "center",
  gap: 6,
  transition: "opacity 0.2s, transform 0.1s",
  width: "100%",
  justifyContent: "center",
};

/* ══════════════════════════════════════════════════════════════════════════
   COMPONENT: StatusBadge
══════════════════════════════════════════════════════════════════════════ */
function StatusBadge({ status, size = "sm" }) {
  const m = STATUS_META[status] || STATUS_META.pending;
  return (
    <span style={{
      background: m.bg,
      color: m.color,
      border: `1px solid ${m.color}40`,
      borderRadius: 999,
      padding: size === "sm" ? "2px 10px" : "4px 14px",
      fontSize: size === "sm" ? 11 : 13,
      fontWeight: 600,
      letterSpacing: "0.04em",
      whiteSpace: "nowrap",
      textTransform: "uppercase",
    }}>
      {m.label}
    </span>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   COMPONENT: PipelineStepper
══════════════════════════════════════════════════════════════════════════ */
function PipelineStepper({ status, messages }) {
  const activeMessages = new Set((messages || []).map(m => m.agent));
  const activeIdx = STATUS_STEP[status] ?? -1;

  return (
    <div style={{ padding: "16px 24px 14px", overflowX: "auto", borderBottom: `1px solid ${C.border}` }}>
      <div style={{ display: "flex", alignItems: "center", minWidth: "fit-content" }}>
        {PIPELINE_STEPS.map((step, i) => {
          const def = AGENT_DEFS[step.key] || {};
          const done   = i < activeIdx || status === "pr_open" || status === "approved";
          const active = i === activeIdx;
          const spoke  = activeMessages.has(step.key) || activeMessages.has(step.key.replace(/_\d/, ""));
          const col    = done ? def.color : active ? def.color : C.surfaceTop;

          return (
            <div key={step.key} style={{ display: "flex", alignItems: "center" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
                {/* Node */}
                <div style={{
                  width: 38, height: 38,
                  borderRadius: "50%",
                  background: active ? `${def.color}25` : done ? `${def.color}18` : C.surfaceMid,
                  border: `2px solid ${col}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 16,
                  boxShadow: active ? `0 0 0 4px ${def.color}30, 0 0 16px ${def.color}50` : spoke ? `0 0 8px ${def.color}40` : "none",
                  transition: "all 0.4s ease",
                  animation: active ? "nodeGlow 2s ease-in-out infinite" : "none",
                  position: "relative",
                }}>
                  {done ? "✓" : step.icon}
                  {active && (
                    <span style={{
                      position: "absolute", top: -2, right: -2,
                      width: 10, height: 10, borderRadius: "50%",
                      background: def.color,
                      animation: "pulse 1.5s ease-in-out infinite",
                    }} />
                  )}
                </div>
                {/* Label */}
                <span style={{
                  fontSize: 10, fontWeight: active ? 700 : 500,
                  color: active ? def.color : done ? C.textMuted : C.textDim,
                  letterSpacing: "0.03em",
                  whiteSpace: "nowrap",
                  transition: "color 0.3s",
                }}>
                  {step.label}
                </span>
              </div>
              {/* Connector */}
              {i < PIPELINE_STEPS.length - 1 && (
                <div style={{
                  width: 40, height: 2, margin: "0 2px",
                  marginBottom: 22,
                  background: i < activeIdx
                    ? `linear-gradient(90deg, ${PIPELINE_STEPS[i].key && AGENT_DEFS[PIPELINE_STEPS[i].key]?.color || C.primary}, ${AGENT_DEFS[PIPELINE_STEPS[i+1].key]?.color || C.primary})`
                    : C.surfaceTop,
                  transition: "background 0.5s ease",
                  borderRadius: 2,
                }} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   COMPONENT: MetricCard
══════════════════════════════════════════════════════════════════════════ */
function MetricCard({ icon, label, value, color = C.primary, sub }) {
  return (
    <div style={{
      ...glass({ borderRadius: 10 }),
      padding: "14px 16px",
      flex: "1 1 0",
      minWidth: 100,
      display: "flex",
      flexDirection: "column",
      gap: 6,
      transition: "border-color 0.3s",
      borderColor: `${color}30`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 16 }}>{icon}</span>
        <span style={{ fontSize: 11, color: C.textDim, letterSpacing: "0.06em", textTransform: "uppercase", fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color, lineHeight: 1 }}>{value ?? "—"}</div>
      {sub && <div style={{ fontSize: 11, color: C.textDim }}>{sub}</div>}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   COMPONENT: AgentMessage
══════════════════════════════════════════════════════════════════════════ */
function AgentMessage({ msg, idx }) {
  const [expanded, setExpanded] = useState(false);
  const def = getAgent(msg.agent);
  const content = msg.content || "";
  const isLong = content.length > 400;
  const displayContent = !expanded && isLong ? content.slice(0, 400) + "…" : content;

  return (
    <div style={{
      display: "flex",
      gap: 12,
      padding: "14px 0",
      borderBottom: `1px solid ${C.border}`,
      animation: "slideIn 0.3s ease",
    }}>
      {/* Avatar */}
      <div style={{
        width: 36, height: 36, minWidth: 36,
        borderRadius: "50%",
        background: `${def.color}20`,
        border: `2px solid ${def.color}60`,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 16,
        boxShadow: `0 0 10px ${def.color}30`,
        flexShrink: 0,
      }}>
        {def.glyph}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, color: def.color, fontSize: 13 }}>{def.label}</span>
          <span style={{ fontSize: 11, color: C.textDim }}>{timeAgo(msg.timestamp)}</span>
        </div>

        {/* Content */}
        <div style={{
          background: `${def.color}08`,
          borderLeft: `3px solid ${def.color}60`,
          borderRadius: "0 8px 8px 0",
          padding: "10px 14px",
          fontSize: 13,
          lineHeight: 1.7,
          color: C.text,
          fontFamily: "'Geist Mono', 'Fira Code', 'JetBrains Mono', monospace",
          wordBreak: "break-word",
          whiteSpace: "pre-wrap",
          overflowX: "auto",
        }}>
          {displayContent}
          {isLong && (
            <button
              onClick={() => setExpanded(!expanded)}
              style={{ display: "block", marginTop: 8, background: "none", border: "none", color: def.color, cursor: "pointer", fontSize: 12, padding: 0, fontWeight: 600 }}>
              {expanded ? "▲ Show less" : "▼ Show more"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   COMPONENT: TaskCreationForm
══════════════════════════════════════════════════════════════════════════ */
function TaskCreationForm({ onCreated }) {
  const [form, setForm] = useState({ title: "", body: "", issue_number: "", repo: "", base_branch: "main" });
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.title.trim()) { setError("Title is required"); return; }
    setLoading(true); setError("");
    try {
      const res = await fetch(`${API}/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.title,
          body: form.body,
          issue_number: parseInt(form.issue_number) || 0,
          repo: form.repo,
          base_branch: form.base_branch || "main",
        }),
      });
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const data = await res.json();
      setForm({ title: "", body: "", issue_number: "", repo: "", base_branch: "main" });
      onCreated?.(data.task_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    background: C.surfaceLow,
    border: `1px solid ${C.border}`,
    borderRadius: 8,
    color: C.text,
    fontSize: 13,
    padding: "9px 12px",
    width: "100%",
    boxSizing: "border-box",
    outline: "none",
    transition: "border-color 0.2s",
    fontFamily: "Inter, sans-serif",
  };

  const fetchIssue = async () => {
    if (!form.repo || !form.issue_number) {
      setError("Provide both owner/repo and issue # to fetch from GitHub.");
      return;
    }
    setFetching(true); setError("");
    try {
      const res = await fetch(`${API}/github/issue?repo=${form.repo}&issue_number=${form.issue_number}`);
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || `Error ${res.status}`);
      }
      const data = await res.json();
      setForm(f => ({ ...f, title: data.title, body: data.body }));
    } catch (e) {
      setError(e.message);
    } finally {
      setFetching(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <input placeholder="Feature / Bug title *" value={form.title} onChange={e => set("title", e.target.value)}
        style={inputStyle} />
      <textarea placeholder="Describe the task in detail…" value={form.body} onChange={e => set("body", e.target.value)}
        rows={3} style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }} />
      <div style={{ display: "flex", gap: 8 }}>
        <input placeholder="owner/repo" value={form.repo} onChange={e => set("repo", e.target.value)}
          style={{ ...inputStyle, flex: 2 }} />
        <input placeholder="Issue #" value={form.issue_number} onChange={e => set("issue_number", e.target.value)}
          style={{ ...inputStyle, flex: 1 }} type="number" />
        <button 
          onClick={fetchIssue} 
          disabled={fetching || !form.repo || !form.issue_number}
          style={{ ...inputStyle, flex: 1, cursor: "pointer", background: C.surfaceMid, fontWeight: 600, color: C.primary, padding: "0 12px" }}>
          {fetching ? "..." : "Fetch"}
        </button>
      </div>
      <input placeholder="Base branch (default: main)" value={form.base_branch} onChange={e => set("base_branch", e.target.value)}
        style={inputStyle} />
      {error && <div style={{ color: C.red, fontSize: 12, padding: "4px 0" }}>⚠ {error}</div>}
      <button
        onClick={submit}
        disabled={loading}
        style={{ ...gradBtn, opacity: loading ? 0.7 : 1 }}>
        {loading ? "🚀 Launching…" : "🚀 Launch Pipeline"}
      </button>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   COMPONENT: TaskListItem
══════════════════════════════════════════════════════════════════════════ */
function TaskListItem({ task, selected, onClick }) {
  const m = STATUS_META[task.status] || STATUS_META.pending;
  return (
    <div
      onClick={onClick}
      style={{
        padding: "12px 14px",
        borderRadius: 10,
        cursor: "pointer",
        background: selected ? `${C.primary}15` : "transparent",
        border: `1px solid ${selected ? C.primary + "50" : "transparent"}`,
        transition: "all 0.2s",
        marginBottom: 4,
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = C.surfaceMid; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = "transparent"; }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6, marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: selected ? C.text : C.textMuted, lineHeight: 1.3, flex: 1 }}>
          {task.github_issue_title || task.title || "Untitled"}
        </span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <StatusBadge status={task.status} />
        <span style={{ fontSize: 11, color: C.textDim }}>{timeAgo(task.created_at)}</span>
      </div>
      {task.coverage > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ height: 2, background: C.surfaceTop, borderRadius: 2 }}>
            <div style={{ height: "100%", width: `${Math.min(task.coverage, 100)}%`, background: C.emerald, borderRadius: 2, transition: "width 0.5s" }} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   COMPONENT: GeneratedFiles
══════════════════════════════════════════════════════════════════════════ */
function GeneratedFiles({ files, generated_files }) {
  const backendFiles = generated_files ? Object.keys(generated_files) : [];
  const allFiles = [...new Set([...backendFiles, ...files])];
  if (!allFiles.length) return null;
  return (
    <div style={{ padding: "12px 24px", borderTop: `1px solid ${C.border}`, flexShrink: 0 }}>
      <div style={{ fontSize: 11, color: C.textDim, letterSpacing: "0.06em", textTransform: "uppercase", fontWeight: 600, marginBottom: 8 }}>
        📁 Generated Files ({allFiles.length})
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 100, overflowY: "auto" }}>
        {allFiles.map((f, i) => (
          <span key={i} style={{
            background: `${C.emerald}15`,
            border: `1px solid ${C.emerald}30`,
            color: C.emerald,
            borderRadius: 6,
            padding: "3px 10px",
            fontSize: 11,
            fontFamily: "monospace",
            cursor: "default",
            transition: "background 0.2s",
          }}>
            {f.split("/").pop()}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   COMPONENT: LiveDot
══════════════════════════════════════════════════════════════════════════ */
function LiveDot({ connected }) {
  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
      <span style={{
        width: 8, height: 8, borderRadius: "50%",
        background: connected ? C.emerald : C.gray,
        display: "inline-block",
        boxShadow: connected ? `0 0 6px ${C.emerald}` : "none",
        animation: connected ? "pulse 2s ease-in-out infinite" : "none",
      }} />
    </span>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   MAIN APP
══════════════════════════════════════════════════════════════════════════ */
export default function App() {
  const [tasks, setTasks]               = useState([]);
  const [selectedId, setSelectedId]     = useState(null);
  const [taskDetail, setTaskDetail]     = useState(null);
  const [wsConnected, setWsConnected]   = useState(false);
  const [sidebarOpen, setSidebarOpen]   = useState(true);
  const [showForm, setShowForm]         = useState(false);
  const [approving, setApproving]       = useState(false);
  const [notification, setNotification] = useState(null);
  const [isMobile, setIsMobile]         = useState(window.innerWidth < 768);

  const wsRef       = useRef(null);
  const feedRef     = useRef(null);
  const pollRef     = useRef(null);
  const listPollRef = useRef(null);

  /* ── Responsive ────────────────────────────────────────────────────────── */
  useEffect(() => {
    const onResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setSidebarOpen(false);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /* ── Notifications ─────────────────────────────────────────────────────── */
  const notify = useCallback((msg, color = C.primary) => {
    setNotification({ msg, color });
    setTimeout(() => setNotification(null), 4000);
  }, []);

  /* ── Fetch task list (polling every 3s) ───────────────────────────────── */
  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch(`${API}/tasks`);
      if (!res.ok) return;
      const data = await res.json();
      setTasks(data);
    } catch (e) {/* silent */}
  }, []);

  useEffect(() => {
    fetchTasks();
    listPollRef.current = setInterval(fetchTasks, 3000);
    return () => clearInterval(listPollRef.current);
  }, [fetchTasks]);

  /* ── Fetch single task detail ──────────────────────────────────────────── */
  const fetchDetail = useCallback(async (id) => {
    if (!id) return;
    try {
      const res = await fetch(`${API}/tasks/${id}`);
      if (!res.ok) return;
      const data = await res.json();
      setTaskDetail(data);
    } catch (e) {/* silent */}
  }, []);

  /* ── WebSocket connection ──────────────────────────────────────────────── */
  const connectWS = useCallback((id) => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    if (!id) return;

    const url = `${WS_BASE}/ws/${id}`;
    const ws  = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      clearInterval(pollRef.current);
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "ping") return;
        setTaskDetail(prev => {
          if (!prev) return prev;
          const prevMsgs = prev.agent_messages || [];
          const alreadyHas = prevMsgs.some(m => m.timestamp === msg.timestamp && m.agent === msg.agent);
          return {
            ...prev,
            status: msg.status || prev.status,
            metrics: msg.metrics || prev.metrics,
            agent_messages: alreadyHas ? prevMsgs : [...prevMsgs, msg],
          };
        });
        // Auto-scroll
        setTimeout(() => {
          if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
        }, 50);
      } catch (err) {/* ignore */}
    };

    ws.onclose = () => {
      setWsConnected(false);
      // Fallback: poll every 2s when WS disconnects
      clearInterval(pollRef.current);
      pollRef.current = setInterval(() => fetchDetail(id), 2000);
    };

    ws.onerror = () => {
      setWsConnected(false);
      clearInterval(pollRef.current);
      pollRef.current = setInterval(() => fetchDetail(id), 2000);
    };
  }, [fetchDetail]);

  useEffect(() => {
    if (selectedId) {
      fetchDetail(selectedId);
      connectWS(selectedId);
    }
    return () => {
      clearInterval(pollRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [selectedId, fetchDetail, connectWS]);

  /* ── Auto-select first task ───────────────────────────────────────────── */
  useEffect(() => {
    if (!selectedId && tasks.length > 0) {
      setSelectedId(tasks[0].task_id);
    }
  }, [tasks, selectedId]);

  /* ── Auto-scroll feed when new messages arrive ────────────────────────── */
  useEffect(() => {
    if (feedRef.current) {
      const el = feedRef.current;
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
      if (atBottom) el.scrollTop = el.scrollHeight;
    }
  }, [taskDetail?.agent_messages?.length]);

  /* ── Task actions ──────────────────────────────────────────────────────── */
  const handleTaskCreated = async (id) => {
    notify("🚀 Pipeline launched!", C.emerald);
    setShowForm(false);
    await fetchTasks();
    setSelectedId(id);
    if (isMobile) setSidebarOpen(false);
  };

  const handleApprove = async () => {
    if (!selectedId || approving) return;
    setApproving(true);
    try {
      const res = await fetch(`${API}/tasks/${selectedId}/approve`, { method: "POST" });
      if (res.ok) { notify("✅ PR Approved!", C.emerald); fetchDetail(selectedId); }
      else notify("Failed to approve", C.red);
    } finally { setApproving(false); }
  };

  const handleReject = async () => {
    if (!selectedId) return;
    try {
      const res = await fetch(`${API}/tasks/${selectedId}/reject`, { method: "POST" });
      if (res.ok) { notify("❌ Task Rejected", C.red); fetchDetail(selectedId); }
    } catch {}
  };

  const handleDelete = async () => {
    if (!selectedId || !confirm("Delete this task?")) return;
    try {
      await fetch(`${API}/tasks/${selectedId}`, { method: "DELETE" });
      notify("🗑 Task deleted", C.gray);
      setSelectedId(null);
      setTaskDetail(null);
      fetchTasks();
    } catch {}
  };

  /* ── Derived data ──────────────────────────────────────────────────────── */
  const detail    = taskDetail;
  const status    = detail?.status || "pending";
  const metrics   = detail?.metrics || {};
  const messages  = detail?.agent_messages || [];
  const files     = extractFiles(messages);
  const sm        = STATUS_META[status] || STATUS_META.pending;
  const isActive  = ["planning","architecting","coding","testing","securing","documenting"].includes(status);
  const subtasksDone  = detail?.subtasks?.filter(s => s.status === "done").length ?? 0;
  const subtasksTotal = detail?.subtasks?.length ?? 0;

  /* ── Styles ────────────────────────────────────────────────────────────── */
  const sidebarW = sidebarOpen ? (isMobile ? "100%" : 280) : 0;

  return (
    <div id="app-root" style={{
      display: "flex",
      height: "100vh",
      width: "100vw",
      background: C.bg,
      color: C.text,
      fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
      overflow: "hidden",
      position: "relative",
    }}>
      {/* ── Inject animations ── */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #2d3546; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: #464554; }
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(1.3); }
        }
        @keyframes nodeGlow {
          0%, 100% { box-shadow: 0 0 0 4px rgba(99,102,241,0.2), 0 0 16px rgba(99,102,241,0.4); }
          50% { box-shadow: 0 0 0 8px rgba(99,102,241,0.1), 0 0 24px rgba(99,102,241,0.6); }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        input:focus, textarea:focus { border-color: ${C.primary} !important; outline: none; }
        input::placeholder, textarea::placeholder { color: ${C.textDim}; }
        button:hover { filter: brightness(1.1); }
        button:active { transform: scale(0.98); }
      `}</style>

      {/* ── Notification toast ── */}
      {notification && (
        <div style={{
          position: "fixed", top: 20, right: 20, zIndex: 9999,
          ...glass({ borderRadius: 10, borderColor: notification.color + "40" }),
          padding: "12px 20px",
          color: notification.color,
          fontSize: 14,
          fontWeight: 600,
          animation: "slideIn 0.3s ease",
          boxShadow: `0 4px 24px ${notification.color}30`,
        }}>
          {notification.msg}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          SIDEBAR
      ══════════════════════════════════════════════════════════════════ */}
      <div id="sidebar" style={{
        width: sidebarW,
        minWidth: sidebarOpen ? (isMobile ? "100%" : 280) : 0,
        maxWidth: isMobile ? "100%" : 280,
        height: "100vh",
        background: C.sidebar,
        borderRight: sidebarOpen ? `1px solid ${C.border}` : "none",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        transition: "width 0.3s ease, min-width 0.3s ease",
        flexShrink: 0,
        zIndex: isMobile ? 200 : 1,
        position: isMobile ? "absolute" : "relative",
      }}>
        {/* Sidebar Header */}
        <div style={{
          padding: "20px 16px 14px",
          borderBottom: `1px solid ${C.border}`,
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{
                width: 38, height: 38, borderRadius: 10,
                background: `linear-gradient(135deg, ${C.primary}, ${C.violet})`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 20,
                boxShadow: `0 0 12px ${C.primaryGlow}`,
              }}>👻</div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>PhantomDev</div>
                <div style={{ fontSize: 10, color: C.textDim, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  Autonomous Engineer
                </div>
              </div>
            </div>
            {isMobile && (
              <button onClick={() => setSidebarOpen(false)} style={{ background: "none", border: "none", color: C.textDim, fontSize: 20, cursor: "pointer" }}>✕</button>
            )}
          </div>

          {/* Status indicator */}
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "7px 12px",
            background: C.surfaceMid,
            borderRadius: 8,
            border: `1px solid ${C.border}`,
            marginBottom: 12,
          }}>
            <LiveDot connected={wsConnected} />
            <span style={{ fontSize: 12, color: wsConnected ? C.emerald : C.textDim, fontWeight: 500 }}>
              {wsConnected ? "Live" : "Polling"}
            </span>
            <span style={{ fontSize: 11, color: C.textDim, marginLeft: "auto" }}>
              {tasks.length} task{tasks.length !== 1 ? "s" : ""}
            </span>
          </div>

          {/* New Task toggle button */}
          <button
            id="new-task-btn"
            onClick={() => setShowForm(!showForm)}
            style={{
              ...gradBtn,
              boxShadow: `0 4px 16px ${C.primaryGlow}`,
            }}>
            {showForm ? "✕ Cancel" : "+ New Task"}
          </button>
        </div>

        {/* Task creation form */}
        {showForm && (
          <div style={{
            padding: "16px",
            borderBottom: `1px solid ${C.border}`,
            flexShrink: 0,
            animation: "slideIn 0.2s ease",
          }}>
            <TaskCreationForm onCreated={handleTaskCreated} />
          </div>
        )}

        {/* Task list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px 8px" }}>
          {tasks.length === 0 ? (
            <div style={{ textAlign: "center", color: C.textDim, fontSize: 13, padding: "40px 16px" }}>
              <div style={{ fontSize: 32, marginBottom: 12 }}>👻</div>
              <div>No tasks yet.</div>
              <div style={{ marginTop: 6, fontSize: 12 }}>Create your first task above.</div>
            </div>
          ) : (
            tasks.map(t => (
              <TaskListItem
                key={t.task_id}
                task={t}
                selected={t.task_id === selectedId}
                onClick={() => {
                  setSelectedId(t.task_id);
                  if (isMobile) setSidebarOpen(false);
                }}
              />
            ))
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: "12px 16px",
          borderTop: `1px solid ${C.border}`,
          flexShrink: 0,
          fontSize: 11,
          color: C.textDim,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}>
          <span>Ollama · AutoGen · ChromaDB</span>
          <span style={{
            background: `${C.primary}20`,
            color: C.primary,
            border: `1px solid ${C.primary}30`,
            borderRadius: 4,
            padding: "2px 6px",
            fontWeight: 600,
            fontSize: 10,
          }}>v2</span>
        </div>
      </div>

      {/* Mobile overlay */}
      {isMobile && sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
            zIndex: 199, animation: "fadeIn 0.2s ease",
          }}
        />
      )}

      {/* ══════════════════════════════════════════════════════════════════
          MAIN CONTENT
      ══════════════════════════════════════════════════════════════════ */}
      <div id="main-content" style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>

        {/* Top Navbar */}
        <div id="navbar" style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 20px",
          borderBottom: `1px solid ${C.border}`,
          background: C.sidebar,
          flexShrink: 0,
          flexWrap: "wrap",
        }}>
          {/* Hamburger */}
          <button
            id="sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{
              background: C.surfaceMid,
              border: `1px solid ${C.border}`,
              borderRadius: 8,
              color: C.textMuted,
              cursor: "pointer",
              padding: "7px 10px",
              fontSize: 16,
              flexShrink: 0,
            }}>
            {sidebarOpen && !isMobile ? "◀" : "☰"}
          </button>

          {/* Task info */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {detail ? (
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, color: C.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {detail.github_issue_title || detail.title || "Untitled Task"}
                </div>
                <div style={{ fontSize: 11, color: C.textDim, fontFamily: "monospace", marginTop: 2 }}>
                  #{selectedId?.slice(0, 8)}
                  {detail.github_issue_number ? ` · Issue #${detail.github_issue_number}` : ""}
                  {detail.target_repo ? ` · ${detail.target_repo}` : ""}
                </div>
              </div>
            ) : (
              <div style={{ color: C.textDim, fontSize: 14 }}>
                {tasks.length ? "Select a task" : "Create your first task →"}
              </div>
            )}
          </div>

          {/* Status + actions */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            {detail && <StatusBadge status={status} size="lg" />}
            {isActive && (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <LiveDot connected={true} />
                <span style={{ fontSize: 12, color: C.emerald, fontWeight: 600 }}>Running</span>
              </div>
            )}
            {status === "pr_open" && (
              <>
                <button
                  id="approve-btn"
                  onClick={handleApprove}
                  disabled={approving}
                  style={{
                    background: `${C.emerald}20`,
                    border: `1px solid ${C.emerald}50`,
                    borderRadius: 8,
                    color: C.emerald,
                    cursor: "pointer",
                    padding: "7px 14px",
                    fontSize: 13,
                    fontWeight: 600,
                  }}>
                  {approving ? "⏳" : "✅ Approve PR"}
                </button>
                <button
                  id="reject-btn"
                  onClick={handleReject}
                  style={{
                    background: `${C.red}15`,
                    border: `1px solid ${C.red}40`,
                    borderRadius: 8,
                    color: C.red,
                    cursor: "pointer",
                    padding: "7px 14px",
                    fontSize: 13,
                    fontWeight: 600,
                  }}>
                  ✕ Reject
                </button>
              </>
            )}
            {detail?.pr_url && (
              <a href={detail.pr_url} target="_blank" rel="noreferrer"
                style={{
                  background: `${C.violet}20`,
                  border: `1px solid ${C.violet}40`,
                  borderRadius: 8,
                  color: C.violet,
                  padding: "7px 14px",
                  fontSize: 13,
                  fontWeight: 600,
                  textDecoration: "none",
                }}>
                🔀 View PR
              </a>
            )}
            {detail && (
              <button
                id="delete-btn"
                onClick={handleDelete}
                style={{
                  background: "transparent",
                  border: `1px solid ${C.border}`,
                  borderRadius: 8,
                  color: C.textDim,
                  cursor: "pointer",
                  padding: "7px 10px",
                  fontSize: 13,
                }}>
                🗑
              </button>
            )}
          </div>
        </div>

        {!detail ? (
          /* Empty state */
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, color: C.textDim }}>
            <div style={{ fontSize: 64, animation: "pulse 3s ease-in-out infinite" }}>👻</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: C.textMuted }}>PhantomDev</div>
            <div style={{ fontSize: 14, maxWidth: 300, textAlign: "center", lineHeight: 1.7 }}>
              Autonomous AI engineering pipeline. Create a task to watch the agents work in real-time.
            </div>
            <button
              onClick={() => { setSidebarOpen(true); setShowForm(true); }}
              style={{ ...gradBtn, width: "auto", padding: "12px 28px", boxShadow: `0 4px 20px ${C.primaryGlow}` }}>
              + Create First Task
            </button>
          </div>
        ) : (
          <>
            {/* Pipeline Stepper */}
            <PipelineStepper status={status} messages={messages} />

            {/* Metrics Row */}
            <div id="metrics-row" style={{
              display: "flex",
              gap: 10,
              padding: "14px 20px",
              flexShrink: 0,
              overflowX: "auto",
              borderBottom: `1px solid ${C.border}`,
            }}>
              <MetricCard icon="📋" label="Subtasks"
                value={`${subtasksDone}/${subtasksTotal}`}
                color={C.primary}
                sub={subtasksTotal > 0 ? `${Math.round(subtasksDone/subtasksTotal*100)}% done` : "none yet"} />
              <MetricCard icon="🧪" label="Coverage"
                value={`${(metrics.coverage_pct || 0).toFixed(0)}%`}
                color={metrics.coverage_pct > 60 ? C.emerald : C.amber}
                sub="test coverage" />
              <MetricCard icon="✅" label="Tests"
                value={`${(metrics.test_pass_rate || 0).toFixed(0)}%`}
                color={metrics.test_pass_rate > 80 ? C.emerald : C.amber}
                sub="pass rate" />
              <MetricCard icon="🛡" label="Sec HIGH"
                value={metrics.security_high_count ?? 0}
                color={metrics.security_high_count > 0 ? C.red : C.emerald}
                sub="critical issues" />
              <MetricCard icon="📁" label="Files"
                value={detail.files_generated ?? files.length}
                color={C.violet}
                sub="generated" />
              <MetricCard icon="💬" label="Messages"
                value={messages.length}
                color={C.primary}
                sub="agent turns" />
            </div>

            {/* Agent Message Feed */}
            <div
              id="agent-feed"
              ref={feedRef}
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "4px 20px 4px",
              }}>
              {messages.length === 0 ? (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 12, color: C.textDim }}>
                  <div style={{ fontSize: 40, animation: "pulse 2s ease-in-out infinite" }}>⚙️</div>
                  <div style={{ fontWeight: 600, fontSize: 14, color: C.textMuted }}>
                    {isActive ? "Agents initialising…" : "Waiting for agents…"}
                  </div>
                  <div style={{ fontSize: 13, textAlign: "center" }}>
                    {wsConnected ? "Connected via WebSocket · Messages appear in real-time" : "Polling backend every 2s…"}
                  </div>
                  {isActive && (
                    <div style={{
                      display: "flex", gap: 6, marginTop: 8,
                    }}>
                      {[0,1,2].map(i => (
                        <div key={i} style={{
                          width: 8, height: 8, borderRadius: "50%",
                          background: C.primary,
                          animation: `pulse 1.4s ease-in-out ${i*0.2}s infinite`,
                        }} />
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                messages.map((msg, i) => (
                  <AgentMessage key={`${msg.agent}-${msg.timestamp}-${i}`} msg={msg} idx={i} />
                ))
              )}
            </div>

            {/* Generated Files Strip */}
            <GeneratedFiles files={files} generated_files={detail.generated_files} />

            {/* Error display */}
            {detail.errors?.length > 0 && (
              <div style={{
                padding: "10px 20px",
                borderTop: `1px solid ${C.red}30`,
                background: `${C.red}08`,
                flexShrink: 0,
              }}>
                <div style={{ fontSize: 12, color: C.red, fontWeight: 600, marginBottom: 4 }}>⚠ Errors</div>
                {detail.errors.map((e, i) => (
                  <div key={i} style={{ fontSize: 12, color: C.red, opacity: 0.8, fontFamily: "monospace" }}>{e}</div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}