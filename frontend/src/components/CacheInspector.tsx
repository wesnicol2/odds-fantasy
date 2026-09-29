import { useEffect, useMemo, useState } from 'react';
import '../cache-browser.css';

type CacheFile = {
  name: string;
  bytes: number;
  modified_at: number;
  entry_count: number;
  parse_error: string | null;
};

type CacheEntry = {
  id: string;
  key: string;
  fetched_at: number | null;
  age_seconds: number | null;
  summary: string;
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

export function CacheInspector() {
  const [files, setFiles] = useState<CacheFile[]>([]);
  const [file, setFile] = useState<string | null>(null);
  const [entries, setEntries] = useState<CacheEntry[]>([]);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getJson<{ files: CacheFile[] }>('/debug/cache')
      .then((payload) => {
        setFiles(payload.files);
        setFile((current) => current ?? payload.files[0]?.name ?? null);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : 'Could not load cache index.'),
      );
  }, []);

  useEffect(() => {
    if (!file) return;
    getJson<{ entries: CacheEntry[] }>(`/debug/cache?file=${encodeURIComponent(file)}`)
      .then((payload) => {
        setEntries(payload.entries);
        setError(null);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : 'Could not load cache entries.'),
      );
  }, [file]);

  const visibleEntries = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return needle
      ? entries.filter((entry) => `${entry.key} ${entry.summary}`.toLowerCase().includes(needle))
      : entries;
  }, [entries, filter]);

  return (
    <main className="cache-browser">
      <header className="cache-browser-header">
        <div>
          <div className="eyebrow">Settings</div>
          <h1>Cache inspector</h1>
          <p>Read-only cache inventory with request credentials removed from displayed keys.</p>
        </div>
        <a href="/">Back to app</a>
      </header>
      {error ? <div className="cache-browser-error">{error}</div> : null}
      <div className="cache-browser-grid safe-grid">
        <aside className="cache-files">
          {files.map((item) => (
            <button
              key={item.name}
              type="button"
              className={item.name === file ? 'active' : ''}
              onClick={() => setFile(item.name)}
            >
              <span>{item.name}</span>
              <small>{item.entry_count} entries</small>
            </button>
          ))}
        </aside>
        <section className="cache-entries">
          <div className="cache-pane-heading cache-entry-heading">
            <span>{file ?? 'Entries'}</span>
            <input
              type="search"
              value={filter}
              placeholder="Filter keys"
              aria-label="Filter cache entries"
              onChange={(event) => setFilter(event.target.value)}
            />
          </div>
          <div className="cache-entry-list">
            {visibleEntries.map((entry) => (
              <div className="cache-entry-row" key={entry.id}>
                <code>{entry.key}</code>
                <span>
                  {entry.summary} · {ageLabel(entry.age_seconds)}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
