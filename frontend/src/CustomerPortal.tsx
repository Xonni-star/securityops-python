import { useEffect, useState } from "react";
import {
  downloadCustomerPortalInvoice,
  getCustomerPortalInvoices,
  getCustomerPortalMe,
  logout,
} from "./api";
import type { AuthUser, CustomerPortalInvoice, CustomerPortalMe } from "./types";

function addressText(address: CustomerPortalMe["customer"]["business_address"]) {
  if (!address) return "Keine Anschrift hinterlegt.";
  return `${address.street} ${address.house_number}, ${address.postal_code} ${address.city}`;
}

function invoiceKind(kind: CustomerPortalInvoice["kind"]) {
  if (kind === "correction") return "Korrekturbeleg";
  if (kind === "cancellation") return "Stornobeleg";
  return "Rechnung";
}

function paymentStatus(status: CustomerPortalInvoice["payment_status"]) {
  if (status === "paid") return "Bezahlt";
  if (status === "partial") return "Teilweise bezahlt";
  return "Offen";
}

export default function CustomerPortal({
  user,
  onSignedOut,
}: {
  user: AuthUser;
  onSignedOut: () => void;
}) {
  const [portal, setPortal] = useState<CustomerPortalMe | null>(null);
  const [invoices, setInvoices] = useState<CustomerPortalInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyInvoice, setBusyInvoice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([getCustomerPortalMe(), getCustomerPortalInvoices()])
      .then(([me, invoiceList]) => {
        if (!active) return;
        setPortal(me);
        setInvoices(invoiceList);
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error
            ? reason.message
            : "Portaldaten konnten nicht geladen werden.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function downloadInvoice(invoice: CustomerPortalInvoice) {
    setBusyInvoice(invoice.id);
    setError("");
    try {
      const blob = await downloadCustomerPortalInvoice(invoice.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${invoice.invoice_number}.pdf`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Rechnung konnte nicht geladen werden.");
    } finally {
      setBusyInvoice("");
    }
  }

  async function signOut() {
    try {
      await logout();
    } finally {
      onSignedOut();
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="SecurityOps Startseite">
          <span className="brand-mark">S</span>
          <span>SECURITY<span className="brand-light">OPS</span></span>
        </a>
        <div className="account">
          <span className="topbar-label">{user.full_name}</span>
          <button className="sign-out" onClick={() => void signOut()}>Abmelden</button>
        </div>
      </header>

      <section className="intro">
        <p className="eyebrow">KUNDENPORTAL</p>
        <h1>Willkommen, {portal?.contact.first_name ?? user.full_name}.</h1>
        <p>Hier sehen Sie die für Ihr Konto freigegebenen Kundeninformationen.</p>
      </section>

      {error && <p className="alert page-alert" role="alert">{error}</p>}
      {loading && <p className="muted">Portaldaten werden geladen …</p>}

      {portal && <>
        <section className="panel" aria-labelledby="portal-customer-title">
          <div className="panel-heading">
            <div><p className="eyebrow">STAMMDATEN</p><h2 id="portal-customer-title">{portal.customer.company_name}</h2></div>
            <span className="result-count">{portal.customer.customer_number}</span>
          </div>
          <dl className="detail-list">
            <div><dt>Ansprechpartner</dt><dd>{portal.contact.first_name} {portal.contact.last_name}</dd></div>
            {portal.contact.responsibility && <div><dt>Funktion</dt><dd>{portal.contact.responsibility}</dd></div>}
            {portal.contact.email && <div><dt>E-Mail</dt><dd>{portal.contact.email}</dd></div>}
            {portal.contact.phone && <div><dt>Telefon</dt><dd>{portal.contact.phone}</dd></div>}
            {portal.customer.email && <div><dt>Unternehmens-E-Mail</dt><dd>{portal.customer.email}</dd></div>}
            {portal.customer.phone && <div><dt>Telefon Zentrale</dt><dd>{portal.customer.phone}</dd></div>}
            <div><dt>Geschäftsanschrift</dt><dd>{addressText(portal.customer.business_address)}</dd></div>
            <div><dt>Rechnungsanschrift</dt><dd>{addressText(portal.customer.billing_address)}</dd></div>
          </dl>
        </section>

        <section className="panel" aria-labelledby="portal-objects-title">
          <div className="panel-heading">
            <div><p className="eyebrow">STANDORTE</p><h2 id="portal-objects-title">Ihre Objekte</h2></div>
          </div>
          {portal.objects.length === 0
            ? <p className="muted">Derzeit sind keine Objekte hinterlegt.</p>
            : <div className="content-grid">
              {portal.objects.map((object) => (
                <article className="panel" key={object.id}>
                  <h3>{object.name}</h3>
                  <p className="muted">{object.code}{object.object_type ? ` · ${object.object_type}` : ""}</p>
                  <p>{object.address ? addressText(object.address) : "Keine Anschrift hinterlegt."}</p>
                  {object.operating_hours && <p><strong>Betriebszeiten:</strong> {object.operating_hours}</p>}
                  {object.service_times && <p><strong>Leistungszeiten:</strong> {object.service_times}</p>}
                </article>
              ))}
            </div>}
        </section>

        <section className="panel" aria-labelledby="portal-invoices-title">
          <div className="panel-heading">
            <div><p className="eyebrow">ABRECHNUNG</p><h2 id="portal-invoices-title">Freigegebene Rechnungen</h2></div>
          </div>
          {invoices.length === 0
            ? <p className="muted">Es liegen keine freigegebenen Rechnungen vor.</p>
            : <div className="table-scroll">
              <table>
                <thead><tr>
                  <th>Beleg</th><th>Art</th><th>Datum</th><th>Fällig am</th>
                  <th>Status</th><th>Gesamt</th><th>Leistungen</th><th>PDF</th>
                </tr></thead>
                <tbody>{invoices.map((invoice) => (
                  <tr key={invoice.id}>
                    <td>{invoice.invoice_number}</td>
                    <td>{invoiceKind(invoice.kind)}</td>
                    <td>{invoice.issued_on}</td>
                    <td>{invoice.due_on}</td>
                    <td>{paymentStatus(invoice.payment_status)}</td>
                    <td>{invoice.gross_amount} {invoice.currency}</td>
                    <td>{invoice.lines.map((line) => `${line.description} (${line.quantity} ${line.unit})`).join("; ")}</td>
                    <td><button
                      type="button"
                      disabled={busyInvoice === invoice.id}
                      onClick={() => void downloadInvoice(invoice)}
                    >{busyInvoice === invoice.id ? "Wird geladen …" : "PDF laden"}</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>}
        </section>
      </>}
    </main>
  );
}
