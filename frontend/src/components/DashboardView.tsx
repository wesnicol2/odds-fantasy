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

function formatPoints(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(1);
}

function actionableDefenses(payload: DefenseResponse | null): DefenseRow[] {
  return (payload?.defenses ?? [])
    .filter((row) => row.owned_by_current || !row.taken)
    .filter((row) => row.implied_total !== null)
    .slice(0, 1);
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
    <section className="dashboard-defense-window" aria-label={`${title} defense target`}>
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
        <p className="dashboard-empty-copy">No playable available or owned defense found.</p>
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
  const decisions = (lineup?.bench_pressure ?? [])
    .filter((row) => Boolean(row.displaces))
    .slice(0, 3);
  const lockedCount = lineup?.locked_count ?? 0;
  const remainingMode = lockedCount > 0;

  return (
    <main className="dashboard-view" aria-label="Dashboard">
      <header className="dashboard-heading">
        <div>
          <span className="eyebrow">This week</span>
          <h2>Lineup & pickups</h2>
          <p>Your closest start/sit decisions come first.</p>
        </div>
        {loading ? <span className="dashboard-loading">Refreshing market…</span> : null}
      </header>

      {error ? <div className="error-state">{error}</div> : null}

      <section className="dashboard-decision-hero" aria-label="Start sit decisions">
        <div className="dashboard-decision-heading">
          <div>
            <span className="section-label">Your decisions</span>
            <h3>
              {decisions.length
                ? `${decisions.length} ${decisions.length === 1 ? 'call' : 'calls'} worth a look`
                : loading && !lineup
                  ? 'Finding your closest calls…'
                  : 'No actionable swaps found'}
            </h3>
          </div>
          <span className="dashboard-decision-source">Sleeper roster × betting market</span>
        </div>

        {decisions.length ? (
          <div className="dashboard-decision-grid">
            {decisions.map((row, index) => (
              <button
                key={row.name}
                type="button"
                className="dashboard-decision-card"
                onClick={() => onCompareBenchPlayer(row)}
                aria-label={`Compare ${row.name} with ${row.displaces}`}
              >
                <span className="dashboard-decision-index">0{index + 1}</span>
                <span className="dashboard-decision-copy">
                  <small>Start</small>
                  <strong>{row.displaces}</strong>
                  <span>over {row.name}</span>
                </span>
                <span className="dashboard-decision-gap">
                  <strong>{row.delta_to_lineup.toFixed(1)}</strong>
                  <small>FP back</small>
                </span>
                <span className="dashboard-decision-cta">See why →</span>
              </button>
            ))}
          </div>
        ) : !loading ? (
          <p className="dashboard-decision-empty">
            The optimizer does not currently have a bench player paired with a movable starter.
          </p>
        ) : null}
      </section>

      <div className="dashboard-support-grid">
        <section
          className="dashboard-lineup"
          aria-label={remainingMode ? 'Best remaining lineup this week' : 'Ideal lineup this week'}
        >
          <div className="dashboard-section-heading">
            <div>
              <span className="section-label">Recommended lineup</span>
              <h3>{remainingMode ? 'Best remaining Mid lineup' : 'Best Mid lineup'}</h3>
            </div>
            <div className="dashboard-total">
              <strong>{lineup ? lineup.total_points.toFixed(1) : '—'}</strong>
              <span>{remainingMode ? 'modeled week FP' : 'total FP'}</span>
            </div>
          </div>

          {remainingMode ? (
            <div className="dashboard-lock-summary">
              <strong>{lockedCount} locked</strong>
              <span>{formatPoints(lineup?.actual_points)} FP scored</span>
              <span>{lineup?.decisions_remaining ?? 0} decisions left</span>
            </div>
          ) : null}

          {lineup?.lineup.length ? (
            <div className="dashboard-lineup-list">
              {lineup.lineup.map((row) => (
                <div className="dashboard-lineup-row" key={`${row.slot}:${row.name}`}>
                  <span className="dashboard-slot">{row.slot}</span>
                  <span className="dashboard-player">
                    <strong>{row.name}</strong>
                    <small>
                      {row.pos}
                      {row.team ? ` · ${row.team}` : ''}
                      {row.locked ? ` · LOCKED · ${formatPoints(row.actual_points)} actual` : ''}
                    </small>
                  </span>
                  <strong className="dashboard-points">{row.points.toFixed(1)}</strong>
                </div>
              ))}
            </div>
          ) : !loading ? (
            <p className="dashboard-empty-copy">No modeled lineup is available.</p>
          ) : null}

          <button type="button" className="dashboard-detail-action" onClick={onOpenLineup}>
            Open full lineup →
          </button>
        </section>

        <section className="dashboard-defenses" aria-label="Defense pickup plan">
          <div className="dashboard-section-heading">
            <div>
              <span className="section-label">Defense</span>
              <h3>Best playable target</h3>
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
