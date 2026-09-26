import { create } from 'zustand';
import type { OddsFormat } from '../analysis/odds';

export type WorkspaceView = 'dashboard' | 'players' | 'defenses' | 'lineup';
export type WeekWindow = 'this' | 'next';
export type LineupTarget = 'floor' | 'mid' | 'ceiling';
export type DataMode = 'auto' | 'cache' | 'fresh';

interface WorkspaceState {
  view: WorkspaceView;
  week: WeekWindow;
  metric: string;
  dataMode: DataMode;
  oddsFormat: OddsFormat;
  selectedPlayer: string | null;
  selectedPositions: string[];
  selectedPlayers: string[];
  targetFantasyPoints: number | null;
  lineupTarget: LineupTarget;
  setView: (view: WorkspaceView) => void;
  setWeek: (week: WeekWindow) => void;
  setMetric: (metric: string) => void;
  setDataMode: (mode: DataMode) => void;
  setOddsFormat: (format: OddsFormat) => void;
  selectPlayer: (player: string | null) => void;
  setSelectedPositions: (positions: string[]) => void;
  setSelectedPlayers: (players: string[]) => void;
  setTargetFantasyPoints: (target: number | null) => void;
  setLineupTarget: (target: LineupTarget) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()((set) => ({
  view: 'dashboard',
  week: 'this',
  metric: 'fantasy_points',
  dataMode: 'auto',
  oddsFormat: 'american',
  selectedPlayer: null,
  selectedPositions: [],
  selectedPlayers: [],
  targetFantasyPoints: null,
  lineupTarget: 'mid',
  setView: (view) => set({ view }),
  setWeek: (week) => set({ week }),
  setMetric: (metric) => set({ metric }),
  setDataMode: (dataMode) => set({ dataMode }),
  setOddsFormat: (oddsFormat) => set({ oddsFormat }),
  selectPlayer: (selectedPlayer) => set({ selectedPlayer }),
  setSelectedPositions: (selectedPositions) => set({ selectedPositions }),
  setSelectedPlayers: (selectedPlayers) => set({ selectedPlayers }),
  setTargetFantasyPoints: (targetFantasyPoints) => set({ targetFantasyPoints }),
  setLineupTarget: (lineupTarget) => set({ lineupTarget }),
}));
