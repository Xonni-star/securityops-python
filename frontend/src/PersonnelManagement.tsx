import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  archiveEmployee,
  archiveEmployeeQualification,
  assignEmployeeToObject,
  createEmployee,
  createEmployeeAbsence,
  createEmployeeQualification,
  employeeQualificationDocumentUrl,
  endEmployeeObjectAssignment,
  getEmployee,
  getEmployeeLinkedUserCandidates,
  getEmployeeObjectAssignmentCandidates,
  getEmployeeObjectAssignmentHistory,
  getEmployeeObjectAssignments,
  getEmployeeAbsences,
  getEmployeeHistory,
  getEmployeeQualificationDocuments,
  getEmployeeQualifications,
  getEmployees,
  getEmployeeSensitiveDetails,
  getExpiringEmployeeQualifications,
  reactivateEmployee,
  updateEmployee,
  updateEmployeeAbsence,
  updateEmployeeSensitiveDetails,
  uploadEmployeeQualificationDocument,
} from "./api";
import type {
  AuthUser,
  Employee,
  EmployeeAccountCandidate,
  EmployeeAbsence,
  EmployeeAbsenceStatus,
  EmployeeAbsenceType,
  EmployeeHistory,
  EmployeeObjectAssignment,
  EmployeeObjectAssignmentHistory,
  EmployeeObjectCandidate,
  EmployeeQualification,
  EmployeeQualificationDocument,
  EmployeeSensitiveDetails,
  EmployeeStatus,
} from "./types";

const pageSize = 25;

const employeeStatuses: Record<EmployeeStatus, string> = {
  active: "Aktiv",
  inactive: "Inaktiv",
  leave: "Abwesend",
  terminated: "Ausgeschieden",
};

const absenceTypes: Record<EmployeeAbsenceType, string> = {
  vacation: "Urlaub",
  sick_leave: "Krankheit",
  other: "Sonstige",
};

const absenceStatuses: Record<EmployeeAbsenceStatus, string> = {
  pending: "Offen",
  approved: "Genehmigt",
  rejected: "Abgelehnt",
};

const historyActions: Record<string, string> = {
  created: "Personalakte angelegt",
  updated: "Stammdaten geändert",
  archived: "Personalakte archiviert",
  reactivated: "Personalakte reaktiviert",
  sensitive_updated: "Vertrauliche Personaldaten geändert",
  qualification_created: "Qualifikationsnachweis hinzugefügt",
  qualification_updated: "Qualifikationsnachweis geändert",
  qualification_archived: "Qualifikationsnachweis archiviert",
  absence_created: "Abwesenheit erfasst",
  absence_updated: "Abwesenheit geändert",
  qualification_document_uploaded: "Qualifikationsdatei hinzugefügt",
  object_assignment_assigned: "Objektzuweisung begonnen",
  object_assignment_ended: "Objektzuweisung beendet",
};

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function optionalValue(data: FormData, name: string) {
  return String(data.get(name) ?? "").trim() || null;
}

