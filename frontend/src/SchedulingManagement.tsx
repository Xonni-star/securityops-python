import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  cancelScheduleShift,
  createScheduleAvailabilityRequest,
  createScheduleShift,
  getEmployees,
  getEmployeeAvailability,
  getObjects,
  getScheduleAvailabilityRequests,
  getScheduleSettings,
  getScheduleShiftHistory,
  getScheduleShiftReplacementCandidates,
  getScheduleShifts,
  publishScheduleShift,
  replaceScheduleShiftEmployee,
  updateScheduleSettings,
  updateScheduleShift,
  updateEmployeeAvailability,
  updateScheduleAvailabilityRequest,
} from "./api";
import type {
  AuthUser,
  EmployeeAvailabilityWindow,
  Employee,
  ScheduleAvailabilityRequest,
  ScheduleAvailabilityRequestKind,
  ScheduleReplacementReason,
  ScheduleReplacementCandidate,
  ScheduleSettings,
  ScheduleShift,
  ScheduleShiftHistory,
} from "./types";

type Props = { user: AuthUser; initialShiftDate?: string; initialShiftId?: string | null };
type ViewMode = "day" | "week" | "month";

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function dateString(date: Date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function viewRange(mode: ViewMode, focusDate: string) {
  const date = new Date(`${focusDate}T12:00:00`);
  if (mode === "day") return { fromDate: focusDate, toDate: focusDate };
  if (mode === "week") {
    const monday = new Date(date);
    monday.setDate(date.getDate() - ((date.getDay() + 6) % 7));
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    return { fromDate: dateString(monday), toDate: dateString(sunday) };
  }
  const first = new Date(date.getFullYear(), date.getMonth(), 1);
  const last = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  return { fromDate: dateString(first), toDate: dateString(last) };
}

function localInputValue(instant: string, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(instant));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

function foldForInstant(instant: string, localValue: string, timeZone: string) {
  const localAsUtc = Date.parse(`${localValue}:00Z`);
  const offsetMinutesAt = (time: number) => {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date(time));
    const values = Object.fromEntries(parts.map((part) => [part.type, Number(part.value)]));
    return (Date.UTC(
      values.year,
      values.month - 1,
      values.day,
      values.hour,
      values.minute,
      values.second,
    ) - time) / 60_000;
  };
  const offsets = new Set([
    offsetMinutesAt(localAsUtc - 86_400_000),
    offsetMinutesAt(localAsUtc),
    offsetMinutesAt(localAsUtc + 86_400_000),
  ]);
  const candidates = [...offsets]
    .map((offset) => localAsUtc - offset * 60_000)
    .sort((left, right) => left - right);
  return Math.max(0, candidates.indexOf(Date.parse(instant)));
}

function formatInstant(instant: string, timeZone: string) {
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  }).format(new Date(instant));
}

const actionNames: Record<string, string> = {
  created: "Dienst angelegt",
  updated: "Dienst geändert",
  published: "Dienst veröffentlicht",
  cancelled: "Dienst abgesagt",
  replaced: "Vertretung eingetragen",
};

const weekdayNames = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];

