import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  createAutomationRule,
  deleteAutomationRule,
  getAutomationDeadLetters,
  getAutomationRules,
  getAutomationRuns,
  retryAutomationEvent,
  retryAutomationRun,
  updateAutomationRule,
} from "./api";
import type {
  AutomationRule,
  AutomationTaskStatus,
  AutomationTrigger,
  AutomationRun,
  AutomationDeadLetter,
} from "./types";

const taskStatuses: { value: AutomationTaskStatus; label: string }[] = [
  { value: "open", label: "Offen" },
  { value: "in_progress", label: "In Bearbeitung" },
  { value: "blocked", label: "Blockiert" },
  { value: "completed", label: "Erledigt" },
  { value: "cancelled", label: "Abgebrochen" },
];

const triggerNames: Record<AutomationTrigger, string> = {
  "task.assigned": "Aufgabe zugewiesen",
  "task.status_changed": "Aufgabenstatus geändert",
  "owks.missed_control": "Kontrollpunkt nicht kontrolliert",
  "owks.deviation_reported": "OWKS-Auffälligkeit gemeldet",
  "owks.offline_event_synced": "Offline-Ereignis synchronisiert",
  "billing.invoice_approved": "Rechnung manuell freigegeben",
};
const eventNames: Record<string, string> = {
  ...triggerNames,
  "automation.notification": "Automatisierungsbenachrichtigung",
};

const runStatusNames: Record<AutomationRun["status"], string> = {
  condition_not_met: "Bedingung nicht erfüllt",
  skipped_no_recipients: "Keine Empfänger",
  queued: "In der Warteschlange",
  succeeded: "Erfolgreich",
  dead_letter: "Fehlerablage",
};

function messageFrom(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("de-DE");
}

