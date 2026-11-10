import { useEffect, useState, type FormEvent } from "react";
import {
  addCustomerPortalRequestMessage,
  createCustomerPortalRequest,
  downloadCustomerPortalInvoice,
  downloadCustomerPortalDocument,
  downloadCustomerPortalRequestAttachment,
  getCustomerPortalDocuments,
  uploadCustomerPortalRequestAttachment,
  getCustomerPortalInvoices,
  getCustomerPortalMe,
  getCustomerPortalRequests,
  logout,
} from "./api";
import type {
  AuthUser,
  CustomerPortalDocument,
  CustomerPortalInvoice,
  CustomerPortalMe,
  CustomerPortalRequest,
} from "./types";

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

const requestStatusLabels: Record<CustomerPortalRequest["status"], string> = {
  submitted: "Eingegangen",
  in_progress: "In Bearbeitung",
  waiting_customer: "Rückfrage an Sie",
  resolved: "Gelöst",
  closed: "Geschlossen",
};

export default function CustomerPortal({
  user,
  onSignedOut,
}: {
  user: AuthUser;
  onSignedOut: () => void;
}) {
  const [portal, setPortal] = useState<CustomerPortalMe | null>(null);
  const [invoices, setInvoices] = useState<CustomerPortalInvoice[]>([]);
  const [documents, setDocuments] = useState<CustomerPortalDocument[]>([]);
  const [requests, setRequests] = useState<CustomerPortalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyInvoice, setBusyInvoice] = useState("");
  const [busyDocument, setBusyDocument] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      getCustomerPortalMe(),
      getCustomerPortalInvoices(),
      getCustomerPortalDocuments(),
      getCustomerPortalRequests(),
    ])
      .then(([me, invoiceList, documentList, requestList]) => {
        if (!active) return;
        setPortal(me);
        setInvoices(invoiceList);
        setDocuments(documentList);
        setRequests(requestList);
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

  async function submitRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setError("");
    setNotice("");
    try {
      const created = await createCustomerPortalRequest({
        category: String(data.get("category")) as "request" | "question" | "complaint",
        object_id: String(data.get("object_id")),
        title: String(data.get("title")).trim(),
        first_message: String(data.get("first_message")).trim(),
      });
      const file = data.get("attachment");
      let attachmentError = "";
      if (file instanceof File && file.size > 0) {
        try {
          await uploadCustomerPortalRequestAttachment(created.id, file);
        } catch (reason) {
          attachmentError = reason instanceof Error ? reason.message : "Datei konnte nicht hochgeladen werden.";
        }
      }
      setRequests(await getCustomerPortalRequests());
      setNotice(attachmentError
        ? `Vorgang wurde angelegt. Der Anhang wurde nicht übernommen: ${attachmentError}`
        : "Ihre Anfrage wurde übermittelt.");
      form.reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Anfrage konnte nicht übermittelt werden.");
    }
  }

  async function replyToRequest(event: FormEvent<HTMLFormElement>, requestId: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = String(new FormData(form).get("reply") ?? "").trim();
    if (!body) return;
    try {
      await addCustomerPortalRequestMessage(requestId, body);
      setRequests(await getCustomerPortalRequests());
      form.reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Nachricht konnte nicht gesendet werden.");
    }
  }

  async function downloadRequestAttachment(
    requestItem: CustomerPortalRequest,
    attachmentId: string,
    fileName: string,
  ) {
    try {
      const blob = await downloadCustomerPortalRequestAttachment(requestItem.id, attachmentId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Anhang konnte nicht geladen werden.");
    }
  }

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

  async function downloadDocument(item: CustomerPortalDocument) {
    setBusyDocument(item.grant_id);
    setError("");
    try {
      const blob = await downloadCustomerPortalDocument(item.grant_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = item.file_name;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Dokument konnte nicht geladen werden.");
    } finally {
      setBusyDocument("");
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
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="SecurityOps Startseite">
          <span className="brand-mark">SO</span>
          <span className="brand-text">SecurityOps<small>Kundenportal</small></span>
        </a>
        <nav className="module-tabs" aria-label="Kundenportal">
          <a className="module-tab active" href="#portal-customer-title">Übersicht</a>
          <a className="module-tab" href="#portal-objects-title">Objekte</a>
          <a className="module-tab" href="#portal-invoices-title">Rechnungen</a>
          <a className="module-tab" href="#portal-documents-title">Dokumente</a>
          <a className="module-tab" href="#portal-requests-title">Anträge</a>
        </nav>
        <div className="sidebar-foot">
          <span className="sidebar-user">{user.full_name}</span>
          <button className="sign-out" onClick={() => void signOut()}>Abmelden</button>
        </div>
      </aside>
      <main className="main">
        <section className="page-head">
          <div>
            <p className="eyebrow">KUNDENPORTAL</p>
            <h1>Willkommen, {portal?.contact.first_name ?? user.full_name}.</h1>
            <p>Hier sehen Sie die für Ihr Konto freigegebenen Kundeninformationen.</p>
          </div>
        </section>

      {error && <p className="alert page-alert" role="alert">{error}</p>}
      {notice && <p className="success page-alert" role="status">{notice}</p>}
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

        <section className="panel" aria-labelledby="portal-documents-title">
          <div className="panel-heading">
            <div><p className="eyebrow">DOKUMENTE</p><h2 id="portal-documents-title">Freigegebene Dokumente</h2></div>
          </div>
          {documents.length === 0
            ? <p className="muted">Es liegen keine freigegebenen Dokumente vor.</p>
            : <div className="table-scroll">
              <table>
                <thead><tr><th>Dokument</th><th>Kategorie</th><th>Version</th><th>Freigegeben am</th><th>Datei</th></tr></thead>
                <tbody>{documents.map((item) => (
                  <tr key={item.grant_id}>
                    <td><strong>{item.title}</strong><small>{item.document_number}</small></td>
                    <td>{item.category}</td>
                    <td>{item.version}</td>
                    <td>{new Date(item.granted_at).toLocaleDateString("de-DE")}</td>
                    <td><button
                      type="button"
                      disabled={busyDocument === item.grant_id}
                      onClick={() => void downloadDocument(item)}
                    >{busyDocument === item.grant_id ? "Wird geladen …" : "Datei laden"}</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>}
        </section>

        <section className="panel" aria-labelledby="portal-requests-title">
          <div className="panel-heading">
            <div><p className="eyebrow">RÜCKFRAGEN & BESCHWERDEN</p><h2 id="portal-requests-title">Ihre Vorgänge</h2></div>
          </div>
          <form className="form-grid" onSubmit={(event) => void submitRequest(event)}>
            <label>Art
              <select name="category" defaultValue="question">
                <option value="question">Rückfrage</option>
                <option value="request">Anfrage</option>
                <option value="complaint">Beschwerde</option>
              </select>
            </label>
            <label>Objekt
              <select name="object_id" required defaultValue={portal.objects[0]?.id ?? ""}>
                {portal.objects.filter((object) => object.status === "active").map((object) => (
                  <option key={object.id} value={object.id}>{object.name} ({object.code})</option>
                ))}
              </select>
            </label>
            <label>Titel<input name="title" maxLength={200} required /></label>
            <label>Nachricht<textarea name="first_message" maxLength={4000} required /></label>
            <label>Anhang (PDF, PNG oder JPEG; höchstens 10 MiB)
              <input name="attachment" type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" />
            </label>
            <button type="submit" disabled={!portal.objects.some((object) => object.status === "active")}>
              Anfrage übermitteln
            </button>
          </form>
          {requests.length === 0
            ? <p className="muted">Sie haben noch keine Vorgänge.</p>
            : <div className="content-grid">
              {requests.map((item) => (
                <article className="panel" key={item.id}>
                  <div className="panel-heading">
                    <div><h3>{item.title}</h3><p className="muted">{
                      item.category === "complaint"
                        ? "Beschwerde"
                        : item.category === "request" ? "Anfrage" : "Rückfrage"
                    } · {item.object_name}</p></div>
                    <span className="status">{requestStatusLabels[item.status]}</span>
                  </div>
                  {item.messages.map((message) => (
                    <p key={message.id}>
                      <strong>{message.author_id === user.id ? "Sie" : "SecurityOps"} · </strong>
                      {message.body}
                    </p>
                  ))}
                  {item.attachments.map((attachment) => (
                    <button
                      type="button"
                      className="text-button"
                      key={attachment.id}
                      onClick={() => void downloadRequestAttachment(item, attachment.id, attachment.file_name)}
                    >Anhang laden: {attachment.file_name}</button>
                  ))}
                  <form className="form-grid" onSubmit={(event) => {
                    void replyToRequest(event, item.id);
                  }}>
                    <label>Nachricht ergänzen
                      <textarea name="reply" maxLength={4000} required />
                    </label>
                    <button type="submit">Nachricht senden</button>
                  </form>
                </article>
              ))}
            </div>}
        </section>
      </>}
      </main>
    </div>
  );
}