export default function SchedulingManagement({
  user,
  initialShiftDate,
  initialShiftId = null,
}: Props) {
  const canManage = user.permissions.includes("scheduling.manage");
  const canRequestAvailability = user.permissions.includes("scheduling.availability.request");
  const [settings, setSettings] = useState<ScheduleSettings | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [objects, setObjects] = useState<Array<{ id: string; code: string; name: string }>>([]);
  const [shifts, setShifts] = useState<ScheduleShift[]>([]);
  const [view, setView] = useState<ViewMode>(initialShiftDate ? "day" : "week");
  const [focusDate, setFocusDate] = useState(initialShiftDate ?? dateString(new Date()));
  const [employeeFilter, setEmployeeFilter] = useState("");
  const [objectFilter, setObjectFilter] = useState("");
  const [includeCancelled, setIncludeCancelled] = useState(false);
  const [editing, setEditing] = useState<ScheduleShift | null>(null);
  const [history, setHistory] = useState<{ shiftId: string; rows: ScheduleShiftHistory[] } | null>(null);
  const [availabilityEmployeeId, setAvailabilityEmployeeId] = useState("");
  const [availabilityWindows, setAvailabilityWindows] = useState<
    Array<Pick<EmployeeAvailabilityWindow, "weekday" | "starts_at" | "ends_at">>
  >([]);
  const [availabilityRequests, setAvailabilityRequests] = useState<ScheduleAvailabilityRequest[]>([]);
  const [replacementFor, setReplacementFor] = useState<ScheduleShift | null>(null);
  const [replacementCandidates, setReplacementCandidates] = useState<ScheduleReplacementCandidate[]>([]);
  const [selectedReplacementCandidateId, setSelectedReplacementCandidateId] = useState("");
  const [replacementCandidatesError, setReplacementCandidatesError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const range = useMemo(() => viewRange(view, focusDate), [focusDate, view]);

  const loadShifts = useCallback(async () => {
    try {
      const result = await getScheduleShifts({
        ...range,
        employeeId: employeeFilter,
        objectId: objectFilter,
        includeCancelled,
      });
      setShifts(result);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Dienstplan konnte nicht geladen werden."));
    }
  }, [employeeFilter, includeCancelled, objectFilter, range]);

  useEffect(() => {
    getScheduleSettings()
      .then(setSettings)
      .catch((reason) => setError(messageFrom(reason, "Planungseinstellungen konnten nicht geladen werden.")));
    if (user.permissions.includes("employees.read")) {
      getEmployees({
        q: "",
        status: "active",
        includeArchived: false,
        sortBy: "full_name",
        sortOrder: "asc",
        limit: 100,
        offset: 0,
      }).then((page) => setEmployees(page.items))
        .catch((reason) => setError(messageFrom(reason, "Mitarbeiter konnten nicht geladen werden.")));
    }
    if (user.permissions.includes("objects.read")) {
      getObjects({
        q: "",
        status: "active",
        customerId: "",
        includeArchived: false,
        sortBy: "name",
        sortOrder: "asc",
        limit: 100,
        offset: 0,
      }).then((page) => setObjects(page.items))
        .catch((reason) => setError(messageFrom(reason, "Objekte konnten nicht geladen werden.")));
    }
  }, [user]);

  useEffect(() => {
    void loadShifts();
  }, [loadShifts]);

  useEffect(() => {
    if (!initialShiftDate) return;
    setView("day");
    setFocusDate(initialShiftDate);
  }, [initialShiftDate]);

  useEffect(() => {
    if (!canManage || !availabilityEmployeeId) return;
    getEmployeeAvailability(availabilityEmployeeId)
      .then((windows) => setAvailabilityWindows(
        windows.map(({ weekday, starts_at, ends_at }) => ({ weekday, starts_at, ends_at })),
      ))
      .catch((reason) => setError(messageFrom(reason, "Verfügbarkeiten konnten nicht geladen werden.")));
  }, [availabilityEmployeeId, canManage]);

  useEffect(() => {
    if (!canManage && !canRequestAvailability) return;
    getScheduleAvailabilityRequests(range.fromDate, range.toDate)
      .then(setAvailabilityRequests)
      .catch((reason) => setError(messageFrom(reason, "Dienstwünsche konnten nicht geladen werden.")));
  }, [canManage, canRequestAvailability, range]);

  useEffect(() => {
    if (availabilityEmployeeId || employees.length === 0) return;
    setAvailabilityEmployeeId(employees[0].id);
  }, [availabilityEmployeeId, employees]);

  function navigateDate(direction: number) {
    const date = new Date(`${focusDate}T12:00:00`);
    if (view === "day") date.setDate(date.getDate() + direction);
    else if (view === "week") date.setDate(date.getDate() + direction * 7);
    else date.setMonth(date.getMonth() + direction);
    setFocusDate(dateString(date));
  }

  async function submitShift(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = {
      employee_id: String(data.get("employee_id")),
      object_id: String(data.get("object_id")),
      starts_at_local: String(data.get("starts_at_local")),
      ends_at_local: String(data.get("ends_at_local")),
      starts_at_fold: Number(data.get("starts_at_fold")),
      ends_at_fold: Number(data.get("ends_at_fold")),
      break_minutes: Number(data.get("break_minutes")),
      required_qualification: String(data.get("required_qualification") ?? "").trim() || undefined,
    };
    setBusy(true);
    setNotice("");
    try {
      const wasEditing = Boolean(editing);
      if (editing) await updateScheduleShift(editing.id, payload);
      else await createScheduleShift(payload);
      setEditing(null);
      setHistory(null);
      setError("");
      await loadShifts();
      setNotice(wasEditing ? "Dienst wurde geändert." : "Dienst wurde angelegt.");
    } catch (reason) {
      setError(messageFrom(reason, "Dienst konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function changeShiftStatus(shift: ScheduleShift, action: "publish" | "cancel") {
    if (action === "cancel" && !window.confirm("Diesen Dienst wirklich absagen?")) return;
    setBusy(true);
    setNotice("");
    try {
      if (action === "publish") await publishScheduleShift(shift.id);
      else await cancelScheduleShift(shift.id);
      await loadShifts();
      setError("");
      setNotice(action === "publish" ? "Dienst wurde veröffentlicht." : "Dienst wurde abgesagt.");
    } catch (reason) {
      setError(messageFrom(reason, "Dienststatus konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function showHistory(shift: ScheduleShift) {
    if (history?.shiftId === shift.id) {
      setHistory(null);
      return;
    }
    try {
      setHistory({ shiftId: shift.id, rows: await getScheduleShiftHistory(shift.id) });
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Änderungsverlauf konnte nicht geladen werden."));
    }
  }

  async function submitSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setNotice("");
    try {
      const updated = await updateScheduleSettings({
        time_zone: String(data.get("time_zone")).trim(),
        minimum_rest_hours: Number(data.get("minimum_rest_hours")),
      });
      setSettings(updated);
      setError("");
      await loadShifts();
    } catch (reason) {
      setError(messageFrom(reason, "Planungseinstellungen konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitAvailability(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!availabilityEmployeeId) return;
    setBusy(true);
    try {
      const saved = await updateEmployeeAvailability(availabilityEmployeeId, availabilityWindows);
      setAvailabilityWindows(saved.map(({ weekday, starts_at, ends_at }) => ({
        weekday,
        starts_at,
        ends_at,
      })));
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Verfügbarkeiten konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitAvailabilityRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const requestData = {
        kind: String(data.get("kind")) as ScheduleAvailabilityRequestKind,
        starts_at_local: String(data.get("starts_at_local")),
        ends_at_local: String(data.get("ends_at_local")),
        starts_at_fold: Number(data.get("starts_at_fold")),
        ends_at_fold: Number(data.get("ends_at_fold")),
        ...(canManage ? { employee_id: String(data.get("employee_id")) } : {}),
      };
      await createScheduleAvailabilityRequest(requestData);
      form.reset();
      setError("");
      setAvailabilityRequests(await getScheduleAvailabilityRequests(range.fromDate, range.toDate));
      await loadShifts();
    } catch (reason) {
      setError(messageFrom(reason, "Dienstwunsch oder Sperrzeit konnte nicht eingereicht werden."));
    } finally {
      setBusy(false);
    }
  }

  async function reviewAvailabilityRequest(
    item: ScheduleAvailabilityRequest,
    status: "accepted" | "rejected",
  ) {
    setBusy(true);
    try {
      await updateScheduleAvailabilityRequest(item.id, status);
      setAvailabilityRequests(await getScheduleAvailabilityRequests(range.fromDate, range.toDate));
      setError("");
      await loadShifts();
    } catch (reason) {
      setError(messageFrom(reason, "Dienstwunsch oder Sperrzeit konnte nicht bearbeitet werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitReplacement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!replacementFor) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await replaceScheduleShiftEmployee(
        replacementFor.id,
        String(data.get("employee_id")),
        String(data.get("reason")) as ScheduleReplacementReason,
      );
      setReplacementFor(null);
      setError("");
      await loadShifts();
      setNotice("Vertretung wurde eingetragen.");
    } catch (reason) {
      setError(messageFrom(reason, "Vertretung konnte nicht eingetragen werden."));
    } finally {
      setBusy(false);
    }
  }

  async function openReplacement(shift: ScheduleShift) {
    setReplacementFor(shift);
    setReplacementCandidates([]);
    setSelectedReplacementCandidateId("");
    setReplacementCandidatesError("");
    setBusy(true);
    setError("");
    try {
      setReplacementCandidates(await getScheduleShiftReplacementCandidates(shift.id));
    } catch (reason) {
      setReplacementCandidatesError(
        messageFrom(reason, "Passende Vertretungen konnten nicht ermittelt werden."),
      );
    } finally {
      setBusy(false);
    }
  }

  const focusRangeLabel = range.fromDate === range.toDate
    ? range.fromDate
    : `${range.fromDate} bis ${range.toDate}`;
  const eligibleReplacementCandidates = replacementCandidates.filter(
    (candidate) => candidate.is_eligible,
  );
  const selectedReplacementCandidate = eligibleReplacementCandidates.find(
    (candidate) => candidate.employee_id === selectedReplacementCandidateId,
  );
  const excludedReplacementCandidates = replacementCandidates.filter(
    (candidate) => !candidate.is_eligible,
  );

  return (
    <section className="scheduling-module">
      <section className="intro object-intro">
        <p className="eyebrow">EINSATZBETRIEB</p>
        <h1>Dienstplanung</h1>
        <p>Schichten planen, prüfen und nachvollziehbar veröffentlichen.</p>
      </section>
      {error && <p className="alert page-alert" role="alert">{error}</p>}
      {notice && <p className="success-message" role="status">{notice}</p>}

      <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">ÜBERSICHT</p><h2>Dienste</h2></div>
          <span className="result-count">{shifts.length} Einträge · {focusRangeLabel}</span>
        </div>
        <div className="filter-row">
          <label>Ansicht
            <select value={view} onChange={(event) => setView(event.target.value as ViewMode)}>
              <option value="day">Tag</option>
              <option value="week">Woche</option>
              <option value="month">Monat</option>
            </select>
          </label>
          <label>Stichtag
            <input type="date" value={focusDate} onChange={(event) => setFocusDate(event.target.value)} />
          </label>
          <div className="schedule-navigation">
            <button type="button" className="secondary-button" onClick={() => navigateDate(-1)}>Zurück</button>
            <button type="button" className="secondary-button" onClick={() => setFocusDate(dateString(new Date()))}>Heute</button>
            <button type="button" className="secondary-button" onClick={() => navigateDate(1)}>Weiter</button>
          </div>
          {employees.length > 0 && <label>Mitarbeiter
            <select value={employeeFilter} onChange={(event) => setEmployeeFilter(event.target.value)}>
              <option value="">Alle Mitarbeiter</option>
              {employees.map((employee) =>
                <option key={employee.id} value={employee.id}>
                  {employee.full_name} ({employee.employee_number})
                </option>,
              )}
            </select>
          </label>}
          {objects.length > 0 && <label>Objekt
            <select value={objectFilter} onChange={(event) => setObjectFilter(event.target.value)}>
              <option value="">Alle Objekte</option>
              {objects.map((obj) =>
                <option key={obj.id} value={obj.id}>{obj.name} ({obj.code})</option>,
              )}
            </select>
          </label>}
          <label className="checkbox-label">
            <input type="checkbox" checked={includeCancelled}
              onChange={(event) => setIncludeCancelled(event.target.checked)} />
            Abgesagte einblenden
          </label>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr>
              <th>Beginn / Ende</th><th>Mitarbeiter</th><th>Objekt</th><th>Pause / Qualifikation</th><th>Status</th><th>Aktionen</th>
            </tr></thead>
            <tbody>
              {shifts.map((shift) => (
                <tr
                  key={shift.id}
                  className={[
                    shift.status === "cancelled" ? "archived-row" : "",
                    shift.id === initialShiftId ? "search-result-row" : "",
                  ].filter(Boolean).join(" ")}
                >
                  <td>
                    <strong>{formatInstant(shift.starts_at, settings?.time_zone ?? shift.time_zone)}</strong>
                    <small>bis {formatInstant(shift.ends_at, settings?.time_zone ?? shift.time_zone)}</small>
                  </td>
                  <td><strong>{shift.employee_name}</strong><small>{shift.employee_number}</small></td>
                  <td><strong>{shift.object_name}</strong><small>{shift.object_code}</small></td>
                  <td>
                    {shift.break_minutes} Min. Pause
                    {shift.required_qualification && <small>{shift.required_qualification}</small>}
                  </td>
                  <td><span className={`status schedule-status-${shift.status}`}>
                    {shift.status === "published" ? "Veröffentlicht" : shift.status === "draft" ? "Entwurf" : "Abgesagt"}
                  </span></td>
                  <td>
                    <div className="schedule-actions">
                      {canManage && shift.status !== "cancelled" && <>
                        <button className="text-button" onClick={() => setEditing(shift)}>Bearbeiten</button>
                        {shift.status === "draft" && <button className="text-button" disabled={busy}
                          onClick={() => void changeShiftStatus(shift, "publish")}>Veröffentlichen</button>}
                        <button className="text-button danger-text" disabled={busy}
                          onClick={() => void changeShiftStatus(shift, "cancel")}>Absagen</button>
                        <button className="text-button" disabled={busy}
                          onClick={() => void openReplacement(shift)}>Vertretung</button>
                      </>}
                      <button className="text-button" onClick={() => void showHistory(shift)}>Verlauf</button>
                    </div>
                  </td>
                </tr>
              ))}
              {shifts.length === 0 && <tr><td className="empty" colSpan={6}>Keine Dienste im ausgewählten Zeitraum.</td></tr>}
            </tbody>
          </table>
        </div>
        {replacementFor && <form className="schedule-replacement-form" onSubmit={(event) => void submitReplacement(event)}>
          <div className="panel-heading">
            <div><p className="eyebrow">VERTRETUNG</p><h3>Vertretung für {replacementFor.employee_name}</h3></div>
            <button type="button" className="secondary-button" onClick={() => setReplacementFor(null)}>Abbrechen</button>
          </div>
          {replacementCandidatesError && <p className="alert" role="alert">{replacementCandidatesError}</p>}
          {busy ? <p className="muted" role="status">Vertretungen werden geprüft …</p>
            : replacementCandidatesError ? null
            : eligibleReplacementCandidates.length === 0
              ? <p className="empty">Für diesen Dienst wurde keine geeignete Vertretung gefunden.</p>
              : <label>Vertretende Person
                <select
                  name="employee_id"
                  required
                  value={selectedReplacementCandidateId}
                  onChange={(event) => setSelectedReplacementCandidateId(event.target.value)}
                >
                  <option value="" disabled>Bitte auswählen</option>
                  {eligibleReplacementCandidates.map((candidate) =>
                    <option key={candidate.employee_id} value={candidate.employee_id}>
                      {candidate.employee_name} ({candidate.employee_number})
                    </option>,
                  )}
                </select>
              </label>}
          {selectedReplacementCandidate && <section aria-label="Eignungsgründe">
            <strong>Geeignet, weil:</strong>
            <ul>{selectedReplacementCandidate.eligibility_reasons.map((reason) =>
              <li key={reason}>{reason}</li>,
            )}</ul>
          </section>}
          {excludedReplacementCandidates.length > 0 && <details>
            <summary>Ausgeschlossene Personen ({excludedReplacementCandidates.length})</summary>
            <ul>{excludedReplacementCandidates.map((candidate) =>
              <li key={candidate.employee_id}>
                <strong>{candidate.employee_name} ({candidate.employee_number})</strong>
                <ul>{candidate.exclusion_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
              </li>,
            )}</ul>
          </details>}
          <label>Grundkategorie der Vertretung
            <select name="reason" required defaultValue="short_notice">
              <option value="short_notice">Kurzfristiger Personalausfall</option>
              <option value="schedule_change">Dienstplanänderung</option>
              <option value="employee_request">Mitarbeiterwunsch</option>
              <option value="qualification">Qualifikationsanforderung</option>
              <option value="other">Sonstiger betrieblicher Grund</option>
            </select>
          </label>
          <p className="muted">Keine Gesundheits- oder anderen sensiblen Personendaten eintragen.</p>
          <button
            type="submit"
            disabled={busy || !selectedReplacementCandidate}
          >
            Vertretung erneut prüfen und speichern
          </button>
        </form>}
        {history && <section className="schedule-history">
          <h3>Änderungsverlauf</h3>
          {history.rows.length === 0
            ? <p className="muted">Keine Verlaufseinträge vorhanden.</p>
            : <ul className="history-list">{history.rows.map((item) => {
              const previousId = typeof item.details.previous_employee_id === "string"
                ? item.details.previous_employee_id
                : "";
              const replacementId = typeof item.details.replacement_employee_id === "string"
                ? item.details.replacement_employee_id
                : "";
              const reason = typeof item.details.reason === "string" ? item.details.reason : "";
              const previousEmployee = employees.find((employee) => employee.id === previousId);
              const replacementEmployee = employees.find((employee) => employee.id === replacementId);
              return <li key={item.id}>
                <strong>{actionNames[item.action] ?? item.action}</strong>
                <time>{formatInstant(item.created_at, settings?.time_zone ?? "UTC")}</time>
                <small>Geänderte Felder: {item.changed_fields.join(", ")}</small>
                {item.action === "replaced" && <small>
                  {previousEmployee?.full_name ?? previousId} → {replacementEmployee?.full_name ?? replacementId}
                  {reason && ` · Grund: ${reason}`}
                </small>}
              </li>;
            })}</ul>}
        </section>}
      </section>

      {canManage && <div className="scheduling-lower">
        <section className="panel form-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">PLANUNG</p><h2>{editing ? "Dienst bearbeiten" : "Dienst anlegen"}</h2></div>
            {editing && <button className="secondary-button" onClick={() => setEditing(null)}>Abbrechen</button>}
          </div>
          {!settings && <p className="muted">Planungseinstellungen werden geladen …</p>}
          {settings && (employees.length === 0 || objects.length === 0)
            ? <p className="muted">Für die Planung werden sichtbare Mitarbeiter und aktive Objekte benötigt.</p>
            : settings && <form key={editing?.id ?? "new-shift"} onSubmit={(event) => void submitShift(event)}>
              <label>Mitarbeiter
                <select name="employee_id" required defaultValue={editing?.employee_id ?? ""}>
                  <option value="" disabled>Bitte auswählen</option>
                  {employees.map((employee) =>
                    <option key={employee.id} value={employee.id}>
                      {employee.full_name} ({employee.employee_number})
                    </option>,
                  )}
                </select>
              </label>
              <label>Objekt
                <select name="object_id" required defaultValue={editing?.object_id ?? ""}>
                  <option value="" disabled>Bitte auswählen</option>
                  {objects.map((obj) => <option key={obj.id} value={obj.id}>{obj.name} ({obj.code})</option>)}
                </select>
              </label>
              <div className="form-row">
                <label>Beginn ({settings.time_zone})
                  <input name="starts_at_local" type="datetime-local" required
                    defaultValue={editing ? localInputValue(editing.starts_at, settings.time_zone) : ""} />
                </label>
                <label>Ende ({settings.time_zone})
                  <input name="ends_at_local" type="datetime-local" required
                    defaultValue={editing ? localInputValue(editing.ends_at, settings.time_zone) : ""} />
                </label>
              </div>
              <div className="form-row">
                <label>Beginn bei doppelter Uhrzeit
                  <select name="starts_at_fold" defaultValue={editing
                    ? foldForInstant(editing.starts_at, localInputValue(editing.starts_at, settings.time_zone), settings.time_zone)
                    : 0}>
                    <option value={0}>Erstes Auftreten</option><option value={1}>Zweites Auftreten</option>
                  </select>
                </label>
                <label>Ende bei doppelter Uhrzeit
                  <select name="ends_at_fold" defaultValue={editing
                    ? foldForInstant(editing.ends_at, localInputValue(editing.ends_at, settings.time_zone), settings.time_zone)
                    : 0}>
                    <option value={0}>Erstes Auftreten</option><option value={1}>Zweites Auftreten</option>
                  </select>
                </label>
              </div>
              <label>Pause in Minuten
                <input name="break_minutes" type="number" min="0" max="1440"
                  defaultValue={editing?.break_minutes ?? 0} required />
              </label>
              <label>Erforderliche Qualifikation (optional)
                <input name="required_qualification" maxLength={160}
                  defaultValue={editing?.required_qualification ?? ""} />
              </label>
              <button type="submit" disabled={busy || !settings}>
                {busy ? "Wird gespeichert …" : editing ? "Änderungen speichern" : "Entwurf anlegen"}
              </button>
            </form>}
        </section>
        {settings && <section className="panel form-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">REGELN</p><h2>Planungseinstellungen</h2></div>
          </div>
          <form onSubmit={(event) => void submitSettings(event)}>
            <label>IANA-Zeitzone
              <input name="time_zone" defaultValue={settings.time_zone} required maxLength={80}
                key={`${settings.time_zone}-${settings.updated_at}`} />
            </label>
            <label>Mindestabstand zwischen Diensten (Stunden)
              <input name="minimum_rest_hours" type="number" min="0" max="168"
                defaultValue={settings.minimum_rest_hours} required
                key={`${settings.minimum_rest_hours}-${settings.updated_at}`} />
            </label>
            <button type="submit" disabled={busy}>Einstellungen speichern</button>
          </form>
          <p className="muted schedule-disclaimer">
            Ruhezeit ist eine konfigurierbare Planungsregel, keine automatische Rechtsprüfung oder
            Zusicherung gesetzlicher Konformität.
          </p>
        </section>}
      </div>}
      {(canRequestAvailability || (canManage && employees.length > 0)) && <div className="scheduling-support">
        {canManage && employees.length > 0 && <section className="panel form-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">VERFÜGBARKEIT</p><h2>Regelmäßige Zeitfenster</h2></div>
          </div>
          <label>Mitarbeiter
            <select value={availabilityEmployeeId}
              onChange={(event) => setAvailabilityEmployeeId(event.target.value)}>
              {employees.map((employee) =>
                <option key={employee.id} value={employee.id}>
                  {employee.full_name} ({employee.employee_number})
                </option>,
              )}
            </select>
          </label>
          <form className="schedule-availability-form" onSubmit={(event) => void submitAvailability(event)}>
            {availabilityWindows.map((window, index) =>
              <div className="schedule-window-row" key={`${window.weekday}-${window.starts_at}-${index}`}>
                <label>Wochentag
                  <select value={window.weekday} onChange={(event) => setAvailabilityWindows((current) =>
                    current.map((item, itemIndex) => itemIndex === index
                      ? { ...item, weekday: Number(event.target.value) }
                      : item),
                  )}>
                    {weekdayNames.map((day, weekday) =>
                      <option key={day} value={weekday}>{day}</option>,
                    )}
                  </select>
                </label>
                <label>Von
                  <input type="time" required value={window.starts_at.slice(0, 5)}
                    onChange={(event) => setAvailabilityWindows((current) =>
                      current.map((item, itemIndex) => itemIndex === index
                        ? { ...item, starts_at: event.target.value }
                        : item),
                    )} />
                </label>
                <label>Bis
                  <input type="time" required value={window.ends_at.slice(0, 5)}
                    onChange={(event) => setAvailabilityWindows((current) =>
                      current.map((item, itemIndex) => itemIndex === index
                        ? { ...item, ends_at: event.target.value }
                        : item),
                    )} />
                </label>
                <button type="button" className="text-button danger-text"
                  onClick={() => setAvailabilityWindows((current) =>
                    current.filter((_item, itemIndex) => itemIndex !== index),
                  )}>Entfernen</button>
              </div>,
            )}
            <div className="schedule-form-actions">
              <button type="button" className="secondary-button" onClick={() =>
                setAvailabilityWindows((current) => [
                  ...current,
                  { weekday: 0, starts_at: "09:00", ends_at: "17:00" },
                ])
              }>Zeitfenster hinzufügen</button>
              <button type="submit" disabled={busy}>Verfügbarkeit speichern</button>
            </div>
          </form>
          <p className="muted schedule-disclaimer">
            Ohne gespeicherte Fenster gilt keine regelmäßige Einschränkung. Sobald Fenster
            eingetragen sind, muss jeder Dienst an jedem lokalen Kalendertag vollständig darin liegen.
          </p>
        </section>}
        <section className="panel form-panel">
          <div className="panel-heading">
            <div><p className="eyebrow">DIENSTWÜNSCHE</p>
              <h2>{canManage ? "Wunsch oder Sperrzeit erfassen" : "Eigene Zeitwünsche"}</h2></div>
          </div>
          {canRequestAvailability && (!canManage || employees.length > 0) && <>
            <form className="schedule-request-form" onSubmit={(event) => void submitAvailabilityRequest(event)}>
              {canManage && <label>Mitarbeiter
                <select name="employee_id" required defaultValue="">
                  <option value="" disabled>Bitte auswählen</option>
                  {employees.map((employee) =>
                    <option key={employee.id} value={employee.id}>
                      {employee.full_name} ({employee.employee_number})
                    </option>,
                  )}
                </select>
              </label>
              }
              <label>Art
                <select name="kind" defaultValue="preferred">
                  <option value="preferred">Gewünschter Einsatzzeitraum</option>
                  <option value="blocked">Sperrzeit</option>
                </select>
              </label>
              <div className="form-row">
                <label>Beginn ({settings?.time_zone ?? "Zeitzone wird geladen"})
                  <input name="starts_at_local" type="datetime-local" required />
                </label>
                <label>Ende ({settings?.time_zone ?? "Zeitzone wird geladen"})
                  <input name="ends_at_local" type="datetime-local" required />
                </label>
              </div>
              <div className="form-row">
                <label>Beginn bei doppelter Uhrzeit
                  <select name="starts_at_fold" defaultValue={0}>
                    <option value={0}>Erstes Auftreten</option><option value={1}>Zweites Auftreten</option>
                  </select>
                </label>
                <label>Ende bei doppelter Uhrzeit
                  <select name="ends_at_fold" defaultValue={0}>
                    <option value={0}>Erstes Auftreten</option><option value={1}>Zweites Auftreten</option>
                  </select>
                </label>
              </div>
              <button type="submit" disabled={busy || !settings}>Zeitraum einreichen</button>
            </form>
            <p className="muted schedule-disclaimer">
              Offene und angenommene Sperrzeiten verhindern neue Zuordnungen. Überschneidungen mit
              bestehenden Diensten bleiben sichtbar und müssen vor Annahme geklärt werden. Wünsche
              sind unverbindliche Planungshinweise.
            </p>
          </>}
          {canManage || canRequestAvailability ? <>
            <h3 className="schedule-request-heading">Wünsche und Sperrzeiten im Zeitraum</h3>
            {availabilityRequests.length === 0
              ? <p className="muted">Keine Einträge im angezeigten Zeitraum.</p>
              : <ul className="schedule-request-list">{availabilityRequests.map((item) =>
                <li key={item.id}>
                  <div>
                    <strong>{item.kind === "blocked" ? "Sperrzeit" : "Dienstwunsch"} · {item.employee_name}</strong>
                    <small>{formatInstant(item.starts_at, item.time_zone)} bis {formatInstant(item.ends_at, item.time_zone)}</small>
                    {item.conflicting_shift_ids.length > 0 && <small className="schedule-request-conflict">
                      {item.conflicting_shift_ids.length} bestehende(r) Dienst(e) überschneiden sich.
                    </small>}
                  </div>
                  <div className="schedule-request-actions">
                    <span className="status">
                      {item.status === "open" ? "Offen" : item.status === "accepted" ? "Angenommen" : "Abgelehnt"}
                    </span>
                    {canManage && item.status === "open" && <>
                      <button type="button" className="text-button" disabled={busy || item.conflicting_shift_ids.length > 0}
                        onClick={() => void reviewAvailabilityRequest(item, "accepted")}>Annehmen</button>
                      <button type="button" className="text-button danger-text" disabled={busy}
                        onClick={() => void reviewAvailabilityRequest(item, "rejected")}>Ablehnen</button>
                    </>}
                  </div>
                </li>,
              )}</ul>}
          </> : null}
        </section>
      </div>}
    </section>
  );
}
