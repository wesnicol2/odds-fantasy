import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { isCountMetric, metricLabel, sortMetrics } from './analysis/metrics';
import {
  fetchBestLineup,
  fetchDefenses,
  fetchLeagueResolution,
  fetchPlayerDetails,
  fetchProjections,
  MissingIdentityError,
} from './api/client';
import { AppSettings } from './components/AppSettings';
import { DashboardView } from './components/DashboardView';
import { DefenseView } from './components/DefenseView';
import { type LeagueSelectionSummary, LeagueSetup } from './components/LeagueSetup';
import { LineupView } from './components/LineupView';
import { PlayerComparisonInspector } from './components/PlayerComparisonInspector';
import { PlayerInspector } from './components/PlayerInspector';
import { PlayerRanking } from './components/PlayerRanking';
import { ProbabilityChart } from './components/ProbabilityChart';
import { StatProbabilityChart } from './components/StatProbabilityChart';
import { savedLeagueIdentity } from './identity';
import './navigation.css';
import { useWorkspaceStore, type WeekWindow, type WorkspaceView } from './state/workspace';
import type {
  BenchPressureRow,
  ChartEvidence,
  DefenseResponse,
  LineupResponse,
  PlayerOddsDetails,
  ProjectionResponse,
} from './types';

const views: ReadonlyArray<readonly [WorkspaceView, string]> = [
  ['dashboard', 'Dashboard'],
  ['players', 'Players'],
  ['defenses', 'Defenses'],
  ['lineup', 'Lineup'],
];

interface StartSitComparison {
  challenger: string;
  starter: string;
  lineupDelta: number;
  week: WeekWindow;
}

function detailsKey(identity: string, mode: string, week: string, player: string): string {
  return `${identity}:${mode}:${week}:${player}`;
}

function defenseKey(identity: string, mode: string, week: string): string {
  return `${identity}:${mode}:${week}`;
}

function lineupKey(identity: string, mode: string, week: string, target: string): string {
  return `${identity}:${mode}:${week}:${target}`;
}

function routeFromLocation(): { view: WorkspaceView; week: WeekWindow } {
  const params = new URLSearchParams(window.location.search);
  const requestedView = params.get('view');
  const view = views.some(([value]) => value === requestedView)
    ? (requestedView as WorkspaceView)
    : 'dashboard';
  const week = params.get('week') === 'next' ? 'next' : 'this';
  return { view, week };
}

function routeUrl(view: WorkspaceView, week: WeekWindow): string {
  const url = new URL(window.location.href);
  url.search = '';
  if (view !== 'dashboard') {
    url.searchParams.set('view', view);
    url.searchParams.set('week', week);
  }
  return `${url.pathname}${url.search}`;
}

