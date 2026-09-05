import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchProjections, MissingIdentityError } from './api/client';
import { PlayerInspector } from './components/PlayerInspector';
import { PlayerRanking } from './components/PlayerRanking';
import { ProbabilityChart } from './components/ProbabilityChart';
import { useWorkspaceStore } from './state/workspace';
import type { ProjectionResponse } from './types';

const views = [
  ['players', 'Players'],
  ['defenses', 'Defenses'],
  ['lineup', 'Best lineup'],
] as const;

export function App() {
  const view = useWorkspaceStore((state) => state.view);
  const week = useWorkspaceStore((state) => state.week);
  const target = useWorkspaceStore((state) => state.targetFantasyPoints);
  const selectedPlayer = useWorkspaceStore((state) => state.selectedPlayer);
  const selectedPlayers = useWorkspaceStore((state) => state.selectedPlayers);
  const selectedPositions = useWorkspaceStore((state) => state.selectedPositions);
  const setView = useWorkspaceStore((state) => state.setView);
  const setWeek = useWorkspaceStore((state) => state.setWeek);
  const setTarget = useWorkspaceStore((state) => state.setTargetFantasyPoints);
  const selectPlayer = useWorkspaceStore((state) => state.selectPlayer);
  const setSelectedPlayers = useWorkspaceStore((state) => state.setSelectedPlayers);
  const setSelectedPositions = useWorkspaceStore((state) => state.setSelectedPositions);

  const [report, setReport] = useState<ProjectionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredPlayer, setHoveredPlayer] = useState<string | null>(null);
  const initializedWeekRef = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchProjections(week, controller.signal)
      .then((payload) => {
        setReport(payload);
        if (initializedWeekRef.current !== week) {
          const positions = [
            ...new Set(payload.players.map((player) => player.pos).filter(Boolean)),
          ];
          const graphed = payload.players
            .filter((player) => player.curve.length > 0)
            .map((player) => player.name);
          setSelectedPositions(positions);
          setSelectedPlayers(graphed);
          initializedWeekRef.current = week;
        }

        const currentSelectedPlayer = useWorkspaceStore.getState().selectedPlayer;
        if (!payload.players.some((player) => player.name === currentSelectedPlayer)) {
          selectPlayer(
            payload.players.find((player) => player.has_projection)?.name ??
              payload.players[0]?.name ??
              null,
          );
        }
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setReport(null);
        if (reason instanceof MissingIdentityError) {
          setError(
            'No saved Sleeper league was found. Use the current app setup flow once, then return here.',
          );
        } else {
          setError(reason instanceof Error ? reason.message : 'Could not load projections.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [week, selectPlayer, setSelectedPlayers, setSelectedPositions]);

  const players = report?.players ?? [];
  const selected = players.find((player) => player.name === selectedPlayer) ?? null;
  const graphSeries = useMemo(
    () =>
      players
        .filter(
          (player) =>
            player.curve.length > 0 &&
            selectedPlayers.includes(player.name) &&
            selectedPositions.includes(player.pos),
        )
        .map((player) => ({
          id: player.name,
          label: player.name,
          points: player.curve.map((point) => ({ x: point.x, probability: point.survival })),
        })),
    [players, selectedPlayers, selectedPositions],
  );

  const toggleComparedPlayer = (name: string) => {
    setSelectedPlayers(
      selectedPlayers.includes(name)
        ? selectedPlayers.filter((player) => player !== name)
        : [...selectedPlayers, name],
    );
  };

  const togglePosition = (position: string) => {
    setSelectedPositions(
      selectedPositions.includes(position)
        ? selectedPositions.filter((value) => value !== position)
        : [...selectedPositions, position],
    );
  };

  return (
    <div className="app-frame">
      <header className="topbar">
        <div>
          <div className="eyebrow">Decision support</div>
          <h1>Odds Fantasy</h1>
        </div>
        <div className="header-status">
          {loading ? <span className="loading-dot">Loading projections…</span> : null}
          {!loading && report?.ratelimit ? <span>{report.ratelimit}</span> : null}
          <fieldset className="topbar-controls">
            <legend className="sr-only">Week window</legend>
            <button
              className={week === 'this' ? 'active' : ''}
              onClick={() => setWeek('this')}
              type="button"
            >
              This week
            </button>
            <button
              className={week === 'next' ? 'active' : ''}
              onClick={() => setWeek('next')}
              type="button"
            >
              Next week
            </button>
          </fieldset>
        </div>
      </header>

      <nav className="primary-nav" aria-label="Analysis view">
        {views.map(([value, label]) => (
          <button
            key={value}
            className={view === value ? 'active' : ''}
            onClick={() => setView(value)}
            type="button"
          >
            {label}
          </button>
        ))}
      </nav>

      {view === 'players' ? (
        <main className="workspace">
          <aside className="ranking-pane" aria-label="Player ranking">
            <div className="pane-heading">
              <span className="eyebrow">Ranking</span>
              <h2>{target === null ? 'Roster projections' : `Target · ${target.toFixed(1)} FP`}</h2>
            </div>
            {error ? <div className="error-state">{error}</div> : null}
            {!error && report?.message ? <div className="status-note">{report.message}</div> : null}
            {!error && !loading ? (
              <PlayerRanking
                players={players}
                target={target}
                selectedPlayer={selectedPlayer}
                comparedPlayers={selectedPlayers}
                selectedPositions={selectedPositions}
                hoveredPlayer={hoveredPlayer}
                onSelectPlayer={selectPlayer}
                onToggleComparedPlayer={toggleComparedPlayer}
                onTogglePosition={togglePosition}
                onSelectAll={() =>
                  setSelectedPlayers(
                    players.filter((player) => player.curve.length).map((player) => player.name),
                  )
                }
                onSelectNone={() => setSelectedPlayers([])}
                onHoverPlayer={setHoveredPlayer}
              />
            ) : null}
          </aside>

          <section className="analysis-pane" aria-label="Probability analysis">
            <div className="pane-heading split">
              <div>
                <span className="eyebrow">Probability</span>
                <h2>Fantasy points survival</h2>
                <p className="pane-description">
                  Chance of scoring at least each fantasy-point threshold.
                </p>
              </div>
              <div className="target-controls">
                <label className="target-control">
                  <span>Target FP</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    step="0.5"
                    value={target ?? ''}
                    placeholder="Set"
                    onChange={(event) => {
                      const value = event.target.value;
                      setTarget(value === '' ? null : Number(value));
                    }}
                  />
                </label>
                {target !== null ? (
                  <button className="clear-target" type="button" onClick={() => setTarget(null)}>
                    Clear
                  </button>
                ) : null}
              </div>
            </div>
            <div className="chart-instruction">
              {target === null
                ? 'Click and drag in the chart to set a target.'
                : 'Drag the dashed target line or type an exact value.'}
            </div>
            <ProbabilityChart
              series={graphSeries}
              target={target}
              activePlayerId={hoveredPlayer ?? selectedPlayer}
              onTargetChange={setTarget}
              onPlayerHover={setHoveredPlayer}
              onPlayerSelect={selectPlayer}
            />
          </section>

          <aside className="inspector-pane" aria-label="Player inspector">
            <div className="pane-heading">
              <span className="eyebrow">Inspector</span>
            </div>
            <PlayerInspector player={selected} target={target} />
          </aside>
        </main>
      ) : (
        <main className="pending-view">
          <span className="eyebrow">Migration in progress</span>
          <h2>{view === 'defenses' ? 'Defense analysis' : 'Best lineup'}</h2>
          <p>
            This section remains on the existing runtime until its workstation view reaches parity.
          </p>
        </main>
      )}
    </div>
  );
}
