import type { LineupTarget } from '../state/workspace';
import type { LineupResponse } from '../types';

interface LineupViewProps {
  payload: LineupResponse | null;
  target: LineupTarget;
  loading: boolean;
  error: string | null;
  onTargetChange: (target: LineupTarget) => void;
}

const TARGETS: LineupTarget[] = ['floor', 'mid', 'ceiling'];

function label(value: LineupTarget): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatValue(value: number | null): string {
  return value === null ? '—' : value.toFixed(1);
}

export function LineupView({ payload, target, loading, error, onTargetChange }: LineupViewProps) {
  const notices: string[] = [];
  if (payload?.unmodeled_slots.length) {
    notices.push(`Not modeled: ${payload.unmodeled_slots.join(', ')}.`);
  }
  if (payload?.unfilled_slots.length) {
    notices.push(`No priced option for: ${payload.unfilled_slots.join(', ')}.`);
  }
  if (payload?.defense_note) notices.push(payload.defense_note);

  return (
    <main className="decision-view" aria-label="Best lineup">
      <header className="decision-heading lineup-heading">
        <div>
          <span className="eyebrow">Starter optimization</span>
          <h2>Best lineup</h2>
          <p>Choose the risk lens used to maximize the league's modeled starter slots.</p>
        </div>
        <fieldset className="lineup-targets">
          <legend className="sr-only">Lineup optimization target</legend>
          {TARGETS.map((value) => (
            <button
              key={value}
              type="button"
              className={target === value ? 'active' : ''}
              onClick={() => onTargetChange(value)}
            >
              {label(value)}
            </button>
          ))}
        </fieldset>
      </header>

      {loading ? <div className="decision-loading">Optimizing modeled starter slots…</div> : null}
      {error ? <div className="error-state">{error}</div> : null}
      {!loading && !error && payload ? (
        <>
          <div className="lineup-total">
            <span>Projected {label(payload.target)}</span>
            <strong>{payload.total_points.toFixed(1)}</strong>
          </div>
          {notices.length ? <div className="status-note">{notices.join(' ')}</div> : null}
          <div className="decision-table-scroll">
            <table className="decision-table lineup-table">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Player</th>
                  <th>Pos</th>
                  <th>Team</th>
                  <th className="number">Selected</th>
                  <th className="number">Floor</th>
                  <th className="number">Mid</th>
                  <th className="number">Ceiling</th>
                </tr>
              </thead>
              <tbody>
                {payload.lineup.map((row) => (
                  <tr key={`${row.slot}:${row.name}`}>
                    <td>
                      <strong>{row.slot}</strong>
                    </td>
                    <td>{row.name}</td>
                    <td>{row.pos}</td>
                    <td>{row.team || '—'}</td>
                    <td className="number primary-decision-value">{row.points.toFixed(1)}</td>
                    <td className="number">{formatValue(row.floor)}</td>
                    <td className="number">{formatValue(row.mid)}</td>
                    <td className="number">{formatValue(row.ceiling)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </main>
  );
}
