export interface FantasyCurvePoint {
  x: number;
  survival: number;
}

export interface ProjectionPlayer {
  name: string;
  alias: string;
  pos: string;
  team: string | null;
  floor: number | null;
  mid: number | null;
  ceiling: number | null;
  mean: number | null;
  curve: FantasyCurvePoint[];
  books_used: number;
  markets_used: number;
  has_projection: boolean;
  locked?: boolean;
  lineup_status?: 'starter' | 'bench' | null;
  actual_points?: number | null;
}

export interface ProjectionResponse {
  week: string;
  players: ProjectionPlayer[];
  roster_positions: string[];
  started_count?: number;
  message?: string;
  error?: string;
  ratelimit?: string;
}

export interface ProbabilityPoint {
  x: number;
  probability: number;
}

export type StatGraphKind = 'continuous_density' | 'discrete_pmf' | 'threshold_gauge';

export interface ProbabilitySeries {
  id: string;
  label: string;
  points: ProbabilityPoint[];
  kind?: StatGraphKind;
}

export interface StatGraph {
  kind: StatGraphKind;
  points: ProbabilityPoint[];
}

export interface ConsensusAnchor {
  threshold: number;
  survival: number;
}

export interface SportsbookLine {
  book: string;
  source: 'main' | 'alternate';
  point: number | null;
  over_odds: number | null;
  under_odds: number | null;
}

export interface MarketDetail {
  stat_range: [number, number, number];
  stat_mean?: number;
  expected_points: number;
  graph: StatGraph;
  anchors: ConsensusAnchor[];
  lines: SportsbookLine[];
}

/** Several markets summed into one comparable quantity by the backend. */
export interface CombinedMarketDetail {
  markets: string[];
  stat_range: [number, number, number];
  stat_mean?: number;
  expected_points: number;
}

export interface PlayerOddsDetails {
  player: {
    name: string;
    pos?: string | null;
    team?: string | null;
  };
  projection: {
    floor: number;
    mid: number;
    ceiling: number;
    mean: number;
    curve: FantasyCurvePoint[];
  } | null;
  matchup?: {
    opponent: string;
    venue: 'home' | 'away';
    commence_time: string;
    game_total: number | null;
    team_spread: number | null;
    team_implied_total: number | null;
    books_used: number;
  } | null;
  markets: Record<string, MarketDetail>;
  combined_markets?: Record<string, CombinedMarketDetail>;
  message?: string;
  error?: string;
  ratelimit?: string;
}

export interface ChartEvidence {
  playerId: string;
  anchors: ConsensusAnchor[];
  lines: SportsbookLine[];
}

export interface DefenseRow {
  defense: string;
  abbr: string | null;
  opponent: string;
  game_date: string | null;
  implied_total: number | null;
  book_count: number;
  taken: boolean;
  owner: string | null;
  owned_by_current: boolean;
  floor: number | null;
  mid: number | null;
  ceiling: number | null;
}

export interface DefenseResponse {
  week: string;
  defenses: DefenseRow[];
  note?: string;
  message?: string;
  error?: string;
  ratelimit?: string;
}

export interface LineupRow {
  slot: string;
  name: string;
  pos: string;
  team: string | null;
  points: number;
  floor: number | null;
  mid: number | null;
  ceiling: number | null;
  locked?: boolean;
  actual_points?: number | null;
}

export interface BenchPressureRow {
  name: string;
  pos: string;
  team: string | null;
  points: number;
  delta_to_lineup: number;
  slot: string | null;
  displaces: string | null;
  displaces_slot: string | null;
}

export interface LockedBenchRow {
  name: string;
  pos: string | null;
  team: string | null;
  actual_points: number;
  lineup_status: 'bench';
}

export interface LineupResponse {
  week: string;
  target: 'floor' | 'mid' | 'ceiling';
  lineup: LineupRow[];
  total_points: number;
  actual_points?: number;
  remaining_projected_points?: number;
  locked_count?: number;
  decisions_remaining?: number;
  locked_bench?: LockedBenchRow[];
  bench_pressure: BenchPressureRow[];
  unmodeled_slots: string[];
  unfilled_slots: string[];
  defense_note?: string;
  error?: string;
  ratelimit?: string;
}

export interface SleeperLeagueSummary {
  league_id: string;
  name: string | null;
  status: string | null;
  season: string | null;
}

export interface UserLeaguesResponse {
  username: string;
  user_id: string;
  season: string;
  leagues: SleeperLeagueSummary[];
  error?: string;
}

export interface SleeperLeagueTeam {
  roster_id: number;
  owner_id?: string | null;
  team_name: string | null;
  display_name?: string | null;
}

export interface LeagueResolution {
  league_id: string;
  name: string | null;
  season?: string | null;
  status?: string | null;
  roster_positions: string[];
  teams: SleeperLeagueTeam[];
  error?: string;
}