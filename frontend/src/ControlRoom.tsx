import { useEffect, useRef, useState } from "react";
import {
  exportObjectOperationsReport,
  getControlRoom,
  getObjectOperationsReport,
  getSession,
} from "./api";
import ControlRoomActions from "./ControlRoomActions";
import type {
  AuthUser,
  ControlRoom as ControlRoomData,
  ObjectOperationsReport as ObjectOperationsReportData,
} from "./types";

type StatusFilter =
  | ""
  | "überfällig"
  | "dringend"
  | "open"
  | "in_progress"
  | "blocked"
  | "reported"
  | "investigating"
  | "action_required"
  | "pending"
  | "approved"
  | "high"
  | "normal"
  | "low"
  | "critical"
  | "warning"
  | "published";

const dateInUtc = (date: Date) => date.toISOString().slice(0, 10);
const initialFromDate = () => {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - 7);
  return dateInUtc(date);
};
const initialToDate = () => {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() + 30);
  return dateInUtc(date);
};

function dateTime(value: string) {
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value)) + " UTC";
}

function date(value: string) {
  return new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeZone: "UTC" })
    .format(new Date(`${value}T00:00:00Z`));
}

function statusName(value: string) {
  const names: Record<string, string> = {
    open: "Offen",
    in_progress: "In Bearbeitung",
    blocked: "Blockiert",
    reported: "Gemeldet",
    investigating: "In Prüfung",
    action_required: "Maßnahme erforderlich",
    pending: "Ausstehend",
    approved: "Genehmigt",
    critical: "Kritisch",
    warning: "Warnung",
    missed: "Versäumte Kontrolle",
    deviation: "Abweichung",
    manipulation: "Manipulation",
    notification: "Alarmmeldung",
    control: "Kontrolle",
    entry: "Eintrag",
    handover: "Übergabe",
    low: "Niedrig",
    normal: "Normal",
    high: "Hoch",
    urgent: "Dringend",
    vacation: "Urlaub",
    sick_leave: "Krankheit",
    other: "Sonstige",
  };
  return names[value] ?? value;
}

