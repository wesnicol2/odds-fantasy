import { metricLabel } from '../analysis/metrics';
import { formatProbability, probabilityAtTarget } from '../analysis/probability';
import type { PlayerOddsDetails, ProjectionPlayer } from '../types';

interface PlayerInspectorProps {
  player: ProjectionPlayer | null;
  target: number | null;
  metric: string;
  details: PlayerOddsDetails | null;
  detailsLoading: boolean;
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

export function PlayerInspector({
  player,
  target,
  metric,
  details,
  detailsLoading,
}: PlayerInspectorProps) {
  if (!player) {
    return <div className="empty-state">Select a player to inspect their projection.</div>;
  }

  const targetProbability = probabilityAtTarget(player.curve, target);
  const market = metric === 'fantasy_points' ? null : (details?.markets[metric] ?? null);
  const sportsbookCount = market
    ? new Set(market.lines.map((line) => line.book).filter(Boolean)).size
    : 0;

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
                    Diamonds are de-vigged cross-book consensus anchors. Small x-axis ticks are
                    exact sportsbook thresholds. The fitted survival curve is the backend model
                    constrained by that evidence.
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
