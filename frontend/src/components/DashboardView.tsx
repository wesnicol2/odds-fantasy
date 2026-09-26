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
  onOpenPlayers: () => void;
  onOpenDefenses: (week: WeekWindow) => void;
  onCompareBenchPlayer: (player: BenchPressureRow) => void;
}

function formatPoints(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(1);
}

function actionableDefenses(payload: DefenseResponse | null): DefenseRow[] {
  return (payload?.defenses ?? [])
    .filter((row) => row.owned_by_current || !row.taken)
    .filter((row) => row.implied_total !== null);
}

function DefenseWatch({
  label,
  week,
  payload,
  onOpen,
}: {
  label: string;
  week: WeekWindow;
  payload: DefenseResponse | null;
  onOpen: (week: WeekWindow) => void;
}) {
  const row = actionableDefenses(payload)[0] ?? null;
  return (
    <button type="button" className="defense-watch-row" onClick={() => onOpen(week)}>
      <span className="defense-watch-window">{label}</span>
      {row ? (
        <>
          <span className="defense-watch-team">
            <strong>{row.abbr || row.defense}</strong>
            <small>vs {row.opponent}</small>
          </span>
          <span className="defense-watch-total">
            <strong>{formatPoints(row.implied_total)}</strong>
            <small>opp. implied</small>
          </span>
        </>
      ) : (
        <span className="defense-watch-empty">No playable defense found</span>
      )}
      <span className="decision-arrow" aria-hidden="true">
        →
      </span>
    </button>
  );
}

export function DashboardView({
  lineup,
  defensesThisWeek,
  defensesNextWeek,
  loading,
  error,
  onOpenLineup,
  onOpenPlayers,
  onOpenDefenses,
  onCompareBenchPlayer,
}: DashboardViewProps) {
  const pairedPressure = (lineup?.bench_pressure ?? []).filter((row) => Boolean(row.displaces));
  const decisions = pairedPressure.slice(0, 3);
  const extraDecisionCount = Math.max(0, pairedPressure.length - decisions.length);
  const lockedCount = lineup?.locked_count ?? 0;
  const remainingMode = lockedCount > 0;

  return (
    <main className="dashboard-view" aria-label="Dashboard">
      <header className="dashboard-heading">
        <div>
          <span className="eyebrow">This week</span>
          <h2>Your lineup decisions</h2>
          <p>Start with the calls that can actually change your optimized lineup.</p>
        </div>
        {loading ? <span className="dashboard-loading">Updating…</span> : null}
      </header>

      {error ? <div className="error-state">{error}</div> : null}

      <section className="decision-panel" aria-label="Start sit decisions">
        <div className="decision-panel-heading">
          <div>
            <span className="section-label">Start / sit</span>
            <h3>
              {decisions.length
                ? `${decisions.length}${extraDecisionCount ? '+' : ''} calls worth checking`
                : loading
                  ? 'Finding your closest calls…'
                  : 'No close calls to flag'}
            </h3>
            <p>
              {decisions.length
                ? 'Tap a matchup to compare the two players using this week’s sportsbook evidence.'
                : loading
                  ? 'We’re comparing your modeled bench against the best remaining lineup.'
                  : 'Your modeled lineup has clear separation right now. You can still compare any roster players.'}
            </p>
          </div>
          {lineup ? (
            <div className="decision-total">
              <strong>{lineup.total_points.toFixed(1)}</strong>
              <span>{remainingMode ? 'modeled week FP' : 'lineup FP'}</span>
            </div>
          ) : null}
        </div>

        {decisions.length ? (
          <div className="decision-list">
            {decisions.map((row) => (
              <button
                key={`${row.name}:${row.displaces}`}
                type="button"
                className="decision-row"
                onClick={() => onCompareBenchPlayer(row)}
                aria-label={`Compare ${row.name} with ${row.displaces}`}
              >
                <span className="decision-player">
                  <small>Bench option</small>
                  <strong>{row.name}</strong>
                  <span>
                    {row.pos}
                    {row.team ? ` · ${row.team}` : ''}
                  </span>
                </span>
                <span className="decision-vs">vs</span>
                <span className="decision-player decision-player-starting">
                  <small>Current best lineup</small>
                  <strong>{row.displaces}</strong>
                  <span>{row.displaces_slot || 'starter'}</span>
                </span>
                <span className="decision-gap">
                  <strong>{row.delta_to_lineup.toFixed(1)}</strong>
                  <small>FP lineup gap</small>
                </span>
                <span className="decision-arrow" aria-hidden="true">
                  →
                </span>
              </button>
            ))}
          </div>
        ) : null}

        <div className="decision-panel-footer">
          <button type="button" className="secondary-action" onClick={onOpenPlayers}>
            Compare any roster players
          </button>
          {extraDecisionCount ? (
            <span>{extraDecisionCount} more modeled bench calls are available in Lineup.</span>
          ) : null}
        </div>
      </section>

      <div className="dashboard-secondary-grid">
        <section className="dashboard-snapshot" aria-label="Lineup snapshot">
          <div className="dashboard-section-heading">
            <div>
              <span className="section-label">Lineup snapshot</span>
              <h3>{remainingMode ? 'Best remaining lineup' : 'Optimized Mid lineup'}</h3>
            </div>
            <button type="button" className="quiet-action" onClick={onOpenLineup}>
              Full lineup →
            </button>
          </div>

          {lineup ? (
            <div className="lineup-snapshot-body">
              <div className="snapshot-number">
                <strong>{lineup.total_points.toFixed(1)}</strong>
                <span>{remainingMode ? 'modeled week FP' : 'projected FP'}</span>
              </div>
              <div className="snapshot-copy">
                <strong>{lineup.lineup.length} modeled starters</strong>
                <span>
                  {remainingMode
                    ? `${lockedCount} locked · ${formatPoints(lineup.actual_points)} FP scored · ${lineup.decisions_remaining ?? 0} decisions left`
                    : 'Floor and ceiling alternatives stay one level deeper.'}
                </span>
              </div>
            </div>
          ) : !loading ? (
            <p className="dashboard-empty-copy">No modeled lineup is available.</p>
          ) : null}
        </section>

        <section className="dashboard-defense-watch" aria-label="Defense watch">
          <div className="dashboard-section-heading">
            <div>
              <span className="section-label">Defense watch</span>
              <h3>Best playable matchup</h3>
            </div>
          </div>
          <div className="defense-watch-list">
            <DefenseWatch
              label="This week"
              week="this"
              payload={defensesThisWeek}
              onOpen={onOpenDefenses}
            />
            <DefenseWatch
              label="Next week"
              week="next"
              payload={defensesNextWeek}
              onOpen={onOpenDefenses}
            />
          </div>
        </section>
      </div>
    </main>
  );
}
