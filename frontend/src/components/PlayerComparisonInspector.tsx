import { metricLabel } from '../analysis/metrics';
import { formatProbability, probabilityAtTarget } from '../analysis/probability';
import type { MarketDetail, PlayerOddsDetails, ProjectionPlayer } from '../types';
import { RangeThermometer } from './RangeThermometer';

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
  challengerRange?: MatrixRange | null;
  starterRange?: MatrixRange | null;
  rangeLabelSuffix?: string;
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

/** Zero-anchored shared scale so both thermometers read as magnitudes, not as a zoomed gap. */
function rangeScale(ranges: (MatrixRange | null | undefined)[]): {
  minimum: number;
  maximum: number;
} {
  const present = ranges.filter((range): range is MatrixRange => Boolean(range));
  const minimum = Math.min(0, ...present.map((range) => range.floor));
  const maximum = Math.max(minimum + 1, ...present.map((range) => range.ceiling));
  return { minimum, maximum };
}

function rangeValue(market: MarketDetail | undefined, index: 0 | 1 | 2): string {
  return formatValue(market?.stat_range[index]);
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

function MatrixCell({
  display,
  winner,
  range,
  scale,
  thermometerLabel,
}: {
  display: string;
  winner: boolean;
  range: MatrixRange | null | undefined;
  scale: { minimum: number; maximum: number } | undefined;
  thermometerLabel: string;
}) {
  return (
    <td className={winner ? 'matrix-winner' : undefined}>
      <span>{display}</span>
      {range && scale ? (
        <RangeThermometer
          floor={range.floor}
          mid={range.mid}
          ceiling={range.ceiling}
          minimum={scale.minimum}
          maximum={scale.maximum}
          label={thermometerLabel}
          className="matrix-range-glyph"
        />
      ) : null}
      {winner ? <small>Edge</small> : null}
    </td>
  );
}

function MatrixRows({
  rows,
  challengerName,
  starterName,
  onMetricChange,
}: {
  rows: MatrixRow[];
  challengerName: string;
  starterName: string;
  onMetricChange?: (metric: string) => void;
}) {
  return rows.map((row) => {
    const winner = rowWinner(row);
    const scale =
      row.challengerRange || row.starterRange
        ? rangeScale([row.challengerRange, row.starterRange])
        : undefined;
    const suffix = row.rangeLabelSuffix ?? '';
    return (
      <tr key={row.key}>
        <th>
          {onMetricChange ? (
            <button
              type="button"
              onClick={() => onMetricChange(row.key)}
              aria-label={row.actionLabel ?? `Compare ${row.label} distributions`}
            >
              {row.label}
            </button>
          ) : (
            row.label
          )}
        </th>
        <MatrixCell
          display={row.challengerDisplay}
          winner={winner === 'challenger'}
          range={row.challengerRange}
          scale={scale}
          thermometerLabel={`${challengerName} ${row.label} floor ${formatValue(row.challengerRange?.floor)}, mid ${formatValue(row.challengerRange?.mid)}, ceiling ${formatValue(row.challengerRange?.ceiling)}${suffix ? ` ${suffix}` : ''}`}
        />
        <MatrixCell
          display={row.starterDisplay}
          winner={winner === 'starter'}
          range={row.starterRange}
          scale={scale}
          thermometerLabel={`${starterName} ${row.label} floor ${formatValue(row.starterRange?.floor)}, mid ${formatValue(row.starterRange?.mid)}, ceiling ${formatValue(row.starterRange?.ceiling)}${suffix ? ` ${suffix}` : ''}`}
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
  const contributionKeys = [
    ...new Set([
      ...Object.keys(challengerDetails?.markets ?? {}),
      ...Object.keys(starterDetails?.markets ?? {}),
    ]),
  ].sort((left, right) => {
    const leftImpact = Math.max(
      Math.abs(challengerDetails?.markets[left]?.expected_points ?? 0),
      Math.abs(starterDetails?.markets[left]?.expected_points ?? 0),
    );
    const rightImpact = Math.max(
      Math.abs(challengerDetails?.markets[right]?.expected_points ?? 0),
      Math.abs(starterDetails?.markets[right]?.expected_points ?? 0),
    );
    return rightImpact - leftImpact;
  });
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
      challengerRange: challengerFantasyRange,
      starterRange: starterFantasyRange,
      rangeLabelSuffix: 'FP',
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
    const challengerStat = challengerDetails?.markets[marketKey];
    const starterStat = starterDetails?.markets[marketKey];
    return {
      key: marketKey,
      label: metricLabel(marketKey),
      challengerValue: challengerStat?.expected_points,
      starterValue: starterStat?.expected_points,
      challengerDisplay: formatContribution(challengerStat?.expected_points),
      starterDisplay: formatContribution(starterStat?.expected_points),
      actionLabel: `Compare ${metricLabel(marketKey)} distributions`,
    };
  });

  const statValueRows: MatrixRow[] = contributionKeys.map((marketKey) => {
    const challengerStat = challengerDetails?.markets[marketKey];
    const starterStat = starterDetails?.markets[marketKey];
    const challengerStatRange = marketRange(challengerStat);
    const starterStatRange = marketRange(starterStat);
    // The league can score a stat negatively (interceptions), so the smaller
    // volume is the better weekly outcome. Read that from the scored points
    // rather than assuming every counted stat is helpful.
    const lowerWins = [challengerStat, starterStat].some(
      (stat) => stat !== undefined && stat.expected_points < 0,
    );
    return {
      key: marketKey,
      label: metricLabel(marketKey),
      challengerValue: challengerStatRange?.mid,
      starterValue: starterStatRange?.mid,
      challengerDisplay: formatRange(challengerStatRange, ''),
      starterDisplay: formatRange(starterStatRange, ''),
      lowerWins,
      challengerRange: challengerStatRange,
      starterRange: starterStatRange,
      actionLabel: `Compare ${metricLabel(marketKey)} stat values`,
    };
  });

  const pointRows = [...projectionRows, ...matchupRows, ...contributionRows];
  const pointLead = leadSentence(pointRows, challenger.name, starter.name, 'fantasy-point');
  const statLead = leadSentence(statValueRows, challenger.name, starter.name, 'stat-value');
  const statScale = rangeScale([marketRange(challengerMarket), marketRange(starterMarket)]);

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
            rows compare the raw weekly stat instead. Each thermometer marks the 10th percentile,
            median and 90th percentile on a shared scale. An edge marks the better comparable value;
            missing data and ties do not award either player a win.
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
                <MatrixRows
                  rows={projectionRows}
                  challengerName={challenger.name}
                  starterName={starter.name}
                />
                <tr className="matrix-group-row">
                  <th colSpan={3}>Matchup</th>
                </tr>
                <MatrixRows
                  rows={matchupRows}
                  challengerName={challenger.name}
                  starterName={starter.name}
                />
                {contributionRows.length ? (
                  <>
                    <tr className="matrix-group-row">
                      <th colSpan={3}>Fantasy-point sources</th>
                    </tr>
                    <MatrixRows
                      rows={contributionRows}
                      challengerName={challenger.name}
                      starterName={starter.name}
                      onMetricChange={onMetricChange}
                    />
                    <tr className="matrix-group-row">
                      <th colSpan={3}>Stat value · 10th · median · 90th</th>
                    </tr>
                    <MatrixRows
                      rows={statValueRows}
                      challengerName={challenger.name}
                      starterName={starter.name}
                      onMetricChange={onMetricChange}
                    />
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
                <tr>
                  <th>Stat value range</th>
                  {[
                    { player: challenger, market: challengerMarket },
                    { player: starter, market: starterMarket },
                  ].map(({ player, market }) => {
                    const range = marketRange(market);
                    return (
                      <td key={player.name}>
                        {range ? (
                          <RangeThermometer
                            floor={range.floor}
                            mid={range.mid}
                            ceiling={range.ceiling}
                            minimum={statScale.minimum}
                            maximum={statScale.maximum}
                            label={`${player.name} ${metricLabel(metric)} floor ${formatValue(range.floor)}, mid ${formatValue(range.mid)}, ceiling ${formatValue(range.ceiling)}`}
                            className="matrix-range-glyph"
                          />
                        ) : (
                          '—'
                        )}
                      </td>
                    );
                  })}
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