export function App() {
  const view = useWorkspaceStore((state) => state.view);
  const week = useWorkspaceStore((state) => state.week);
  const metric = useWorkspaceStore((state) => state.metric);
  const dataMode = useWorkspaceStore((state) => state.dataMode);
  const target = useWorkspaceStore((state) => state.targetFantasyPoints);
  const lineupTarget = useWorkspaceStore((state) => state.lineupTarget);
  const selectedPlayer = useWorkspaceStore((state) => state.selectedPlayer);
  const selectedPlayers = useWorkspaceStore((state) => state.selectedPlayers);
  const selectedPositions = useWorkspaceStore((state) => state.selectedPositions);
  const setView = useWorkspaceStore((state) => state.setView);
  const setWeek = useWorkspaceStore((state) => state.setWeek);
  const setMetric = useWorkspaceStore((state) => state.setMetric);
  const setDataMode = useWorkspaceStore((state) => state.setDataMode);
  const setTarget = useWorkspaceStore((state) => state.setTargetFantasyPoints);
  const setLineupTarget = useWorkspaceStore((state) => state.setLineupTarget);
  const selectPlayer = useWorkspaceStore((state) => state.selectPlayer);
  const setSelectedPlayers = useWorkspaceStore((state) => state.setSelectedPlayers);
  const setSelectedPositions = useWorkspaceStore((state) => state.setSelectedPositions);

  const [identity, setIdentity] = useState(savedLeagueIdentity);
  const [setupOpen, setSetupOpen] = useState(() => !(identity.leagueId && identity.rosterId));
  const [leagueContext, setLeagueContext] = useState<string | null>(null);
  const [report, setReport] = useState<ProjectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredPlayer, setHoveredPlayer] = useState<string | null>(null);
  const [comparisonContext, setComparisonContext] = useState<StartSitComparison | null>(null);
  const [detailsByKey, setDetailsByKey] = useState<Record<string, PlayerOddsDetails>>({});
  const [loadingDetailKeys, setLoadingDetailKeys] = useState<string[]>([]);
  const [defensePayload, setDefensePayload] = useState<DefenseResponse | null>(null);
  const [defenseLoading, setDefenseLoading] = useState(false);
  const [defenseError, setDefenseError] = useState<string | null>(null);
  const [lineupPayload, setLineupPayload] = useState<LineupResponse | null>(null);
  const [lineupLoading, setLineupLoading] = useState(false);
  const [lineupError, setLineupError] = useState<string | null>(null);
  const [dashboardLineup, setDashboardLineup] = useState<LineupResponse | null>(null);
  const [dashboardDefensesThis, setDashboardDefensesThis] = useState<DefenseResponse | null>(null);
  const [dashboardDefensesNext, setDashboardDefensesNext] = useState<DefenseResponse | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const detailsRef = useRef<Record<string, PlayerOddsDetails>>({});
  const detailInflightRef = useRef(new Set<string>());
  const defensesRef = useRef<Record<string, DefenseResponse>>({});
  const lineupsRef = useRef<Record<string, LineupResponse>>({});
  const initializedWeekRef = useRef<string | null>(null);
  const pendingComparisonRef = useRef<{
    week: WeekWindow;
    players: string[];
    selected: string;
  } | null>(null);

  const identityReady = Boolean(identity.leagueId && identity.rosterId);
  const identityKey = `${identity.leagueId ?? ''}:${identity.rosterId ?? ''}`;

  const navigateTo = useCallback(
    (nextView: WorkspaceView, nextWeek: WeekWindow = week) => {
      setView(nextView);
      if (nextView !== 'dashboard') setWeek(nextWeek);
      window.history.pushState({}, '', routeUrl(nextView, nextWeek));
      window.scrollTo({ top: 0 });
    },
    [setView, setWeek, week],
  );

  const loadPlayerDetails = useCallback(
    async (name: string) => {
      if (!identityReady) return;
      const key = detailsKey(identityKey, dataMode, week, name);
      if (detailsRef.current[key] || detailInflightRef.current.has(key)) return;
      detailInflightRef.current.add(key);
      setLoadingDetailKeys((current) => [...current, key]);
      try {
        const payload = await fetchPlayerDetails(name, week, dataMode);
        detailsRef.current = { ...detailsRef.current, [key]: payload };
        setDetailsByKey(detailsRef.current);
      } catch (reason) {
        console.error(`Could not load evidence for ${name}`, reason);
      } finally {
        detailInflightRef.current.delete(key);
        setLoadingDetailKeys((current) => current.filter((value) => value !== key));
      }
    },
    [dataMode, identityKey, identityReady, week],
  );

  useEffect(() => {
    const syncRoute = () => {
      const route = routeFromLocation();
      setView(route.view);
      if (route.view !== 'dashboard') setWeek(route.week);
    };
    syncRoute();
    window.addEventListener('popstate', syncRoute);
    return () => window.removeEventListener('popstate', syncRoute);
  }, [setView, setWeek]);

  useEffect(() => {
    if (!identity.leagueId || !identity.rosterId) {
      setLeagueContext(null);
      return;
    }

    const controller = new AbortController();
    fetchLeagueResolution(identity.leagueId, controller.signal)
      .then((payload) => {
        const team = payload.teams.find(
          (row) => String(row.roster_id) === String(identity.rosterId),
        );
        const leagueName = payload.name || identity.leagueId;
        const teamName = team?.team_name || team?.display_name || `Team ${identity.rosterId}`;
        setLeagueContext(`${leagueName} · ${teamName}`);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLeagueContext(null);
      });
    return () => controller.abort();
  }, [identity.leagueId, identity.rosterId]);

  useEffect(() => {
    if (view !== 'players') {
      setLoading(false);
      return;
    }
    if (!identityReady) {
      setLoading(false);
      setReport(null);
      setError(null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchProjections(week, dataMode, controller.signal)
      .then((payload) => {
        setReport(payload);
        const initializationKey = `${identityKey}:${week}`;
        if (initializedWeekRef.current !== initializationKey) {
          const positions = [
            ...new Set(payload.players.map((player) => player.pos).filter(Boolean)),
          ];
          const graphed = payload.players
            .filter((player) => player.curve.length > 0)
            .map((player) => player.name);
          setSelectedPositions(positions);
          setSelectedPlayers(graphed);
          initializedWeekRef.current = initializationKey;
        }

        const pendingComparison = pendingComparisonRef.current;
        if (pendingComparison?.week === week) {
          const validPlayers = pendingComparison.players.filter((name) =>
            payload.players.some((player) => player.name === name),
          );
          setSelectedPlayers(validPlayers);
          selectPlayer(
            payload.players.some((player) => player.name === pendingComparison.selected)
              ? pendingComparison.selected
              : (validPlayers[0] ?? null),
          );
          pendingComparisonRef.current = null;
          return;
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
        if (reason instanceof MissingIdentityError) {
          setSetupOpen(true);
          setError(null);
        } else {
          setError(reason instanceof Error ? reason.message : 'Could not load projections.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [
    dataMode,
    identityKey,
    identityReady,
    week,
    view,
    selectPlayer,
    setSelectedPlayers,
    setSelectedPositions,
  ]);

  useEffect(() => {
    if (view !== 'players' || !selectedPlayer) return;
    void loadPlayerDetails(selectedPlayer);
  }, [selectedPlayer, loadPlayerDetails, view]);

  useEffect(() => {
    if (
      view !== 'players' ||
      !comparisonContext ||
      comparisonContext.week !== week ||
      report?.week !== week ||
      !report.players.some((player) => player.name === comparisonContext.challenger) ||
      !report.players.some((player) => player.name === comparisonContext.starter)
    )
      return;
    void loadPlayerDetails(comparisonContext.challenger);
    void loadPlayerDetails(comparisonContext.starter);
  }, [comparisonContext, loadPlayerDetails, report, view, week]);

  useEffect(() => {
    if (view !== 'players' || metric === 'fantasy_points') return;
    for (const player of selectedPlayers) void loadPlayerDetails(player);
  }, [metric, selectedPlayers, loadPlayerDetails, view]);

  useEffect(() => {
    if (view !== 'defenses' || !identityReady) return;
    const key = defenseKey(identityKey, dataMode, week);
    const cached = defensesRef.current[key];
    if (cached) {
      setDefensePayload(cached);
      setDefenseError(null);
      setDefenseLoading(false);
      return;
    }

    const controller = new AbortController();
    setDefenseLoading(true);
    setDefenseError(null);
    fetchDefenses(week, dataMode, controller.signal)
      .then((payload) => {
        defensesRef.current = { ...defensesRef.current, [key]: payload };
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
  }, [dataMode, identityKey, identityReady, view, week]);

  useEffect(() => {
    if (view !== 'lineup' || !identityReady) return;
    const key = lineupKey(identityKey, dataMode, week, lineupTarget);
    const cached = lineupsRef.current[key];
    if (cached) {
      setLineupPayload(cached);
      setLineupError(null);
      setLineupLoading(false);
      return;
    }

    const controller = new AbortController();
    setLineupLoading(true);
    setLineupError(null);
    fetchBestLineup(week, lineupTarget, dataMode, controller.signal)
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
  }, [dataMode, identityKey, identityReady, lineupTarget, view, week]);

  useEffect(() => {
    if (view !== 'dashboard' || !identityReady) {
      setDashboardLoading(false);
      return;
    }

    const controller = new AbortController();
    setDashboardLoading(true);
    setDashboardError(null);

    const loadDefense = async (targetWeek: WeekWindow) => {
      const key = defenseKey(identityKey, dataMode, targetWeek);
      const cached = defensesRef.current[key];
      if (cached) return cached;
      const payload = await fetchDefenses(targetWeek, dataMode, controller.signal);
      defensesRef.current = { ...defensesRef.current, [key]: payload };
      return payload;
    };

    const loadMidLineup = async () => {
      const key = lineupKey(identityKey, dataMode, 'this', 'mid');
      const cached = lineupsRef.current[key];
      if (cached) return cached;
      const payload = await fetchBestLineup('this', 'mid', dataMode, controller.signal);
      lineupsRef.current = { ...lineupsRef.current, [key]: payload };
      return payload;
    };

    const loadDashboard = async () => {
      const nextDefensePromise = loadDefense('next');
      const lineup = await loadMidLineup();
      const thisDefense = await loadDefense('this');
      const nextDefense = await nextDefensePromise;
      return { lineup, thisDefense, nextDefense };
    };

    loadDashboard()
      .then(({ lineup, thisDefense, nextDefense }) => {
        setDashboardLineup(lineup);
        setDashboardDefensesThis(thisDefense);
        setDashboardDefensesNext(nextDefense);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (reason instanceof MissingIdentityError) {
          setSetupOpen(true);
          setDashboardError(null);
        } else {
          setDashboardError(
            reason instanceof Error ? reason.message : 'Could not build dashboard.',
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setDashboardLoading(false);
      });

    return () => controller.abort();
  }, [dataMode, identityKey, identityReady, view]);

  const players = report?.players ?? [];
  const selected = players.find((player) => player.name === selectedPlayer) ?? null;
  const selectedDetails = selectedPlayer
    ? (detailsByKey[detailsKey(identityKey, dataMode, week, selectedPlayer)] ?? null)
    : null;
  const selectedDetailsLoading = selectedPlayer
    ? loadingDetailKeys.includes(detailsKey(identityKey, dataMode, week, selectedPlayer))
    : false;
  const comparisonChallenger = comparisonContext
    ? (players.find((player) => player.name === comparisonContext.challenger) ?? null)
    : null;
  const comparisonStarter = comparisonContext
    ? (players.find((player) => player.name === comparisonContext.starter) ?? null)
    : null;
  const activeComparison =
    comparisonContext &&
    comparisonContext.week === week &&
    comparisonChallenger &&
    comparisonStarter
      ? {
          context: comparisonContext,
          challenger: comparisonChallenger,
          starter: comparisonStarter,
          challengerDetails:
            detailsByKey[detailsKey(identityKey, dataMode, week, comparisonContext.challenger)] ??
            null,
          starterDetails:
            detailsByKey[detailsKey(identityKey, dataMode, week, comparisonContext.starter)] ??
            null,
          detailsLoading: [comparisonContext.challenger, comparisonContext.starter].some((name) =>
            loadingDetailKeys.includes(detailsKey(identityKey, dataMode, week, name)),
          ),
        }
      : null;

  const availableMetrics = useMemo(() => {
    const metrics = new Set<string>(['fantasy_points']);
    for (const player of selectedPlayers) {
      const details = detailsByKey[detailsKey(identityKey, dataMode, week, player)];
      if (!details) continue;
      for (const key of Object.keys(details.markets)) metrics.add(key);
    }
    if (selectedDetails) {
      for (const key of Object.keys(selectedDetails.markets)) metrics.add(key);
    }
    return sortMetrics([...metrics]);
  }, [dataMode, detailsByKey, identityKey, selectedDetails, selectedPlayers, week]);

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
        const market =
          detailsByKey[detailsKey(identityKey, dataMode, week, player.name)]?.markets[metric];
        if (!market?.graph.points.length) return [];
        return [
          {
            id: player.name,
            label: player.name,
            points: market.graph.points,
            kind: market.graph.kind,
          },
        ];
      });
  }, [
    dataMode,
    detailsByKey,
    identityKey,
    metric,
    players,
    selectedPlayers,
    selectedPositions,
    week,
  ]);

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

  const compareBenchPlayer = (pressure: BenchPressureRow) => {
    const comparison = [pressure.name, pressure.displaces].filter((name): name is string =>
      Boolean(name),
    );
    pendingComparisonRef.current = {
      week: 'this',
      players: [...new Set(comparison)],
      selected: pressure.name,
    };
    setComparisonContext(
      pressure.displaces
        ? {
            challenger: pressure.name,
            starter: pressure.displaces,
            lineupDelta: pressure.delta_to_lineup,
            week: 'this',
          }
        : null,
    );
    setMetric('fantasy_points');
    navigateTo('players', 'this');
  };

  const completeLeagueSetup = (summary: LeagueSelectionSummary) => {
    detailsRef.current = {};
    detailInflightRef.current.clear();
    defensesRef.current = {};
    lineupsRef.current = {};
    initializedWeekRef.current = null;
    pendingComparisonRef.current = null;
    setComparisonContext(null);
    setDetailsByKey({});
    setLoadingDetailKeys([]);
    setDefensePayload(null);
    setLineupPayload(null);
    setDashboardLineup(null);
    setDashboardDefensesThis(null);
    setDashboardDefensesNext(null);
    setReport(null);
    setLeagueContext(`${summary.leagueName} · ${summary.teamName}`);
    setIdentity(savedLeagueIdentity());
    setSetupOpen(false);
  };

  const fantasyPointsMetric = metric === 'fantasy_points';
  const activeMetricLabel = metricLabel(metric);
  const lowGranularityMetric =
    !fantasyPointsMetric && isCountMetric(metric) && metric !== 'player_receptions';
  const highGranularityMetric =
    !fantasyPointsMetric && isCountMetric(metric) && metric === 'player_receptions';
  const activeLoading =
    view === 'dashboard'
      ? dashboardLoading
      : view === 'players'
        ? loading
        : view === 'defenses'
          ? defenseLoading
          : lineupLoading;
  const activeRatelimit =
    view === 'dashboard'
      ? (dashboardLineup?.ratelimit ?? dashboardDefensesNext?.ratelimit)
      : view === 'players'
        ? report?.ratelimit
        : view === 'defenses'
          ? defensePayload?.ratelimit
          : lineupPayload?.ratelimit;

  return (
    <div className="app-frame">
      <header className="topbar">
        <div>
          <div className="eyebrow">Decision support</div>
          <h1>Odds Fantasy</h1>
          {leagueContext ? <div className="league-context">{leagueContext}</div> : null}
        </div>
        <div className="header-status">
          {activeLoading ? <span className="loading-dot">Updating…</span> : null}
          {!activeLoading && activeRatelimit ? <span>{activeRatelimit}</span> : null}
          <AppSettings
            dataMode={dataMode}
            onDataModeChange={setDataMode}
            onChangeLeague={() => setSetupOpen(true)}
          />
        </div>
      </header>

      <nav className="primary-nav" aria-label="Primary navigation">
        {views.map(([value, label]) => (
          <button
            key={value}
            className={view === value ? 'active' : ''}
            onClick={() => navigateTo(value)}
            type="button"
            aria-current={view === value ? 'page' : undefined}
          >
            {label}
          </button>
        ))}
      </nav>

      {view !== 'dashboard' ? (
        <div className="view-context">
          <span className="view-context-label">Week</span>
          <fieldset className="week-switch">
            <legend className="sr-only">Week window</legend>
            <button
              className={week === 'this' ? 'active' : ''}
              onClick={() => navigateTo(view, 'this')}
              type="button"
            >
              This week
            </button>
            <button
              className={week === 'next' ? 'active' : ''}
              onClick={() => navigateTo(view, 'next')}
              type="button"
            >
              Next week
            </button>
          </fieldset>
        </div>
      ) : null}

      {view === 'dashboard' ? (
        <DashboardView
          lineup={dashboardLineup}
          defensesThisWeek={dashboardDefensesThis}
          defensesNextWeek={dashboardDefensesNext}
          loading={dashboardLoading}
          error={dashboardError}
          onOpenLineup={() => {
            setLineupTarget('mid');
            navigateTo('lineup', 'this');
          }}
          onOpenDefenses={(targetWeek) => navigateTo('defenses', targetWeek)}
          onCompareBenchPlayer={compareBenchPlayer}
        />
      ) : null}

      {view === 'players' ? (
        <main className={activeComparison ? 'workspace comparison-workspace' : 'workspace'}>
          <aside className="ranking-pane" aria-label="Player ranking">
            <div className="pane-heading">
              <span className="eyebrow">Ranking</span>
              <h2>{target === null ? 'Roster projections' : `Target · ${target.toFixed(1)} FP`}</h2>
            </div>
            {error ? <div className="error-state">{error}</div> : null}
            {!error && report?.message ? <div className="status-note">{report.message}</div> : null}
            {!identityReady ? (
              <div className="empty-state">
                Choose a Sleeper league and team to load projections.
              </div>
            ) : null}
            {!error && !loading && identityReady ? (
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
                <h2>
                  {fantasyPointsMetric
                    ? `${activeMetricLabel} distribution`
                    : lowGranularityMetric
                      ? `${activeMetricLabel} thresholds`
                      : `${activeMetricLabel} distribution`}
                </h2>
                <p className="pane-description">
                  {fantasyPointsMetric
                    ? 'Chance of landing in each one-point fantasy-score bucket.'
                    : lowGranularityMetric
                      ? `Chance of meeting or exceeding each ${activeMetricLabel.toLowerCase()} count threshold.`
                      : highGranularityMetric
                        ? `Chance of each exact ${activeMetricLabel.toLowerCase()} value; the line is smoothed only between integer outcomes.`
                        : `Probability density across the fitted ${activeMetricLabel.toLowerCase()} distribution.`}
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
                : lowGranularityMetric
                  ? `Each thermometer shows P(${activeMetricLabel} ≥ threshold); player markers are fitted probabilities derived from sportsbook lines.`
                  : 'Exact sportsbook thresholds are marked on the x-axis. Consensus P(≥x) anchors remain in the inspector because this chart shows P(x).'}
            </div>
            {fantasyPointsMetric ? (
              <ProbabilityChart
                series={graphSeries}
                target={target}
                activePlayerId={hoveredPlayer ?? selectedPlayer}
                metric={metric}
                xAxisName={activeMetricLabel}
                yAxisName={`P(${activeMetricLabel} = x)`}
                targetEnabled
                onTargetChange={setTarget}
                onPlayerHover={setHoveredPlayer}
                onPlayerSelect={selectPlayer}
              />
            ) : (
              <StatProbabilityChart
                series={graphSeries}
                activePlayerId={hoveredPlayer ?? selectedPlayer}
                metric={metric}
                xAxisName={activeMetricLabel}
                evidence={chartEvidence}
                onPlayerHover={setHoveredPlayer}
                onPlayerSelect={selectPlayer}
              />
            )}
          </section>

          <aside className="inspector-pane" aria-label="Player inspector">
            <div className="pane-heading">
              <span className="eyebrow">Inspector</span>
            </div>
            {activeComparison ? (
              <PlayerComparisonInspector
                challenger={activeComparison.challenger}
                starter={activeComparison.starter}
                challengerDetails={activeComparison.challengerDetails}
                starterDetails={activeComparison.starterDetails}
                detailsLoading={activeComparison.detailsLoading}
                lineupDelta={activeComparison.context.lineupDelta}
                target={target}
                metric={metric}
                onMetricChange={setMetric}
                onExit={() => setComparisonContext(null)}
              />
            ) : (
              <PlayerInspector
                player={selected}
                target={target}
                metric={metric}
                details={selectedDetails}
                detailsLoading={selectedDetailsLoading}
                onMetricChange={setMetric}
              />
            )}
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

      <LeagueSetup
        open={setupOpen}
        required={!identityReady}
        onClose={() => setSetupOpen(false)}
        onComplete={completeLeagueSetup}
      />
    </div>
  );
}
