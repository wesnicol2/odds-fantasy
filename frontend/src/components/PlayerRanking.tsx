import { useMemo, useState } from 'react';
import { formatProbability, probabilityAtTarget } from '../analysis/probability';
import type { ProjectionPlayer } from '../types';
import { RangeThermometer } from './RangeThermometer';

interface PlayerRankingProps {
  players: ProjectionPlayer[];
  target: number | null;
  selectedPlayer: string | null;
  comparedPlayers: string[];
  selectedPositions: string[];
  hoveredPlayer: string | null;
  onSelectPlayer: (name: string) => void;
  onToggleComparedPlayer: (name: string) => void;
  onTogglePosition: (position: string) => void;
  onSelectAll: () => void;
  onSelectNone: () => void;
  onHoverPlayer: (name: string | null) => void;
}

function formatPoints(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toFixed(1);
}

export function PlayerRanking({
  players,
  target,
  selectedPlayer,
  comparedPlayers,
  selectedPositions,
  hoveredPlayer,
  onSelectPlayer,
  onToggleComparedPlayer,
  onTogglePosition,
  onSelectAll,
  onSelectNone,
  onHoverPlayer,
}: PlayerRankingProps) {
  const [query, setQuery] = useState('');
  const compared = useMemo(() => new Set(comparedPlayers), [comparedPlayers]);
  const positions = useMemo(
    () => [...new Set(players.map((player) => player.pos).filter(Boolean))].sort(),
    [players],
  );
  const projected = players.filter(
    (player) => player.floor !== null && player.mid !== null && player.ceiling !== null,
  );
  const glyphMinimum = Math.min(0, ...projected.map((player) => player.floor ?? 0));
  const glyphMaximum = Math.max(1, ...projected.map((player) => player.ceiling ?? 0));

  const visiblePlayers = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = players.filter((player) => {
      if (!selectedPositions.includes(player.pos)) return false;
      if (!normalizedQuery) return true;
      return `${player.name} ${player.pos} ${player.team ?? ''}`
        .toLowerCase()
        .includes(normalizedQuery);
    });

    return [...filtered].sort((left, right) => {
      if (Boolean(left.locked) !== Boolean(right.locked)) return left.locked ? 1 : -1;
      if (target !== null) {
        const leftProbability = probabilityAtTarget(left.curve, target) ?? -1;
        const rightProbability = probabilityAtTarget(right.curve, target) ?? -1;
        if (rightProbability !== leftProbability) return rightProbability - leftProbability;
      }
      return (right.mid ?? -1) - (left.mid ?? -1);
    });
  }, [players, query, selectedPositions, target]);

  return (
    <div className="ranking-content">
      <div className="ranking-tools">
        <input
          className="player-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search players"
          aria-label="Search players"
        />
        <fieldset className="position-filters">
          <legend className="sr-only">Position filters</legend>
          {positions.map((position) => (
            <button
              key={position}
              type="button"
              className={selectedPositions.includes(position) ? 'active' : ''}
              aria-pressed={selectedPositions.includes(position)}
              onClick={() => onTogglePosition(position)}
            >
              {position}
            </button>
          ))}
        </fieldset>
        <div className="compare-actions">
          <span>{comparedPlayers.length} graphed</span>
          <button type="button" onClick={onSelectAll}>
            All
          </button>
          <button type="button" onClick={onSelectNone}>
            None
          </button>
        </div>
      </div>

      <div className="ranking-scroll">
        <table className="ranking-table">
          <thead>
            <tr>
              <th className="compare-column">
                <span className="sr-only">Graph</span>
              </th>
              <th>Player</th>
              <th className="number">Floor</th>
              <th className="number">Mid</th>
              <th className="number">Ceil</th>
              <th>Range</th>
              {target !== null ? (
                <th className="number target-column">≥ {target.toFixed(1)}</th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {visiblePlayers.map((player) => {
              const isSelected = player.name === selectedPlayer;
              const isHovered = player.name === hoveredPlayer;
              const targetProbability = probabilityAtTarget(player.curve, target);
              const hasRange =
                player.floor !== null && player.mid !== null && player.ceiling !== null;
              const unavailable = !player.has_projection || player.locked;

              return (
                <tr
                  key={player.name}
                  className={`${isSelected ? 'selected' : ''} ${isHovered ? 'hover-linked' : ''} ${unavailable ? 'unavailable' : ''}`}
                  onMouseEnter={() => onHoverPlayer(player.name)}
                  onMouseLeave={() => onHoverPlayer(null)}
                >
                  <td className="compare-column">
                    <input
                      type="checkbox"
                      checked={compared.has(player.name)}
                      disabled={!player.curve.length}
                      onChange={() => onToggleComparedPlayer(player.name)}
                      aria-label={`Graph ${player.name}`}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="player-name-button"
                      onClick={() => onSelectPlayer(player.name)}
                    >
                      <strong>{player.name}</strong>
                      <span>
                        {player.pos} · {player.team || 'Team unavailable'}
                      </span>
                      {player.locked ? (
                        <small>
                          LOCKED {player.lineup_status === 'bench' ? 'ON BENCH' : 'STARTER'} ·{' '}
                          {formatPoints(player.actual_points)} actual FP
                        </small>
                      ) : !player.has_projection ? (
                        <small>no priced markets</small>
                      ) : null}
                    </button>
                  </td>
                  <td className="number">{formatPoints(player.floor)}</td>
                  <td className="number mid-value">{formatPoints(player.mid)}</td>
                  <td className="number">{formatPoints(player.ceiling)}</td>
                  <td>
                    {hasRange ? (
                      <RangeThermometer
                        floor={player.floor ?? 0}
                        mid={player.mid ?? 0}
                        ceiling={player.ceiling ?? 0}
                        minimum={glyphMinimum}
                        maximum={glyphMaximum}
                        label={`Floor ${formatPoints(player.floor)}, mid ${formatPoints(player.mid)}, ceiling ${formatPoints(player.ceiling)}`}
                      />
                    ) : (
                      <span className="subtle">—</span>
                    )}
                  </td>
                  {target !== null ? (
                    <td className="number target-value">{formatProbability(targetProbability)}</td>
                  ) : null}
                </tr>
              );
            })}
          </tbody>
        </table>
        {visiblePlayers.length === 0 ? (
          <div className="empty-state">No players match the current filters.</div>
        ) : null}
      </div>
    </div>
  );
}