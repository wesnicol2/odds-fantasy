import { metricLabel } from '../analysis/metrics';
import { formatProbability, probabilityAtTarget } from '../analysis/probability';
import type { MarketDetail, PlayerOddsDetails, ProjectionPlayer } from '../types';

interface PlayerComparisonInspectorProps {
  challenger: ProjectionPlayer;
  starter: ProjectionPlayer;
  challengerDetails: PlayerOddsDetails | null;
  starterDetails: PlayerOddsDetails | null;
  detailsLoading: boolean;
  lineupDelta: number;
  target: number | null;
  metric: string;
  onMetricChange: (metric: string) => void;
  onExit: () => void;
}

type MatrixSide = 'challenger' | 'starter';

interface MatrixRange {
  floor: number;
  mid: number;
  ceiling: number;
}

interface MatrixRow {
  key: string;
  label: string;
  challengerValue: number | null | undefined;
  starterValue: number | null | undefined;
  challengerDisplay: string;
  starterDisplay: string;
  comparable?: boolean;
  /** A lower value wins the row, e.g. a stat the league scores negatively. */
  lowerWins?: boolean;
  challengerRange?: MatrixRange | null | undefined;
  starterRange?: MatrixRange | null | undefined;
  /** A stat the league scores against you, so the larger value is the warning. */
  negativeStat?: boolean;
  /** Metric this row drills into; rows without one render as plain labels. */
  actionMetric?: string;
  /** Accessible name for the drill-down button when the row has one. */
  actionLabel?: string;
}

