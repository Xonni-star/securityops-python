import { FormEvent, useState } from "react";
import { getEmployees } from "./api";
import type { Employee } from "./types";

function messageFrom(reason: unknown) {
  return reason instanceof Error ? reason.message : "Mitarbeiter konnten nicht gesucht werden.";
}

export default function ControlRoomEmployeeSearch() {
  const [query, setQuery] = useState("");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [total, setTotal] = useState(0);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function searchEmployees(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setSearched(true);
    setError("");
    try {
      const page = await getEmployees({
        q: query.trim(),
        status: "active",
        includeArchived: false,
        sortBy: "full_name",
        sortOrder: "asc",
        limit: 25,
        offset: 0,
      });
      setEmployees(page.items);
      setTotal(page.total);
    } catch (reason) {
      setEmployees([]);
      setTotal(0);
      setError(messageFrom(reason));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="control-room-employee-search" aria-labelledby="control-room-employee-title">
      <h3 id="control-room-employee-title">Mitarbeiter suchen</h3>
      <form className="control-room-employee-search-form" onSubmit={(event) => void searchEmployees(event)}>
        <label>
          Name oder Personalnummer
          <input
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            required
            minLength={2}
            maxLength={200}
            autoComplete="off"
          />
        </label>
        <button className="primary-button" disabled={loading}>
          {loading ? "Suche läuft …" : "Suchen"}
        </button>
      </form>
      {error && <p className="alert" role="alert">{error}</p>}
      {loading && <p className="muted" role="status">Mitarbeiter werden gesucht …</p>}
      {!loading && searched && !error && employees.length === 0
        && <p className="empty">Keine aktiven Mitarbeiter gefunden.</p>}
      {!loading && employees.length > 0 && <>
        <p className="muted">{total} Treffer, höchstens 25 werden angezeigt.</p>
        <ul className="control-room-employee-results">
          {employees.map((employee) => (
            <li key={employee.id}>
              <strong>{employee.full_name}</strong>
              <small>{employee.employee_number}{employee.job_title ? ` · ${employee.job_title}` : ""}</small>
              {employee.assigned_objects.length > 0
                && <small>Zugeordnete Objekte: {employee.assigned_objects.join(", ")}</small>}
            </li>
          ))}
        </ul>
      </>}
    </section>
  );
}
