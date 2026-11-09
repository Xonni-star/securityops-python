import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  addIncidentPerson,
  createIncidentMeasure,
  createIncident,
  downloadIncidentAttachment,
  getIncident,
  getIncidentChoices,
  getIncidents,
  updateIncident,
  updateIncidentMeasure,
  updateIncidentSensitiveDetails,
  updateIncidentStatus,
  uploadIncidentAttachment,
} from "./api";
import type {
  AuthUser,
  IncidentDetail,
  IncidentItem,
  IncidentSeverity,
  IncidentStatus,
  IncidentType,
} from "./types";

const typeNames: Record<IncidentType, string> = {
  incident: "Vorfall",
  accident: "Unfall",
  assault: "Übergriff",
  property_damage: "Sachbeschädigung",
  complaint: "Beschwerde",
  other: "Sonstiges",
};

const severityNames: Record<IncidentSeverity, string> = {
  low: "Niedrig",
  medium: "Mittel",
  high: "Hoch",
  critical: "Kritisch",
};

const statusNames: Record<IncidentStatus, string> = {
  reported: "Gemeldet",
  investigating: "In Prüfung",
  action_required: "Maßnahme erforderlich",
  closed: "Abgeschlossen",
};

const statusTransitions: Record<IncidentStatus, IncidentStatus[]> = {
  reported: ["investigating", "closed"],
  investigating: ["action_required", "closed"],
  action_required: ["investigating", "closed"],
  closed: [],
};

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function localDateTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("de-DE") : "Keine Frist";
}

function historyDescription(entry: IncidentDetail["history"][number]) {
  const actionNames: Record<string, string> = {
    created: "Vorgang angelegt",
    updated: "Vorgang geändert",
    status_changed: "Status geändert",
    closed: "Vorgang abgeschlossen",
    sensitive_updated: "Sensible Details geändert",
    measure_created: "Maßnahme angelegt",
    measure_updated: "Maßnahme geändert",
    person_added: "Personenbezug ergänzt",
    attachment_added: "Datei hinzugefügt",
  };
  const fieldNames: Record<string, string> = {
    title: "Titel",
    report: "Kurzmeldung",
    incident_type: "Art",
    severity: "Schweregrad",
    due_at: "Frist",
    assigned_to_id: "Verantwortlichkeit",
    narrative: "Vorfallhergang",
    closure_report: "Abschlussbericht",
    description: "Beschreibung",
    status: "Status",
  };
  const changes = entry.changes;
  const transition = changes.status_transition;
  if (transition && typeof transition === "object" && "from" in transition && "to" in transition) {
    const { from, to } = transition;
    if (typeof from === "string" && typeof to === "string" && from in statusNames && to in statusNames) {
      return `Maßnahmenstatus: ${statusNames[from as IncidentStatus]} → ${statusNames[to as IncidentStatus]}`;
    }
  }
  if (
    (entry.action === "status_changed" || entry.action === "closed")
    && typeof changes.from === "string"
    && typeof changes.to === "string"
    && changes.from in statusNames
    && changes.to in statusNames
  ) {
    return `Status: ${statusNames[changes.from as IncidentStatus]} → ${statusNames[changes.to as IncidentStatus]}`;
  }
  const actionName = actionNames[entry.action] ?? "Vorgang aktualisiert";
  const fields = changes.fields;
  if (Array.isArray(fields)) {
    const changedFields = fields
      .filter((field): field is string => typeof field === "string")
      .map((field) => fieldNames[field] ?? field)
      .join(", ");
    if (changedFields) return `${actionName}: ${changedFields}`;
  }
  return actionName;
}