function formatPoints(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${value.toFixed(1)} FP`;
}

function formatContribution(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const normalized = Math.abs(value) < 0.05 ? 0 : value;
  return `${normalized > 0 ? '+' : ''}${normalized.toFixed(1)} FP`;
}

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatLine(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value > 0 ? `+${formatValue(value)}` : formatValue(value);
}

function formatKickoff(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(date);
}

function formatRange(range: MatrixRange | null | undefined, suffix: string): string {
  if (!range) return '—';
  const values = [range.floor, range.mid, range.ceiling].map(formatValue).join(' · ');
  return suffix ? `${values} ${suffix}` : values;
}

function playerRange(player: ProjectionPlayer): MatrixRange | null {
  if (player.floor === null || player.mid === null || player.ceiling === null) return null;
  return { floor: player.floor, mid: player.mid, ceiling: player.ceiling };
}

function marketRange(market: MarketDetail | undefined): MatrixRange | null {
  if (!market) return null;
  const [floor, mid, ceiling] = market.stat_range;
  if (floor === undefined || mid === undefined || ceiling === undefined) return null;
  return { floor, mid, ceiling };
}

function rangeValue(market: MarketDetail | undefined, index: 0 | 1 | 2): string {
  return formatValue(market?.stat_range[index]);
}

const COMBINED_YARDAGE_KEY = 'rush_reception_yds';
const COMBINED_YARDAGE_MARKETS = ['player_rush_yds', 'player_reception_yds'];

/**
 * A back's yards are priced as rushing and a pass catcher's as receiving, so
 * lining those markets up separately shows a gap that is really just a
 * position difference. Only that mismatch earns the combined yardage row;
 * back-against-back and receiver-against-receiver already compare like for
 * like and keep their own markets.
 */
function comparesAcrossYardageRoles(left: string, right: string): boolean {
  const isBack = (position: string) => position.toUpperCase() === 'RB';
  const isPassCatcher = (position: string) =>
    position.toUpperCase() === 'WR' || position.toUpperCase() === 'TE';
  return (isBack(left) && isPassCatcher(right)) || (isBack(right) && isPassCatcher(left));
}

interface SideMeasure {
  expectedPoints: number;
  range: MatrixRange | null;
}

/** One player's contribution and stat range for a market key or a combined key. */
function sideMeasure(details: PlayerOddsDetails | null, key: string): SideMeasure | null {
  if (key === COMBINED_YARDAGE_KEY) {
    const combined = details?.combined_markets?.[key];
    if (!combined) return null;
    const [floor, mid, ceiling] = combined.stat_range;
    return {
      expectedPoints: combined.expected_points,
      range:
        floor === undefined || mid === undefined || ceiling === undefined
          ? null
          : { floor, mid, ceiling },
    };
  }
  const market = details?.markets[key];
  return market ? { expectedPoints: market.expected_points, range: marketRange(market) } : null;
}

function rowWinner(row: MatrixRow): MatrixSide | null {
  if (row.comparable === false) return null;
  if (row.challengerValue === null || row.challengerValue === undefined) return null;
  if (row.starterValue === null || row.starterValue === undefined) return null;
  if (Math.abs(row.challengerValue - row.starterValue) < 0.05) return null;
  const challengerLeads = row.lowerWins
    ? row.challengerValue < row.starterValue
    : row.challengerValue > row.starterValue;
  return challengerLeads ? 'challenger' : 'starter';
}

function isScored(row: MatrixRow): boolean {
  return (
    row.comparable !== false &&
    row.challengerValue !== null &&
    row.challengerValue !== undefined &&
    row.starterValue !== null &&
    row.starterValue !== undefined
  );
}

function leadSentence(
  rows: MatrixRow[],
  challengerName: string,
  starterName: string,
  measure: string,
): string {
  const scored = rows.filter(isScored);
  const challengerWins = scored.filter((row) => rowWinner(row) === 'challenger').length;
  const starterWins = scored.filter((row) => rowWinner(row) === 'starter').length;
  const lead =
    challengerWins > starterWins
      ? `${challengerName} leads ${challengerWins}–${starterWins}`
      : starterWins > challengerWins
        ? `${starterName} leads ${starterWins}–${challengerWins}`
        : `Signals are tied ${challengerWins}–${starterWins}`;
  return `${lead} across ${scored.length} comparable ${measure} signals`;
}

function PlayerHeading({
  player,
  details,
  label,
}: {
  player: ProjectionPlayer;
  details: PlayerOddsDetails | null;
  label: string;
}) {
  const matchup = details?.matchup;
  return (
    <span className="comparison-player-heading">
      <strong>{player.name}</strong>
      <small>
        {label} · {player.pos}
      </small>
      {matchup ? (
        <small>
          {matchup.venue === 'home' ? 'vs' : '@'} {matchup.opponent}
        </small>
      ) : null}
    </span>
  );
}

interface Shading {
  side: MatrixSide;
  tone: 'positive' | 'negative';
  intensity: number;
}

/**
 * Which cell to tint, in what colour, and how strongly.
 *
 * The row is read as numbers; colour only says how far apart those numbers
 * are. A stat the league rewards tints the leader green; a stat it punishes
 * tints the player carrying more of it red, because there the larger number
 * is the thing worth spotting. Intensity tracks the relative gap, so a near
 * tie stays almost uncoloured and a blowout is unmistakable.
 */
function rowShading(row: MatrixRow): Shading | null {
  const winner = rowWinner(row);
  if (winner === null) return null;
  const challenger = row.challengerValue as number;
  const starter = row.starterValue as number;
  const magnitude = Math.max(Math.abs(challenger), Math.abs(starter));
  const gap = magnitude > 0 ? Math.abs(challenger - starter) / magnitude : 0;
  // Ease the ramp so a small but real edge is still visible.
  const intensity = Math.sqrt(Math.min(1, gap));
  if (row.negativeStat) {
    return {
      side: winner === 'challenger' ? 'starter' : 'challenger',
      tone: 'negative',
      intensity,
    };
  }
  return { side: winner, tone: 'positive', intensity };
}

function shadingStyle(shading: Shading | null, side: MatrixSide) {
  if (!shading || shading.side !== side) return undefined;
  const alpha = (0.12 + shading.intensity * 0.42).toFixed(3);
  const rgb = shading.tone === 'positive' ? '75, 200, 131' : '214, 92, 92';
  return { backgroundColor: `rgba(${rgb}, ${alpha})` };
}

function MatrixCell({
  display,
  winner,
  shading,
  side,
}: {
  display: string;
  winner: boolean;
  shading: Shading | null;
  side: MatrixSide;
}) {
  return (
    <td style={shadingStyle(shading, side)}>
      <span>{display}</span>
      {/* Colour alone must not carry the result, so the edge stays in the
          accessible name even though it is no longer drawn. */}
      {winner ? <small className="sr-only">Edge</small> : null}
    </td>
  );
}

function MatrixRows({
  rows,
  onMetricChange,
}: {
  rows: MatrixRow[];
  onMetricChange: (metric: string) => void;
}) {
  return rows.map((row) => {
    const winner = rowWinner(row);
    const shading = rowShading(row);
    return (
      <tr key={row.key}>
        <th>
          {row.actionMetric ? (
            <button
              type="button"
              onClick={() => onMetricChange(row.actionMetric as string)}
              aria-label={row.actionLabel ?? `Compare ${row.label} distributions`}
            >
              {row.label}
            </button>
          ) : (
            row.label
          )}
        </th>
        <MatrixCell
          side="challenger"
          display={row.challengerDisplay}
          winner={winner === 'challenger'}
          shading={shading}
        />
        <MatrixCell
          side="starter"
          display={row.starterDisplay}
          winner={winner === 'starter'}
          shading={shading}
        />
      </tr>
    );
  });
}

export function PlayerComparisonInspector({
  challenger,
  starter,
  challengerDetails,
  starterDetails,
  detailsLoading,
  lineupDelta,
  target,
  metric,
  onMetricChange,
  onExit,
}: PlayerComparisonInspectorProps) {
  const modeledKeys = [
    ...new Set([
      ...Object.keys(challengerDetails?.markets ?? {}),
      ...Object.keys(starterDetails?.markets ?? {}),
    ]),
  ];
  const mergeYardage =
    comparesAcrossYardageRoles(challenger.pos, starter.pos) &&
    modeledKeys.some((key) => COMBINED_YARDAGE_MARKETS.includes(key));
  const rowImpact = (key: string) =>
    Math.max(
      Math.abs(sideMeasure(challengerDetails, key)?.expectedPoints ?? 0),
      Math.abs(sideMeasure(starterDetails, key)?.expectedPoints ?? 0),
    );
  const contributionKeys = (
    mergeYardage
      ? [
          COMBINED_YARDAGE_KEY,
          ...modeledKeys.filter((key) => !COMBINED_YARDAGE_MARKETS.includes(key)),
        ]
      : modeledKeys
  ).sort((left, right) => rowImpact(right) - rowImpact(left));
  const challengerMarket = challengerDetails?.markets[metric];
  const starterMarket = starterDetails?.markets[metric];
  const challengerMatchup = challengerDetails?.matchup;
  const starterMatchup = starterDetails?.matchup;

  const challengerFantasyRange = playerRange(challenger);
  const starterFantasyRange = playerRange(starter);

  const projectionRows: MatrixRow[] = [
    {
      key: 'fantasy-range',
      label: 'Fantasy point range',
      challengerValue: null,
      starterValue: null,
      challengerDisplay: formatRange(challengerFantasyRange, 'FP'),
      starterDisplay: formatRange(starterFantasyRange, 'FP'),
      comparable: false,
    },
    {
      key: 'floor',
      label: 'Floor',
      challengerValue: challenger.floor,
      starterValue: starter.floor,
      challengerDisplay: formatPoints(challenger.floor),
      starterDisplay: formatPoints(starter.floor),
    },
    {
      key: 'mid',
      label: 'Median',
      challengerValue: challenger.mid,
      starterValue: starter.mid,
      challengerDisplay: formatPoints(challenger.mid),
      starterDisplay: formatPoints(starter.mid),
    },
    {
      key: 'ceiling',
      label: 'Ceiling',
      challengerValue: challenger.ceiling,
      starterValue: starter.ceiling,
      challengerDisplay: formatPoints(challenger.ceiling),
      starterDisplay: formatPoints(starter.ceiling),
    },
    {
      key: 'mean',
      label: 'Mean',
      challengerValue: challengerDetails?.projection?.mean ?? challenger.mean,
      starterValue: starterDetails?.projection?.mean ?? starter.mean,
      challengerDisplay: formatPoints(challengerDetails?.projection?.mean ?? challenger.mean),
      starterDisplay: formatPoints(starterDetails?.projection?.mean ?? starter.mean),
    },
  ];

  if (target !== null) {
    const challengerProbability = probabilityAtTarget(challenger.curve, target);
    const starterProbability = probabilityAtTarget(starter.curve, target);
    projectionRows.push({
      key: 'target',
      label: `Chance of ≥ ${target.toFixed(1)} FP`,
      challengerValue: challengerProbability,
      starterValue: starterProbability,
      challengerDisplay: formatProbability(challengerProbability),
      starterDisplay: formatProbability(starterProbability),
    });
  }

  const matchupRows: MatrixRow[] = [
    {
      key: 'team-implied-total',
      label: 'Team implied total',
      challengerValue: challengerMatchup?.team_implied_total,
      starterValue: starterMatchup?.team_implied_total,
      challengerDisplay:
        challengerMatchup?.team_implied_total == null
          ? '—'
          : `${formatValue(challengerMatchup.team_implied_total)} pts`,
      starterDisplay:
        starterMatchup?.team_implied_total == null
          ? '—'
          : `${formatValue(starterMatchup.team_implied_total)} pts`,
    },
    {
      key: 'game-total',
      label: 'Game total',
      challengerValue: challengerMatchup?.game_total,
      starterValue: starterMatchup?.game_total,
      challengerDisplay:
        challengerMatchup?.game_total == null
          ? '—'
          : `${formatValue(challengerMatchup.game_total)} pts`,
      starterDisplay:
        starterMatchup?.game_total == null ? '—' : `${formatValue(starterMatchup.game_total)} pts`,
    },
    {
      key: 'spread',
      label: 'Team spread',
      challengerValue: challengerMatchup?.team_spread,
      starterValue: starterMatchup?.team_spread,
      challengerDisplay: formatLine(challengerMatchup?.team_spread),
      starterDisplay: formatLine(starterMatchup?.team_spread),
      comparable: false,
    },
    {
      key: 'kickoff',
      label: 'Kickoff',
      challengerValue: null,
      starterValue: null,
      challengerDisplay: formatKickoff(challengerMatchup?.commence_time),
      starterDisplay: formatKickoff(starterMatchup?.commence_time),
      comparable: false,
    },
  ];

  const contributionRows: MatrixRow[] = contributionKeys.map((marketKey) => {
    const challengerStat = sideMeasure(challengerDetails, marketKey);
    const starterStat = sideMeasure(starterDetails, marketKey);
    // Points from a punished stat are negative, so the deeper number is the
    // warning even though the higher one still wins the row.
    const punished = [challengerStat, starterStat].some(
      (stat) => stat !== null && stat.expectedPoints < 0,
    );
    // A summed row has no single fitted distribution to open; its component
    // markets stay reachable from the chart's own metric strip.
    const drillDown =
      marketKey === COMBINED_YARDAGE_KEY
        ? {}
        : {
            actionMetric: marketKey,
            actionLabel: `Compare ${metricLabel(marketKey)} distributions`,
          };
    return {
      key: marketKey,
      label: metricLabel(marketKey),
      challengerValue: challengerStat?.expectedPoints,
      starterValue: starterStat?.expectedPoints,
      challengerDisplay: formatContribution(challengerStat?.expectedPoints),
      starterDisplay: formatContribution(starterStat?.expectedPoints),
      negativeStat: punished,
      ...drillDown,
    };
  });

  const statValueRows: MatrixRow[] = contributionKeys.map((marketKey) => {
    const challengerStat = sideMeasure(challengerDetails, marketKey);
    const starterStat = sideMeasure(starterDetails, marketKey);
    // The league can score a stat negatively (interceptions), so the smaller
    // volume is the better weekly outcome. Read that from the scored points
    // rather than assuming every counted stat is helpful.
    const lowerWins = [challengerStat, starterStat].some(
      (stat) => stat !== null && stat.expectedPoints < 0,
    );
    const drillDown =
      marketKey === COMBINED_YARDAGE_KEY
        ? {}
        : {
            actionMetric: marketKey,
            actionLabel: `Compare ${metricLabel(marketKey)} stat values`,
          };
    return {
      key: marketKey,
      label: metricLabel(marketKey),
      challengerValue: challengerStat?.range?.mid,
      starterValue: starterStat?.range?.mid,
      challengerDisplay: formatRange(challengerStat?.range, ''),
      starterDisplay: formatRange(starterStat?.range, ''),
      lowerWins,
      negativeStat: lowerWins,
      ...drillDown,
    };
  });

  const pointRows = [...projectionRows, ...matchupRows, ...contributionRows];
  const pointLead = leadSentence(pointRows, challenger.name, starter.name, 'fantasy-point');
  const statLead = leadSentence(statValueRows, challenger.name, starter.name, 'stat-value');

  return (
    <div className="start-sit-comparison">
      <header className="comparison-heading">
        <div>
          <div className="section-label">This week’s tie-breaker matrix</div>
          <h2>
            {challenger.name} <span>vs</span> {starter.name}
          </h2>
        </div>
        <button type="button" onClick={onExit}>
          Exit comparison
        </button>
      </header>

      <div className="comparison-recommendation">
        <strong>Start {starter.name}</strong>
        <span className="comparison-recommendation-copy">
          {challenger.name} is {lineupDelta.toFixed(1)} lineup FP back after re-optimizing every
          eligible slot.
        </span>
        <span className="comparison-signal-score">{pointLead}</span>
        <span className="comparison-signal-score">{statLead}</span>
      </div>

      {metric === 'fantasy_points' ? (
        <section
          className="comparison-section matrix-section"
          aria-label="Weekly tie-breaker matrix"
        >
          <p>
            Every value is tied to this matchup week. Fantasy-point rows use league scoring; stat
            rows compare the raw weekly stat instead. Shading marks the gap between the two players
            in that row and fades as they converge: green highlights the leader on a stat the league
            rewards, red the player carrying more of one it punishes. Missing data and ties leave
            both sides unshaded.
          </p>
          {detailsLoading && (!challengerDetails || !starterDetails) ? (
            <p className="subtle evidence-status">Loading both players’ weekly evidence…</p>
          ) : null}
          <div className="comparison-table-scroll">
            <table
              className="comparison-table matrix-table"
              aria-label="Weekly player comparison matrix"
            >
              <thead>
                <tr>
                  <th>Weekly signal</th>
                  <th>
                    <PlayerHeading
                      player={challenger}
                      details={challengerDetails}
                      label="Bench option"
                    />
                  </th>
                  <th>
                    <PlayerHeading
                      player={starter}
                      details={starterDetails}
                      label="Ideal starter"
                    />
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr className="matrix-group-row">
                  <th colSpan={3}>Projection · fantasy points</th>
                </tr>
                <MatrixRows rows={projectionRows} onMetricChange={onMetricChange} />
                <tr className="matrix-group-row">
                  <th colSpan={3}>Matchup</th>
                </tr>
                <MatrixRows rows={matchupRows} onMetricChange={onMetricChange} />
                {contributionRows.length ? (
                  <>
                    <tr className="matrix-group-row">
                      <th colSpan={3}>Fantasy-point sources</th>
                    </tr>
                    <MatrixRows rows={contributionRows} onMetricChange={onMetricChange} />
                    <tr className="matrix-group-row">
                      <th colSpan={3}>Stat value · 10th · median · 90th</th>
                    </tr>
                    <MatrixRows rows={statValueRows} onMetricChange={onMetricChange} />
                  </>
                ) : null}
              </tbody>
            </table>
          </div>
          {!detailsLoading && contributionRows.length === 0 ? (
            <div className="empty-state">
              No shared weekly point-source comparison is available.
            </div>
          ) : null}
          <p className="comparison-count-note">
            {mergeYardage
              ? `Rushing and receiving yards are summed because ${challenger.pos} and ${starter.pos} earn yardage in different markets; the combined range is sampled from both fitted distributions, not added percentile by percentile. Open either market from the chart's metric strip. `
              : ''}
            Row wins are a transparent scan aid, not independent evidence or a confidence score.
            Fantasy-point and stat-value signals are counted separately because a stat and the
            points it produces are the same underlying market. The start recommendation remains the
            optimizer’s league-scored lineup result.
          </p>
        </section>
      ) : (
        <section className="comparison-section" aria-label={`${metricLabel(metric)} comparison`}>
          <div className="comparison-section-heading">
            <div>
              <div className="section-label">This week’s stat drill-down</div>
              <h3>{metricLabel(metric)} comparison</h3>
            </div>
            <button type="button" onClick={() => onMetricChange('fantasy_points')}>
              Full matrix
            </button>
          </div>
          <div className="comparison-table-scroll">
            <table className="comparison-table stat-detail-table">
              <thead>
                <tr>
                  <th>Measure</th>
                  <th>{challenger.name}</th>
                  <th>{starter.name}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>Mean FP contribution</th>
                  <td
                    className={
                      challengerMarket && challengerMarket.expected_points < 0 ? 'negative' : ''
                    }
                  >
                    {formatContribution(challengerMarket?.expected_points)}
                  </td>
                  <td
                    className={starterMarket && starterMarket.expected_points < 0 ? 'negative' : ''}
                  >
                    {formatContribution(starterMarket?.expected_points)}
                  </td>
                </tr>
                <tr>
                  <th>10th</th>
                  <td>{rangeValue(challengerMarket, 0)}</td>
                  <td>{rangeValue(starterMarket, 0)}</td>
                </tr>
                <tr>
                  <th>Median</th>
                  <td>{rangeValue(challengerMarket, 1)}</td>
                  <td>{rangeValue(starterMarket, 1)}</td>
                </tr>
                <tr>
                  <th>90th</th>
                  <td>{rangeValue(challengerMarket, 2)}</td>
                  <td>{rangeValue(starterMarket, 2)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p>
            The central chart compares the complete fitted distributions for this week’s stat. The
            range thermometers place both players on one shared stat-value scale.
          </p>
        </section>
      )}
    </div>
  );
}
