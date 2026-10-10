import { useEffect, useMemo, useState } from 'react';
import '../cache-browser.css';

type OddsRow = {
  id: string;
  provider: string;
  source: string;
  player: string;
  market: string;
  market_key: string;
  side: string;
  line: number | string | null;
  american_odds: number | null;
  decimal_odds: number | null;
  probability: number | null;
  price_source: string;
  raw_title: string;
  cache_file: string;
  age_seconds: number | null;
};

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return (await response.json()) as T;
}

function ageLabel(seconds: number | null): string {
  if (seconds === null) return 'age unknown';
  if (seconds < 60) return `${Math.round(seconds)}s old`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m old`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h old`;
  return `${(seconds / 86400).toFixed(1)}d old`;
}

function americanLabel(value: number | null): string {
  if (value === null) return '—';
  return value > 0 ? `+${value}` : `${value}`;
}

function decimalLabel(value: number | null): string {
  return value === null ? '—' : value.toFixed(2);
}

function probabilityLabel(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`;
}

function lineLabel(row: OddsRow): string {
  if (row.line === null || row.line === '') return row.side || '—';
  return `${row.side} ${row.line}`.trim();
}

export function CacheInspector() {
  const [rows, setRows] = useState<OddsRow[]>([]);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJson<{ rows: OddsRow[]; count: number }>('/debug/odds-cache')
      .then((payload) => {
        setRows(payload.rows);
        setError(null);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : 'Could not load cached odds.'),
      );
  }, []);

  const visibleRows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) =>
      [row.player, row.market, row.market_key, row.provider, row.source, row.side, row.raw_title]
        .join(' ')
        .toLowerCase()
        .includes(needle),
    );
  }, [filter, rows]);

  return (
    <main className="cache-browser">
      <header className="cache-browser-header">
        <div>
          <div className="eyebrow">Settings</div>
          <h1>Cached odds</h1>
          <p>
            Search the odds currently stored locally and verify exactly what each source reported.
          </p>
        </div>
        <a href="/">Back to app</a>
      </header>

      <section className="cache-search-panel">
        <input
          type="search"
          value={filter}
          placeholder="Search player or market — e.g. Justin Jefferson or anytime touchdown"
          aria-label="Search cached odds by player or market"
          onChange={(event) => setFilter(event.target.value)}
        />
        <div className="cache-search-count">
          {visibleRows.length.toLocaleString()} of {rows.length.toLocaleString()} cached odds
        </div>
      </section>

      {error ? <div className="cache-browser-error">{error}</div> : null}

      <section className="cache-odds-shell">
        <div className="cache-odds-table-wrap">
          <table className="cache-odds-table">
            <thead>
              <tr>
                <th>Player</th>
                <th>Market</th>
                <th>Side / line</th>
                <th>Source</th>
                <th>Odds</th>
                <th>Implied</th>
                <th>Cached</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.player || '—'}</strong>
                    {row.raw_title && row.raw_title !== row.player ? (
                      <small>{row.raw_title}</small>
                    ) : null}
                  </td>
                  <td>
                    <span>{row.market}</span>
                    {row.market_key ? <small>{row.market_key}</small> : null}
                  </td>
                  <td className="cache-line-cell">{lineLabel(row)}</td>
                  <td>
                    <strong>{row.source}</strong>
                    <small>
                      {row.provider} · {row.price_source}
                    </small>
                  </td>
                  <td className="cache-odds-cell">
                    <strong>{americanLabel(row.american_odds)}</strong>
                    <small>{decimalLabel(row.decimal_odds)} decimal</small>
                  </td>
                  <td className="cache-number-cell">{probabilityLabel(row.probability)}</td>
                  <td>
                    <span>{ageLabel(row.age_seconds)}</span>
                    <small>{row.cache_file}</small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {visibleRows.length === 0 ? (
          <div className="cache-empty">No cached odds match that player or market.</div>
        ) : null}
      </section>
    </main>
  );
}
