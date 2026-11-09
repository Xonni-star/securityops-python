import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  archiveKey,
  createKey,
  createKeyMovement,
  getEligibleKeyEmployees,
  getKeyMovements,
  getKeyObjects,
  getKeys,
  updateKey,
} from "./api";
import type {
  KeyEmployeeCandidate,
  KeyMovement,
  KeyMovementType,
  KeyObjectCandidate,
  PhysicalKey,
  PhysicalKeyStatus,
} from "./types";

const pageSize = 25;

const statusNames: Record<PhysicalKeyStatus, string> = {
  available: "Verfügbar",
  issued: "Ausgegeben",
  lost: "Verloren",
  defective: "Defekt",
  archived: "Archiviert",
};

const movementNames: Record<KeyMovementType, string> = {
  issued: "Ausgabe",
  returned: "Rückgabe",
  lost: "Verlustmeldung",
  defective: "Defektmeldung",
  inventory: "Inventur bestätigt",
};

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("de-DE");
}

export default function KeyManagement({
  canManage,
  canMove,
  initialQuery = "",
  initialKeyId = null,
}: {
  canManage: boolean;
  canMove: boolean;
  initialQuery?: string;
  initialKeyId?: string | null;
}) {
  const [items, setItems] = useState<PhysicalKey[]>([]);
  const [objects, setObjects] = useState<KeyObjectCandidate[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState(initialQuery);
  const [status, setStatus] = useState<PhysicalKeyStatus | "">("");
  const [objectId, setObjectId] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [editingKey, setEditingKey] = useState<PhysicalKey | null>(null);
  const [movementKey, setMovementKey] = useState<PhysicalKey | null>(null);
  const [movementType, setMovementType] = useState<KeyMovementType>("issued");
  const [eligibleEmployees, setEligibleEmployees] = useState<KeyEmployeeCandidate[]>([]);
  const [expandedKeyId, setExpandedKeyId] = useState("");
  const [history, setHistory] = useState<Record<string, KeyMovement[]>>({});

  const loadKeys = useCallback(async () => {
    setLoading(true);
    try {
      const [page, objectOptions] = await Promise.all([
        getKeys({
          q: query,
          status,
          object_id: objectId,
          employee_id: "",
          include_archived: includeArchived,
          limit: pageSize,
          offset,
        }),
        getKeyObjects(),
      ]);
      setItems(page.items);
      setTotal(page.total);
      setObjects(objectOptions);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Schlüssel konnten nicht geladen werden."));
    } finally {
      setLoading(false);
    }
  }, [includeArchived, objectId, offset, query, status]);

  useEffect(() => {
    void loadKeys();
  }, [loadKeys]);

  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await createKey({
        key_number: String(data.get("key_number") ?? "").trim(),
        description: String(data.get("description") ?? "").trim(),
        object_id: String(data.get("object_id") ?? ""),
      });
      setShowCreate(false);
      setOffset(0);
      await loadKeys();
    } catch (reason) {
      setError(messageFrom(reason, "Schlüssel konnte nicht angelegt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingKey) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await updateKey(editingKey.id, {
        description: String(data.get("description") ?? "").trim(),
      });
      setEditingKey(null);
      await loadKeys();
    } catch (reason) {
      setError(messageFrom(reason, "Beschreibung konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function startMovement(key: PhysicalKey, type: KeyMovementType) {
    setMovementKey(key);
    setMovementType(type);
    setEligibleEmployees([]);
    if (type !== "issued") return;
    try {
      setEligibleEmployees(await getEligibleKeyEmployees(key.object_id));
    } catch (reason) {
      setError(messageFrom(reason, "Zugeordnete Mitarbeiter konnten nicht geladen werden."));
    }
  }

  async function submitMovement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!movementKey) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await createKeyMovement(movementKey.id, {
        movement_type: movementType,
        ...(movementType === "issued"
          ? {
            employee_id: String(data.get("employee_id") ?? ""),
            acknowledged: data.get("acknowledged") === "on",
            acknowledgement_note: String(data.get("acknowledgement_note") ?? "").trim() || undefined,
          }
          : {}),
        note: String(data.get("note") ?? "").trim() || undefined,
      });
      setMovementKey(null);
      await loadKeys();
      if (expandedKeyId === movementKey.id) await loadHistory(movementKey.id);
    } catch (reason) {
      setError(messageFrom(reason, "Schlüsselbewegung konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function loadHistory(keyId: string) {
    try {
      const page = await getKeyMovements(keyId);
      setHistory((current) => ({ ...current, [keyId]: page.items }));
    } catch (reason) {
      setError(messageFrom(reason, "Schlüsselhistorie konnte nicht geladen werden."));
    }
  }

  async function toggleHistory(keyId: string) {
    if (expandedKeyId === keyId) {
      setExpandedKeyId("");
      return;
    }
    setExpandedKeyId(keyId);
    await loadHistory(keyId);
  }

  async function handleArchive(key: PhysicalKey) {
    setBusy(true);
    try {
      await archiveKey(key.id);
      await loadKeys();
    } catch (reason) {
      setError(messageFrom(reason, "Schlüssel konnte nicht archiviert werden."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="key-register">
      <section className="panel" aria-labelledby="key-register-heading">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">BESTANDSVERWALTUNG</p>
            <h2 id="key-register-heading">Schlüsselverwaltung</h2>
          </div>
          <span className="result-count">{total} Schlüssel</span>
        </div>
        {error && <p className="alert" role="alert">{error}</p>}
        <div className="key-filters">
          <label>
            Suche
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setOffset(0);
              }}
              maxLength={200}
              placeholder="Nummer, Beschreibung oder Objekt"
            />
          </label>
          <label>
            Status
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as PhysicalKeyStatus | "");
                setOffset(0);
              }}
            >
              <option value="">Alle aktiven Status</option>
              {Object.entries(statusNames).map(([value, name]) =>
                <option key={value} value={value}>{name}</option>)}
            </select>
          </label>
          <label>
            Objekt
            <select
              value={objectId}
              onChange={(event) => {
                setObjectId(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">Alle Objekte</option>
              {objects.map((obj) => <option key={obj.id} value={obj.id}>{obj.code} · {obj.name}</option>)}
            </select>
          </label>
          <label className="key-archived-filter">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(event) => {
                setIncludeArchived(event.target.checked);
                setOffset(0);
              }}
            />
            Archivierte einbeziehen
          </label>
        </div>

        {canManage && <button className="primary-button" onClick={() => setShowCreate((value) => !value)}>
          {showCreate ? "Neuen Schlüssel schließen" : "Schlüssel anlegen"}
        </button>}
        {showCreate && canManage && <form className="key-form" onSubmit={(event) => void submitCreate(event)}>
          <h3>Schlüssel erfassen</h3>
          <div className="form-row">
            <label>Schlüsselnummer<input name="key_number" required maxLength={80} /></label>
            <label>Objekt<select name="object_id" required defaultValue="">
              <option value="" disabled>Objekt auswählen</option>
              {objects.map((obj) => <option key={obj.id} value={obj.id}>{obj.code} · {obj.name}</option>)}
            </select></label>
          </div>
          <label>Beschreibung<input name="description" required maxLength={500} /></label>
          <button className="primary-button" disabled={busy}>{busy ? "Wird gespeichert …" : "Schlüssel speichern"}</button>
        </form>}

        {loading
          ? <p className="muted" role="status">Schlüssel werden geladen …</p>
          : items.length === 0
          ? <p className="empty">Keine Schlüssel für diese Auswahl vorhanden.</p>
          : <div className="key-list">
            {items.map((key) => (
              <article
                className={`key-card${key.id === initialKeyId ? " search-result-row" : ""}`}
                key={key.id}
              >
                <div className="key-card-heading">
                  <div>
                    <h3>{key.key_number} <span className={`key-status key-status-${key.status}`}>{statusNames[key.status]}</span></h3>
                    <p>{key.description}</p>
                    <p className="muted">{key.object_code} · {key.object_name}
                      {key.current_employee_name ? ` · bei ${key.current_employee_name}` : ""}
                    </p>
                  </div>
                  <button className="secondary-button" onClick={() => void toggleHistory(key.id)}>
                    {expandedKeyId === key.id ? "Historie schließen" : "Historie"}
                  </button>
                </div>
                <div className="key-actions">
                  {canManage && key.status !== "archived" && <>
                    <button className="secondary-button" onClick={() => setEditingKey(key)}>Beschreibung ändern</button>
                    {key.status !== "issued" && <button
                      className="secondary-button"
                      disabled={busy}
                      onClick={() => void handleArchive(key)}
                    >Archivieren</button>}
                  </>}
                  {canMove && key.status === "available" && <>
                    <button className="secondary-button" onClick={() => void startMovement(key, "issued")}>Ausgeben</button>
                    <button className="secondary-button" onClick={() => void startMovement(key, "defective")}>Defekt melden</button>
                    <button className="secondary-button" onClick={() => void startMovement(key, "lost")}>Verlust melden</button>
                    <button className="secondary-button" onClick={() => void startMovement(key, "inventory")}>Inventur bestätigen</button>
                  </>}
                  {canMove && key.status === "issued" && <>
                    <button className="secondary-button" onClick={() => void startMovement(key, "returned")}>Rückgabe erfassen</button>
                    <button className="secondary-button" onClick={() => void startMovement(key, "defective")}>Defekt melden</button>
                    <button className="secondary-button" onClick={() => void startMovement(key, "lost")}>Verlust melden</button>
                    <button className="secondary-button" onClick={() => void startMovement(key, "inventory")}>Inventur bestätigen</button>
                  </>}
                </div>
                {editingKey?.id === key.id && <form className="key-form" onSubmit={(event) => void submitUpdate(event)}>
                  <label>Beschreibung<input name="description" defaultValue={key.description} required maxLength={500} /></label>
                  <button className="primary-button" disabled={busy}>Änderung speichern</button>
                  <button type="button" className="secondary-button" onClick={() => setEditingKey(null)}>Abbrechen</button>
                </form>}
                {movementKey?.id === key.id && <form className="key-form" onSubmit={(event) => void submitMovement(event)}>
                  <h3>{movementNames[movementType]} · {key.key_number}</h3>
                  {movementType === "issued" && <>
                    <label>Mitarbeiter<select name="employee_id" required defaultValue="">
                      <option value="" disabled>Mitarbeiter auswählen</option>
                      {eligibleEmployees.map((employee) =>
                        <option key={employee.id} value={employee.id}>
                          {employee.employee_number} · {employee.full_name}
                        </option>)}
                    </select></label>
                    {eligibleEmployees.length === 0 && <p className="muted">Für dieses Objekt sind keine aktiven Mitarbeiter mit Benutzerkonto zugewiesen.</p>}
                    <label className="key-acknowledgement">
                      <input type="checkbox" name="acknowledged" required />
                      Empfang durch den ausgewählten Mitarbeiter bestätigt
                    </label>
                    <label>Quittierungsnotiz<input name="acknowledgement_note" maxLength={2000} /></label>
                  </>}
                  {(movementType === "lost" || movementType === "defective") && <label>
                    Notiz zur Meldung<textarea name="note" required maxLength={5000} />
                  </label>}
                  {movementType === "inventory" && <p className="muted">Bestätigt, dass der Schlüssel bei der Inventur physisch vorhanden war.</p>}
                  {movementType === "returned" && <label>Notiz<textarea name="note" maxLength={5000} /></label>}
                  <button className="primary-button" disabled={busy || (movementType === "issued" && eligibleEmployees.length === 0)}>
                    {busy ? "Wird gespeichert …" : "Bewegung protokollieren"}
                  </button>
                  <button type="button" className="secondary-button" onClick={() => setMovementKey(null)}>Abbrechen</button>
                </form>}
                {expandedKeyId === key.id && <div className="key-history">
                  <h4>Unveränderliche Historie</h4>
                  {(history[key.id] ?? []).length === 0
                    ? <p className="empty">Noch keine Bewegungen protokolliert.</p>
                    : <ol>
                      {(history[key.id] ?? []).map((movement) => <li key={movement.id}>
                        <strong>{movementNames[movement.movement_type]}</strong>
                        <span>{formatDate(movement.created_at)} · {movement.actor_name}</span>
                        {movement.employee_name && <span>Mitarbeiter: {movement.employee_name}</span>}
                        {movement.acknowledged_at && <span>Empfang quittiert: {formatDate(movement.acknowledged_at)}</span>}
                        {movement.acknowledgement_note && <span>Quittierungsnotiz: {movement.acknowledgement_note}</span>}
                        {movement.note && <span>Notiz: {movement.note}</span>}
                      </li>)}
                    </ol>}
                </div>}
              </article>
            ))}
          </div>}
        <div className="pagination">
          <span className="result-count">
            {total === 0 ? "0 Einträge" : `${offset + 1}–${Math.min(offset + pageSize, total)} von ${total}`}
          </span>
          <div>
            <button className="secondary-button" disabled={offset === 0 || loading} onClick={() => setOffset((value) => Math.max(0, value - pageSize))}>Zurück</button>
            <button className="secondary-button" disabled={offset + pageSize >= total || loading} onClick={() => setOffset((value) => value + pageSize)}>Weiter</button>
          </div>
        </div>
      </section>
    </section>
  );
}