export default function IncidentManagement({ user }: { user: AuthUser }) {
  const canCreate = user.permissions.includes("incidents.create");
  const canWrite = user.permissions.some((permission) =>
    ["incidents.update", "incidents.manage_all"].includes(permission),
  );
  const canSensitiveRead = user.permissions.includes("incidents.sensitive.read");
  const canSensitiveManage = user.permissions.includes("incidents.sensitive.manage");
  const [incidents, setIncidents] = useState<IncidentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [choices, setChoices] = useState<Awaited<ReturnType<typeof getIncidentChoices>>>({
    objects: [],
    assignees: [],
    linked_owks_event_ids: [],
  });
  const [selectedObject, setSelectedObject] = useState("");
  const [statusFilter, setStatusFilter] = useState<IncidentStatus | "">("");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [nextStatus, setNextStatus] = useState<IncidentStatus>("investigating");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadIncidents = useCallback(async () => {
    setLoading(true);
    try {
      const page = await getIncidents({
        status: statusFilter,
        overdue: overdueOnly,
        limit: 25,
        offset,
      });
      setIncidents(page.items);
      setTotal(page.total);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Vorfälle konnten nicht geladen werden."));
    } finally {
      setLoading(false);
    }
  }, [offset, overdueOnly, statusFilter]);

  const loadDetail = useCallback(async (incidentId: string) => {
    try {
      const loaded = await getIncident(incidentId);
      setDetail(loaded);
      setNextStatus(statusTransitions[loaded.status][0] ?? loaded.status);
      return loaded;
    } catch (reason) {
      setError(messageFrom(reason, "Vorfalldetails konnten nicht geladen werden."));
      return null;
    }
  }, []);

  useEffect(() => {
    void loadIncidents();
  }, [loadIncidents]);

  useEffect(() => {
    getIncidentChoices()
      .then(setChoices)
      .catch((reason: unknown) =>
        setError(messageFrom(reason, "Objektzuordnungen konnten nicht geladen werden.")));
  }, []);

  useEffect(() => {
    const objectId = selectedObject || detail?.object_id;
    if (!objectId) {
      setChoices((current) => ({ ...current, assignees: [] }));
      return;
    }
    getIncidentChoices(objectId)
      .then((result) => setChoices((current) => ({ ...current, assignees: result.assignees })))
      .catch((reason: unknown) =>
        setError(messageFrom(reason, "Verantwortliche konnten nicht geladen werden.")));
  }, [detail?.object_id, selectedObject]);

  async function submitIncident(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const due = String(data.get("due_at") ?? "");
    setBusy(true);
    setError("");
    try {
      const created = await createIncident({
        title: String(data.get("title") ?? "").trim(),
        report: String(data.get("report") ?? "").trim(),
        incident_type: String(data.get("incident_type")) as IncidentType,
        severity: String(data.get("severity")) as IncidentSeverity,
        object_id: String(data.get("object_id")),
        assigned_to_id: String(data.get("assigned_to_id") ?? "") || undefined,
        due_at: due ? new Date(due).toISOString() : undefined,
        owks_event_id: String(data.get("owks_event_id") ?? "").trim() || undefined,
      });
      form.reset();
      setSelectedObject("");
      await Promise.all([loadIncidents(), loadDetail(created.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Vorfall konnte nicht gemeldet werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitIncidentUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await updateIncident(detail.id, {
        title: String(data.get("title") ?? "").trim(),
        report: String(data.get("report") ?? "").trim(),
        incident_type: String(data.get("incident_type")) as IncidentType,
        severity: String(data.get("severity")) as IncidentSeverity,
        due_at: String(data.get("due_at") ?? "")
          ? new Date(String(data.get("due_at"))).toISOString()
          : null,
        assigned_to_id: String(data.get("assigned_to_id") ?? "") || detail.assigned_to_id,
      });
      await Promise.all([loadIncidents(), loadDetail(detail.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Vorfall konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    setBusy(true);
    setError("");
    try {
      await updateIncidentStatus(detail.id, nextStatus);
      await Promise.all([loadIncidents(), loadDetail(detail.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Status konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function saveSensitive(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await updateIncidentSensitiveDetails(detail.id, {
        narrative: String(data.get("narrative") ?? "").trim() || null,
        closure_report: String(data.get("closure_report") ?? "").trim() || null,
      });
      await loadDetail(detail.id);
    } catch (reason) {
      setError(messageFrom(reason, "Sensible Details konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function addPerson(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      await addIncidentPerson(detail.id, {
        name: String(data.get("name") ?? "").trim(),
        role: String(data.get("role")) as "involved" | "witness",
        notes: String(data.get("notes") ?? "").trim() || null,
      });
      form.reset();
      await loadDetail(detail.id);
    } catch (reason) {
      setError(messageFrom(reason, "Person konnte nicht hinzugefügt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function addMeasure(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const due = String(data.get("due_at") ?? "");
    setBusy(true);
    setError("");
    try {
      await createIncidentMeasure(detail.id, {
        title: String(data.get("title") ?? "").trim(),
        description: String(data.get("description") ?? "").trim() || undefined,
        due_at: due ? new Date(due).toISOString() : undefined,
        assigned_to_id: String(data.get("assigned_to_id")),
      });
      form.reset();
      await Promise.all([loadIncidents(), loadDetail(detail.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Maßnahme konnte nicht angelegt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function changeMeasureStatus(measureId: string, status: "open" | "in_progress" | "completed") {
    if (!detail) return;
    setBusy(true);
    setError("");
    try {
      await updateIncidentMeasure(detail.id, measureId, { status });
      await loadDetail(detail.id);
    } catch (reason) {
      setError(messageFrom(reason, "Maßnahmenstatus konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function uploadAttachment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!detail) return;
    const form = event.currentTarget;
    const file = (new FormData(form).get("file"));
    if (!(file instanceof File)) return;
    setBusy(true);
    setError("");
    try {
      await uploadIncidentAttachment(detail.id, file);
      form.reset();
      await loadDetail(detail.id);
    } catch (reason) {
      setError(messageFrom(reason, "Datei konnte nicht hochgeladen werden."));
    } finally {
      setBusy(false);
    }
  }

  async function downloadAttachment(attachmentId: string, fileName: string) {
    if (!detail) return;
    try {
      const blob = await downloadIncidentAttachment(detail.id, attachmentId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(messageFrom(reason, "Datei konnte nicht geladen werden."));
    }
  }

  return (
    <section className="incident-module">
      <header className="panel-heading">
        <div><p className="eyebrow">OPERATIVES FALLMANAGEMENT</p><h2>Vorfälle & Beschwerden</h2></div>
        <span className="result-count">{total} Einträge</span>
      </header>
      {error && <p className="alert" role="alert">{error}</p>}
      <div className="incident-layout">
        <section className="panel incident-list" aria-label="Vorfallliste">
          <label>Status
            <select value={statusFilter} onChange={(event) => {
              setStatusFilter(event.target.value as IncidentStatus | "");
              setOffset(0);
              setDetail(null);
            }}>
              <option value="">Alle Status</option>
              {Object.entries(statusNames).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>,
              )}
            </select>
          </label>
          <label className="incident-overdue-filter">
            <input type="checkbox" checked={overdueOnly} onChange={(event) => {
              setOverdueOnly(event.target.checked);
              setOffset(0);
              setDetail(null);
            }} />
            Frist überschritten
          </label>
          {loading
            ? <p className="muted" role="status">Vorfälle werden geladen …</p>
            : incidents.length === 0
              ? <p className="muted">Keine Vorfälle vorhanden.</p>
              : <ul className="incident-items">
                {incidents.map((incident) => (
                  <li key={incident.id}>
                    <button
                      type="button"
                      className={detail?.id === incident.id ? "incident-item selected" : "incident-item"}
                      onClick={() => void loadDetail(incident.id)}
                    >
                      <strong>{incident.title}</strong>
                      <span>{incident.object_name} · {typeNames[incident.incident_type]}</span>
                      <span>{statusNames[incident.status]} · {severityNames[incident.severity]}</span>
                    </button>
                  </li>
                ))}
              </ul>}
          <div className="incident-pagination">
            <button type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 25))}>
              Zurück
            </button>
            <button type="button" disabled={offset + incidents.length >= total || loading} onClick={() => setOffset(offset + 25)}>
              Weiter
            </button>
          </div>
        </section>

        <div className="incident-workspace">
          {canCreate && <section className="panel">
            <h3>Vorfall melden</h3>
            <form className="incident-form" onSubmit={(event) => void submitIncident(event)}>
              <label>Titel<input name="title" required maxLength={200} /></label>
              <label>Kurzmeldung
                <textarea name="report" required maxLength={4000} rows={3} />
              </label>
              <div className="form-row">
                <label>Art<select name="incident_type">
                  {Object.entries(typeNames).map(([value, name]) =>
                    <option key={value} value={value}>{name}</option>,
                  )}
                </select></label>
                <label>Schweregrad<select name="severity" defaultValue="medium">
                  {Object.entries(severityNames).map(([value, name]) =>
                    <option key={value} value={value}>{name}</option>,
                  )}
                </select></label>
              </div>
              <label>Objekt<select name="object_id" required value={selectedObject} onChange={(event) => setSelectedObject(event.target.value)}>
                <option value="">Objekt auswählen</option>
                {choices.objects.map((object) =>
                  <option key={object.id} value={object.id}>{object.name} ({object.code})</option>,
                )}
              </select></label>
              <label>Verantwortlich<select name="assigned_to_id" disabled={!selectedObject}>
                <option value="">Ich selbst</option>
                {choices.assignees.map((assignee) =>
                  <option key={assignee.id} value={assignee.id}>{assignee.full_name}</option>,
                )}
              </select></label>
              <div className="form-row">
                <label>Frist<input type="datetime-local" name="due_at" /></label>
                <label>OWKS-Meldung (optional)<input name="owks_event_id" /></label>
              </div>
              <p className="muted">Keine Namen oder vertraulichen Angaben in die Kurzmeldung aufnehmen. Solche Angaben gehören in den gesondert geschützten Detailbereich.</p>
              <button type="submit" disabled={busy || !choices.objects.length}>
                {busy ? "Wird gespeichert …" : "Vorfall melden"}
              </button>
            </form>
          </section>}

          {detail && <section className="panel incident-detail">
            <div className="panel-heading">
              <div><p className="eyebrow">{detail.object_name}</p><h3>{detail.title}</h3></div>
              <span className={`incident-status status-${detail.status}`}>{statusNames[detail.status]}</span>
            </div>
            {canWrite && detail.status !== "closed"
              ? <form className="incident-form" onSubmit={(event) => void submitIncidentUpdate(event)}>
                <label>Titel<input name="title" defaultValue={detail.title} required maxLength={200} /></label>
                <label>Kurzmeldung<textarea name="report" defaultValue={detail.report} required maxLength={4000} rows={3} /></label>
                <div className="form-row">
                  <label>Art<select name="incident_type" defaultValue={detail.incident_type}>
                    {Object.entries(typeNames).map(([value, name]) =>
                      <option key={value} value={value}>{name}</option>,
                    )}
                  </select></label>
                  <label>Schweregrad<select name="severity" defaultValue={detail.severity}>
                    {Object.entries(severityNames).map(([value, name]) =>
                      <option key={value} value={value}>{name}</option>,
                    )}
                  </select></label>
                </div>
                <label>Verantwortlich<select name="assigned_to_id" defaultValue={detail.assigned_to_id}>
                  {choices.assignees.map((assignee) =>
                    <option key={assignee.id} value={assignee.id}>{assignee.full_name}</option>,
                  )}
                  {!choices.assignees.some((assignee) => assignee.id === detail.assigned_to_id)
                    && <option value={detail.assigned_to_id}>{detail.assigned_to_name}</option>}
                </select></label>
                <label>Frist<input type="datetime-local" name="due_at" defaultValue={localDateTime(detail.due_at)} /></label>
                <button type="submit" disabled={busy}>Änderungen speichern</button>
              </form>
              : <dl className="incident-meta">
                <dt>Kurzmeldung</dt><dd>{detail.report}</dd>
                <dt>Art / Schweregrad</dt><dd>{typeNames[detail.incident_type]} · {severityNames[detail.severity]}</dd>
                <dt>Verantwortlich / Frist</dt><dd>{detail.assigned_to_name} · {formatDate(detail.due_at)}</dd>
                {detail.owks_event_id && <><dt>OWKS-Meldung</dt><dd>{detail.owks_event_id}</dd></>}
              </dl>}

            {canWrite && detail.status !== "closed" && statusTransitions[detail.status].length > 0 && (
              <form className="form-row incident-status-form" onSubmit={(event) => void changeStatus(event)}>
                <label>Status ändern<select value={nextStatus} onChange={(event) =>
                  setNextStatus(event.target.value as IncidentStatus)}>
                  {statusTransitions[detail.status]
                    .filter((status) => status !== "closed" || canSensitiveManage)
                    .map((status) =>
                    <option key={status} value={status}>{statusNames[status]}</option>,
                  )}
                </select></label>
                <button type="submit" disabled={busy}>Status übernehmen</button>
              </form>
            )}

            <section className="incident-sensitive">
              <h4>Sensible Vorfalldetails</h4>
              {!canSensitiveRead && <p className="muted">Für diesen Bereich ist eine gesonderte Berechtigung erforderlich.</p>}
              {canSensitiveRead && canSensitiveManage && canWrite && detail.status !== "closed" && (
                <form className="incident-form" onSubmit={(event) => void saveSensitive(event)}>
                  <label>Vorfallhergang<textarea name="narrative" defaultValue={detail.sensitive_details?.narrative ?? ""} rows={4} maxLength={20000} /></label>
                  <label>Abschlussbericht<textarea name="closure_report" defaultValue={detail.sensitive_details?.closure_report ?? ""} rows={4} maxLength={10000} /></label>
                  <button type="submit" disabled={busy}>Sensible Details speichern</button>
                </form>
              )}
              {canSensitiveRead && !(canSensitiveManage && canWrite && detail.status !== "closed") && (
                <>
                  <p><strong>Vorfallhergang:</strong> {detail.sensitive_details?.narrative || "Keine sensiblen Details erfasst."}</p>
                  <p><strong>Abschlussbericht:</strong> {detail.sensitive_details?.closure_report || "Noch kein Abschlussbericht."}</p>
                </>
              )}
              {canSensitiveRead && <ul className="incident-people">
                {detail.people.map((person) => (
                  <li key={person.id}>{person.name} · {person.role === "witness" ? "Zeuge" : "Beteiligte Person"}
                    {person.notes && <span> — {person.notes}</span>}
                  </li>
                ))}
              </ul>}
              {canSensitiveManage && canWrite && detail.status !== "closed" && (
                <form className="incident-form" onSubmit={(event) => void addPerson(event)}>
                  <h5>Personenbezug hinzufügen</h5>
                  <label>Name<input name="name" required maxLength={160} /></label>
                  <label>Rolle<select name="role"><option value="involved">Beteiligte Person</option><option value="witness">Zeuge</option></select></label>
                  <label>Notiz<textarea name="notes" rows={2} maxLength={5000} /></label>
                  <button type="submit" disabled={busy}>Person ergänzen</button>
                </form>
              )}
              {canSensitiveRead && <div>
                <h5>Fotos und Anhänge</h5>
                <ul className="incident-attachments">
                  {detail.attachments.map((attachment) => (
                    <li key={attachment.id}>
                      <button type="button" onClick={() =>
                        void downloadAttachment(attachment.id, attachment.file_name)}>
                        {attachment.file_name} ({Math.ceil(attachment.size_bytes / 1024)} KB)
                      </button>
                    </li>
                  ))}
                </ul>
              </div>}
              {canSensitiveManage && canWrite && detail.status !== "closed" && (
                <form className="incident-form" onSubmit={(event) => void uploadAttachment(event)}>
                  <label>PDF oder Bild hochladen<input type="file" name="file" required accept="application/pdf,image/png,image/jpeg" /></label>
                  <button type="submit" disabled={busy}>Datei sicher hochladen</button>
                </form>
              )}
            </section>

            <section className="incident-measures">
              <h4>Maßnahmen</h4>
              {detail.measures.length === 0
                ? <p className="muted">Noch keine Maßnahmen erfasst.</p>
                : <ul>
                  {detail.measures.map((measure) => (
                    <li key={measure.id}>
                      <div>
                        <strong>{measure.title}</strong>
                        {measure.description && <p>{measure.description}</p>}
                        <small>Frist: {formatDate(measure.due_at)}</small>
                      </div>
                      {canWrite && detail.status !== "closed"
                        ? <select aria-label={`Status Maßnahme ${measure.title}`}
                          value={measure.status}
                          onChange={(event) => void changeMeasureStatus(
                            measure.id,
                            event.target.value as "open" | "in_progress" | "completed",
                          )}>
                          <option value="open">Offen</option>
                          <option value="in_progress">In Bearbeitung</option>
                          <option value="completed">Erledigt</option>
                        </select>
                        : <span>{measure.status === "completed" ? "Erledigt" : measure.status === "in_progress" ? "In Bearbeitung" : "Offen"}</span>}
                    </li>
                  ))}
                </ul>}
              {canWrite && detail.status !== "closed" && <form className="incident-form" onSubmit={(event) => void addMeasure(event)}>
                <h5>Maßnahme ergänzen</h5>
                <label>Titel<input name="title" required maxLength={200} /></label>
                <label>Beschreibung<textarea name="description" rows={2} maxLength={4000} /></label>
                <div className="form-row">
                  <label>Verantwortlich<select name="assigned_to_id" required defaultValue={detail.assigned_to_id}>
                    {choices.assignees.map((assignee) =>
                      <option key={assignee.id} value={assignee.id}>{assignee.full_name}</option>,
                    )}
                    {!choices.assignees.some((assignee) => assignee.id === detail.assigned_to_id)
                      && <option value={detail.assigned_to_id}>{detail.assigned_to_name}</option>}
                  </select></label>
                  <label>Frist<input type="datetime-local" name="due_at" /></label>
                </div>
                <button type="submit" disabled={busy}>Maßnahme anlegen</button>
              </form>}
            </section>

            <section>
              <h4>Verlauf</h4>
              {detail.history.length === 0
                ? <p className="muted">Noch kein Verlauf vorhanden.</p>
                : <ol className="incident-history">
                  {detail.history.map((entry) => (
                    <li key={entry.id}>
                      <time>{formatDate(entry.created_at)}</time>
                      <span>{historyDescription(entry)}</span>
                    </li>
                  ))}
                </ol>}
            </section>
          </section>}
          {!detail && !canCreate && <p className="muted">Wähle einen Vorfall aus der Liste.</p>}
        </div>
      </div>
    </section>
  );
}