export default function PersonnelManagement({
  user,
  initialSearch = "",
  initialEmployeeId = null,
}: {
  user: AuthUser;
  initialSearch?: string;
  initialEmployeeId?: string | null;
}) {
  const canRead = user.permissions.includes("employees.read");
  const canManage = user.permissions.includes("employees.manage");
  const canReadSensitive = user.permissions.includes("employees.sensitive.read");
  const canManageSensitive = user.permissions.includes("employees.sensitive.manage");
  const canReadAbsences = user.permissions.includes("employees.absences.read");
  const canManageAbsences = user.permissions.includes("employees.absences.manage");
  const canReadDocuments = user.permissions.includes("employees.documents.read");
  const canManageDocuments = user.permissions.includes("employees.documents.manage");
  const canManageObjectAssignments = canManage && user.permissions.includes("objects.assign");

  const [employees, setEmployees] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState(initialSearch);
  const [statusFilter, setStatusFilter] = useState<EmployeeStatus | "">("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [sortBy, setSortBy] = useState<
    "employee_number" | "full_name" | "hired_on" | "employment_status"
  >("full_name");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Employee | null>(null);
  const [qualifications, setQualifications] = useState<EmployeeQualification[]>([]);
  const [qualificationDocuments, setQualificationDocuments] =
    useState<EmployeeQualificationDocument[]>([]);
  const [accountCandidates, setAccountCandidates] = useState<EmployeeAccountCandidate[]>([]);
  const [objectAssignments, setObjectAssignments] = useState<EmployeeObjectAssignment[]>([]);
  const [objectAssignmentHistory, setObjectAssignmentHistory] =
    useState<EmployeeObjectAssignmentHistory[]>([]);
  const [objectCandidates, setObjectCandidates] = useState<EmployeeObjectCandidate[]>([]);
  const [objectSelection, setObjectSelection] = useState("");
  const [absences, setAbsences] = useState<EmployeeAbsence[]>([]);
  const [history, setHistory] = useState<EmployeeHistory[]>([]);
  const [expiring, setExpiring] = useState<Array<EmployeeQualification & {
    employee_number: string;
    employee_name: string;
    days_until_expiry: number;
  }>>([]);
  const [sensitive, setSensitive] = useState<EmployeeSensitiveDetails | null>(null);
  const [sensitiveForm, setSensitiveForm] = useState({
    address: "",
    emergency_contact: "",
    internal_notes: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadEmployees = useCallback(async () => {
    if (!canRead) return;
    try {
      const page = await getEmployees({
        q: search,
        status: statusFilter,
        includeArchived,
        sortBy,
        sortOrder,
        limit: pageSize,
        offset,
      });
      setEmployees(page.items);
      setTotal(page.total);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Personalbestand konnte nicht geladen werden."));
    }
  }, [canRead, includeArchived, offset, search, sortBy, sortOrder, statusFilter]);

  useEffect(() => {
    void loadEmployees();
  }, [loadEmployees]);

  useEffect(() => {
    setSearch(initialSearch);
  }, [initialSearch]);

  useEffect(() => {
    if (!canRead) return;
    getExpiringEmployeeQualifications()
      .then(setExpiring)
      .catch((reason) => setError(messageFrom(reason, "Ablaufübersicht konnte nicht geladen werden.")));
  }, [canRead]);

  useEffect(() => {
    if (!canManage) return;
    getEmployeeLinkedUserCandidates()
      .then(setAccountCandidates)
      .catch((reason) => setError(messageFrom(reason, "Benutzerkonten konnten nicht geladen werden.")));
  }, [canManage]);

  const refreshSelected = useCallback(async (employeeId: string) => {
    const [
      employee,
      qualificationRows,
      absenceRows,
      historyRows,
      sensitiveDetails,
      objectRows,
      objectHistoryRows,
      documentRows,
      linkedAccounts,
      availableObjects,
    ] = await Promise.all([
      getEmployee(employeeId),
      getEmployeeQualifications(employeeId, true),
      canReadAbsences ? getEmployeeAbsences(employeeId) : Promise.resolve([]),
      getEmployeeHistory(employeeId),
      canReadSensitive ? getEmployeeSensitiveDetails(employeeId) : Promise.resolve(null),
      getEmployeeObjectAssignments(employeeId),
      getEmployeeObjectAssignmentHistory(employeeId),
      canReadDocuments ? getEmployeeQualificationDocuments(employeeId) : Promise.resolve([]),
      canManage ? getEmployeeLinkedUserCandidates(employeeId) : Promise.resolve([]),
      canManageObjectAssignments
        ? getEmployeeObjectAssignmentCandidates()
        : Promise.resolve([]),
    ]);
    setSelected(employee);
    setQualifications(qualificationRows);
    setQualificationDocuments(documentRows);
    setAccountCandidates(linkedAccounts);
    setAbsences(absenceRows);
    setHistory(historyRows);
    setObjectAssignments(objectRows);
    setObjectAssignmentHistory(objectHistoryRows);
    setObjectCandidates(availableObjects);
    setObjectSelection("");
    setSensitive(sensitiveDetails);
    setSensitiveForm({
      address: sensitiveDetails?.address ?? "",
      emergency_contact: sensitiveDetails?.emergency_contact ?? "",
      internal_notes: sensitiveDetails?.internal_notes ?? "",
    });
  }, [
    canManage,
    canManageObjectAssignments,
    canReadAbsences,
    canReadDocuments,
    canReadSensitive,
  ]);

  useEffect(() => {
    if (!initialEmployeeId) return;
    refreshSelected(initialEmployeeId)
      .catch((reason: unknown) =>
        setError(messageFrom(reason, "Mitarbeiterdetails konnten nicht geladen werden.")));
  }, [initialEmployeeId, refreshSelected]);

  async function openEmployee(employee: Employee) {
    setError("");
    try {
      await refreshSelected(employee.id);
    } catch (reason) {
      setError(messageFrom(reason, "Personalakte konnte nicht geladen werden."));
    }
  }

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      const employee = await createEmployee({
        employee_number: String(data.get("employee_number")).trim(),
        user_id: optionalValue(data, "user_id"),
        full_name: String(data.get("full_name")).trim(),
        email: optionalValue(data, "email"),
        phone: optionalValue(data, "phone"),
        job_title: optionalValue(data, "job_title"),
        employment_status: String(data.get("employment_status")) as EmployeeStatus,
        hired_on: String(data.get("hired_on")),
        ended_on: optionalValue(data, "ended_on"),
        contract_type: optionalValue(data, "contract_type"),
        weekly_hours: optionalValue(data, "weekly_hours")
          ? Number(data.get("weekly_hours"))
          : null,
      });
      form.reset();
      setOffset(0);
      await loadEmployees();
      await refreshSelected(employee.id);
    } catch (reason) {
      setError(messageFrom(reason, "Personalakte konnte nicht angelegt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await updateEmployee(selected.id, {
        employee_number: String(data.get("employee_number")).trim(),
        user_id: optionalValue(data, "user_id"),
        full_name: String(data.get("full_name")).trim(),
        email: optionalValue(data, "email"),
        phone: optionalValue(data, "phone"),
        job_title: optionalValue(data, "job_title"),
        employment_status: String(data.get("employment_status")) as EmployeeStatus,
        hired_on: String(data.get("hired_on")),
        ended_on: optionalValue(data, "ended_on"),
        contract_type: optionalValue(data, "contract_type"),
        weekly_hours: optionalValue(data, "weekly_hours")
          ? Number(data.get("weekly_hours"))
          : null,
      });
      await Promise.all([loadEmployees(), refreshSelected(selected.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Personalstammdaten konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function changeArchiveState() {
    if (!selected) return;
    if (
      !selected.archived_at
      && !window.confirm(`Soll die Personalakte von „${selected.full_name}“ archiviert werden?`)
    ) return;
    setBusy(true);
    try {
      const action = selected.archived_at ? reactivateEmployee : archiveEmployee;
      await action(selected.id);
      await Promise.all([loadEmployees(), refreshSelected(selected.id)]);
    } catch (reason) {
      setError(messageFrom(reason, "Archivierungsstatus konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitQualification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      await createEmployeeQualification(selected.id, {
        category: String(data.get("category")).trim(),
        name: String(data.get("name")).trim(),
        issuer: optionalValue(data, "issuer") ?? undefined,
        valid_from: optionalValue(data, "valid_from") ?? undefined,
        expires_on: optionalValue(data, "expires_on") ?? undefined,
      });
      form.reset();
      await Promise.all([refreshSelected(selected.id), getExpiringEmployeeQualifications().then(setExpiring)]);
    } catch (reason) {
      setError(messageFrom(reason, "Qualifikationsnachweis konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitSensitive(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    try {
      const details = await updateEmployeeSensitiveDetails(selected.id, {
        address: sensitiveForm.address.trim() || null,
        emergency_contact: sensitiveForm.emergency_contact.trim() || null,
        internal_notes: sensitiveForm.internal_notes.trim() || null,
      });
      setSensitive(details);
      await getEmployeeHistory(selected.id).then(setHistory);
    } catch (reason) {
      setError(messageFrom(reason, "Vertrauliche Personaldaten konnten nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function addAbsence(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      await createEmployeeAbsence(selected.id, {
        absence_type: String(data.get("absence_type")) as EmployeeAbsenceType,
        starts_on: String(data.get("starts_on")),
        ends_on: String(data.get("ends_on")),
      });
      form.reset();
      await refreshSelected(selected.id);
    } catch (reason) {
      setError(messageFrom(reason, "Abwesenheit konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function changeAbsenceStatus(absence: EmployeeAbsence, nextStatus: EmployeeAbsenceStatus) {
    if (!selected) return;
    setBusy(true);
    try {
      await updateEmployeeAbsence(selected.id, absence.id, { status: nextStatus });
      await refreshSelected(selected.id);
    } catch (reason) {
      setError(messageFrom(reason, "Abwesenheit konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function archiveQualification(qualification: EmployeeQualification) {
    if (!selected || !window.confirm(`„${qualification.name}“ archivieren? Der Nachweis bleibt erhalten.`)) return;
    setBusy(true);
    try {
      await archiveEmployeeQualification(selected.id, qualification.id);
      await Promise.all([refreshSelected(selected.id), getExpiringEmployeeQualifications().then(setExpiring)]);
    } catch (reason) {
      setError(messageFrom(reason, "Nachweis konnte nicht archiviert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function addObjectAssignment() {
    if (!selected || !objectSelection) return;
    setBusy(true);
    try {
      await assignEmployeeToObject(selected.id, objectSelection);
      await refreshSelected(selected.id);
    } catch (reason) {
      setError(messageFrom(reason, "Objektzuweisung konnte nicht angelegt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function endObjectAssignment(assignment: EmployeeObjectAssignment) {
    if (!selected || !window.confirm(`Zuweisung zu „${assignment.object_name}“ beenden?`)) return;
    setBusy(true);
    try {
      await endEmployeeObjectAssignment(selected.id, assignment.object_id);
      await refreshSelected(selected.id);
    } catch (reason) {
      setError(messageFrom(reason, "Objektzuweisung konnte nicht beendet werden."));
    } finally {
      setBusy(false);
    }
  }

  async function uploadQualificationDocument(
    event: FormEvent<HTMLFormElement>,
    qualification: EmployeeQualification,
  ) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const file = new FormData(form).get("document");
    if (!(file instanceof File) || file.size === 0) {
      setError("Bitte eine PDF-, PNG- oder JPEG-Datei auswählen.");
      return;
    }
    setBusy(true);
    try {
      await uploadEmployeeQualificationDocument(selected.id, qualification.id, file);
      form.reset();
      const documents = await getEmployeeQualificationDocuments(selected.id);
      setQualificationDocuments(documents);
      await getEmployeeHistory(selected.id).then(setHistory);
    } catch (reason) {
      setError(messageFrom(reason, "Qualifikationsdatei konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  if (!canRead) {
    return <section className="panel"><h2>Kein Personalzugriff</h2>
      <p className="muted">Deinem Konto fehlt die Leseberechtigung für Personalakten.</p></section>;
  }

  return (
    <section className="object-module">
      <section className="intro object-intro">
        <p className="eyebrow">PERSONALVERWALTUNG</p>
        <h1>Mitarbeiter</h1>
        <p>Personalstammdaten, Qualifikationen und Abwesenheiten mit rollenbasiertem Zugriff.</p>
      </section>

      {error && <p className="alert page-alert" role="alert">{error}</p>}

      {expiring.length > 0 && <section className="panel">
        <div className="panel-heading"><div><p className="eyebrow">FRISTEN</p>
          <h2>Ablaufende oder abgelaufene Qualifikationen</h2></div>
          <span className="result-count">{expiring.length} Einträge</span></div>
        <div className="table-scroll">
          <table><thead><tr><th>Mitarbeiter</th><th>Nachweis</th><th>Ablauf</th><th>Frist</th></tr></thead>
            <tbody>{expiring.map((item) => <tr key={item.id}>
              <td><strong>{item.employee_name}</strong><small>{item.employee_number}</small></td>
              <td>{item.name}<small>{item.category}</small></td>
              <td>{item.expires_on}</td>
              <td>{item.days_until_expiry < 0
                ? `Seit ${Math.abs(item.days_until_expiry)} Tagen abgelaufen`
                : item.days_until_expiry === 0 ? "Läuft heute ab" : `${item.days_until_expiry} Tage`}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>}

      <section className="content-grid">
        <section className="panel">
          <div className="panel-heading">
            <div><p className="eyebrow">PERSONALBESTAND</p><h2>Mitarbeiterliste</h2></div>
            <span className="result-count">{total} Einträge</span>
          </div>
          <label className="search-field">
            <span className="sr-only">Mitarbeiter suchen</span><span aria-hidden="true">⌕</span>
            <input value={search} placeholder="Name, Personalnummer oder Kontakt suchen"
              onChange={(event) => { setSearch(event.target.value); setOffset(0); }} />
          </label>
          <div className="filter-row">
            <label>Status<select value={statusFilter} onChange={(event) => {
              setStatusFilter(event.target.value as EmployeeStatus | "");
              setOffset(0);
            }}>
              <option value="">Alle Status</option>
              {Object.entries(employeeStatuses).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>,
              )}
            </select></label>
            <label>Sortieren nach<select value={sortBy}
              onChange={(event) => setSortBy(event.target.value as typeof sortBy)}>
              <option value="full_name">Name</option>
              <option value="employee_number">Personalnummer</option>
              <option value="hired_on">Eintrittsdatum</option>
              <option value="employment_status">Status</option>
            </select></label>
            <label>Reihenfolge<select value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value as "asc" | "desc")}>
              <option value="asc">Aufsteigend</option><option value="desc">Absteigend</option>
            </select></label>
            {canManage && <label className="checkbox-label">
              <input type="checkbox" checked={includeArchived}
                onChange={(event) => { setIncludeArchived(event.target.checked); setOffset(0); }} />
              Archivierte einblenden
            </label>}
          </div>
          <div className="table-scroll"><table>
            <thead><tr><th>Mitarbeiter</th><th>Funktion</th><th>Objekte</th><th>Status</th><th>Eintritt</th><th>Personalakte</th></tr></thead>
            <tbody>
              {employees.map((employee) => <tr key={employee.id}
                className={employee.archived_at ? "archived-row" : ""}>
                <td><strong>{employee.full_name}</strong><small>{employee.employee_number}</small></td>
                <td>{employee.job_title || "—"}</td>
                <td>{employee.assigned_objects.length
                  ? employee.assigned_objects.join(", ")
                  : "—"}</td>
                <td>{employee.archived_at ? "Archiviert" : employeeStatuses[employee.employment_status]}</td>
                <td>{employee.hired_on}</td>
                <td><button className="text-button" onClick={() => void openEmployee(employee)}>Öffnen</button></td>
              </tr>)}
              {employees.length === 0 && <tr><td className="empty" colSpan={6}>Keine passenden Mitarbeiter vorhanden.</td></tr>}
            </tbody>
          </table></div>
          <div className="pagination">
            <span className="result-count">{total === 0 ? 0 : offset + 1}–{Math.min(offset + pageSize, total)} von {total}</span>
            <div>
              <button className="secondary-button" disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - pageSize))}>Zurück</button>
              <button className="secondary-button" disabled={offset + pageSize >= total}
                onClick={() => setOffset(offset + pageSize)}>Weiter</button>
            </div>
          </div>
        </section>

        {canManage && <aside className="panel form-panel">
          <div className="panel-heading"><div><p className="eyebrow">NEU ANLEGEN</p><h2>Personalakte anlegen</h2></div></div>
          <form onSubmit={submitCreate}>
            <label>Personalnummer <span aria-hidden="true">*</span>
              <input name="employee_number" required maxLength={40} /></label>
            <label>Benutzerkonto
              <select name="user_id" defaultValue="">
                <option value="">Kein Konto verknüpfen</option>
                {accountCandidates.map((account) => <option key={account.id} value={account.id}>
                  {account.full_name} ({account.username})
                </option>)}
              </select>
            </label>
            <label>Vollständiger Name <span aria-hidden="true">*</span>
              <input name="full_name" required maxLength={160} /></label>
            <div className="form-row">
              <label>E-Mail<input name="email" type="email" maxLength={254} /></label>
              <label>Telefon<input name="phone" type="tel" maxLength={40} /></label>
            </div>
            <label>Funktion<input name="job_title" maxLength={120} /></label>
            <div className="form-row">
              <label>Eintritt <input name="hired_on" type="date" required /></label>
              <label>Wochenstunden <input name="weekly_hours" type="number" min="0.01" max="168" step="0.01" /></label>
            </div>
            <label>Vertragsart<input name="contract_type" maxLength={80} /></label>
            <label>Status<select name="employment_status" defaultValue="active">
              {Object.entries(employeeStatuses).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>,
              )}
            </select></label>
            <button type="submit" disabled={busy}>Personalakte speichern</button>
          </form>
        </aside>}
      </section>

      {selected && <section className="panel detail-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">PERSONALAKTE · {selected.employee_number}</p>
            <h2>{selected.full_name}</h2></div>
          <button className="secondary-button" onClick={() => setSelected(null)}>Schließen</button>
        </div>
        <div className="detail-grid">
          {canManage && !selected.archived_at ? <form key={selected.id} className="form-panel detail-form"
            onSubmit={submitUpdate}>
            <label>Personalnummer<input name="employee_number" required maxLength={40}
              defaultValue={selected.employee_number} /></label>
            <label>Benutzerkonto
              <select name="user_id" defaultValue={selected.user_id ?? ""}>
                <option value="">Kein Konto verknüpfen</option>
                {accountCandidates.map((account) => <option key={account.id} value={account.id}>
                  {account.full_name} ({account.username})
                </option>)}
              </select>
            </label>
            <label>Vollständiger Name<input name="full_name" required maxLength={160}
              defaultValue={selected.full_name} /></label>
            <div className="form-row">
              <label>E-Mail<input name="email" type="email" maxLength={254} defaultValue={selected.email ?? ""} /></label>
              <label>Telefon<input name="phone" type="tel" maxLength={40} defaultValue={selected.phone ?? ""} /></label>
            </div>
            <label>Funktion<input name="job_title" maxLength={120} defaultValue={selected.job_title ?? ""} /></label>
            <div className="form-row">
              <label>Eintritt<input name="hired_on" type="date" required defaultValue={selected.hired_on} /></label>
              <label>Austritt<input name="ended_on" type="date" defaultValue={selected.ended_on ?? ""} /></label>
            </div>
            <div className="form-row">
              <label>Vertragsart<input name="contract_type" maxLength={80}
                defaultValue={selected.contract_type ?? ""} /></label>
              <label>Wochenstunden<input name="weekly_hours" type="number" min="0.01" max="168"
                step="0.01" defaultValue={selected.weekly_hours ?? ""} /></label>
            </div>
            <label>Status<select name="employment_status" defaultValue={selected.employment_status}>
              {Object.entries(employeeStatuses).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>,
              )}
            </select></label>
            <button type="submit" disabled={busy}>Stammdaten speichern</button>
          </form> : <div className="detail-summary">
            <p><strong>Status:</strong> {selected.archived_at ? "Archiviert" : employeeStatuses[selected.employment_status]}</p>
            <p><strong>Eintritt:</strong> {selected.hired_on}</p>
            {selected.ended_on && <p><strong>Austritt:</strong> {selected.ended_on}</p>}
            {selected.email && <p><strong>E-Mail:</strong> {selected.email}</p>}
            {selected.phone && <p><strong>Telefon:</strong> {selected.phone}</p>}
            {selected.job_title && <p><strong>Funktion:</strong> {selected.job_title}</p>}
          </div>}
          <div className="detail-side">
            {canManage && <div className="archive-box">
              <h3>{selected.archived_at ? "Archivierte Personalakte" : "Personalstatus"}</h3>
              <button className={selected.archived_at ? "primary-button" : "danger-button"}
                disabled={busy} onClick={() => void changeArchiveState()}>
                {selected.archived_at ? "Reaktivieren" : "Personalakte archivieren"}
              </button>
            </div>}

            {canReadSensitive && <section className="security-section">
              <h3>Vertrauliche Personaldaten</h3>
              {canManageSensitive && !selected.archived_at
                ? <form className="contact-form" onSubmit={submitSensitive}>
                  <label>Anschrift<textarea rows={2} maxLength={500} value={sensitiveForm.address}
                    onChange={(event) => setSensitiveForm({ ...sensitiveForm, address: event.target.value })} /></label>
                  <label>Notfallkontakt<textarea rows={2} maxLength={300}
                    value={sensitiveForm.emergency_contact}
                    onChange={(event) => setSensitiveForm({
                      ...sensitiveForm,
                      emergency_contact: event.target.value,
                    })} /></label>
                  <label>Interne Notizen<textarea rows={3} maxLength={10000}
                    value={sensitiveForm.internal_notes}
                    onChange={(event) => setSensitiveForm({
                      ...sensitiveForm,
                      internal_notes: event.target.value,
                    })} /></label>
                  <button className="secondary-button" disabled={busy}>Vertrauliche Daten speichern</button>
                </form>
                : <div className="detail-summary sensitive-summary">
                  <p><strong>Anschrift:</strong><br />{sensitive?.address || "Keine Angabe"}</p>
                  <p><strong>Notfallkontakt:</strong><br />
                    {sensitive?.emergency_contact || "Keine Angabe"}</p>
                  <p><strong>Interne Notizen:</strong><br />{sensitive?.internal_notes || "Keine Angabe"}</p>
                </div>}
            </section>}
          </div>
        </div>

        <div className="detail-grid">
          <section className="contact-section">
            <h3>Qualifikationen und Unterweisungen</h3>
            {qualifications.length === 0 && <p className="muted">Keine Nachweise vorhanden.</p>}
            {qualifications.map((qualification) => <article className="contact-card" key={qualification.id}>
              <div><strong>{qualification.name}</strong>
                <small>{qualification.category}{qualification.issuer ? ` · ${qualification.issuer}` : ""}</small>
                <small>Gültig ab: {qualification.valid_from ?? "nicht angegeben"}</small>
                <small>Ablauf: {qualification.expires_on ?? "kein Ablaufdatum"}</small>
                {qualification.archived_at && <small>Archiviert</small>}
              </div>
              {canManage && !selected.archived_at && !qualification.archived_at
                && <button className="text-button danger-text" disabled={busy}
                  onClick={() => void archiveQualification(qualification)}>Archivieren</button>}
              {canReadDocuments && qualificationDocuments
                .filter((document) => document.qualification_id === qualification.id)
                .map((document) => <div className="document-version" key={document.id}>
                  <small>Version {document.version}: {document.file_name} ·
                    {" "}{Math.ceil(document.size_bytes / 1024)} KiB</small>
                  <a
                    href={employeeQualificationDocumentUrl(
                      selected.id,
                      qualification.id,
                      document.id,
                    )}
                    target="_blank"
                    rel="noreferrer"
                  >Ansehen</a>
                  {" · "}
                  <a href={employeeQualificationDocumentUrl(
                    selected.id,
                    qualification.id,
                    document.id,
                    true,
                  )}>Herunterladen</a>
                </div>)}
              {canManageDocuments && !selected.archived_at && !qualification.archived_at
                && <form className="document-upload" onSubmit={(event) =>
                  void uploadQualificationDocument(event, qualification)}>
                  <label>Nachweisdatei (PDF, PNG oder JPEG, max. 10 MiB)
                    <input name="document" type="file" accept=".pdf,.png,.jpg,.jpeg"
                      required disabled={busy} />
                  </label>
                  <button className="secondary-button" disabled={busy}>Neue Version hochladen</button>
                </form>}
            </article>)}
            {canManage && !selected.archived_at && <form className="contact-form" onSubmit={submitQualification}>
              <h4>Nachweis hinzufügen</h4>
              <label>Kategorie<input name="category" required maxLength={80} /></label>
              <label>Bezeichnung<input name="name" required maxLength={160} /></label>
              <label>Aussteller<input name="issuer" maxLength={160} /></label>
              <div className="form-row">
                <label>Gültig ab<input name="valid_from" type="date" /></label>
                <label>Ablaufdatum<input name="expires_on" type="date" /></label>
              </div>
              <button className="secondary-button" disabled={busy}>Nachweis speichern</button>
            </form>}
          </section>

          <section className="assignment-section">
            <h3>Objektzuweisungen</h3>
            {!selected.user_id && <p className="muted">
              Für Objektzuweisungen muss ein passendes Benutzerkonto verknüpft sein.
            </p>}
            {objectAssignments.length === 0 && selected.user_id
              && <p className="muted">Keine aktiven Objektzuweisungen vorhanden.</p>}
            {objectAssignments.map((assignment) => <article className="contact-card"
              key={assignment.object_id}>
              <div><strong>{assignment.object_name}</strong><small>{assignment.object_code}</small>
                <small>Zugewiesen am {new Date(assignment.assigned_at).toLocaleString("de-DE")}</small>
              </div>
              {canManageObjectAssignments && !selected.archived_at
                && <button className="text-button danger-text" disabled={busy}
                  onClick={() => void endObjectAssignment(assignment)}>Zuweisung beenden</button>}
            </article>)}
            {canManageObjectAssignments && selected.user_id && !selected.archived_at && (
              <div className="contact-form">
                <label>Weiteres Objekt auswählen
                  <select value={objectSelection}
                    onChange={(event) => setObjectSelection(event.target.value)}>
                    <option value="">Objekt auswählen</option>
                    {objectCandidates
                      .filter((candidate) => !objectAssignments.some(
                        (assignment) => assignment.object_id === candidate.object_id,
                      ))
                      .map((candidate) => <option key={candidate.object_id} value={candidate.object_id}>
                        {candidate.object_name} ({candidate.object_code})
                      </option>)}
                  </select>
                </label>
                <button className="secondary-button" disabled={busy || !objectSelection}
                  onClick={() => void addObjectAssignment()}>Objekt zuweisen</button>
              </div>
            )}
            {objectAssignmentHistory.length > 0 && <details className="history-section">
              <summary>Zuweisungsverlauf</summary>
              <ol className="history-list">{objectAssignmentHistory.map((entry) => <li key={entry.id}>
                <strong>{entry.action === "assigned" ? "Zugewiesen" : "Zuweisung beendet"}:{" "}
                  {entry.object_name} ({entry.object_code})</strong>
                <time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString("de-DE")}</time>
              </li>)}</ol>
            </details>}
          </section>

          {canReadAbsences && <section className="assignment-section">
            <h3>Abwesenheiten</h3>
            {absences.length === 0 && <p className="muted">Keine Abwesenheiten erfasst.</p>}
            {absences.map((absence) => <article className="contact-card" key={absence.id}>
              <div><strong>{absenceTypes[absence.absence_type]}</strong>
                <small>{absence.starts_on} bis {absence.ends_on}</small>
                <small>{absenceStatuses[absence.status]}</small>
              </div>
              {canManageAbsences && !selected.archived_at && absence.status === "pending"
                && <div className="contact-actions">
                  <button className="text-button" disabled={busy}
                    onClick={() => void changeAbsenceStatus(absence, "approved")}>Genehmigen</button>
                  <button className="text-button danger-text" disabled={busy}
                    onClick={() => void changeAbsenceStatus(absence, "rejected")}>Ablehnen</button>
                </div>}
            </article>)}
            {canManageAbsences && !selected.archived_at && <form className="contact-form" onSubmit={addAbsence}>
              <h4>Abwesenheit erfassen</h4>
              <label>Art<select name="absence_type" defaultValue="vacation">
                {Object.entries(absenceTypes).map(([value, name]) =>
                  <option key={value} value={value}>{name}</option>,
                )}
              </select></label>
              <div className="form-row">
                <label>Beginn<input name="starts_on" type="date" required /></label>
                <label>Ende<input name="ends_on" type="date" required /></label>
              </div>
              <button className="secondary-button" disabled={busy}>Abwesenheit speichern</button>
            </form>}
          </section>}
        </div>

        <section className="history-section">
          <h3>Personalhistorie</h3>
          {history.length === 0 ? <p className="muted">Noch keine Historieneinträge.</p> : (
            <ol className="history-list">{history.map((item) => <li key={item.id}>
              <strong>{historyActions[item.action] ?? item.action}</strong>
              <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString("de-DE")}</time>
              {item.changed_fields.length > 0 && <small>Geänderte Bereiche: {item.changed_fields.join(", ")}</small>}
            </li>)}</ol>
          )}
        </section>
      </section>}
    </section>
  );
}