export default function AutomationManagement() {
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [deadLetters, setDeadLetters] = useState<AutomationDeadLetter[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [triggerType, setTriggerType] = useState<AutomationTrigger>("task.assigned");
  const [conditionStatus, setConditionStatus] = useState<AutomationTaskStatus | "">("");
  const [editingRuleId, setEditingRuleId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [ruleItems, runPage, deadLetterPage] = await Promise.all([
        getAutomationRules(),
        getAutomationRuns(),
        getAutomationDeadLetters(),
      ]);
      setRules(ruleItems);
      setRuns(runPage.items);
      setDeadLetters(deadLetterPage.items);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason, "Automatisierungen konnten nicht geladen werden."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  function resetForm() {
    setName("");
    setDescription("");
    setTriggerType("task.assigned");
    setConditionStatus("");
    setEditingRuleId("");
  }

  async function saveRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = {
        name: name.trim(),
        description: description.trim() || undefined,
        trigger_type: triggerType,
        conditions: triggerType.startsWith("task.") && conditionStatus
          ? { status: conditionStatus }
          : {},
      };
      if (editingRuleId) {
        await updateAutomationRule(editingRuleId, data);
        setNotice("Regel wurde aktualisiert.");
      } else {
        await createAutomationRule(data);
        setNotice("Regel wurde angelegt und ist zunächst deaktiviert.");
      }
      resetForm();
      await loadData();
    } catch (reason) {
      setError(messageFrom(reason, "Regel konnte nicht gespeichert werden."));
    } finally {
      setBusy(false);
    }
  }

  function editRule(rule: AutomationRule) {
    setEditingRuleId(rule.id);
    setName(rule.name);
    setDescription(rule.description ?? "");
    setTriggerType(rule.trigger_type);
    setConditionStatus(rule.conditions.status ?? "");
    setNotice("");
    setError("");
  }

  async function toggleRule(rule: AutomationRule) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await updateAutomationRule(rule.id, { is_active: !rule.is_active });
      await loadData();
      setNotice(rule.is_active ? "Regel wurde deaktiviert." : "Regel wurde aktiviert.");
    } catch (reason) {
      setError(messageFrom(reason, "Regelstatus konnte nicht geändert werden."));
    } finally {
      setBusy(false);
    }
  }

  async function removeRule(rule: AutomationRule) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await deleteAutomationRule(rule.id);
      if (editingRuleId === rule.id) resetForm();
      await loadData();
      setNotice("Regel wurde deaktiviert und aus der Übersicht entfernt.");
    } catch (reason) {
      setError(messageFrom(reason, "Regel konnte nicht entfernt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function retryRun(runId: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await retryAutomationRun(runId);
      await loadData();
      setNotice("Automatisierungslauf wurde zur kontrollierten Wiederholung vorgemerkt.");
    } catch (reason) {
      setError(messageFrom(reason, "Automatisierungslauf konnte nicht wiederholt werden."));
    } finally {
      setBusy(false);
    }
  }

  async function retryEvent(eventId: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await retryAutomationEvent(eventId);
      await loadData();
      setNotice("Ereignis wurde zur kontrollierten Wiederholung vorgemerkt.");
    } catch (reason) {
      setError(messageFrom(reason, "Ereignis konnte nicht wiederholt werden."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="automation-module">
      <header className="panel-heading">
        <div><p className="eyebrow">ADMINISTRATION</p><h2>Automatisierungen</h2></div>
        <button className="secondary-button" disabled={loading || busy} onClick={() => void loadData()}>
          Aktualisieren
        </button>
      </header>
      {error && <p className="alert" role="alert">{error}</p>}
      {notice && <p className="success-message" role="status">{notice}</p>}

      <section className="panel" aria-labelledby="automation-rule-form-heading">
        <div className="panel-heading">
          <div><p className="eyebrow">REGELWERK</p>
            <h3 id="automation-rule-form-heading">
              {editingRuleId ? "Regel bearbeiten" : "Regel anlegen"}
            </h3>
          </div>
        </div>
        <p className="muted">
          Verfügbar sind registrierte Aufgabenereignisse sowie versäumte Kontrollen,
          gemeldete OWKS-Auffälligkeiten, erfolgreich synchronisierte Offline-Ereignisse und
          manuelle Rechnungsfreigaben. Benachrichtigungen gehen nur an aktive Benutzer mit
          passender Objektzuweisung beziehungsweise Rechnungslese- und Benachrichtigungsrecht.
          Neue Regeln starten deaktiviert.
        </p>
        <form className="form-panel automation-form" onSubmit={(event) => void saveRule(event)}>
          <label>Regelname<input value={name} onChange={(event) => setName(event.target.value)}
            maxLength={100} required /></label>
          <label>Beschreibung<input value={description}
            onChange={(event) => setDescription(event.target.value)} maxLength={500} /></label>
          <div className="form-row">
            <label>Auslöser<select value={triggerType}
              onChange={(event) => {
                const trigger = event.target.value as AutomationTrigger;
                setTriggerType(trigger);
                if (!trigger.startsWith("task.")) setConditionStatus("");
              }}>
              <option value="task.assigned">Aufgabe zugewiesen</option>
              <option value="task.status_changed">Aufgabenstatus geändert</option>
              <option value="owks.missed_control">Kontrollpunkt nicht kontrolliert</option>
              <option value="owks.deviation_reported">OWKS-Auffälligkeit gemeldet</option>
              <option value="owks.offline_event_synced">Offline-Ereignis synchronisiert</option>
              <option value="billing.invoice_approved">Rechnung manuell freigegeben</option>
            </select></label>
            {triggerType.startsWith("task.") && <label>Bedingung: Aufgabenstatus<select value={conditionStatus}
              onChange={(event) => setConditionStatus(event.target.value as AutomationTaskStatus | "")}>
              <option value="">Beliebiger Status</option>
              {taskStatuses.map((item) => <option key={item.value} value={item.value}>
                {item.label}
              </option>)}
            </select></label>}
          </div>
          <div className="form-actions">
            <button className="primary-button" disabled={busy || !name.trim()}>
              {busy ? "Wird gespeichert …" : editingRuleId ? "Änderungen speichern" : "Regel anlegen"}
            </button>
            {editingRuleId && <button type="button" className="secondary-button"
              disabled={busy} onClick={resetForm}>Abbrechen</button>}
          </div>
        </form>
      </section>

      <section className="panel" aria-labelledby="automation-rules-heading">
        <div className="panel-heading">
          <div><p className="eyebrow">REGELN</p><h3 id="automation-rules-heading">Verwaltete Regeln</h3></div>
          <span className="result-count">{rules.length} Regeln</span>
        </div>
        {loading ? <p className="muted" role="status">Regeln werden geladen …</p>
          : rules.length === 0 ? <p className="empty">Noch keine Regeln angelegt.</p>
          : <ul className="automation-list">{rules.map((rule) => (
            <li key={rule.id}>
              <div>
                <strong>{rule.name}</strong>
                <p>{rule.description || "Keine Beschreibung"}</p>
                <span>{triggerNames[rule.trigger_type]} · {
                  rule.trigger_type.startsWith("task.")
                    ? `Status: ${rule.conditions.status
                      ? taskStatuses.find((item) => item.value === rule.conditions.status)?.label
                      : "beliebig"}`
                    : "keine Bedingung"
                } · Aktion: In-App-Benachrichtigung</span>
              </div>
              <div className="automation-actions">
                <span className={rule.is_active ? "automation-active" : "automation-inactive"}>
                  {rule.is_active ? "Aktiv" : "Deaktiviert"}
                </span>
                <button className="secondary-button" disabled={busy}
                  onClick={() => editRule(rule)}>Bearbeiten</button>
                <button className="secondary-button" disabled={busy}
                  onClick={() => void toggleRule(rule)}>
                  {rule.is_active ? "Deaktivieren" : "Aktivieren"}
                </button>
                <button className="secondary-button danger-button" disabled={busy}
                  onClick={() => void removeRule(rule)}>Entfernen</button>
              </div>
            </li>
          ))}</ul>}
      </section>

      <section className="panel" aria-labelledby="automation-runs-heading">
        <div className="panel-heading">
          <div><p className="eyebrow">NACHVOLLZIEHBARKEIT</p>
            <h3 id="automation-runs-heading">Ausführungshistorie</h3>
          </div>
          <span className="result-count">{runs.length} Einträge</span>
        </div>
        {runs.length === 0 ? <p className="empty">Keine Ausführungen vorhanden.</p>
          : <ul className="automation-list">{runs.map((run) => (
            <li key={run.id}>
              <div>
                <strong>{run.rule_name}</strong>
                <p>{triggerNames[run.trigger_type]} · {runStatusNames[run.status]}</p>
                <span>{formatDate(run.created_at)} · Fehlercode: {run.last_error ?? "—"}
                  {run.attempt_history.length > 0
                    ? ` · Versuche: ${run.attempt_history.length}`
                    : ""}
                </span>
              </div>
              {run.status === "dead_letter" && <button className="secondary-button"
                disabled={busy || run.manual_retry_count >= 3}
                onClick={() => void retryRun(run.id)}>Erneut versuchen</button>}
            </li>
          ))}</ul>}
      </section>

      <section className="panel" aria-labelledby="automation-deadletters-heading">
        <div className="panel-heading">
          <div><p className="eyebrow">FEHLERABLAGE</p><h3 id="automation-deadletters-heading">
            Fehlgeschlagene Outbox-Ereignisse</h3></div>
          <span className="result-count">{deadLetters.length} Ereignisse</span>
        </div>
        {deadLetters.length === 0 ? <p className="empty">Keine Ereignisse in der Fehlerablage.</p>
          : <ul className="automation-list">{deadLetters.map((event) => (
            <li key={event.id}>
              <div><strong>{eventNames[event.event_type] ?? "Unbekanntes Ereignis"}</strong>
                <p>Fehlercode: {event.last_error ?? "—"} · Versuche: {event.attempt_count}</p>
                <span>{formatDate(event.created_at)} · Wiederholungen: {event.manual_retry_count}/3</span>
              </div>
              <button className="secondary-button" disabled={busy || event.manual_retry_count >= 3}
                onClick={() => void retryEvent(event.id)}>Erneut versuchen</button>
            </li>
          ))}</ul>}
      </section>

      <section className="panel automation-limits" aria-labelledby="automation-limits-heading">
        <h3 id="automation-limits-heading">Nicht verfügbare Auslöser</h3>
        <p>
          Kontrollgang gestartet/beendet oder unvollständig, Qualifikationsablauf,
          unbesetzte Dienste, Vorfälle, Schlüssel/Inventar, Dokumente/Verträge, allgemeine
          Aufgabenfristen und Worker-Ausfall sind nicht registriert und daher nicht auswählbar.
          Rechnungsfreigaben erzeugen nur eine neutrale In-App-Benachrichtigung für derzeit
          berechtigte Leser. Regeln veröffentlichen keine personenbezogenen OWKS-Beschreibungen
          und ändern keine Aufgaben-, Personal-, OWKS-, Vertrags- oder Rechnungszustände.
        </p>
      </section>
    </section>
  );
}
