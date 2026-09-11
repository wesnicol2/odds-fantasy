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

  const lockedCount = payload?.locked_count ?? 0;
  const hasLocks = lockedCount > 0;
  const lockedPoints = payload?.locked_points ?? 0;
  const remainingPoints = payload?.remaining_points ?? payload?.total_points ?? 0;
  const remainingSlots = payload?.remaining_slots ?? 0;

  return (
    <main className="decision-view" aria-label="Best lineup">
      <header className="decision-heading lineup-heading">
        <div>
          <span className="eyebrow">Starter optimization</span>
          <h2>{hasLocks ? 'Best remaining lineup' : 'Best lineup'}</h2>
          <p>
            {hasLocks
              ? 'Started players are frozen in their submitted slots. The selected risk lens optimizes only lineup decisions that can still change.'
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

      {loading ? <div className="decision-loading">Optimizing remaining starter slots…</div> : null}
      {error ? <div className="error-state">{error}</div> : null}
      {!loading && !error && payload ? (
        <>
          <div className="lineup-total">
            <span>
              {hasLocks
                ? `Actual + projected ${label(payload.target)}`
                : `Projected ${label(payload.target)}`}
            </span>
            <strong>{payload.total_points.toFixed(1)}</strong>
          </div>
          {hasLocks ? (
            <div className="lineup-live-summary" role="group" aria-label="Locked lineup summary">
              <span>
                <strong>{lockedCount}</strong> {lockedCount === 1 ? 'slot' : 'slots'} locked
              </span>
              <span>
                <strong>{lockedPoints.toFixed(1)}</strong> actual FP
              </span>
              <span>
                <strong>{remainingPoints.toFixed(1)}</strong> projected remaining FP
              </span>
              <span>
                <strong>{remainingSlots}</strong> {remainingSlots === 1 ? 'slot' : 'slots'} still
                open
              </span>
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
                  <th>Status</th>
                  <th className="number">{hasLocks ? 'Actual / selected' : 'Selected'}</th>
                  <th className="number">Floor</th>
                  <th className="number">Mid</th>
                  <th className="number">Ceiling</th>
                </tr>
              </thead>
              <tbody>
                {payload.lineup.map((row) => (
                  <tr
                    key={`${row.slot}:${row.name}`}
                    className={row.locked ? 'locked-row' : undefined}
                  >
                    <td>
                      <strong>{row.slot}</strong>
                    </td>
                    <td>{row.name}</td>
                    <td>{row.pos}</td>
                    <td>{row.team || '—'}</td>
                    <td>
                      <span
                        className={`lineup-status ${
                          row.locked ? (row.game_status === 'live' ? 'live' : 'final') : 'open'
                        }`}
                      >
                        {row.locked
                          ? row.game_status === 'live'
                            ? 'Live · locked'
                            : 'Final · locked'
                          : 'Open'}
                      </span>
                    </td>
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
