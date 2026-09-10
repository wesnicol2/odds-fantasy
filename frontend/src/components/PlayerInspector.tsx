import { metricLabel } from '../analysis/metrics';
import { formatProbability, probabilityAtTarget } from '../analysis/probability';
import type { PlayerOddsDetails, ProjectionPlayer } from '../types';

interface PlayerInspectorProps {
  player: ProjectionPlayer | null;
  target: number | null;
  metric: string;
  details: PlayerOddsDetails | null;
  detailsLoading: boolean;
  onMetricChange: (metric: string) => void;
}

function formatPoints(value: number | null): string {
  return value === null ? '—' : value.toFixed(1);
}

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatOdds(value: number | null): string {
  return value === null ? '—' : value.toFixed(2);
}

function formatContribution(value: number): string {
  const normalized = Math.abs(value) < 0.05 ? 0 : value;
  return `${normalized > 0 ? '+' : ''}${normalized.toFixed(1)} FP`;
}

export function PlayerInspector({
  player,
  target,
  metric,
  details,
  detailsLoading,
  onMetricChange,
}: PlayerInspectorProps) {
  if (!player) {
    return <div className="empty-state">Select a player to inspect their projection.</div>;
  }

  const targetProbability = probabilityAtTarget(player.curve, target);
  const market = metric === 'fantasy_points' ? null : (details?.markets[metric] ?? null);
  const sportsbookCount = market
    ? new Set(market.lines.map((line) => line.book).filter(Boolean)).size
    : 0;
  const contributions = Object.entries(details?.markets ?? {})
    .map(([marketKey, detail]) => ({
      marketKey,
      label: metricLabel(marketKey),
      points: detail.expected_points,
    }))
    .sort((left, right) => Math.abs(right.points) - Math.abs(left.points));
  const largestContribution = Math.max(...contributions.map(({ points }) => Math.abs(points)), 0);

  return (
    <div className="inspector-content">
      <div className="player-identity">
        <span className="position-chip">{player.pos}</span>
        <div>
          <h2>{player.name}</h2>
          <p>{player.team || 'Team unavailable'}</p>
        </div>
      </div>

      {player.has_projection ? (
        <>
          <dl className="projection-summary">
            <div>
              <dt>Floor</dt>
              <dd>{formatPoints(player.floor)}</dd>
            </div>
            <div className="emphasis">
              <dt>Mid</dt>
              <dd>{formatPoints(player.mid)}</dd>
            </div>
            <div>
              <dt>Ceiling</dt>
              <dd>{formatPoints(player.ceiling)}</dd>
            </div>
          </dl>

          {metric === 'fantasy_points' && target !== null ? (
            <div className="target-summary">
              <span>Chance of ≥ {target.toFixed(1)} FP</span>
              <strong>{formatProbability(targetProbability)}</strong>
            </div>
          ) : null}

          {metric === 'fantasy_points' ? (
            <div className="inspector-section contribution-section">
              <div className="section-label">Mean point sources</div>
              {detailsLoading && !details ? (
                <p className="subtle evidence-status">Loading point sources…</p>
              ) : null}
              {!detailsLoading && contributions.length === 0 ? (
                <div className="empty-state">No modeled stat contributions are available.</div>
              ) : null}
              {contributions.length ? (
                <>
                  <div className="contribution-total">
                    <span>Mean fantasy points</span>
                    <strong>{formatPoints(details?.projection?.mean ?? player.mean)}</strong>
                  </div>
                  <ul className="contribution-list" aria-label="Fantasy point contributions">
                    {contributions.map(({ marketKey, label, points }) => (
                      <li key={marketKey}>
                        <button
                          type="button"
                          className="contribution-row"
                          onClick={() => onMetricChange(marketKey)}
                          aria-label={`Analyze ${label}, ${formatContribution(points)}`}
                        >
                          <span className="contribution-row-heading">
                            <span>{label}</span>
                            <strong className={points < 0 ? 'negative' : ''}>
                              {formatContribution(points)}
                            </strong>
                          </span>
                          <span className="contribution-track" aria-hidden="true">
                            <span
                              className={
                                points < 0 ? 'contribution-fill negative' : 'contribution-fill'
                              }
                              style={{
                                width: `${largestContribution ? (Math.abs(points) / largestContribution) * 100 : 0}%`,
                              }}
                            />
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <p className="contribution-note">
                    Expected contributions add to the mean. Select a stat to inspect its outcomes
                    and betting lines.
                  </p>
                </>
              ) : null}
            </div>
          ) : null}

          {metric !== 'fantasy_points' ? (
            <div className="inspector-section evidence-section">
              <div className="section-label">{metricLabel(metric)} evidence</div>
              {detailsLoading && !market ? (
                <p className="subtle evidence-status">Loading market evidence…</p>
              ) : null}
              {!detailsLoading && !market ? (
                <div className="empty-state">No priced market is available for this metric.</div>
              ) : null}
              {market ? (
                <>
                  <div className="stat-contribution-summary">
                    <span>Mean point contribution</span>
                    <strong className={market.expected_points < 0 ? 'negative' : ''}>
                      {formatContribution(market.expected_points)}
                    </strong>
                    <button type="button" onClick={() => onMetricChange('fantasy_points')}>
                      All point sources
                    </button>
                  </div>
                  <dl className="stat-range-summary">
                    <div>
                      <dt>10th</dt>
                      <dd>{formatValue(market.stat_range[0])}</dd>
                    </div>
                    <div>
                      <dt>Median</dt>
                      <dd>{formatValue(market.stat_range[1])}</dd>
                    </div>
                    <div>
                      <dt>90th</dt>
                      <dd>{formatValue(market.stat_range[2])}</dd>
                    </div>
                  </dl>
                  <div className="evidence-summary">
                    <span>{market.anchors.length} consensus thresholds</span>
                    <span>{market.lines.length} source lines</span>
                    <span>{sportsbookCount} books</span>
                  </div>
                  <p className="evidence-explainer">
                    Consensus thresholds are de-vigged cross-book P(≥x) evidence. Exact sportsbook
                    lines show the source prices. The chart re-expresses the same backend-fitted
                    distribution using the visualization appropriate for this stat.
                  </p>
                  <details className="evidence-details">
                    <summary>Explain betting lines</summary>
                    <div className="evidence-block">
                      <h3>Consensus anchors</h3>
                      {market.anchors.length ? (
                        <div className="evidence-table-scroll">
                          <table className="evidence-table">
                            <thead>
                              <tr>
                                <th>Threshold</th>
                                <th className="number">Fair P(over)</th>
                              </tr>
                            </thead>
                            <tbody>
                              {market.anchors.map((anchor) => (
                                <tr key={`${anchor.threshold}:${anchor.survival}`}>
                                  <td>{formatValue(anchor.threshold)}</td>
                                  <td className="number">{formatProbability(anchor.survival)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="subtle">No consensus anchors.</p>
                      )}
                    </div>
                    <div className="evidence-block">
                      <h3>Exact sportsbook lines</h3>
                      {market.lines.length ? (
                        <div className="evidence-table-scroll raw-lines">
                          <table className="evidence-table">
                            <thead>
                              <tr>
                                <th>Book</th>
                                <th>Type</th>
                                <th className="number">Line</th>
                                <th className="number">Over</th>
                                <th className="number">Under</th>
                              </tr>
                            </thead>
                            <tbody>
                              {market.lines.map((line) => (
                                <tr
                                  key={`${line.book}:${line.source}:${line.point}:${line.over_odds}:${line.under_odds}`}
                                >
                                  <td>{line.book}</td>
                                  <td>{line.source === 'alternate' ? 'Alt' : 'Main'}</td>
                                  <td className="number">{formatValue(line.point)}</td>
                                  <td className="number">{formatOdds(line.over_odds)}</td>
                                  <td className="number">{formatOdds(line.under_odds)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="subtle">No exact source lines.</p>
                      )}
                    </div>
                  </details>
                </>
              ) : null}
            </div>
          ) : null}

          <div className="inspector-section">
            <div className="section-label">Model summary</div>
            <dl className="detail-list">
              <div>
                <dt>Mean</dt>
                <dd>{formatPoints(player.mean)}</dd>
              </div>
              <div>
                <dt>Sportsbooks</dt>
                <dd>{player.books_used}</dd>
              </div>
              <div>
                <dt>Modeled markets</dt>
                <dd>{player.markets_used}</dd>
              </div>
            </dl>
          </div>
        </>
      ) : (
        <div className="empty-state">No usable priced markets are available for this player.</div>
      )}
    </div>
  );
}
