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

type IndexedLineupRow = LineupResponse['lineup'][number] & {
  slot_index?: number | null;
};

type IndexedBenchPressureRow = BenchPressureRow & {
  slot_index?: number | null;
  displaces_slot_index?: number | null;
};

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

function decisionSlotKey(
  decision: IndexedBenchPressureRow,
  lineupRows: IndexedLineupRow[],
): number | null {
  if (decision.slot_index !== null && decision.slot_index !== undefined) {
    return decision.slot_index;
  }

  const displacedIndex = lineupRows.findIndex((row) => row.name === decision.displaces);
  if (displacedIndex >= 0) {
    return lineupRows[displacedIndex]?.slot_index ?? displacedIndex;
  }

  const matchingSlotIndex = lineupRows.findIndex((row) => row.slot === decision.slot && !row.locked);
  if (matchingSlotIndex >= 0) {
    return lineupRows[matchingSlotIndex]?.slot_index ?? matchingSlotIndex;
  }

  return null;
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
  const lineupRows = (lineup?.lineup ?? []) as IndexedLineupRow[];
  const decisions = (lineup?.bench_pressure ?? [])
    .filter((row) => Boolean(row.displaces))
    .slice(0, 3) as IndexedBenchPressureRow[];
  const decisionRanks = new Map(decisions.map((row, index) => [row.name, index + 1]));
  const decisionsBySlot = new Map<number, IndexedBenchPressureRow[]>();

  for (const decision of decisions) {
    const slotKey = decisionSlotKey(decision, lineupRows);
    if (slotKey === null) continue;
    const rows = decisionsBySlot.get(slotKey) ?? [];
    rows.push(decision);
    decisionsBySlot.set(slotKey, rows);
  }

  const lockedCount = lineup?.locked_count ?? 0;
  const remainingMode = lockedCount > 0;

  return (
    <main className="dashboard-view" aria-label="Dashboard">
      <header className="dashboard-heading">
        <div>
          <span className="eyebrow">This week</span>
          <h2>Lineup & pickups</h2>
          <p>Close calls are highlighted directly in the lineup slots they affect.</p>
        </div>
        {loading ? <span className="dashboard-loading">Refreshing market…</span> : null}
      </header>

      {error ? <div className="error-state">{error}</div> : null}

      <div className="dashboard-support-grid">
        <section
          className="dashboard-lineup"
          aria-label={remainingMode ? 'Best remaining lineup this week' : 'Ideal lineup this week'}
        >
          <div className="dashboard-section-heading">
            <div>
              <span className="section-label">Your lineup</span>
              <h3>{remainingMode ? 'Best remaining Mid lineup' : 'Best Mid lineup'}</h3>
            </div>
            <div className="dashboard-lineup-summary">
              <div className="dashboard-total">
                <strong>{lineup ? lineup.total_points.toFixed(1) : '—'}</strong>
                <span>{remainingMode ? 'modeled week FP' : 'total FP'}</span>
              </div>
              <span className={`dashboard-decision-count${decisions.length ? ' active' : ''}`}>
                {decisions.length
                  ? `${decisions.length} close ${decisions.length === 1 ? 'call' : 'calls'}`
                  : 'No close calls'}
              </span>
            </div>
          </div>

          {remainingMode ? (
            <div className="dashboard-lock-summary">
              <strong>{lockedCount} locked</strong>
              <span>{formatPoints(lineup?.actual_points)} FP scored</span>
              <span>{lineup?.decisions_remaining ?? 0} decisions left</span>
            </div>
          ) : null}

          {lineupRows.length ? (
            <div className="dashboard-lineup-list">
              {lineupRows.map((row, rowIndex) => {
                const slotKey = row.slot_index ?? rowIndex;
                const slotDecisions = decisionsBySlot.get(slotKey) ?? [];
                const hasClosestDecision = slotDecisions.some(
                  (decision) => decisionRanks.get(decision.name) === 1,
                );

                return (
                  <div
                    className={`dashboard-lineup-slot${slotDecisions.length ? ' has-decision' : ''}${hasClosestDecision ? ' has-closest-decision' : ''}`}
                    key={`${slotKey}:${row.slot}:${row.name}`}
                  >
                    <div className="dashboard-lineup-row">
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

                    {slotDecisions.length ? (
                      <div className="dashboard-slot-decisions" aria-label={`${row.slot} alternatives`}>
                        {slotDecisions.map((decision) => {
                          const rank = decisionRanks.get(decision.name) ?? 0;
                          const reshufflesLineup =
                            Boolean(decision.displaces) && decision.displaces !== row.name;

                          return (
                            <button
                              key={decision.name}
                              type="button"
                              className={`dashboard-slot-decision${rank === 1 ? ' is-closest' : ''}`}
                              onClick={() => onCompareBenchPlayer(decision)}
                              aria-label={`Compare ${decision.name} with ${decision.displaces}`}
                            >
                              <span className="dashboard-slot-decision-rank">0{rank}</span>
                              <span className="dashboard-slot-decision-player">
                                <small>{rank === 1 ? 'Closest call' : 'Also close'}</small>
                                <strong>{decision.name}</strong>
                                <span>
                                  {decision.pos}
                                  {decision.team ? ` · ${decision.team}` : ''}
                                  {reshufflesLineup ? ` · moves out ${decision.displaces}` : ''}
                                </span>
                              </span>
                              <span className="dashboard-slot-decision-projection">
                                <strong>{decision.points.toFixed(1)}</strong>
                                <small>proj.</small>
                              </span>
                              <span className="dashboard-slot-decision-gap">
                                <strong>{decision.delta_to_lineup.toFixed(1)}</strong>
                                <small>FP back</small>
                              </span>
                              <span className="dashboard-slot-decision-cta">Compare →</span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                );
              })}
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
