import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/* ── API config ───────────────────────────────────────────────────────────── */
const API = window.location.port === "3000" ? "http://localhost:8000" : "";
const WS  = window.location.port === "3000" ? "ws://localhost:8000" : `wss://${window.location.host}`;

function apiFetch(path, options = {}) {
  const key = localStorage.getItem("phantomdev_api_key");
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (key) headers["X-API-Key"] = key;
  return fetch(`${API}${path}`, { ...options, headers });
}

const stages = ["PM", "Architect", "Engineers", "QA", "Security", "Writer", "PR"];
const stageFor = { planning: 0, architecting: 1, coding: 2, testing: 3, securing: 4, documenting: 5, pr_open: 6, approved: 6 };
const statuses = {
  pending: ["Pending", "muted"], planning: ["Planning", "blue"], architecting: ["Architecting", "blue"],
  coding: ["Coding", "green"], testing: ["Testing", "amber"], securing: ["Securing", "red"],
  documenting: ["Documenting", "blue"], pr_open: ["Ready for review", "amber"],
  approved: ["Approved", "green"], failed: ["Failed", "red"], rejected: ["Rejected", "red"],
};

function Icon({ name, size = 16 }) {
  const paths = {
    menu: "M3 6h18M3 12h18M3 18h18", plus: "M12 5v14M5 12h14", search: "m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4",
    grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z", list: "M5 6h14M5 12h14M5 18h14",
    check: "m5 12 4 4L19 6", x: "M6 6l12 12M18 6 6 18", branch: "M6 3v12a4 4 0 0 0 4 4h8M18 7l3 3-3 3",
    bot: "M12 3v3M8 10h.01M16 10h.01M7 15h10M5 7h14v12H5z", settings: "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z",
    file: "M6 3h8l4 4v14H6zM14 3v5h5", shield: "M12 3 20 7v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V7z",
    flask: "M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3M7 16h10",
    external: "M14 4h6v6M20 4l-9 9M18 13v6H5V6h6", trash: "M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3",
    copy: "M9 9h10v12H9zM5 15H4V4h11v1", arrow: "M5 12h14M13 6l6 6-6 6", download: "M12 3v12M7 10l5 5 5-5M5 21h14",
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name] || paths.grid} /></svg>;
}

function Badge({ status }) {
  const [label, tone] = statuses[status] || statuses.pending;
  return <span className={`badge ${tone}`}>{label}</span>;
}

function ago(value) {
  if (!value) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(`${value}Z`)) / 1000));
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

