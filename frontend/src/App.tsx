import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { isCountMetric, metricLabel, sortMetrics } from './analysis/metrics';
import {
  fetchBestLineup,
  fetchDefenses,
  fetchPlayerDetails,
  fetchProjections,
  MissingIdentityError,
} from './api/client';
import { DefenseView } from './components/DefenseView';
import { LineupView } from './components/LineupView';
import { PlayerInspector } from './components/PlayerInspector';
import { PlayerRanking } from './components/PlayerRanking';
import { ProbabilityChart } from './components/ProbabilityChart';
import { useWorkspaceStore } from './state/workspace';
import type {
  ChartEvidence,
  DefenseResponse,
  LineupResponse,
  PlayerOddsDetails,
  ProjectionResponse,
} from './types';

const views = [
  ['players', 'Players'],
  ['defenses', 'Defenses'],
  ['lineup', 'Best lineup'],
] as const;

function detailsKey(week: string, player: string): string {
  return `${week}:${player}`;
}

function lineupKey(week: string, target: string): string {
  return `${week}:${target}`;
}

export function App() {
  const view = useWorkspaceStore((state) => state.view);
  const week = useWorkspaceStore((state) => state.week);
  const metric = useWorkspaceStore((state) => state.metric);
  const target = useWorkspaceStore((state) => state.targetFantasyPoints);
  const lineupTarget = useWorkspaceStore((state) => state.lineupTarget);
  const selectedPlayer = useWorkspaceStore((state) => state.selectedPlayer);
  const selectedPlayers = useWorkspaceStore((state) => state.selectedPlayers);
  const selectedPositions = useWorkspaceStore((state) => state.selectedPositions);
  const setView = useWorkspaceStore((state) => state.setView);
  const setWeek = useWorkspaceStore((state) => state.setWeek);
  const setMetric = useWorkspaceStore((state) => state.setMetric);
  const setTarget = useWorkspaceStore((state) => state.setTargetFantasyPoints);
  const setLineupTarget = useWorkspaceStore((state) => state.setLineupTarget);
  const selectPlayer = useWorkspaceStore((state) => state.selectPlayer);
  const setSelectedPlayers = useWorkspaceStore((state) => state.setSelectedPlayers);
  const setSelectedPositions = useWorkspaceStore((state) => state.setSelectedPositions);

  const [report, setReport] = useState<ProjectionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredPlayer, setHoveredPlayer] = useState<string | null>(null);
  const [detailsByKey, setDetailsByKey] = useState<Record<string, PlayerOddsDetails>>({});
  const [loadingDetailKeys, setLoadingDetailKeys] = useState<string[]>([]);
  const [defensePayload, setDefensePayload] = useState<DefenseResponse | null>(null);
  const [defenseLoading, setDefenseLoading] = useState(false);
  const [defenseError, setDefenseError] = useState<string | null>(null);
  const [lineupPayload, setLineupPayload] = useState<LineupResponse | null>(null);
  const [lineupLoading, setLineupLoading] = useState(false);
  const [lineupError, setLineupError] = useState<string | null>(null);
  const detailsRef = useRef<Record<string, PlayerOddsDetails>>({});
  const detailInflightRef = useRef(new Set<string>());
  const defensesRef = useRef<Record<string, DefenseResponse>>({});
  const lineupsRef = useRef<Record<string, LineupResponse>>({});
  const initializedWeekRef = useRef<string | null>(null);

  const loadPlayerDetails = useCallback(
    async (name: string) => {
      const key = detailsKey(week, name);
      if (detailsRef.current[key] || detailInflightRef.current.has(key)) return;
      detailInflightRef.current.add(key);
      setLoadingDetailKeys((current) => [...current, key]);
      try {
        const payload = await fetchPlayerDetails(name, week);
        detailsRef.current = { ...detailsRef.current, [key]: payload };
        setDetailsByKey(detailsRef.current);
      } catch (reason) {
        console.error(`Could not load evidence for ${name}`, reason);
      } finally {
        detailInflightRef.current.delete(key);
        setLoadingDetailKeys((current) => current.filter((value) => value !== key));
      }
    },
    [week],
  );

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

  useEffect(() => {
    if (selectedPlayer) void loadPlayerDetails(selectedPlayer);
  }, [selectedPlayer, loadPlayerDetails]);

  useEffect(() => {
    if (metric === 'fantasy_points') return;
    for (const player of selectedPlayers) void loadPlayerDetails(player);
  }, [metric, selectedPlayers, loadPlayerDetails]);

  useEffect(() => {
    if (view !== 'defenses') return;
    const cached = defensesRef.current[week];
    if (cached) {
      setDefensePayload(cached);
      setDefenseError(null);
      return;
    }

    const controller = new AbortController();
    setDefenseLoading(true);
    setDefenseError(null);
    fetchDefenses(week, controller.signal)
      .then((payload) => {
        defensesRef.current = { ...defensesRef.current, [week]: payload };
        setDefensePayload(payload);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setDefenseError(reason instanceof Error ? reason.message : 'Could not load defenses.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setDefenseLoading(false);
      });
    return () => controller.abort();
  }, [view, week]);

  useEffect(() => {
    if (view !== 'lineup') return;
    const key = lineupKey(week, lineupTarget);
    const cached = lineupsRef.current[key];
    if (cached) {
      setLineupPayload(cached);
      setLineupError(null);
      return;
    }

    const controller = new AbortController();
    setLineupLoading(true);
    setLineupError(null);
    fetchBestLineup(week, lineupTarget, controller.signal)
      .then((payload) => {
        lineupsRef.current = { ...lineupsRef.current, [key]: payload };
        setLineupPayload(payload);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setLineupError(reason instanceof Error ? reason.message : 'Could not build lineup.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLineupLoading(false);
      });
    return () => controller.abort();
  }, [lineupTarget, view, week]);

  const players = report?.players ?? [];
  const selected = players.find((player) => player.name === selectedPlayer) ?? null;
  const selectedDetails = selectedPlayer
    ? (detailsByKey[detailsKey(week, selectedPlayer)] ?? null)
    : null;
  const selectedDetailsLoading = selectedPlayer
    ? loadingDetailKeys.includes(detailsKey(week, selectedPlayer))
    : false;

  const availableMetrics = useMemo(() => {
    const metrics = new Set<string>(['fantasy_points']);
    for (const player of selectedPlayers) {
      const details = detailsByKey[detailsKey(week, player)];
      if (!details) continue;
      for (const key of Object.keys(details.markets)) metrics.add(key);
    }
    if (selectedDetails) {
      for (const key of Object.keys(selectedDetails.markets)) metrics.add(key);
    }
    return sortMetrics([...metrics]);
  }, [detailsByKey, selectedDetails, selectedPlayers, week]);

  const graphSeries = useMemo(() => {
    if (metric === 'fantasy_points') {
      return players
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
        }));
    }

    return players
      .filter(
        (player) => selectedPlayers.includes(player.name) && selectedPositions.includes(player.pos),
      )
      .flatMap((player) => {
        const market = detailsByKey[detailsKey(week, player.name)]?.markets[metric];
        if (!market?.graph.points.length) return [];
        return [{ id: player.name, label: player.name, points: market.graph.points }];
      });
  }, [detailsByKey, metric, players, selectedPlayers, selectedPositions, week]);

  const chartEvidence: ChartEvidence | null = useMemo(() => {
    if (!selectedPlayer || metric === 'fantasy_points') return null;
    const market = selectedDetails?.markets[metric];
    if (!market) return null;
    return { playerId: selectedPlayer, anchors: market.anchors, lines: market.lines };
  }, [metric, selectedDetails, selectedPlayer]);

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

  const fantasyPointsMetric = metric === 'fantasy_points';
  const activeMetricLabel = metricLabel(metric);

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
                target={fantasyPointsMetric ? target : null}
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
                <h2>{activeMetricLabel} survival</h2>
                <p className="pane-description">
                  Chance of reaching or exceeding each {activeMetricLabel.toLowerCase()} threshold.
                </p>
              </div>
              {fantasyPointsMetric ? (
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
              ) : null}
            </div>

            <fieldset className="metric-strip">
              <legend className="sr-only">Probability metric</legend>
              {availableMetrics.map((value) => (
                <button
                  key={value}
                  type="button"
                  className={metric === value ? 'active' : ''}
                  onClick={() => setMetric(value)}
                >
                  {metricLabel(value)}
                </button>
              ))}
            </fieldset>

            <div className="chart-instruction">
              {fantasyPointsMetric
                ? target === null
                  ? 'Click and drag in the chart to set a target.'
                  : 'Drag the dashed target line or type an exact value.'
                : 'Diamonds show consensus market anchors; x-axis ticks show exact sportsbook thresholds for the selected player.'}
            </div>
            <ProbabilityChart
              series={graphSeries}
              target={fantasyPointsMetric ? target : null}
              activePlayerId={hoveredPlayer ?? selectedPlayer}
              metric={metric}
              xAxisName={activeMetricLabel}
              yAxisName={`P(${activeMetricLabel} ≥ x)`}
              targetEnabled={fantasyPointsMetric}
              stepCurve={!fantasyPointsMetric && isCountMetric(metric)}
              evidence={chartEvidence}
              onTargetChange={setTarget}
              onPlayerHover={setHoveredPlayer}
              onPlayerSelect={selectPlayer}
            />
          </section>

          <aside className="inspector-pane" aria-label="Player inspector">
            <div className="pane-heading">
              <span className="eyebrow">Inspector</span>
            </div>
            <PlayerInspector
              player={selected}
              target={target}
              metric={metric}
              details={selectedDetails}
              detailsLoading={selectedDetailsLoading}
            />
          </aside>
        </main>
      ) : null}

      {view === 'defenses' ? (
        <DefenseView payload={defensePayload} loading={defenseLoading} error={defenseError} />
      ) : null}

      {view === 'lineup' ? (
        <LineupView
          payload={lineupPayload}
          target={lineupTarget}
          loading={lineupLoading}
          error={lineupError}
          onTargetChange={setLineupTarget}
        />
      ) : null}
    </div>
  );
}
