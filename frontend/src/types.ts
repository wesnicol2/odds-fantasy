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
}

export interface ProjectionResponse {
  week: string;
  players: ProjectionPlayer[];
  roster_positions: string[];
  message?: string;
  error?: string;
  ratelimit?: string;
}

export interface ProbabilityPoint {
  x: number;
  probability: number;
}

export interface ProbabilitySeries {
  id: string;
  label: string;
  points: ProbabilityPoint[];
}

export interface StatGraph {
  kind: 'survival' | 'survival_step';
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
  expected_points: number;
  graph: StatGraph;
  anchors: ConsensusAnchor[];
  lines: SportsbookLine[];
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
  markets: Record<string, MarketDetail>;
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
}

export interface LineupResponse {
  week: string;
  target: 'floor' | 'mid' | 'ceiling';
  lineup: LineupRow[];
  total_points: number;
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