/* ── GitHub issue fetch hook ──────────────────────────────────────────────── */
function useGitHubIssue() {
  const [fetching, setFetching] = useState(false);
  const [fetchHint, setFetchHint] = useState("");
  const [fetchError, setFetchError] = useState(false);

  const fetchIssue = useCallback(async (repo, issueNumber) => {
    if (!repo.trim() || !issueNumber) {
      setFetchHint("Enter a repo and issue number to auto-fill.");
      setFetchError(false);
      return null;
    }
    setFetching(true);
    setFetchHint("Fetching from GitHub...");
    setFetchError(false);
    try {
      const res = await apiFetch(`/github/issue?repo=${encodeURIComponent(repo.trim())}&issue_number=${issueNumber}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
      if (data?.error) throw new Error(data.error);
      setFetchHint(`Fetched issue #${issueNumber}: "${data.title}"`);
      setFetchError(false);
      return data;
    } catch (err) {
      setFetchHint(err.message || "Could not fetch issue. Check repo and number.");
      setFetchError(true);
      return null;
    } finally {
      setFetching(false);
    }
  }, []);

  return { fetching, fetchHint, fetchError, fetchIssue };
}

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
function Sidebar({ tasks, selected, onSelect, onNew, view, setView }) {
  const [query, setQuery] = useState("");
  const filtered = tasks.filter(t =>
    (t.title || "").toLowerCase().includes(query.toLowerCase()) ||
    (t.repo || "").toLowerCase().includes(query.toLowerCase())
  );
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">P</div>
        <div><strong>PhantomDev</strong><small>Engineering platform</small></div>
      </div>
      <button className="new-task" onClick={onNew}><Icon name="plus" /> New Task</button>
      <nav>
        <div className="nav-label">Workspace</div>
        {[["overview","Overview","grid"],["active","Active Tasks","list"],["completed","Completed","check"],["failed","Failed","x"]].map(([key,label,icon]) => (
          <button key={key} className={`nav-item ${view === key ? "active" : ""}`} onClick={() => setView(key)}>
            <Icon name={icon} />{label}
            <span>{key === "active" ? tasks.filter(t => !["approved","failed","rejected"].includes(t.status)).length : ""}</span>
          </button>
        ))}
        <div className="nav-label">Repositories</div>
        <button className={`nav-item ${view === "repos" ? "active" : ""}`} onClick={() => setView("repos")}><Icon name="branch" />Repositories</button>
        <div className="nav-label">System</div>
        <button className="nav-item"><Icon name="settings" />Settings</button>
      </nav>
      <div className="task-section">
        <div className="section-head"><span>Tasks</span><span>{tasks.length}</span></div>
        <div className="search"><Icon name="search" size={14} /><input placeholder="Filter tasks" value={query} onChange={e => setQuery(e.target.value)} /></div>
        <div className="task-list">
          {filtered.map(t => (
            <button className={`task-row ${selected === t.id ? "selected" : ""}`} key={t.id} onClick={() => onSelect(t.id)}>
              <strong>{t.title || "Untitled task"}</strong>
              <small className="mono">{t.repo || "No repository"}</small>
              <div className="row"><Badge status={t.status} /><em>{ago(t.created_at)}</em></div>
            </button>
          ))}
          {!filtered.length && <p className="muted" style={{ padding: "10px 8px", fontSize: 12 }}>No tasks yet.</p>}
        </div>
      </div>
      <div className="system">
        <div className="nav-label">System status</div>
        <div className="system-row"><i className="dot online" />Database<span>Connected</span></div>
      </div>
    </aside>
  );
}

