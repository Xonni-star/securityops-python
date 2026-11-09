import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  createEmployeePortalAbsence,
  createEmployeePortalAvailabilityRequest,
  employeePortalDocumentUrl,
  updateEmployeePortalAbsence,
  updateEmployeePortalAvailabilityRequest,
  getEmployeePortalDocuments,
  getEmployeePortalAbsences,
  getEmployeePortalAvailabilityRequests,
  getEmployeePortalNotifications,
  getEmployeePortalProfile,
  getEmployeePortalQualifications,
  getEmployeePortalShift,
  getEmployeePortalShifts,
  getEmployeePortalTasks,
  getEmployeePortalTimeOverview,
  markEmployeePortalNotificationRead,
  withdrawEmployeePortalAbsence,
  withdrawEmployeePortalAvailabilityRequest,
} from "./api";
import type {
  EmployeePortalAbsence,
  EmployeePortalAvailabilityRequest,
  EmployeePortalDocument,
  EmployeePortalNotification,
  EmployeePortalProfile,
  EmployeePortalQualification,
  EmployeePortalShift as PortalShift,
  EmployeePortalTask,
  EmployeePortalTimeOverview,
} from "./types";

type PortalSection =
  | "shifts"
  | "tasks"
  | "notifications"
  | "documents"
  | "qualifications"
  | "time"
  | "requests";

const sectionTitles: Record<PortalSection, string> = {
  shifts: "Meine Dienste",
  tasks: "Meine Aufgaben",
  notifications: "Benachrichtigungen",
  documents: "Freigegebene Dokumente",
  qualifications: "Qualifikationen",
  time: "Arbeitszeiten",
  requests: "Abwesenheit & Verfügbarkeit",
};

const absenceNames = {
  vacation: "Urlaub",
  sick_leave: "Krankheit",
  other: "Sonstige Abwesenheit",
} as const;

const statusNames: Record<string, string> = {
  open: "Offen",
  in_progress: "In Bearbeitung",
  blocked: "Blockiert",
  completed: "Erledigt",
  cancelled: "Abgebrochen",
  submitted: "Eingereicht",
  approved: "Freigegeben",
  rejected: "Abgelehnt",
  correction_requested: "Korrektur angefragt",
  locked: "Abgeschlossen",
  pending: "Ausstehend",
  accepted: "Angenommen",
  withdrawn: "Zurückgezogen",
};

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeZone: "Europe/Berlin",
  }).format(new Date(value));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Berlin",
  }).format(new Date(value));
}

function formatLocalDateTimeInput(value: string, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  }).formatToParts(new Date(value));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

function formatHours(seconds: number) {
  return new Intl.NumberFormat("de-DE", {
    maximumFractionDigits: 1,
  }).format(seconds / 3600);
}

function historyEventName(event: string) {
  const names: Record<string, string> = {
    requested: "Eingereicht",
    updated: "Bearbeitet",
    approved: "Freigegeben",
    accepted: "Angenommen",
    rejected: "Abgelehnt",
    withdrawn: "Zurückgezogen",
  };
  return names[event] ?? event;
}

