import type { DefenseResponse } from '../types';

interface DefenseViewProps {
  payload: DefenseResponse | null;
  loading: boolean;
  error: string | null;
}

function formatValue(value: number | null): string {
  return value === null ? '—' : value.toFixed(1);
}

function ownershipLabel(row: DefenseResponse['defenses'][number]): string {
  if (row.owned_by_current) return 'Yours';
  if (row.taken) return row.owner ? `Taken · ${row.owner}` : 'Taken';
  return 'Available';
}

function ownershipClass(row: DefenseResponse['defenses'][number]): string {
  if (row.owned_by_current) return 'yours';
  if (row.taken) return 'taken';
  return 'available';
}

export function DefenseView({ payload, loading, error }: DefenseViewProps) {
  return (
    <main className="decision-view" aria-label="Defense analysis">
      <header className="decision-heading">
        <div>
          <span className="eyebrow">Matchup ranking</span>
          <h2>Defenses</h2>
          <p>Lower opponent implied team total is the stronger market matchup.</p>
        </div>
        {payload?.ratelimit ? <span className="decision-meta">{payload.ratelimit}</span> : null}
      </header>

      {loading ? <div className="decision-loading">Loading spread and total markets…</div> : null}
      {error ? <div className="error-state">{error}</div> : null}
      {!error && payload?.message ? <div className="status-note">{payload.message}</div> : null}
      {!loading && !error && payload ? (
        <>
          <div className="decision-table-scroll">
            <table className="decision-table defense-table">
              <thead>
                <tr>
                  <th>Defense</th>
                  <th>Opponent</th>
                  <th className="number">Opp. implied</th>
                  <th className="number">Floor</th>
                  <th className="number">Mid</th>
                  <th className="number">Ceiling</th>
                  <th className="number">Books</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {payload.defenses.map((row) => (
                  <tr key={row.defense} className={row.implied_total === null ? 'unavailable' : ''}>
                    <td>
                      <strong>{row.abbr || row.defense}</strong>
                      <span className="row-secondary">{row.defense}</span>
                    </td>
                    <td>{row.opponent}</td>
                    <td className="number primary-decision-value">
                      {formatValue(row.implied_total)}
                    </td>
                    <td className="number">{formatValue(row.floor)}</td>
                    <td className="number">{formatValue(row.mid)}</td>
                    <td className="number">{formatValue(row.ceiling)}</td>
                    <td className="number">{row.book_count}</td>
                    <td>
                      <span className={`ownership ${ownershipClass(row)}`}>
                        {ownershipLabel(row)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {payload.note ? <p className="decision-note">{payload.note}</p> : null}
        </>
      ) : null}
    </main>
  );
}
