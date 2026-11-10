import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  approveBillingInvoice,
  addBillingPayment,
  archiveBillingInvoice,
  createBillingCorrection,
  createBillingInvoice,
  createBillingRate,
  exportBillingInvoice,
  exportBillingInvoiceCsv,
  getBillingInvoices,
  getBillingRates,
  getCustomers,
  updateBillingDunning,
} from "./api";
import type { AuthUser, BillingInvoice, BillingRate, Customer } from "./types";

function messageFrom(reason: unknown) {
  return reason instanceof Error ? reason.message : "Die Rechnungsdaten konnten nicht verarbeitet werden.";
}

function money(value: string, currency: string) {
  return new Intl.NumberFormat("de-DE", { style: "currency", currency }).format(Number(value));
}

export default function BillingManagement({ user }: { user: AuthUser }) {
  const canCreate = user.permissions.includes("billing.invoices.create");
  const canApprove = user.permissions.includes("billing.invoices.approve");
  const canArchive = user.permissions.includes("billing.invoices.archive");
  const canManageRates = user.permissions.includes("billing.rates.manage");
  const canExport = user.permissions.includes("billing.exports.create");
  const canManagePayments = user.permissions.includes("billing.payments.manage");
  const canReadCustomers = user.permissions.includes("customers.read");
  const [rates, setRates] = useState<BillingRate[]>([]);
  const [invoices, setInvoices] = useState<BillingInvoice[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [nextRates, nextInvoices, customerPage] = await Promise.all([
        getBillingRates(),
        getBillingInvoices(),
        canReadCustomers
          ? getCustomers({
            q: "",
            status: "",
            contractStatus: "",
            includeArchived: false,
            sortBy: "company_name",
            sortOrder: "asc",
            limit: 500,
            offset: 0,
          })
          : Promise.resolve({ items: [] as Customer[] }),
      ]);
      setRates(nextRates);
      setInvoices(nextInvoices);
      setCustomers(customerPage.items);
      setError("");
    } catch (reason) {
      setError(messageFrom(reason));
    }
  }, [canReadCustomers]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function submitRate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      await createBillingRate({
        code: String(data.get("code")),
        name: String(data.get("name")),
        kind: String(data.get("kind")) as BillingRate["kind"],
        unit: String(data.get("unit")),
        unit_price: String(data.get("unit_price")),
        tax_code: String(data.get("tax_code")),
        tax_rate: String(data.get("tax_rate")),
        currency: "EUR",
      });
      form.reset();
      setNotice("Preiskonfiguration gespeichert.");
      await reload();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submitInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    try {
      await createBillingInvoice({
        idempotency_key: crypto.randomUUID(),
        customer_id: String(data.get("customer_id")),
        issued_on: String(data.get("issued_on")),
        due_on: String(data.get("due_on")),
        lines: [{
          rate_id: String(data.get("rate_id")),
          quantity: String(data.get("quantity")),
        }],
      });
      form.reset();
      setNotice("Rechnungsentwurf wurde erstellt.");
      await reload();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    try {
      await action();
      setNotice(success);
      await reload();
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function downloadPdf(invoice: BillingInvoice) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/v1/billing/invoices/${invoice.id}/pdf`, {
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("PDF konnte nicht geladen werden.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `${invoice.invoice_number}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  async function downloadCsv(invoice: BillingInvoice) {
    setBusy(true);
    setError("");
    try {
      const blob = await exportBillingInvoiceCsv(invoice.id, crypto.randomUUID());
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${invoice.invoice_number}.csv`;
      link.click();
      URL.revokeObjectURL(url);
      setNotice("CSV-Rechnungsexport heruntergeladen.");
    } catch (reason) {
      setError(messageFrom(reason));
    } finally {
      setBusy(false);
    }
  }

  const statusLabel = { draft: "Entwurf", approved: "Freigegeben", archived: "Archiviert" };

  return (
    <section className="content-grid billing-management">
      <section className="panel">
        <div className="panel-heading">
          <div><p className="eyebrow">FINANZEN</p><h2>Rechnungswesen</h2></div>
          <span className="result-count">{invoices.length} Rechnungen</span>
        </div>
        {error && <p className="alert" role="alert">{error}</p>}
        {notice && <p className="notice" role="status">{notice}</p>}
        <p className="muted">
          Preise und Steuerkennzeichen sind konfigurierbare Eingaben. Die Anwendung bestätigt keine
          steuerliche oder buchhalterische Konformität.
        </p>
        {canManageRates && <details>
          <summary>Abrechnungspreis konfigurieren</summary>
          <form onSubmit={(event) => void submitRate(event)}>
            <label>Schlüssel<input name="code" required maxLength={80} /></label>
            <label>Bezeichnung<input name="name" required maxLength={160} /></label>
            <label>Art<select name="kind">
              <option value="hourly">Stundenpreis</option>
              <option value="flat">Pauschale</option>
              <option value="surcharge">Zuschlag</option>
            </select></label>
            <label>Einheit<input name="unit" defaultValue="Stunde" required maxLength={40} /></label>
            <label>Preis<input name="unit_price" type="number" min="0" step="0.0001" required /></label>
            <label>Steuerkennzeichen<input name="tax_code" required maxLength={40} /></label>
            <label>Steuersatz (%)<input name="tax_rate" type="number" min="0" max="100" step="0.0001" required /></label>
            <button type="submit" disabled={busy}>Preis speichern</button>
          </form>
        </details>}
        {canCreate && <details>
          <summary>Rechnungsentwurf erstellen</summary>
          <form onSubmit={(event) => void submitInvoice(event)}>
            <label>Kunde<select name="customer_id" required>
              <option value="">Bitte auswählen</option>
              {customers.map((customer) =>
                <option key={customer.id} value={customer.id}>{customer.company_name}</option>)}
            </select></label>
            <label>Preis<select name="rate_id" required>
              <option value="">Bitte auswählen</option>
              {rates.map((rate) =>
                <option key={rate.id} value={rate.id}>
                  {rate.name} · {rate.unit_price} {rate.currency}/{rate.unit}
                </option>)}
            </select></label>
            <label>Menge<input name="quantity" type="number" min="0.0001" step="0.0001" required /></label>
            <label>Rechnungsdatum<input name="issued_on" type="date" required /></label>
            <label>Fällig am<input name="due_on" type="date" required /></label>
            <button type="submit" disabled={busy || customers.length === 0 || rates.length === 0}>
              Entwurf erstellen
            </button>
          </form>
        </details>}
        <div className="table-scroll">
          <table>
            <thead><tr>
              <th>Nummer</th><th>Kunde</th><th>Status</th><th>Fälligkeit</th><th>Gesamt</th><th>Aktionen</th>
            </tr></thead>
            <tbody>
              {invoices.map((invoice) => {
                const customer = customers.find((item) => item.id === invoice.customer_id)?.company_name
                  ?? invoice.customer_id;
                return <tr key={invoice.id}>
                  <td>{invoice.invoice_number}{invoice.kind !== "invoice" && <small> Folgebeleg</small>}</td>
                  <td>{customer}</td>
                  <td>{statusLabel[invoice.status]}</td>
                  <td>{new Date(`${invoice.due_on}T12:00:00`).toLocaleDateString("de-DE")}</td>
                  <td>{money(invoice.gross_amount, invoice.currency)}</td>
                  <td>
                    {invoice.status === "draft" && canApprove && <button disabled={busy}
                      onClick={() => void runAction(() => approveBillingInvoice(invoice.id), "Rechnung freigegeben.")}>
                      Freigeben
                    </button>}
                    {invoice.status === "approved" && <button disabled={busy}
                      onClick={() => void downloadPdf(invoice)}>PDF</button>}
                    {invoice.status === "approved" && canExport && <button disabled={busy}
                      onClick={() => void runAction(
                        () => exportBillingInvoice(invoice.id, crypto.randomUUID()),
                        "JSON-Export erstellt.",
                      )}>JSON-Export</button>}
                    {invoice.status !== "draft" && canExport && <button disabled={busy}
                      onClick={() => void downloadCsv(invoice)}>CSV herunterladen</button>}
                    {invoice.status === "approved" && invoice.payment_status !== "paid" && canManagePayments &&
                      <button disabled={busy} onClick={() => {
                        const amount = window.prompt("Zahlungseingang in EUR");
                        if (amount?.trim()) {
                          void runAction(
                            () => addBillingPayment(invoice.id, amount.trim().replace(",", ".")),
                            "Zahlungseingang erfasst.",
                          );
                        }
                      }}>Zahlung erfassen</button>}
                    {invoice.status === "approved" && invoice.payment_status !== "paid" && canManagePayments &&
                      <button disabled={busy} onClick={() => {
                        const status = window.prompt(
                          "Mahnstatus: none, reminder_1, reminder_2 oder final",
                          invoice.dunning_status,
                        );
                        if (status && ["none", "reminder_1", "reminder_2", "final"].includes(status)) {
                          void runAction(
                            () => updateBillingDunning(
                              invoice.id,
                              status as "none" | "reminder_1" | "reminder_2" | "final",
                              "Manuell durch berechtigte Person gesetzt",
                            ),
                            "Mahnstatus aktualisiert.",
                          );
                        }
                      }}>Mahnstatus</button>}
                    {invoice.kind === "invoice" && invoice.status !== "draft" && canCreate && <button disabled={busy}
                      onClick={() => {
                        const reason = window.prompt("Begründung für Folgebeleg");
                        if (reason?.trim()) {
                          void runAction(
                            () => createBillingCorrection(invoice.id, reason, crypto.randomUUID()),
                            "Korrekturbeleg als Entwurf erstellt.",
                          );
                        }
                      }}>Korrigieren</button>}
                    {invoice.status === "approved" && canArchive && <button disabled={busy}
                      onClick={() => void runAction(
                        () => archiveBillingInvoice(invoice.id, "Archivierung nach Prüfung"),
                        "Rechnung archiviert.",
                      )}>Archivieren</button>}
                  </td>
                </tr>;
              })}
            </tbody>
          </table>
        </div>
        {invoices.length === 0 && <p className="muted">Noch keine Rechnungen vorhanden.</p>}
      </section>
    </section>
  );
}