/* ── Topbar ───────────────────────────────────────────────────────────────── */
function Topbar({ task, onNew }) {
  return (
    <header className="topbar">
      <div className="crumb">
        <span className="mono">{task?.repo || "Engineering workspace"}</span>
        {task?.issue_number && <><b>/</b><span className="mono">#{task.issue_number}</span></>}
        {task && <><b>/</b><strong>{task.title}</strong></>}
      </div>
      <div className="top-actions">
        <div className="global-search"><Icon name="search" size={14} /><input placeholder="Search workspace" /></div>
        <span className="connection"><i className="dot online" /> Live</span>
        <button className="btn-quiet" onClick={onNew}><Icon name="plus" size={14} /> New task</button>
      </div>
    </header>
  );
}

/* ── Overview ─────────────────────────────────────────────────────────────── */
function Overview({ tasks, onSelect, onNew }) {
  const active = tasks.filter(t => !["approved","failed","rejected"].includes(t.status));
  const prs = tasks.filter(t => t.status === "pr_open");
  const done = tasks.filter(t => t.status === "approved");
  const failed = tasks.filter(t => ["failed","rejected"].includes(t.status));
  return (
    <main className="content">
      <div className="page-title">
        <div><h1>Engineering Workspace</h1><p>Monitor autonomous pipelines, review generated code, and ship with confidence.</p></div>
        <button className="btn-primary" onClick={onNew}><Icon name="plus" /> New task</button>
      </div>
      <div className="stats">
        <div className="stat"><span>Active tasks</span><strong className="blue">{active.length}</strong></div>
        <div className="stat"><span>Awaiting review</span><strong className="amber">{prs.length}</strong></div>
        <div className="stat"><span>Completed</span><strong className="green">{done.length}</strong></div>
        <div className="stat"><span>Failed</span><strong className="red">{failed.length}</strong></div>
      </div>
      <section className="section">
        <div className="section-title"><h2>Active runs</h2><button className="btn-quiet" onClick={onNew}>Start a pipeline <Icon name="arrow" size={14} /></button></div>
        {active.length ? (
          <div className="run-grid">{active.map(t => <RunCard key={t.id} task={t} onClick={() => onSelect(t.id)} />)}</div>
        ) : (
          <div className="empty"><strong>Your engineering workspace is empty</strong><p>Create a task and PhantomDev will plan, implement, test, and prepare a pull request.</p><button className="btn-primary" onClick={onNew}>Create task</button></div>
        )}
      </section>
      {prs.length > 0 && (
        <section className="section">
          <div className="section-title"><h2>Pull requests awaiting review</h2></div>
          <div className="run-grid">{prs.map(t => <RunCard key={t.id} task={t} onClick={() => onSelect(t.id)} />)}</div>
        </section>
      )}
    </main>
  );
}

function RunCard({ task, onClick }) {
  const idx = stageFor[task.status] ?? -1;
  return (
    <button className="run-card" onClick={onClick}>
      <div className="run-head">
        <div><strong>{task.title || "Untitled task"}</strong><small className="mono">{task.repo || "No repository"} {task.issue_number ? `· #${task.issue_number}` : ""}</small></div>
        <Badge status={task.status} />
      </div>
      <div className="run-pipeline">
        {stages.map((s, i) => <span key={s} className={i < idx ? "done" : i === idx ? "current" : ""}>{i < idx ? "✓" : i === idx ? "●" : "○"} {s}</span>)}
      </div>
      <footer><span>{task.current_agent || "Pipeline queued"}</span><em>{ago(task.updated_at || task.created_at)}</em></footer>
    </button>
  );
}

/* ── Task Workspace ───────────────────────────────────────────────────────── */
function Workspace({ task, onDelete }) {
  const [tab, setTab] = useState("activity");
  const messages = task.messages || [];
  const idx = stageFor[task.status] ?? -1;
  return (
    <main className="workspace">
      <div className="task-header">
        <div>
          <h1>{task.title || "Untitled task"}</h1>
          <div className="meta">
            <span className="mono">{task.repo || "No repository"}</span><span>·</span>
            <span className="mono">{task.base_branch || "main"}</span><span>·</span>
            <span className="mono">{task.id.slice(0, 8)}</span>
          </div>
        </div>
        <div className="task-actions">
          <Badge status={task.status} />
          {task.pr_url && <a className="btn-quiet" href={task.pr_url} target="_blank" rel="noreferrer"><Icon name="external" /> View PR</a>}
          <button className="icon-btn" onClick={onDelete}><Icon name="trash" /></button>
        </div>
      </div>
      <div className="pipeline">
        {stages.map((s, i) => (
          <div className={`stage ${i < idx || task.status === "approved" ? "done" : i === idx ? "current" : ""}`} key={s}>
            <span>{i < idx || task.status === "approved" ? "✓" : i === idx ? "●" : "○"}</span>
            <label>{s}</label>
            {i < stages.length - 1 && <i></i>}
          </div>
        ))}
      </div>
      <div className="tabs">
        {[["activity","Activity"],["details","Details"]].map(([key,label]) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>
            {label}{key === "activity" && <small>{messages.length}</small>}
          </button>
        ))}
      </div>
      <div className="panel-body">
        {tab === "activity" && (
          messages.length ? (
            <div className="activity">
              {messages.map((m, i) => (
                <article key={i}>
                  <div><header><strong>{m.agent || "System"}</strong><span>{ago(m.timestamp)}</span></header><p>{m.content}</p></div>
                </article>
              ))}
            </div>
          ) : <div className="empty"><strong>Waiting for agent activity</strong><p>Events will appear here once the pipeline starts.</p></div>
        )}
        {tab === "details" && (
          <div style={{ padding: 20 }}>
            <pre style={{ color: "var(--muted)", font: "12px/1.6 'JetBrains Mono', monospace", whiteSpace: "pre-wrap" }}>
              {JSON.stringify(task, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </main>
  );
}

/* ── New Task Modal ───────────────────────────────────────────────────────── */
function NewTask({ onClose, onCreated }) {
  const [form, setForm] = useState({ title: "", body: "", repo: "", issue_number: "", base_branch: "main" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { fetching, fetchHint, fetchError, fetchIssue } = useGitHubIssue();

  const handleFetch = async () => {
    const data = await fetchIssue(form.repo, form.issue_number);
    if (data) {
      setForm(prev => ({
        ...prev,
        title: data.title || prev.title,
        body: data.body || prev.body,
      }));
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title.trim()) { setError("Add a task title first."); return; }
    setLoading(true);
    try {
      const res = await apiFetch("/tasks", {
        method: "POST",
        body: JSON.stringify({
          title: form.title.trim(),
          body: form.body.trim(),
          repo: form.repo.trim(),
          issue_number: Number(form.issue_number) || 0,
          base_branch: form.base_branch || "main",
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
      onCreated(data.task_id);
    } catch (err) {
      setError(err.message || "Could not create task.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <form className="modal" onSubmit={submit} onMouseDown={e => e.stopPropagation()}>
        <header>
          <div><h2>New task</h2><p>Give PhantomDev a feature request or GitHub issue to implement.</p></div>
          <button type="button" className="icon-btn" onClick={onClose}><Icon name="x" /></button>
        </header>

        <div className="form-grid-3">
          <label>Repository
            <input value={form.repo} onChange={e => setForm({ ...form, repo: e.target.value })} placeholder="owner/repo-name" />
          </label>
          <label>Issue number
            <input type="number" value={form.issue_number} onChange={e => setForm({ ...form, issue_number: e.target.value })} placeholder="184" />
          </label>
          <button type="button" className="btn-primary fetch-btn" onClick={handleFetch} disabled={fetching || !form.repo || !form.issue_number}>
            {fetching ? <Icon name="settings" size={14} /> : <Icon name="download" size={14} />} Fetch
          </button>
        </div>
        <p className={`fetch-hint ${fetchError ? "error" : fetchHint.includes("Fetched") ? "success" : ""}`}>
          {fetchHint || "Enter a repo and issue number, then click Fetch to auto-fill the title and description."}
        </p>

        <label>What should PhantomDev build?
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Implement OAuth refresh-token rotation" />
        </label>
        <label>Description
          <textarea rows={6} value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} placeholder="Describe requirements, acceptance criteria, and technical context..." />
        </label>
        <label>Base branch
          <input value={form.base_branch} onChange={e => setForm({ ...form, base_branch: e.target.value })} />
        </label>

        {error && <p className="form-error">{error}</p>}
        <footer>
          <button type="button" className="btn-quiet" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={loading}>
            {loading ? "Starting..." : "Start pipeline"}<Icon name="arrow" size={14} />
          </button>
        </footer>
      </form>
    </div>
  );
}

/* ── Main App ─────────────────────────────────────────────────────────────── */
export default function App() {
  const [tasks, setTasks] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [view, setView] = useState("overview");
  const [modal, setModal] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch("/tasks");
      if (res.ok) {
        const data = await res.json();
        // FastAPI returns an array; map task_id -> id for compatibility
        setTasks(data.map(t => ({ ...t, id: t.task_id })));
      }
    } catch {/* silent */}
  }, []);

  const loadDetail = useCallback(async (id) => {
    if (!id) return;
    try {
      const res = await apiFetch(`/tasks/${id}`);
      if (res.ok) {
        const data = await res.json();
        setDetail({ ...data, id: data.task_id, messages: data.agent_messages || [] });
      }
    } catch {/* silent */}
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!selected) return;
    loadDetail(selected);
    const timer = setInterval(() => loadDetail(selected), 3000);
    return () => clearInterval(timer);
  }, [selected, loadDetail]);

  const select = (id) => { setSelected(id); setView("task"); };
  const create = (id) => { setModal(false); setSelected(id); setView("task"); refresh(); };
  const remove = async () => {
    if (!selected || !window.confirm("Delete this task?")) return;
    await apiFetch(`/tasks/${selected}`, { method: "DELETE" });
    setSelected(null); setDetail(null); setView("overview"); refresh();
  };

  const current = detail || tasks.find(t => t.id === selected);

  return (
    <div className="app">
      <Sidebar tasks={tasks} selected={selected} onSelect={select} onNew={() => setModal(true)} view={view} setView={setView} />
      <div className="main">
        <Topbar task={view === "task" ? current : null} onNew={() => setModal(true)} />
        {view === "task" && current
          ? <Workspace task={current} onDelete={remove} />
          : <Overview tasks={tasks} onSelect={select} onNew={() => setModal(true)} />}
      </div>
      {modal && <NewTask onClose={() => setModal(false)} onCreated={create} />}
    </div>
  );
}
