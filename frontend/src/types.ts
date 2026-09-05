export interface ProbabilityPoint {
  x: number;
  probability: number;
}

export interface ProbabilitySeries {
  id: string;
  label: string;
  points: ProbabilityPoint[];
}
