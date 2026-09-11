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

function formatValue(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(1);
}

export function LineupView({ payload, target, loading, error, onTargetChange }: LineupViewProps) {
  const notices: string[] = [];
  const lockedCount = payload?.locked_count ?? 0;
  const remainingMode = lockedCount > 0;
  if (payload?.unmodeled_slots.length) {
    notices.push(`Not modeled: ${payload.unmodeled_slots.join(', ')}.`);
  }
  if (payload?.unfilled_slots.length) {
    notices.push(`No priced option for: ${payload.unfilled_slots.join(', ')}.`);
  }
  if (remainingMode) {
    notices.unshift(
      `${lockedCount} ${lockedCount === 1 ? 'slot is' : 'slots are'} locked at actual Sleeper points; only unstarted slots are optimized.`,
    );
  }
  if (payload?.locked_bench?.length) {
    notices.push(
      `Already played on bench: ${payload.locked_bench
        .map((row) => `${row.name} (${row.actual_points.toFixed(1)} FP)`)
        .join(', ')}.`,
    );
  }
  if (payload?.defense_note) notices.push(payload.defense_note);

  return (
    <main className="decision-view" aria-label="Best lineup">
      <header className="decision-heading lineup-heading">
        <div>
          <span className="eyebrow">Starter optimization</span>
          <h2>{remainingMode ? 'Best remaining lineup' : 'Best lineup'}</h2>
          <p>
            {remainingMode
              ? "Started players are fixed where you submitted them; choose the risk lens for the decisions you can still change."
              : "Choose the risk lens used to maximize the league's modeled starter slots."}
          </p>
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

      {loading ? <div className="decision-loading">Optimizing movable starter slots…</div> : null}
      {error ? <div className="error-state">{error}</div> : null}
      {!loading && !error && payload ? (
        <>
          <div className="lineup-total">
            <span>{remainingMode ? `Actual + projected ${label(payload.target)}` : `Projected ${label(payload.target)}`}</span>
            <strong>{payload.total_points.toFixed(1)}</strong>
          </div>
          {remainingMode ? (
            <div className="status-note">
              {formatValue(payload.actual_points)} FP already scored ·{' '}
              {formatValue(payload.remaining_projected_points)} FP projected from remaining slots ·{' '}
              {payload.decisions_remaining ?? 0} decisions remain.
            </div>
          ) : null}
          {notices.length ? <div className="status-note">{notices.join(' ')}</div> : null}
          <div className="decision-table-scroll">
            <table className="decision-table lineup-table">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Player</th>
                  <th>Pos</th>
                  <th>Team</th>
                  <th className="number">{remainingMode ? 'Actual / selected' : 'Selected'}</th>
                  <th className="number">Floor</th>
                  <th className="number">Mid</th>
                  <th className="number">Ceiling</th>
                </tr>
              </thead>
              <tbody>
                {payload.lineup.map((row) => (
                  <tr key={`${row.slot}:${row.name}`} className={row.locked ? 'unavailable' : ''}>
                    <td>
                      <strong>{row.slot}</strong>
                    </td>
                    <td>
                      {row.name}
                      {row.locked ? <span className="row-secondary">LOCKED · actual</span> : null}
                    </td>
                    <td>{row.pos}</td>
                    <td>{row.team || '—'}</td>
                    <td className="number primary-decision-value">{row.points.toFixed(1)}</td>
                    <td className="number">{row.locked ? '—' : formatValue(row.floor)}</td>
                    <td className="number">{row.locked ? '—' : formatValue(row.mid)}</td>
                    <td className="number">{row.locked ? '—' : formatValue(row.ceiling)}</td>
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