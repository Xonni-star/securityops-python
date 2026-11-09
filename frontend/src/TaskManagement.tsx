import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  createTask,
  createTaskComment,
  getTask,
  getTaskAssignees,
  getTaskLocations,
  getTasks,
  updateTask,
} from "./api";
import type {
  AuthUser,
  TaskAssignee,
  TaskDetail,
  TaskItem,
  TaskLocations,
  TaskPriority,
  TaskStatus,
} from "./types";

const pageSize = 25;

const statusNames: Record<TaskStatus, string> = {
  open: "Offen",
  in_progress: "In Bearbeitung",
  blocked: "Blockiert",
  completed: "Erledigt",
  cancelled: "Abgebrochen",
};

const priorityNames: Record<TaskPriority, string> = {
  low: "Niedrig",
  normal: "Normal",
  high: "Hoch",
  urgent: "Dringend",
};

const historyNames: Record<string, string> = {
  created: "Aufgabe erstellt",
  updated: "Aufgabe geändert",
  assigned: "Verantwortung geändert",
  completed: "Aufgabe abgeschlossen",
  comment_added: "Kommentar hinzugefügt",
};

const historyFieldNames: Record<string, string> = {
  title: "Titel",
  description: "Beschreibung",
  assigned_to_id: "Verantwortlichkeit",
  customer_id: "Kundenzuordnung",
  object_id: "Objektzuordnung",
  due_at: "Fälligkeit",
  priority: "Priorität",
  status: "Status",
  completion_evidence: "Erledigungsnachweis",
};

function historyDetails(changes: Record<string, unknown>) {
  const updated = changes.after;
  if (typeof updated === "object" && updated !== null) {
    const fields = Object.keys(updated);
    return fields.map((field) => historyFieldNames[field] ?? field).join(", ");
  }
  if (typeof changes.title === "string") return `Titel: ${changes.title}`;
  if (changes.assignee_id) return "Verantwortlichkeit geändert";
  return "";
}

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("de-DE") : "Keine Fälligkeit";
}

function localDateTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export default function TaskManagement({ user }: { user: AuthUser }) {
  const canCreate = user.permissions.includes("tasks.create");
  const canAssign = user.permissions.includes("tasks.assign");
  const canEdit = user.permissions.some((permission) =>
    ["tasks.update_own", "tasks.manage", "tasks.manage_all"].includes(permission),
  );
  const canSeeAll = user.permissions.some((permission) =>
    ["tasks.read_all", "tasks.manage_all"].includes(permission),
  );
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<TaskDetail | null>(null);
  const [locations, setLocations] = useState<TaskLocations>({ customers: [], objects: [] });
  const [assignees, setAssignees] = useState<TaskAssignee[]>([]);
  const [detailAssignees, setDetailAssignees] = useState<TaskAssignee[]>([]);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "">("");
  const [overdue, setOverdue] = useState(false);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedCustomerId, setSelectedCustomerId] = useState("");
  const [selectedObjectId, setSelectedObjectId] = useState("");
  const [selectedAssigneeId, setSelectedAssigneeId] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<TaskStatus>("open");
  const [completionEvidence, setCompletionEvidence] = useState("");
  const [commentError, setCommentError] = useState("");
  const scopedObjects = useMemo(
    () => locations.objects.filter((item) =>
      !selectedCustomerId || item.customer_id === selectedCustomerId,
    ),
    [locations.objects, selectedCustomerId],
  );

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const page = await getTasks({
        q: search.trim() || undefined,
        status: statusFilter,
        overdue,
        limit: pageSize,
        offset,
      });
      setTasks(page.items);
      setTotal(page.total);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Aufgaben konnten nicht geladen werden."));
    } finally {
      setLoading(false);
    }
  }, [offset, overdue, search, statusFilter]);

  const loadDetail = useCallback(async (taskId: string) => {
    setError("");
    try {
      const task = await getTask(taskId);
      setDetail(task);
      setSelectedStatus(task.status);
      setSelectedAssigneeId(task.assigned_to_id);
      setCompletionEvidence(task.completion_evidence ?? "");
    } catch (reason) {
      setError(messageFrom(reason, "Aufgabe konnte nicht geladen werden."));
    }
  }, []);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    if (!canCreate) return;
    getTaskLocations()
      .then(setLocations)
      .catch((reason: unknown) => setError(messageFrom(reason, "Zuordnungen konnten nicht geladen werden.")));
  }, [canCreate]);

  useEffect(() => {
    if (!canAssign) return;
    getTaskAssignees(selectedObjectId || undefined)
      .then(setAssignees)
      .catch((reason: unknown) => setError(messageFrom(reason, "Verantwortliche konnten nicht geladen werden.")));
  }, [canAssign, selectedObjectId]);

  useEffect(() => {
    if (!canAssign || !detail) return;
    getTaskAssignees(detail.object_id ?? undefined)
      .then(setDetailAssignees)
      .catch((reason: unknown) => setError(messageFrom(reason, "Verantwortliche konnten nicht geladen werden.")));
  }, [canAssign, detail?.id, detail?.object_id]);

  async function submitTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const objectId = String(data.get("object_id") ?? "");
    const object = locations.objects.find((item) => item.id === objectId);
    const dueValue = String(data.get("due_at") ?? "");
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const task = await createTask({
        title: String(data.get("title") ?? "").trim(),
        description: String(data.get("description") ?? "").trim() || undefined,
        priority: String(data.get("priority") ?? "normal") as TaskPriority,
        due_at: dueValue ? new Date(dueValue).toISOString() : undefined,
        assigned_to_id: canAssign ? String(data.get("assigned_to_id") ?? "") || undefined : undefined,
        customer_id: object?.customer_id
          ?? (String(data.get("customer_id") ?? "") || undefined),
        object_id: objectId || undefined,
      });
      form.reset();
      setSelectedCustomerId("");
      setSelectedObjectId("");
      await Promise.all([loadTasks(), loadDetail(task.id)]);
      setNotice("Aufgabe wurde angelegt.");
    } catch (reason) {
      setError(messageFrom(reason, "Aufgabe konnte nicht angelegt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const data = new FormData(event.currentTarget);
    const title = String(data.get("title") ?? "").trim();
    const description = String(data.get("description") ?? "").trim() || null;
    const dueValue = String(data.get("due_at") ?? "");
    const dueAt = dueValue ? new Date(dueValue).toISOString() : null;
    const priority = String(data.get("priority") ?? "normal") as TaskPriority;
    const completionEvidence = String(data.get("completion_evidence") ?? "").trim();
    const assignedToId = canAssign ? String(data.get("assigned_to_id") ?? "") : "";
    if (
      title === detail.title
      && description === detail.description
      && (dueAt ? new Date(dueAt).getTime() : null)
        === (detail.due_at ? new Date(detail.due_at).getTime() : null)
      && priority === detail.priority
      && selectedStatus === detail.status
      && (selectedStatus !== "completed" || completionEvidence === detail.completion_evidence)
      && (!canAssign || assignedToId === detail.assigned_to_id)
    ) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await updateTask(detail.id, {
        title,
        description,
        due_at: dueAt,
        priority,
        status: selectedStatus,
        ...(selectedStatus === "completed" ? { completion_evidence: completionEvidence } : {}),
        ...(canAssign ? { assigned_to_id: assignedToId } : {}),
      });
      await Promise.all([loadTasks(), loadDetail(detail.id)]);
      setNotice(selectedStatus === "completed"
        ? "Aufgabe wurde mit Erledigungsnachweis abgeschlossen."
        : "Aufgabe wurde gespeichert.");
    } catch (reason) {
      setError(messageFrom(reason, "Aufgabe konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const body = String(data.get("body") ?? "").trim();
    setBusy(true);
    setCommentError("");
    try {
      await createTaskComment(detail.id, body);
      form.reset();
      await loadDetail(detail.id);
    } catch (reason) {
      setCommentError(messageFrom(reason, "Kommentar konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="task-module">
      <div className="panel-heading">
        <div><p className="eyebrow">ARBEITSORGANISATION</p><h2>Aufgaben</h2></div>
        <span className="result-count">{total} Aufgaben</span>
      </div>
      {error && <p className="alert" role="alert">{error}</p>}
      {notice && <p className="success-message" role="status">{notice}</p>}

      <section className="panel task-list-panel" aria-label="Aufgabenliste">
        <div className="task-filters">
          <label className="search-field">
            <span className="sr-only">Aufgaben suchen</span>
            <span aria-hidden="true">⌕</span>
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.currentTarget.value);
                setOffset(0);
              }}
              placeholder="Aufgaben suchen"
            />
          </label>
          <label>Bearbeitungsstatus
            <select value={statusFilter} onChange={(event) => {
              setStatusFilter(event.currentTarget.value as TaskStatus | "");
              setOffset(0);
            }}>
              <option value="">Alle Status</option>
              {Object.entries(statusNames).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>,
              )}
            </select>
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={overdue} onChange={(event) => {
              setOverdue(event.currentTarget.checked);
              setOffset(0);
            }} />
            Nur überfällige
          </label>
        </div>
        {loading ? <p className="muted" role="status">Aufgaben werden geladen …</p> : tasks.length === 0
          ? <p className="empty">Keine Aufgaben gefunden.</p>
          : <ul className="task-list">
            {tasks.map((task) => (
              <li key={task.id} className={detail?.id === task.id ? "task-card selected" : "task-card"}>
                <button className="task-open" onClick={() => void loadDetail(task.id)}>
                  <span className="task-title">{task.title}</span>
                  <span className="task-meta">
                    {statusNames[task.status]} · {priorityNames[task.priority]} · {task.assigned_to_name}
                  </span>
                  <span className="task-meta">
                    {task.object_name ?? task.customer_name ?? "Ohne Zuordnung"} · {formatDate(task.due_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>}
        {!loading && total > pageSize && <div className="pagination">
          <span>{offset + 1}–{Math.min(offset + pageSize, total)} von {total}</span>
          <div>
            <button className="secondary-button" disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}>Zurück</button>
            <button className="secondary-button" disabled={offset + pageSize >= total}
              onClick={() => setOffset(offset + pageSize)}>Weiter</button>
          </div>
        </div>}
      </section>

      <div className="task-columns">
        {canCreate && <section className="panel form-panel task-form-panel">
          <h3>Aufgabe anlegen</h3>
          <form onSubmit={submitTask} aria-label="Aufgabe anlegen">
            <label>Titel<input name="title" required maxLength={200} /></label>
            <label>Beschreibung<textarea name="description" maxLength={10000} /></label>
            <label>Kunde
              <select name="customer_id" value={selectedCustomerId} onChange={(event) => {
                setSelectedCustomerId(event.currentTarget.value);
                setSelectedObjectId("");
              }}>
                <option value="">Keine Kundenzuordnung</option>
                {locations.customers.map((customer) =>
                  <option key={customer.id} value={customer.id}>{customer.company_name}</option>,
                )}
              </select>
            </label>
            <label>Objekt
              <select name="object_id" value={selectedObjectId} onChange={(event) => {
                const objectId = event.currentTarget.value;
                setSelectedObjectId(objectId);
                const object = locations.objects.find((item) => item.id === objectId);
                setSelectedCustomerId(object?.customer_id ?? selectedCustomerId);
              }}>
                <option value="">Keine Objektzuordnung</option>
                {scopedObjects.map((object) =>
                  <option key={object.id} value={object.id}>{object.name} · {object.customer_name}</option>,
                )}
              </select>
            </label>
            {canAssign && <label>Verantwortlich
              <select name="assigned_to_id" defaultValue={user.id}>
                {assignees.map((assignee) =>
                  <option key={assignee.id} value={assignee.id}>{assignee.full_name}</option>,
                )}
              </select>
            </label>}
            <label>Fällig am<input name="due_at" type="datetime-local" /></label>
            <label>Priorität
              <select name="priority" defaultValue="normal">
                {Object.entries(priorityNames).map(([value, name]) =>
                  <option key={value} value={value}>{name}</option>,
                )}
              </select>
            </label>
            <button disabled={busy}>Aufgabe speichern</button>
          </form>
        </section>}

        {detail ? <section className="panel task-detail" aria-labelledby="task-detail-title">
          <div className="panel-heading">
            <div><p className="eyebrow">AUFGABENDETAIL</p><h3 id="task-detail-title">{detail.title}</h3></div>
            <button className="text-button" onClick={() => setDetail(null)}>Schließen</button>
          </div>
          <p>{detail.description || <span className="muted">Keine Beschreibung hinterlegt.</span>}</p>
          <dl className="task-facts">
            <div><dt>Verantwortlich</dt><dd>{detail.assigned_to_name}</dd></div>
            <div><dt>Erstellt von</dt><dd>{detail.created_by_name ?? "Unbekannt"}</dd></div>
            <div><dt>Fälligkeit</dt><dd>{formatDate(detail.due_at)}</dd></div>
            <div><dt>Zuordnung</dt><dd>{detail.object_name ?? detail.customer_name ?? "Keine Zuordnung"}</dd></div>
            <div><dt>Priorität</dt><dd>{priorityNames[detail.priority]}</dd></div>
          </dl>
          {canEdit && <form className="task-status-form" onSubmit={submitUpdate}>
            <label>Titel<input name="title" defaultValue={detail.title} required maxLength={200} /></label>
            <label>Beschreibung<textarea name="description" defaultValue={detail.description ?? ""} maxLength={10000} /></label>
            <label>Fälligkeit<input name="due_at" type="datetime-local" defaultValue={localDateTime(detail.due_at)} /></label>
            <label>Priorität
              <select name="priority" defaultValue={detail.priority}>
                {Object.entries(priorityNames).map(([value, name]) =>
                  <option key={value} value={value}>{name}</option>,
                )}
              </select>
            </label>
            <label>Status
              <select value={selectedStatus} onChange={(event) =>
                setSelectedStatus(event.currentTarget.value as TaskStatus)
              }>
                {Object.entries(statusNames).map(([value, name]) =>
                  <option key={value} value={value}>{name}</option>,
                )}
              </select>
            </label>
            {canAssign && <label>Verantwortlich
              <select
                name="assigned_to_id"
                value={selectedAssigneeId || detail.assigned_to_id}
                onChange={(event) => setSelectedAssigneeId(event.currentTarget.value)}
              >
                {!detailAssignees.some((assignee) => assignee.id === detail.assigned_to_id)
                  && <option value={detail.assigned_to_id}>{detail.assigned_to_name}</option>}
                {detailAssignees.map((assignee) =>
                  <option key={assignee.id} value={assignee.id}>{assignee.full_name}</option>,
                )}
              </select>
            </label>}
            {selectedStatus === "completed" && <label>Erledigungsnachweis
              <textarea
                name="completion_evidence"
                required
                value={completionEvidence}
                onChange={(event) => setCompletionEvidence(event.currentTarget.value)}
                maxLength={10000}
              />
            </label>}
            <button className="primary-button" disabled={busy}>Änderungen speichern</button>
          </form>}
          {detail.completion_evidence && <p className="task-proof"><strong>Erledigungsnachweis:</strong> {detail.completion_evidence}</p>}

          <section className="task-subsection">
            <h4>Kommentare</h4>
            {detail.comments.length === 0 ? <p className="muted">Noch keine Kommentare.</p>
              : <ul className="task-activity">
                {detail.comments.map((comment) => (
                  <li key={comment.id}><strong>{comment.author_name ?? "Unbekannt"}</strong>
                    <small>{formatDate(comment.created_at)}</small><p>{comment.body}</p>
                  </li>
                ))}
              </ul>}
            {canEdit && <form className="task-comment-form" onSubmit={submitComment}>
              <label>Kommentar hinzufügen<textarea name="body" required maxLength={5000} /></label>
              {commentError && <p className="alert" role="alert">{commentError}</p>}
              <button className="secondary-button" disabled={busy}>Kommentar speichern</button>
            </form>}
          </section>

          <section className="task-subsection">
            <h4>Verlauf</h4>
            {detail.history.length === 0 ? <p className="muted">Noch keine Verlaufseinträge.</p>
              : <ul className="task-activity">
                {detail.history.map((entry) => (
                  <li key={entry.id}>
                    <strong>{historyNames[entry.action] ?? "Änderung"}</strong>
                    <small>{entry.actor_name ?? "Unbekannt"} · {formatDate(entry.created_at)}</small>
                    {historyDetails(entry.changes) && <p>{historyDetails(entry.changes)}</p>}
                  </li>
                ))}
              </ul>}
          </section>
        </section> : <section className="panel task-detail task-detail-empty">
          <h3>Aufgabe auswählen</h3>
          <p className="muted">Wähle eine Aufgabe aus der Liste, um Kommentare und Verlauf einzusehen.</p>
        </section>}
      </div>
      <p className="task-scope-note">
        {canSeeAll
          ? "Du siehst Aufgaben gemäß deiner Verwaltungsberechtigung."
          : "Angezeigt werden eigene Aufgaben und Aufgaben zu deinen zugewiesenen Objekten."}
      </p>
    </section>
  );
}
