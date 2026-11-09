import { FormEvent, useEffect, useState } from "react";
import { getGlobalSearch } from "./api";
import type {
  GlobalSearchEntityType,
  GlobalSearchPage,
  GlobalSearchResult,
} from "./types";

const pageSize = 10;

const typeNames: Record<GlobalSearchEntityType, string> = {
  customer: "Kunde",
  object: "Objekt",
  employee: "Mitarbeiter",
  document: "Dokument",
  contract: "Vertrag",
  shift: "Dienst",
  task: "Aufgabe",
  incident: "Vorfall/Beschwerde",
  key: "Schlüssel",
  inventory_asset: "Inventar",
  owks_event: "Wachbuch",
};

export default function GlobalSearch({
  availableTypes,
  onOpenResult,
}: {
  availableTypes: GlobalSearchEntityType[];
  onOpenResult: (result: GlobalSearchResult) => void;
}) {
  const [query, setQuery] = useState("");
  const [entityType, setEntityType] = useState<GlobalSearchEntityType | "">("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<GlobalSearchPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setPage(null);
      setLoading(false);
      setError("");
      return;
    }

    let active = true;
    setLoading(true);
    setError("");
    const timer = window.setTimeout(() => {
      getGlobalSearch({
        q: term,
        type: entityType,
        limit: pageSize,
        offset,
      })
        .then((result) => {
          if (active) setPage(result);
        })
        .catch((reason: unknown) => {
          if (active) {
            setPage(null);
            setError(reason instanceof Error
              ? reason.message
              : "Die Suche konnte nicht ausgeführt werden.");
          }
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [entityType, offset, query]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
  }

  return (
    <section className="panel global-search" aria-labelledby="global-search-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">BERECHTIGUNGSGEFILTERT</p>
          <h2 id="global-search-title">Globale Suche</h2>
        </div>
      </div>
      <form className="global-search-form" onSubmit={submit}>
        <label htmlFor="global-search-query">Freigegebene Bereiche durchsuchen</label>
        <div className="global-search-controls">
          <input
            id="global-search-query"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
            minLength={2}
            maxLength={100}
            placeholder="Mindestens zwei Zeichen"
          />
          {availableTypes.length > 1 && (
            <label className="sr-only" htmlFor="global-search-type">Suchbereich</label>
          )}
          {availableTypes.length > 1 && (
            <select
              id="global-search-type"
              aria-label="Suchbereich"
              value={entityType}
              onChange={(event) => {
                setEntityType(event.target.value as GlobalSearchEntityType | "");
                setOffset(0);
              }}
            >
              <option value="">Alle Treffer</option>
              {availableTypes.map((type) => (
                <option key={type} value={type}>{typeNames[type]}</option>
              ))}
            </select>
          )}
        </div>
      </form>

      {query.trim().length === 1 && (
        <p className="muted" role="status">Bitte mindestens zwei Zeichen eingeben.</p>
      )}
      {loading && <p className="muted" role="status">Suche läuft …</p>}
      {error && <p className="alert" role="alert">{error}</p>}
      {page && !loading && (
        <>
          <p className="result-count" role="status">{page.total} Treffer</p>
          <ul className="global-search-results">
            {page.items.map((result) => (
              <li key={`${result.type}-${result.id}`}>
                <div>
                  <span className="global-search-type">{typeNames[result.type]}</span>
                  <strong>{result.title}</strong>
                  <small>{result.reference}</small>
                </div>
                <button className="text-button" onClick={() => onOpenResult(result)}>
                  Öffnen
                </button>
              </li>
            ))}
            {page.items.length === 0 && (
              <li className="muted">Keine passenden Treffer.</li>
            )}
          </ul>
          {page.total > pageSize && (
            <div className="pagination">
              <span className="result-count">
                {offset + 1}–{Math.min(offset + page.items.length, page.total)} von {page.total}
              </span>
              <div>
                <button
                  className="secondary-button"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - pageSize))}
                >
                  Zurück
                </button>
                <button
                  className="secondary-button"
                  disabled={offset + pageSize >= page.total}
                  onClick={() => setOffset(offset + pageSize)}
                >
                  Weiter
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
