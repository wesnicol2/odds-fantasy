import { formatProbability, probabilityAtTarget } from '../analysis/probability';
import type { ProjectionPlayer } from '../types';

interface PlayerInspectorProps {
  player: ProjectionPlayer | null;
  target: number | null;
}

function formatPoints(value: number | null): string {
  return value === null ? '—' : value.toFixed(1);
}

export function PlayerInspector({ player, target }: PlayerInspectorProps) {
  if (!player) {
    return <div className="empty-state">Select a player to inspect their projection.</div>;
  }

  const targetProbability = probabilityAtTarget(player.curve, target);

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

          {target !== null ? (
            <div className="target-summary">
              <span>Chance of ≥ {target.toFixed(1)} FP</span>
              <strong>{formatProbability(targetProbability)}</strong>
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
