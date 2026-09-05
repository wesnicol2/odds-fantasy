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
