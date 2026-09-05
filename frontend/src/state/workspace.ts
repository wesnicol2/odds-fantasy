import { create } from 'zustand';

export type WorkspaceView = 'players' | 'defenses' | 'lineup';
export type WeekWindow = 'this' | 'next';
export type LineupTarget = 'floor' | 'mid' | 'ceiling';

interface WorkspaceState {
  view: WorkspaceView;
  week: WeekWindow;
  metric: string;
  selectedPlayer: string | null;
  selectedPositions: string[];
  selectedPlayers: string[];
  targetFantasyPoints: number | null;
  lineupTarget: LineupTarget;
  setView: (view: WorkspaceView) => void;
  setWeek: (week: WeekWindow) => void;
  setMetric: (metric: string) => void;
  selectPlayer: (player: string | null) => void;
  setSelectedPositions: (positions: string[]) => void;
  setSelectedPlayers: (players: string[]) => void;
  setTargetFantasyPoints: (target: number | null) => void;
  setLineupTarget: (target: LineupTarget) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()((set) => ({
  view: 'players',
  week: 'this',
  metric: 'fantasy_points',
  selectedPlayer: null,
  selectedPositions: [],
  selectedPlayers: [],
  targetFantasyPoints: null,
  lineupTarget: 'mid',
  setView: (view) => set({ view }),
  setWeek: (week) => set({ week }),
  setMetric: (metric) => set({ metric }),
  selectPlayer: (selectedPlayer) => set({ selectedPlayer }),
  setSelectedPositions: (selectedPositions) => set({ selectedPositions }),
  setSelectedPlayers: (selectedPlayers) => set({ selectedPlayers }),
  setTargetFantasyPoints: (targetFantasyPoints) => set({ targetFantasyPoints }),
  setLineupTarget: (lineupTarget) => set({ lineupTarget }),
}));