export default function EmployeePortal() {
  const [profile, setProfile] = useState<EmployeePortalProfile | null>(null);
  const [shifts, setShifts] = useState<PortalShift[]>([]);
  const [tasks, setTasks] = useState<EmployeePortalTask[]>([]);
  const [notifications, setNotifications] = useState<EmployeePortalNotification[]>([]);
  const [documents, setDocuments] = useState<EmployeePortalDocument[]>([]);
  const [qualifications, setQualifications] = useState<EmployeePortalQualification[]>([]);
  const [timeOverview, setTimeOverview] = useState<EmployeePortalTimeOverview | null>(null);
  const [absences, setAbsences] = useState<EmployeePortalAbsence[]>([]);
  const [availabilityRequests, setAvailabilityRequests] = useState<
    EmployeePortalAvailabilityRequest[]
  >([]);
  const [section, setSection] = useState<PortalSection>("shifts");
  const [selectedShift, setSelectedShift] = useState<PortalShift | null>(null);
  const [editingAbsence, setEditingAbsence] = useState<string | null>(null);
  const [editingAvailability, setEditingAvailability] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadPortal = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [
        nextProfile,
        nextShifts,
        nextTasks,
        nextNotifications,
        nextDocuments,
        nextQualifications,
        nextTimeOverview,
        nextAbsences,
        nextAvailabilityRequests,
      ] = await Promise.all([
        getEmployeePortalProfile(),
        getEmployeePortalShifts(),
        getEmployeePortalTasks(),
        getEmployeePortalNotifications(),
        getEmployeePortalDocuments(),
        getEmployeePortalQualifications(),
        getEmployeePortalTimeOverview(),
        getEmployeePortalAbsences(),
        getEmployeePortalAvailabilityRequests(),
      ]);
      setProfile(nextProfile);
      setShifts(nextShifts);
      setTasks(nextTasks);
      setNotifications(nextNotifications);
      setDocuments(nextDocuments);
      setQualifications(nextQualifications);
      setTimeOverview(nextTimeOverview);
      setAbsences(nextAbsences);
      setAvailabilityRequests(nextAvailabilityRequests);
    } catch (reason) {
      setError(messageFrom(reason, "Das Mitarbeiterportal konnte nicht geladen werden."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPortal();
  }, [loadPortal]);

  async function submitAbsence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await createEmployeePortalAbsence({
        absence_type: String(data.get("absence_type")) as keyof typeof absenceNames,
        starts_on: String(data.get("starts_on")),
        ends_on: String(data.get("ends_on")),
      });
      form.reset();
      setSuccess("Der Abwesenheitsantrag wurde zur Prüfung eingereicht.");
      await loadPortal();
    } catch (reason) {
      setError(messageFrom(reason, "Der Abwesenheitsantrag konnte nicht eingereicht werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitAvailability(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await createEmployeePortalAvailabilityRequest({
        kind: String(data.get("kind")) as "preferred" | "blocked",
        starts_at_local: String(data.get("starts_at_local")),
        ends_at_local: String(data.get("ends_at_local")),
      });
      form.reset();
      setSuccess("Der Verfügbarkeitsantrag wurde zur Prüfung eingereicht.");
      await loadPortal();
    } catch (reason) {
      setError(messageFrom(reason, "Der Verfügbarkeitsantrag konnte nicht eingereicht werden."));
    } finally {
      setBusy(false);
    }
  }

  async function showShiftDetails(shiftId: string) {
    setError("");
    try {
      setSelectedShift(await getEmployeePortalShift(shiftId));
    } catch (reason) {
      setError(messageFrom(reason, "Die Dienstdetails konnten nicht geladen werden."));
    }
  }

  async function markAsRead(notificationId: string) {
    setError("");
    try {
      const updated = await markEmployeePortalNotificationRead(notificationId);
      setNotifications((current) =>
        current.map((item) => item.id === updated.id ? updated : item),
      );
    } catch (reason) {
      setError(messageFrom(reason, "Die Benachrichtigung konnte nicht aktualisiert werden."));
    }
  }

  async function submitAbsenceUpdate(event: FormEvent<HTMLFormElement>, absenceId: string) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await updateEmployeePortalAbsence(absenceId, {
        absence_type: String(data.get("absence_type")) as keyof typeof absenceNames,
        starts_on: String(data.get("starts_on")),
        ends_on: String(data.get("ends_on")),
      });
      setEditingAbsence(null);
      setSuccess("Der ausstehende Abwesenheitsantrag wurde aktualisiert.");
      await loadPortal();
    } catch (reason) {
      setError(messageFrom(reason, "Der Abwesenheitsantrag konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitAvailabilityUpdate(
    event: FormEvent<HTMLFormElement>,
    requestId: string,
  ) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await updateEmployeePortalAvailabilityRequest(requestId, {
        kind: String(data.get("kind")) as "preferred" | "blocked",
        starts_at_local: String(data.get("starts_at_local")),
        ends_at_local: String(data.get("ends_at_local")),
      });
      setEditingAvailability(null);
      setSuccess("Der offene Verfügbarkeitsantrag wurde aktualisiert.");
      await loadPortal();
    } catch (reason) {
      setError(messageFrom(reason, "Der Verfügbarkeitsantrag konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function withdrawAbsence(absence: EmployeePortalAbsence) {
    if (!window.confirm("Möchtest du diesen offenen Abwesenheitsantrag zurückziehen?")) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await withdrawEmployeePortalAbsence(absence.id);
      setSuccess("Der Abwesenheitsantrag wurde nachvollziehbar zurückgezogen.");
      await loadPortal();
    } catch (reason) {
      setError(messageFrom(reason, "Der Abwesenheitsantrag konnte nicht zurückgezogen werden."));
    } finally {
      setBusy(false);
    }
  }

  async function withdrawAvailability(item: EmployeePortalAvailabilityRequest) {
    if (!window.confirm("Möchtest du diesen offenen Verfügbarkeitswunsch zurückziehen?")) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await withdrawEmployeePortalAvailabilityRequest(item.id);
      setSuccess("Der Verfügbarkeitswunsch wurde nachvollziehbar zurückgezogen.");
      await loadPortal();
    } catch (reason) {
      setError(messageFrom(reason, "Der Verfügbarkeitswunsch konnte nicht zurückgezogen werden."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="employee-portal">
      <div className="panel-heading employee-portal-heading">
        <div>
          <p className="eyebrow">MITARBEITERSERVICE</p>
          <h2>{profile ? `Willkommen, ${profile.full_name}` : "Mein Mitarbeiterportal"}</h2>
          {profile?.job_title && <p className="muted">{profile.job_title}</p>}
        </div>
        <button className="secondary-button" onClick={() => void loadPortal()} disabled={loading}>
          Aktualisieren
        </button>
      </div>

      <nav className="portal-tabs" aria-label="Mitarbeiterportal">
        {(Object.keys(sectionTitles) as PortalSection[]).map((item) => (
          <button
            key={item}
            className={section === item ? "module-tab active" : "module-tab"}
            onClick={() => setSection(item)}
          >
            {sectionTitles[item]}
          </button>
        ))}
      </nav>

      {error && <p className="alert page-alert" role="alert">{error}</p>}
      {success && <p className="success-message" role="status">{success}</p>}
      {loading ? (
        <p className="muted" role="status">Portal-Daten werden geladen …</p>
      ) : (
        <>
          {section === "shifts" && <section className="panel portal-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">DIENSTPLAN</p><h2>{sectionTitles.shifts}</h2></div>
              <span className="result-count">{shifts.length} Dienste</span>
            </div>
            {shifts.length === 0 ? <p className="empty">Keine veröffentlichten Dienste vorhanden.</p> : (
              <ul className="portal-list">
                {shifts.map((shift) => (
                  <li key={shift.id}>
                    <div>
                      <strong>{shift.object_name}</strong>
                      <small>{shift.object_code} · {formatDateTime(shift.starts_at)} – {formatDateTime(shift.ends_at)}</small>
                      <small>Pause: {shift.break_minutes} Minuten</small>
                    </div>
                    <button className="text-button" onClick={() => void showShiftDetails(shift.id)}>
                      Details
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {selectedShift && <aside className="portal-detail" aria-live="polite">
              <h3>Dienst-Details</h3>
              <p><strong>{selectedShift.object_name}</strong> ({selectedShift.object_code})</p>
              <p>{formatDateTime(selectedShift.starts_at)} bis {formatDateTime(selectedShift.ends_at)}</p>
              <p>Pause: {selectedShift.break_minutes} Minuten</p>
              <button className="text-button" onClick={() => setSelectedShift(null)}>Schließen</button>
            </aside>}
          </section>}

          {section === "tasks" && <section className="panel portal-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">AUFGABEN</p><h2>{sectionTitles.tasks}</h2></div>
              <span className="result-count">{tasks.length} Aufgaben</span>
            </div>
            {tasks.length === 0 ? <p className="empty">Keine eigenen Aufgaben vorhanden.</p> : (
              <ul className="portal-list">
                {tasks.map((task) => (
                  <li key={task.id}>
                    <div>
                      <strong>{task.title}</strong>
                      <small>{statusNames[task.status] ?? task.status} · Priorität: {task.priority}</small>
                      {task.due_at && <small>Fällig: {formatDateTime(task.due_at)}</small>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>}

          {section === "notifications" && <section className="panel portal-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">POSTEINGANG</p><h2>{sectionTitles.notifications}</h2></div>
              <span className="result-count">
                {notifications.filter((item) => item.read_at === null).length} ungelesen
              </span>
            </div>
            {notifications.length === 0 ? <p className="empty">Keine Benachrichtigungen vorhanden.</p> : (
              <ul className="portal-list">
                {notifications.map((item) => (
                  <li key={item.id}>
                    <div>
                      <strong>{item.title}</strong>
                      <small>{item.body} · {formatDateTime(item.created_at)}</small>
                    </div>
                    {item.read_at === null && (
                      <button className="text-button" onClick={() => void markAsRead(item.id)}>
                        Als gelesen markieren
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>}

          {section === "documents" && <section className="panel portal-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">PERSÖNLICHE DOKUMENTE</p><h2>{sectionTitles.documents}</h2></div>
              <span className="result-count">{documents.length} Dokumente</span>
            </div>
            {documents.length === 0 ? (
              <p className="empty">Es wurden keine Dokumente ausdrücklich für dein Konto freigegeben.</p>
            ) : (
              <ul className="portal-list">
                {documents.map((document) => (
                  <li key={document.grant_id}>
                    <div>
                      <strong>{document.qualification_name}</strong>
                      <small>Version {document.version} · {document.file_name}</small>
                      <small>Freigegeben am {formatDateTime(document.granted_at)} ·
                        {" "}{Math.ceil(document.size_bytes / 1024)} KiB</small>
                    </div>
                    <a
                      className="text-button"
                      href={employeePortalDocumentUrl(document)}
                      target="_blank"
                      rel="noreferrer"
                    >Nachweis öffnen</a>
                  </li>
                ))}
              </ul>
            )}
          </section>}

          {section === "qualifications" && <section className="panel portal-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">NACHWEISE</p><h2>{sectionTitles.qualifications}</h2></div>
              <span className="result-count">{qualifications.length} Qualifikationen</span>
            </div>
            {qualifications.length === 0 ? <p className="empty">Keine aktiven Qualifikationen hinterlegt.</p> : (
              <ul className="portal-list">
                {qualifications.map((qualification) => (
                  <li key={qualification.id}>
                    <div>
                      <strong>{qualification.name}</strong>
                      <small>{qualification.category}{qualification.issuer ? ` · ${qualification.issuer}` : ""}</small>
                      <small>
                        Gültig ab: {qualification.valid_from ? formatDate(qualification.valid_from) : "nicht angegeben"}
                        {" · "}
                        Ablauf: {qualification.expires_on ? formatDate(qualification.expires_on) : "ohne Ablaufdatum"}
                      </small>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>}

          {section === "time" && <section className="panel portal-panel">
            <div className="panel-heading">
              <div><p className="eyebrow">ZEITERFASSUNG</p><h2>{sectionTitles.time}</h2></div>
              <span className="result-count">{timeOverview?.total ?? 0} Einträge</span>
            </div>
            <div className="time-summary-grid">
              <article><span>Erfasste Arbeitszeit (angezeigte Einträge)</span>
                <strong>{formatHours(timeOverview?.total_work_seconds ?? 0)} Stunden</strong></article>
            </div>
            {timeOverview?.items.length === 0 ? <p className="empty">Keine Zeiteinträge vorhanden.</p> : (
              <ul className="portal-list">
                {timeOverview?.items.map((entry) => (
                  <li key={entry.id}>
                    <div>
                      <strong>{formatDateTime(entry.started_at)}</strong>
                      <small>{entry.ended_at ? `Ende: ${formatDateTime(entry.ended_at)}` : "Noch nicht beendet"}</small>
                      <small>{statusNames[entry.status] ?? entry.status} · {formatHours(entry.actual_work_seconds)} Stunden</small>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {(timeOverview?.total ?? 0) > (timeOverview?.items.length ?? 0) &&
              <p className="muted">Es werden die 100 neuesten Einträge angezeigt.</p>}
          </section>}

          {section === "requests" && <div className="portal-request-grid">
            <section className="panel form-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">ANTRAG</p><h2>Abwesenheit beantragen</h2></div>
              </div>
              <form onSubmit={(event) => void submitAbsence(event)}>
                <label>Art der Abwesenheit
                  <select name="absence_type" defaultValue="vacation" required>
                    {Object.entries(absenceNames).map(([value, name]) =>
                      <option key={value} value={value}>{name}</option>,
                    )}
                  </select>
                </label>
                <div className="form-row">
                  <label>Beginn<input name="starts_on" type="date" required /></label>
                  <label>Ende<input name="ends_on" type="date" required /></label>
                </div>
                <p className="muted">Der Antrag bleibt bis zur Prüfung ausstehend.</p>
                <button className="primary-button" disabled={busy}>Abwesenheit einreichen</button>
              </form>
            </section>
            <section className="panel form-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">DIENSTPLAN</p><h2>Verfügbarkeit melden</h2></div>
              </div>
              <form onSubmit={(event) => void submitAvailability(event)}>
                <label>Art des Wunsches
                  <select name="kind" defaultValue="blocked" required>
                    <option value="blocked">In diesem Zeitraum nicht verfügbar</option>
                    <option value="preferred">Bevorzugter Dienstzeitraum</option>
                  </select>
                </label>
                <div className="form-row">
                  <label>Beginn<input name="starts_at_local" type="datetime-local" required /></label>
                  <label>Ende<input name="ends_at_local" type="datetime-local" required /></label>
                </div>
                <p className="muted">Die lokale Dienstzeitzone ist Europe/Berlin. Der Wunsch wird geprüft.</p>
                <button className="primary-button" disabled={busy}>Verfügbarkeit einreichen</button>
              </form>
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div><p className="eyebrow">MEINE ANTRÄGE</p><h2>Abwesenheiten</h2></div>
              </div>
              {absences.length === 0 ? <p className="empty">Keine Abwesenheitsanträge vorhanden.</p> : (
                <ul className="portal-list">
                  {absences.map((absence) => (
                    <li key={absence.id} className="portal-request-item">
                      <div>
                        <strong>{absenceNames[absence.absence_type]}</strong>
                        <small>{formatDate(absence.starts_on)} – {formatDate(absence.ends_on)}</small>
                        <small>Status: {statusNames[absence.status]} · zuletzt geändert: {formatDateTime(absence.updated_at)}</small>
                        <small className="portal-request-history">
                          Verlauf: {absence.history.map((item) =>
                            `${historyEventName(item.event)} am ${formatDateTime(item.occurred_at)}`,
                          ).join(" · ")}
                        </small>
                      </div>
                      <span className="status status-inactive">{statusNames[absence.status]}</span>
                      {absence.status === "pending" && <div className="portal-request-actions">
                        <button className="text-button" onClick={() =>
                          setEditingAbsence(editingAbsence === absence.id ? null : absence.id)
                        }>Bearbeiten</button>
                        <button className="text-button danger-text" disabled={busy}
                          onClick={() => void withdrawAbsence(absence)}>Zurückziehen</button>
                      </div>}
                      {editingAbsence === absence.id && <form
                        className="portal-edit-form"
                        onSubmit={(event) => void submitAbsenceUpdate(event, absence.id)}
                      >
                        <label>Art
                          <select name="absence_type" defaultValue={absence.absence_type}>
                            {Object.entries(absenceNames).map(([value, name]) =>
                              <option key={value} value={value}>{name}</option>,
                            )}
                          </select>
                        </label>
                        <label>Beginn<input name="starts_on" type="date" defaultValue={absence.starts_on} required /></label>
                        <label>Ende<input name="ends_on" type="date" defaultValue={absence.ends_on} required /></label>
                        <div className="portal-request-actions">
                          <button className="primary-button" disabled={busy}>Änderungen speichern</button>
                          <button type="button" className="secondary-button" onClick={() => setEditingAbsence(null)}>Abbrechen</button>
                        </div>
                      </form>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="panel">
              <div className="panel-heading">
                <div><p className="eyebrow">MEINE ANTRÄGE</p><h2>Verfügbarkeitswünsche</h2></div>
              </div>
              {availabilityRequests.length === 0 ? <p className="empty">Keine Verfügbarkeitswünsche vorhanden.</p> : (
                <ul className="portal-list">
                  {availabilityRequests.map((item) => (
                    <li key={item.id} className="portal-request-item">
                      <div>
                        <strong>{item.kind === "blocked" ? "Nicht verfügbar" : "Bevorzugter Zeitraum"}</strong>
                        <small>{formatDateTime(item.starts_at)} – {formatDateTime(item.ends_at)}</small>
                        <small>Status: {statusNames[item.status]} · zuletzt geändert: {formatDateTime(item.updated_at)}</small>
                        {item.reviewed_at && <small>Entschieden am: {formatDateTime(item.reviewed_at)}</small>}
                        <small className="portal-request-history">
                          Verlauf: {item.history.map((event) =>
                            `${historyEventName(event.event)} am ${formatDateTime(event.occurred_at)}`,
                          ).join(" · ")}
                        </small>
                      </div>
                      <span className="status status-inactive">{statusNames[item.status]}</span>
                      {item.status === "open" && <div className="portal-request-actions">
                        <button className="text-button" onClick={() =>
                          setEditingAvailability(editingAvailability === item.id ? null : item.id)
                        }>Bearbeiten</button>
                        <button className="text-button danger-text" disabled={busy}
                          onClick={() => void withdrawAvailability(item)}>Zurückziehen</button>
                      </div>}
                      {editingAvailability === item.id && <form
                        className="portal-edit-form"
                        onSubmit={(event) => void submitAvailabilityUpdate(event, item.id)}
                      >
                        <label>Art
                          <select name="kind" defaultValue={item.kind}>
                            <option value="blocked">Nicht verfügbar</option>
                            <option value="preferred">Bevorzugter Zeitraum</option>
                          </select>
                        </label>
                        <label>Beginn<input
                          name="starts_at_local"
                          type="datetime-local"
                          defaultValue={formatLocalDateTimeInput(item.starts_at, item.time_zone)}
                          required
                        /></label>
                        <label>Ende<input
                          name="ends_at_local"
                          type="datetime-local"
                          defaultValue={formatLocalDateTimeInput(item.ends_at, item.time_zone)}
                          required
                        /></label>
                        <div className="portal-request-actions">
                          <button className="primary-button" disabled={busy}>Änderungen speichern</button>
                          <button type="button" className="secondary-button" onClick={() => setEditingAvailability(null)}>Abbrechen</button>
                        </div>
                      </form>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>}
        </>
      )}
    </section>
  );
}
