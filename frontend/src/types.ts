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
