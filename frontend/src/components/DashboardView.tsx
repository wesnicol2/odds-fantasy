import '../dashboard.css';
import type { WeekWindow } from '../state/workspace';
import type { BenchPressureRow, DefenseResponse, DefenseRow, LineupResponse } from '../types';

interface DashboardViewProps {
  lineup: LineupResponse | null;
  defensesThisWeek: DefenseResponse | null;
  defensesNextWeek: DefenseResponse | null;
  loading: boolean;
  error: string | null;
  onOpenLineup: () => void;
  onOpenDefenses: (week: WeekWindow) => void;
  onCompareBenchPlayer: (player: BenchPressureRow) => void;
}

function formatPoints(value: number | null): string {
  return value === null ? '—' : value.toFixed(1);
}

function actionableDefenses(payload: DefenseResponse | null): DefenseRow[] {
  return (payload?.defenses ?? [])
    .filter((row) => row.owned_by_current || !row.taken)
    .filter((row) => row.implied_total !== null)
    .slice(0, 3);
}

function defenseStatus(row: DefenseRow): string {
  return row.owned_by_current ? 'Yours' : 'Available';
}

function DefenseShortlist({
  title,
  week,
  payload,
  onOpen,
}: {
  title: string;
  week: WeekWindow;
  payload: DefenseResponse | null;
  onOpen: (week: WeekWindow) => void;
}) {
  const rows = actionableDefenses(payload);
  return (
    <section className="dashboard-defense-window" aria-label={`${title} defense targets`}>
      <div className="dashboard-section-heading compact">
        <h3>{title}</h3>
        <button type="button" className="quiet-action" onClick={() => onOpen(week)}>
          View all
        </button>
      </div>
      {rows.length ? (
        <div className="dashboard-defense-list">
          {rows.map((row) => (
            <button
              key={row.defense}
              type="button"
              className="dashboard-defense-row"
              onClick={() => onOpen(week)}
            >
              <span className="dashboard-defense-name">
                <strong>{row.abbr || row.defense}</strong>
                <small>vs {row.opponent}</small>
              </span>
              <span className="dashboard-defense-matchup">
                <strong>{formatPoints(row.implied_total)}</strong>
                <small>opp. implied</small>
              </span>
              <span className={`dashboard-defense-status ${row.owned_by_current ? 'yours' : ''}`}>
                {defenseStatus(row)}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="dashboard-empty-copy">No playable available or owned defenses found.</p>
      )}
    </section>
  );
}

export function DashboardView({
  lineup,
  defensesThisWeek,
  defensesNextWeek,
  loading,
  error,
  onOpenLineup,
  onOpenDefenses,
  onCompareBenchPlayer,
}: DashboardViewProps) {
  const pressure = (lineup?.bench_pressure ?? []).slice(0, 4);
  const lockedCount = lineup?.locked_count ?? 0;
  const hasLocks = lockedCount > 0;
  const lockedPoints = lineup?.locked_points ?? 0;
  const remainingSlots = lineup?.remaining_slots ?? 0;
  const lockedBench = lineup?.locked_bench_count ?? 0;

  return (
    <main className="dashboard-view" aria-label="Dashboard">
      <header className="dashboard-heading">
        <div>
          <span className="eyebrow">This week</span>
          <h2>Lineup & pickups</h2>
        </div>
        {loading ? <span className="dashboard-loading">Updating plan…</span> : null}
      </header>

      {error ? <div className="error-state">{error}</div> : null}

      <div className="dashboard-grid">
        <section
          className="dashboard-lineup"
          aria-label={hasLocks ? 'Best remaining lineup this week' : 'Ideal lineup this week'}
        >
          <div className="dashboard-section-heading">
            <div>
              <span className="section-label">
                {hasLocks ? 'Best remaining lineup' : 'Ideal lineup'}
              </span>
              <h3>{hasLocks ? 'Actual + remaining mid projection' : 'Mid projection'}</h3>
            </div>
            <div className="dashboard-total">
              <strong>{lineup ? lineup.total_points.toFixed(1) : '—'}</strong>
              <span>{hasLocks ? 'current + projected FP' : 'total FP'}</span>
            </div>
          </div>

          {hasLocks ? (
            <div className="dashboard-lock-summary" role="group" aria-label="Locked lineup summary">
              <span>
                <strong>{lockedCount}</strong> {lockedCount === 1 ? 'slot' : 'slots'} locked
              </span>
              <span>
                <strong>{lockedPoints.toFixed(1)}</strong> FP scored
              </span>
              <span>
                <strong>{remainingSlots}</strong> {remainingSlots === 1 ? 'slot' : 'slots'} still
                open
              </span>
              {lockedBench ? (
                <span>
                  <strong>{lockedBench}</strong> played bench{' '}
                  {lockedBench === 1 ? 'player' : 'players'} excluded
                </span>
              ) : null}
            </div>
          ) : null}

          {lineup?.lineup.length ? (
            <div className="dashboard-lineup-list">
              {lineup.lineup.map((row) => (
                <div
                  className={row.locked ? 'dashboard-lineup-row locked' : 'dashboard-lineup-row'}
                  key={`${row.slot}:${row.name}`}
                >
                  <span className="dashboard-slot">{row.slot}</span>
                  <span className="dashboard-player">
                    <strong>{row.name}</strong>
                    <small>
                      {row.pos}
                      {row.team ? ` · ${row.team}` : ''}
                      {row.locked ? ` · ${row.game_status === 'live' ? 'LIVE' : 'FINAL'}` : ''}
                    </small>
                  </span>
                  <span className="dashboard-points-wrap">
                    <strong className="dashboard-points">{row.points.toFixed(1)}</strong>
                    {row.locked ? <small>actual</small> : <small>projected</small>}
                  </span>
                </div>
              ))}
            </div>
          ) : !loading ? (
            <p className="dashboard-empty-copy">No modeled lineup is available.</p>
          ) : null}

          <button type="button" className="dashboard-detail-action" onClick={onOpenLineup}>
            Open lineup details
          </button>

          {pressure.length ? (
            <section className="bench-pressure" aria-label="Bench pressure">
              <div className="dashboard-section-heading compact">
                <div>
                  <span className="section-label">Closest bench calls</span>
                  <h3>
                    {hasLocks
                      ? 'Distance from the best remaining lineup'
                      : 'Distance from the ideal lineup'}
                  </h3>
                </div>
              </div>
              <div className="bench-pressure-list">
                {pressure.map((row) => (
                  <button
                    key={row.name}
                    type="button"
                    className="bench-pressure-row"
                    onClick={() => onCompareBenchPlayer(row)}
                    aria-label={
                      row.displaces
                        ? `Compare ${row.name} with ${row.displaces}`
                        : `Inspect ${row.name}`
                    }
                  >
                    <span className="dashboard-player">
                      <strong>{row.name}</strong>
                      <small>
                        {row.pos}
                        {row.displaces ? ` · behind ${row.displaces} · compare` : ''}
                      </small>
                    </span>
                    <span className="bench-pressure-gap">
                      <strong>{row.delta_to_lineup.toFixed(1)}</strong>
                      <small>FP back</small>
                    </span>
                  </button>
                ))}
              </div>
            </section>
          ) : null}
        </section>

        <section className="dashboard-defenses" aria-label="Defense pickup plan">
          <div className="dashboard-section-heading">
            <div>
              <span className="section-label">Defense planning</span>
              <h3>Available or already yours</h3>
            </div>
          </div>
          <DefenseShortlist
            title="This week"
            week="this"
            payload={defensesThisWeek}
            onOpen={onOpenDefenses}
          />
          <DefenseShortlist
            title="Next week"
            week="next"
            payload={defensesNextWeek}
            onOpen={onOpenDefenses}
          />
        </section>
      </div>
    </main>
  );
}