export default function ControlRoom() {
  const [data, setData] = useState<ControlRoomData | null>(null);
  const [report, setReport] = useState<ObjectOperationsReportData | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [objectId, setObjectId] = useState("");
  const [fromDate, setFromDate] = useState(initialFromDate);
  const [toDate, setToDate] = useState(initialToDate);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [userError, setUserError] = useState("");
  const [reportError, setReportError] = useState("");
  const [reportLoading, setReportLoading] = useState(true);
  const [reportExporting, setReportExporting] = useState(false);
  const [reportOffset, setReportOffset] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const requestId = useRef(0);
  const reportRequestId = useRef(0);
  const reportLimit = 50;

  useEffect(() => {
    getSession()
      .then((session) => {
        setUser(session.user);
        setUserError("");
      })
      .catch((reason: unknown) => {
        setUser(null);
        setUserError(
          reason instanceof Error
            ? reason.message
            : "Berechtigungen für Leitstellenaktionen konnten nicht geladen werden.",
        );
      });
  }, []);

  useEffect(() => {
    const currentRequest = ++requestId.current;
    setLoading(true);
    setError("");
    getControlRoom({
      object_id: objectId || undefined,
      from_date: fromDate,
      to_date: toDate,
    })
      .then((response) => {
        if (requestId.current === currentRequest) setData(response);
      })
      .catch((reason: unknown) => {
        if (requestId.current === currentRequest) {
          setData(null);
          setError(reason instanceof Error ? reason.message : "Leitstellendaten konnten nicht geladen werden.");
        }
      })
      .finally(() => {
        if (requestId.current === currentRequest) setLoading(false);
      });
    return () => {
      requestId.current += 1;
    };
  }, [fromDate, objectId, refreshKey, toDate]);

  useEffect(() => {
    const currentRequest = ++reportRequestId.current;
    setReportLoading(true);
    setReportError("");
    getObjectOperationsReport({
      object_id: objectId || undefined,
      from_date: fromDate,
      to_date: toDate,
      limit: reportLimit,
      offset: reportOffset,
    })
      .then((response) => {
        if (reportRequestId.current === currentRequest) setReport(response);
      })
      .catch((reason: unknown) => {
        if (reportRequestId.current === currentRequest) {
          setReport(null);
          setReportError(reason instanceof Error ? reason.message : "Objektbericht konnte nicht geladen werden.");
        }
      })
      .finally(() => {
        if (reportRequestId.current === currentRequest) setReportLoading(false);
      });
    return () => {
      reportRequestId.current += 1;
    };
  }, [fromDate, objectId, refreshKey, reportLimit, reportOffset, toDate]);

  const downloadReport = async () => {
    setReportExporting(true);
    setReportError("");
    try {
      const blob = await exportObjectOperationsReport({
        object_id: objectId || undefined,
        from_date: fromDate,
        to_date: toDate,
        limit: reportLimit,
        offset: reportOffset,
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "objektbetriebsbericht.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setReportError(reason instanceof Error ? reason.message : "CSV-Export fehlgeschlagen.");
    } finally {
      setReportExporting(false);
    }
  };

  const counts = data?.counts ?? {};
  const cards = [
    ["Aktive Objekte", "active_objects"],
    ["Laufende Dienste", "active_shifts"],
    ["Offene Kontrollen / Alarme", "open_owks_events"],
    ["Unbestätigte Übergaben", "pending_handovers"],
    ["Offene Vorfälle", "open_incidents"],
    ["Überfällige Vorfälle", "overdue_incidents"],
    ["Offene Aufgaben", "open_tasks"],
    ["Dringende Aufgaben", "urgent_tasks"],
    ["Personalausfälle", "active_absences"],
    ["Qualifikationsprobleme", "qualification_problems"],
    ["Abrechnungsfreigaben", "billing_approvals"],
  ] as const;
  const visibleCards = cards.filter(([, key]) => key in counts);
  const matchesStatus = (
    status: string,
    overdue: boolean,
    urgent = false,
    severityOrPriority = "",
  ) => {
    if (!statusFilter) return true;
    if (statusFilter === "überfällig") return overdue;
    if (statusFilter === "dringend") return urgent;
    return status === statusFilter || severityOrPriority === statusFilter;
  };

  return (
    <section className="control-room">
      <div className="panel-heading">
        <div><p className="eyebrow">OPERATIONSÜBERSICHT</p><h2>Leitstelle</h2></div>
        <button className="secondary-button" onClick={() => setRefreshKey((value) => value + 1)}
          disabled={loading}>Aktualisieren</button>
      </div>
      <div className="control-room-filters" aria-label="Leitstellen- und Berichtsfilter">
        <label>Objekt
          <select value={objectId} onChange={(event) => {
            setObjectId(event.target.value);
            setReportOffset(0);
          }}>
            <option value="">Alle zugänglichen Objekte</option>
            {(data?.objects ?? []).map((object) =>
              <option key={object.id} value={object.id}>{object.name} ({object.code})</option>)}
          </select>
        </label>
        <label>Zeitraum von
          <input type="date" value={fromDate} onChange={(event) => {
            setFromDate(event.target.value);
            setReportOffset(0);
          }} />
        </label>
        <label>Zeitraum bis
          <input type="date" value={toDate} onChange={(event) => {
            setToDate(event.target.value);
            setReportOffset(0);
          }} />
        </label>
        <label>Status / Priorität
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}>
            <option value="">Alle</option>
            <option value="überfällig">Überfällig</option>
            <option value="dringend">Dringend</option>
            <option value="open">Offen</option>
            <option value="in_progress">In Bearbeitung</option>
            <option value="blocked">Blockiert</option>
            <option value="reported">Gemeldet</option>
            <option value="investigating">In Prüfung</option>
            <option value="action_required">Maßnahme erforderlich</option>
            <option value="pending">Ausstehend</option>
            <option value="approved">Genehmigt</option>
            <option value="high">Hoch</option>
            <option value="normal">Normal</option>
            <option value="low">Niedrig</option>
            <option value="critical">Kritisch</option>
            <option value="warning">Warnung</option>
            <option value="published">Veröffentlicht</option>
          </select>
        </label>
      </div>

      {loading && <p className="muted" role="status">Leitstellendaten werden geladen …</p>}
      {error && <p className="alert page-alert" role="alert">{error}</p>}
      {userError && <p className="alert page-alert" role="alert">{userError}</p>}
      {!loading && !error && data && <>
        <p className="control-room-updated">
          Erstellt am {dateTime(data.generated_at)} · Zeitraum {date(data.range_start)} bis {date(data.range_end)} (UTC)
        </p>
        <section className="control-room-stats" aria-label="Leitstellenkennzahlen">
          {visibleCards.map(([label, key]) =>
            <article className="stat-card" key={key}>
              <span>{label}</span><strong>{counts[key]}</strong>
            </article>)}
        </section>

        <div className="control-room-grid">
          {data.objects && <article className="panel control-room-panel">
            <h3>Aktive Objekte <span>{counts.active_objects ?? data.objects.length}</span></h3>
            {data.objects.length === 0 ? <p className="empty">Keine aktiven, zugänglichen Objekte.</p> :
              <ul>{data.objects.map((item) =>
                <li key={item.id}><strong>{item.name}</strong><small>{item.code}</small></li>)}</ul>}
          </article>}
          {data.shifts && <article className="panel control-room-panel">
            <h3>Laufende Dienste <span>{counts.active_shifts ?? data.shifts.length}</span></h3>
            {data.shifts.filter((item) => matchesStatus(item.status, false)).length === 0 ? <p className="empty">Keine passenden veröffentlichten Dienste laufen derzeit.</p> :
              <ul>{data.shifts.filter((item) => matchesStatus(item.status, false)).map((item) =>
                <li key={item.id}><strong>{item.employee_name} · {item.object_name}</strong>
                  <small>Bis {dateTime(item.ends_at)} · Veröffentlicht</small></li>)}</ul>}
          </article>}
          {data.owks_events && <article className="panel control-room-panel">
            <h3>Kontrollen und Alarmmeldungen <span>{counts.open_owks_events ?? data.owks_events.length}</span></h3>
            {data.owks_events.filter((item) => matchesStatus(item.status, false) &&
              matchesStatus(item.severity, false, item.severity === "critical", item.severity)).length === 0
              ? <p className="empty">Keine passenden offenen Kontrollereignisse im Zeitraum.</p>
              : <ul>{data.owks_events.filter((item) => matchesStatus(item.status, false) &&
                matchesStatus(item.severity, false, item.severity === "critical", item.severity)).map((item) =>
                <li key={item.id}><strong>{item.title}</strong>
                  <small>{item.object_name} · {statusName(item.event_type)} · {statusName(item.severity)} · {statusName(item.status)} · {dateTime(item.occurred_at)}</small></li>)}</ul>}
          </article>}
          {data.pending_handovers && <article className="panel control-room-panel">
           <h3>Unbestätigte Schichtübergaben <span>{counts.pending_handovers ?? data.pending_handovers.length}</span></h3>
           {!data.pending_handovers.length
             ? <p className="empty">Keine unbestätigten Übergaben im erreichbaren Objektbereich.</p>
             : <ul>{data.pending_handovers.map((item) =>
               <li key={item.id}>
                 <strong>{item.sender_name ?? "Mitarbeiter"} → {item.recipient_name ?? "Mitarbeiter"}</strong>
                 <small>{item.object_name} · Übergabe vom {dateTime(item.created_at)}</small>
               </li>,
             )}</ul>}
          </article>}
          {data.incidents && <article className="panel control-room-panel">
            <h3>Offene Vorfälle <span>{counts.open_incidents ?? data.incidents.length}</span></h3>
            {data.incidents.filter((item) =>
              matchesStatus(item.status,
              Boolean(item.due_at && Date.parse(item.due_at) < Date.now()),
              false,
              item.severity),
            ).length === 0 ? <p className="empty">Keine passenden offenen Vorfälle.</p> :
              <ul>{data.incidents.filter((item) =>
                matchesStatus(item.status,
                Boolean(item.due_at && Date.parse(item.due_at) < Date.now()),
                false,
                item.severity),
              ).map((item) =>
                <li key={item.id}><strong>{item.title}</strong>
                  <small>{item.object_name} · {statusName(item.status)} · {statusName(item.severity)} · Verantwortlich: {item.assigned_to_name}
                    {item.due_at ? ` · Fällig ${dateTime(item.due_at)}` : ""}</small></li>)}</ul>}
          </article>}
          {data.tasks && <article className="panel control-room-panel">
            <h3>Offene Aufgaben <span>{counts.open_tasks ?? data.tasks.length}</span></h3>
            {data.tasks.filter((item) =>
              matchesStatus(item.status,
              Boolean(item.due_at && Date.parse(item.due_at) < Date.now()),
              item.priority === "urgent" || Boolean(item.due_at && Date.parse(item.due_at) < Date.now()),
              item.priority),
            ).length === 0 ? <p className="empty">Keine passenden offenen Aufgaben.</p> :
              <ul>{data.tasks.filter((item) =>
                matchesStatus(item.status,
                Boolean(item.due_at && Date.parse(item.due_at) < Date.now()),
                item.priority === "urgent" || Boolean(item.due_at && Date.parse(item.due_at) < Date.now()),
                item.priority),
              ).map((item) =>
                <li key={item.id}><strong>{item.title}</strong>
                  <small>{item.object_name ?? "Ohne Objekt"} · {statusName(item.status)} · {statusName(item.priority)} · Verantwortlich: {item.assigned_to_name}
                    {item.due_at ? ` · Fällig ${dateTime(item.due_at)}` : ""}</small></li>)}</ul>}
          </article>}
          {data.absences && <article className="panel control-room-panel">
            <h3>Personalausfälle <span>{counts.active_absences ?? data.absences.length}</span></h3>
            {data.absences.filter((item) => matchesStatus(item.status, false)).length === 0 ? <p className="empty">Keine passenden offenen oder bestätigten Abwesenheiten im Zeitraum.</p> :
              <ul>{data.absences.filter((item) => matchesStatus(item.status, false)).map((item, index) =>
                <li key={`${item.employee_id}-${item.starts_on}-${index}`}><strong>{item.employee_name}</strong>
                  <small>{statusName(item.absence_type)} · {statusName(item.status)} · {date(item.starts_on)}–{date(item.ends_on)}</small></li>)}</ul>}
          </article>}
          {data.qualifications && <article className="panel control-room-panel">
            <h3>Qualifikationen <span>{counts.qualification_problems ?? data.qualifications.length}</span></h3>
            {data.qualifications.filter((item) =>
              matchesStatus("open", item.expires_on < dateInUtc(new Date())),
            ).length === 0 ? <p className="empty">Keine passenden abgelaufenen oder auslaufenden Qualifikationen.</p> :
              <ul>{data.qualifications.filter((item) =>
                matchesStatus("open", item.expires_on < dateInUtc(new Date())),
              ).map((item, index) =>
                <li key={`${item.employee_id}-${item.name}-${index}`}><strong>{item.name} · {item.employee_name}</strong>
                  <small>{item.category} · {item.expires_on < dateInUtc(new Date()) ? "Abgelaufen am" : "Läuft aus am"} {date(item.expires_on)}</small></li>)}</ul>}
          </article>}
          {data.billing_approvals && <article className="panel control-room-panel">
            <h3>Offene Abrechnungsfreigaben <span>{counts.billing_approvals ?? data.billing_approvals.length}</span></h3>
            {data.billing_approvals.length === 0 ? <p className="empty">Keine offenen Rechnungsfreigaben für zugängliche Objekte.</p> :
              <ul>{data.billing_approvals.map((item) =>
                <li key={item.id}><strong>{item.invoice_number} · {item.object_name}</strong>
                  <small>Rechnungsdatum {date(item.issued_on)} · Erstellt {dateTime(item.created_at)}</small></li>)}</ul>}
          </article>}
        </div>
      </>}
      <section className="object-operations-report panel" aria-labelledby="object-operations-report-title">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">AGGREGIERTE OBJEKTDATEN</p>
            <h3 id="object-operations-report-title">Objektbetriebsbericht</h3>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={downloadReport}
            disabled={!report || reportLoading || reportExporting}
          >
            {reportExporting ? "CSV wird erstellt …" : "CSV herunterladen (aktuelle Seite)"}
          </button>
        </div>
        {reportLoading && <p className="muted" role="status">Objektbericht wird geladen …</p>}
        {reportError && <p className="alert page-alert" role="alert">{reportError}</p>}
        {!reportLoading && report && <>
          <p className="muted">
            {report.total} zugängliche Objekte · Seite mit {report.items.length} Einträgen · Zeitraum in UTC
          </p>
          <div className="object-operations-table-wrap">
            <table className="object-operations-table">
              <thead><tr>
                <th scope="col">Objekt</th>
                <th scope="col">Veröffentlichte, zugewiesene Schichten</th>
                <th scope="col">Erstellte Vorfälle</th>
                <th scope="col">Kontrollereignisse</th>
                <th scope="col">Versäumte Kontrollen</th>
                <th scope="col">Schichten mit Qualifikationslücken</th>
                <th scope="col">Aufgaben offen</th>
                <th scope="col">In Bearbeitung</th>
                <th scope="col">Blockiert</th>
                <th scope="col">Abgeschlossen</th>
                <th scope="col">Abgebrochen</th>
              </tr></thead>
              <tbody>
                {report.items.map((item) => <tr key={item.object_id}>
                  <th scope="row">{item.object_name} ({item.object_code})</th>
                  <td>{item.published_assigned_shifts}</td>
                  <td>{item.incidents_created}</td>
                  <td>{item.control_events}</td>
                  <td>{item.missed_controls}</td>
                  <td>{item.qualification_conflict_shifts ?? "–"}</td>
                  <td>{item.task_status_counts.open}</td>
                  <td>{item.task_status_counts.in_progress}</td>
                  <td>{item.task_status_counts.blocked}</td>
                  <td>{item.task_status_counts.completed}</td>
                  <td>{item.task_status_counts.cancelled}</td>
                </tr>)}
              </tbody>
            </table>
          </div>
          {report.items.length === 0 && <p className="empty">Keine aktiven, zugänglichen Objekte im Bericht.</p>}
          <div className="object-operations-pagination">
            <span>Einträge {report.total === 0 ? 0 : report.offset + 1}–{report.offset + report.items.length} von {report.total}</span>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setReportOffset(Math.max(0, reportOffset - reportLimit))}
              disabled={reportOffset === 0}
            >Zurück</button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => setReportOffset(reportOffset + reportLimit)}
              disabled={!report.has_more}
            >Weiter</button>
          </div>
          <p className="object-operations-definition">
            Schichten sind veröffentlichte und im Modell einer Person zugewiesene Dienste, die den Zeitraum berühren.
            Vorfälle zählen nach Erstellungszeit; Kontrollereignisse und versäumte Kontrollen nach OWKS-Ereigniszeit.
            Aufgaben zählen nach Erstellungszeit und ihrem aktuellen Status. Personen- oder Vorfalltexte werden nicht ausgegeben.
            Qualifikationslücken zählen veröffentlichte Dienste, die zum Berechnungszeitpunkt noch nicht beendet sind und deren aktuelle Nachweise nicht alle Schicht- und Objektanforderungen über den gesamten Dienst abdecken.
            Die Kennzahl erfordert Mitarbeiter-Leserecht und ist keine rückwirkende Aussage über die damalige Besetzungsfreigabe.
            Eine Besetzungs- oder Ausfallquote wird mangels fachlich bestätigter Sollbesetzung und Ausfalldefinition nicht berechnet.
          </p>
        </>}
      </section>
      {user && <ControlRoomActions user={user} />}
    </section>
  );
}
