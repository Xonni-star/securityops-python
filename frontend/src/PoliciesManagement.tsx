import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  assignPolicy,
  confirmPolicy,
  createPolicy,
  createPolicyVersion,
  exportPolicyProof,
  getMyPolicyAssignments,
  getPolicies,
  getPolicyEmployees,
  getPolicyHistory,
  getPolicyObjects,
  recordPolicyRead,
} from "./api";
import type {
  PolicyAssignment,
  PolicyEmployeeOption,
  PolicyHistory,
  PolicyItem,
  PolicyObjectOption,
} from "./types";

function messageFrom(reason: unknown) {
  return reason instanceof Error ? reason.message : "Der Vorgang ist fehlgeschlagen.";
}

function utcInputValue() {
  return new Date().toISOString().slice(0, 16);
}

function utcValue(value: FormDataEntryValue | null) {
  const text = String(value ?? "").trim();
  return text ? new Date(`${text}:00Z`).toISOString() : undefined;
}

export default function PoliciesManagement({
  canManage,
  canReadOwn,
}: {
  canManage: boolean;
  canReadOwn: boolean;
}) {
  const [policies, setPolicies] = useState<PolicyItem[]>([]);
  const [assignments, setAssignments] = useState<PolicyAssignment[]>([]);
  const [objects, setObjects] = useState<PolicyObjectOption[]>([]);
  const [employees, setEmployees] = useState<PolicyEmployeeOption[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [history, setHistory] = useState<PolicyHistory | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const selectedPolicy = useMemo(
    () => policies.find((policy) => policy.id === selectedId) ?? null,
    [policies, selectedId],
  );

  const refresh = useCallback(async () => {
    const [ownAssignments, managedPolicies, objectOptions] = await Promise.all([
      canReadOwn ? getMyPolicyAssignments() : Promise.resolve([]),
      canManage ? getPolicies() : Promise.resolve([]),
      canManage ? getPolicyObjects() : Promise.resolve([]),
    ]);
    setAssignments(ownAssignments);
    setPolicies(managedPolicies);
    setObjects(objectOptions);
    setSelectedId((current) =>
      managedPolicies.some((policy) => policy.id === current)
        ? current
        : managedPolicies[0]?.id ?? "",
    );
  }, [canManage, canReadOwn]);

  useEffect(() => {
    void refresh().catch((reason: unknown) => setError(messageFrom(reason)));
  }, [refresh]);

  useEffect(() => {
    if (!selectedPolicy) {
      setEmployees([]);
      setHistory(null);
      return;
    }
    Promise.all([
      getPolicyEmployees(selectedPolicy.id),
      getPolicyHistory(selectedPolicy.id),
    ])
      .then(([employeeOptions, policyHistory]) => {
        setEmployees(employeeOptions);
        setHistory(policyHistory);
      })
      .catch((reason: unknown) => setError(messageFrom(reason)));
  }, [selectedPolicy]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      const policy = await createPolicy({
        kind: String(data.get("kind")) as "instruction" | "training",
        title: String(data.get("title")).trim(),
        object_id: String(data.get("object_id") ?? "") || undefined,
        repeat_interval_days: Number(data.get("repeat_interval_days")) || undefined,
        reminder_days: Number(data.get("reminder_days")) || undefined,
      });
      await refresh();
      setSelectedId(policy.id);
      form.reset();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submitVersion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPolicy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    try {
      await createPolicyVersion(selectedPolicy.id, {
        content: String(data.get("content")).trim(),
        valid_from: utcValue(data.get("valid_from")) ?? "",
        valid_until: utcValue(data.get("valid_until")),
      });
      await refresh();
      form.reset();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submitAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPolicy) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const versionId = String(data.get("version_id") ?? "");
    setBusy(true);
    setError("");
    try {
      await assignPolicy(selectedPolicy.id, versionId, {
        employee_id: String(data.get("employee_id")),
        due_at: utcValue(data.get("due_at")),
      });
      await Promise.all([refresh(), loadHistory(selectedPolicy.id)]);
      form.reset();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function loadHistory(policyId: string) {
    setHistory(await getPolicyHistory(policyId));
  }

  async function acknowledge(
    assignment: PolicyAssignment,
    action: "read" | "confirm",
  ) {
    setBusy(true);
    setError("");
    try {
      if (action === "read") await recordPolicyRead(assignment.id);
      else await confirmPolicy(assignment.id);
      await refresh();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function downloadProof(policyId: string) {
    setError("");
    try {
      const blob = await exportPolicyProof(policyId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `nachweis-${policyId}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(messageFrom(reason));
    }
  }

  return (
    <section className="policy-module">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">PERSONAL & OBJEKTE</p>
          <h2>Dienstanweisungen & Unterweisungen</h2>
        </div>
      </div>
      {error && <p className="alert" role="alert">{error}</p>}

      {canManage && (
        <section className="panel form-panel">
          <h3>Neue Anweisung oder Unterweisung</h3>
          <form onSubmit={(event) => void submit(event)}>
            <label>Art
              <select name="kind">
                <option value="instruction">Dienst-/Arbeits-/Verfahrensanweisung</option>
                <option value="training">Unterweisung</option>
              </select>
            </label>
            <label>Titel<input name="title" required maxLength={200} /></label>
            <label>Geltungsbereich
              <select name="object_id" defaultValue="">
                <option value="">Allgemein</option>
                {objects.map((object) => (
                  <option value={object.id} key={object.id}>{object.name} ({object.code})</option>
                ))}
              </select>
            </label>
            <div className="form-row">
              <label>Wiederholung nach Tagen (optional)
                <input name="repeat_interval_days" type="number" min="1" max="3650" />
              </label>
              <label>Erinnerung vorher in Tagen (optional)
                <input name="reminder_days" type="number" min="1" max="3649" />
              </label>
            </div>
            <small>Erinnerungen werden mit dem konfigurierten Vorlauf als fälliger Hinweis in der Anwendung angezeigt. Es erfolgt kein E-Mail- oder Push-Versand.</small>
            <button disabled={busy}>Anlegen</button>
          </form>
        </section>
      )}

      {canManage && (
        <section className="panel policy-manager">
          <label>Anweisung / Unterweisung
            <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              {policies.map((policy) => (
                <option key={policy.id} value={policy.id}>
                  {policy.kind === "training" ? "Unterweisung" : "Dienstanweisung"}: {policy.title}
                  {policy.object_name ? ` — ${policy.object_name}` : " — Allgemein"}
                </option>
              ))}
            </select>
          </label>
          {!selectedPolicy ? <p className="empty">Noch keine Inhalte angelegt.</p> : <>
            <div className="policy-versions">
              <h3>Unveränderliche Versionen</h3>
              {selectedPolicy.versions.map((version) => (
                <article className="policy-version" key={version.id}>
                  <strong>Version {version.version_number}</strong>
                  <span>{new Date(version.valid_from).toLocaleString("de-DE", { timeZone: "UTC" })} UTC
                    {version.valid_until
                      ? ` bis ${new Date(version.valid_until).toLocaleString("de-DE", { timeZone: "UTC" })} UTC`
                      : " — unbegrenzt"}
                  </span>
                  <p>{version.content}</p>
                </article>
              ))}
            </div>
            <form onSubmit={(event) => void submitVersion(event)}>
              <h3>Neue Version anlegen</h3>
              <label>Inhalt<textarea name="content" required maxLength={100000} /></label>
              <div className="form-row">
                <label>Gültig ab (UTC)
                  <input name="valid_from" type="datetime-local" defaultValue={utcInputValue()} required />
                </label>
                <label>Gültig bis (UTC, optional)
                  <input name="valid_until" type="datetime-local" />
                </label>
              </div>
              <button disabled={busy}>Version speichern</button>
            </form>
            {selectedPolicy.versions.length > 0 && employees.length > 0 && (
              <form onSubmit={(event) => void submitAssignment(event)}>
                <h3>Mitarbeiter zuweisen</h3>
                <label>Version
                  <select name="version_id" required>
                    {selectedPolicy.versions.map((version) => (
                      <option key={version.id} value={version.id}>
                        Version {version.version_number}
                      </option>
                    ))}
                  </select>
                </label>
                <label>Mitarbeiter
                  <select name="employee_id" required>
                    {employees.map((employee) => (
                      <option key={employee.id} value={employee.id}>
                        {employee.full_name} ({employee.employee_number})
                      </option>
                    ))}
                  </select>
                </label>
                <label>Fällig am (UTC, optional)
                  <input name="due_at" type="datetime-local" />
                </label>
                <button disabled={busy}>Zuweisen</button>
              </form>
            )}
            {history && (
              <div className="policy-history">
                <div className="panel-heading">
                  <h3>Nachweis- und Versionshistorie</h3>
                  <button type="button" onClick={() => void downloadProof(selectedPolicy.id)}>
                    CSV-Nachweis exportieren
                  </button>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead><tr><th>Mitarbeiter</th><th>Version / Zyklus</th><th>Fälligkeit</th><th>Erinnerung</th><th>Gelesen</th><th>Bestätigt</th></tr></thead>
                    <tbody>
                      {history.assignments.map((entry) => (
                        <tr key={`${entry.employee_id}-${entry.version_id}-${entry.cycle_number}`}>
                          <td>{entry.employee_name}<small>{entry.employee_number}</small></td>
                          <td>{entry.version_number} / {entry.cycle_number}</td>
                          <td>{entry.due_at ? new Date(entry.due_at).toLocaleString("de-DE") : "Nicht festgelegt"}</td>
                          <td>{entry.overdue ? "Überfällig" : entry.reminder_due ? "Fällig" : "—"}</td>
                          <td>{entry.read_at ? new Date(entry.read_at).toLocaleString("de-DE") : "Offen"}</td>
                          <td>{entry.confirmed_at ? new Date(entry.confirmed_at).toLocaleString("de-DE") : "Offen"}</td>
                        </tr>
                      ))}
                      {history.assignments.length === 0 && (
                        <tr><td className="empty" colSpan={6}>Noch keine Zuweisungen.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>}
        </section>
      )}

      {canReadOwn && (
        <section className="policy-own">
          <h3>Meine gültigen Inhalte</h3>
          {assignments.map((assignment) => (
            <article className="panel policy-own-item" key={assignment.id}>
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">{assignment.kind === "training" ? "UNTERWEISUNG" : "DIENSTANWEISUNG"}</p>
                  <h3>{assignment.title} · Version {assignment.version_number}</h3>
                  <small>{assignment.object_name ?? "Allgemein"} · Zyklus {assignment.cycle_number}</small>
                </div>
                {assignment.overdue && <span className="status status-lead">Überfällig</span>}
                {!assignment.overdue && assignment.reminder_due && (
                  <span className="status status-lead">Erinnerung fällig</span>
                )}
              </div>
              <p className="policy-content">{assignment.content}</p>
              {assignment.due_at && <p>Fällig: {new Date(assignment.due_at).toLocaleString("de-DE")}</p>}
              <div className="policy-actions">
                {assignment.read_at
                  ? <span>Gelesen am {new Date(assignment.read_at).toLocaleString("de-DE")}</span>
                  : <button disabled={busy} onClick={() => void acknowledge(assignment, "read")}>Als gelesen markieren</button>}
                {assignment.confirmed_at
                  ? <span>Bestätigt am {new Date(assignment.confirmed_at).toLocaleString("de-DE")}</span>
                  : <button disabled={busy || !assignment.read_at} onClick={() => void acknowledge(assignment, "confirm")}>
                    Bestätigung abgeben
                  </button>}
              </div>
            </article>
          ))}
          {assignments.length === 0 && (
            <p className="empty">Derzeit sind keine gültigen Inhalte zugewiesen.</p>
          )}
        </section>
      )}
    </section>
  );
}
