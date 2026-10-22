import { useEffect, useRef, useState } from 'react';
import { searchPlayers } from '../api/client';
import type { PlayerSearchCandidate, ProjectionPlayer } from '../types';

interface ComparisonPlayerPickerProps {
  side: 'challenger' | 'starter';
  roster: ProjectionPlayer[];
  otherPlayer: string;
  onPick: (player: PlayerSearchCandidate) => void;
  onClose: () => void;
}

export function ComparisonPlayerPicker({
  side,
  roster,
  otherPlayer,
  onPick,
  onClose,
}: ComparisonPlayerPickerProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlayerSearchCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    searchRef.current?.focus();
  }, []);
  const searched = query.trim().length >= 2;

  useEffect(() => {
    if (!searched) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      setLoading(true);
      setError(false);
      searchPlayers(query.trim(), controller.signal)
        .then((response) => setResults(response.players))
        .catch(() => {
          if (!controller.signal.aborted) setError(true);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 200);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [query, searched]);

  const choices: PlayerSearchCandidate[] = searched
    ? results
    : roster.slice(0, 20).map((player) => ({
        id: '',
        name: player.name,
        pos: player.pos,
        team: player.team,
      }));

  return (
    <div
      className="comparison-player-picker"
      role="dialog"
      aria-label={`Replace ${side === 'challenger' ? 'left' : 'right'} comparison player`}
      onKeyDown={(event) => {
        if (event.key === 'Escape') onClose();
      }}
    >
      <div className="comparison-picker-header">
        <strong>Choose {side === 'challenger' ? 'left' : 'right'} player</strong>
        <button type="button" onClick={onClose} aria-label="Close player search">
          Close
        </button>
      </div>
      <input
        ref={searchRef}
        className="player-search"
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search all NFL players"
        aria-label="Search replacement players"
      />
      <div className="comparison-picker-results">
        {!searched ? (
          <span className="subtle">Your roster · type to search all NFL players</span>
        ) : null}
        {searched && loading ? <span className="subtle">Searching…</span> : null}
        {searched && error ? <span className="error-state">Player search unavailable.</span> : null}
        {searched && !loading && !error && choices.length === 0 ? (
          <span className="subtle">No matching players.</span>
        ) : null}
        {(!searched || (!loading && !error)) &&
          choices.map((player) => (
            <button
              type="button"
              key={player.id || player.name}
              disabled={player.name === otherPlayer}
              onClick={() => onPick(player)}
            >
              <strong>{player.name}</strong>
              <span>
                {player.pos} · {player.team || 'Team unavailable'}
                {player.name === otherPlayer ? ' · Already compared' : ''}
              </span>
            </button>
          ))}
      </div>
    </div>
  );
}
