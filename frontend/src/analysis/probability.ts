import type { FantasyCurvePoint } from '../types';

export function probabilityAtTarget(
  curve: FantasyCurvePoint[],
  target: number | null,
): number | null {
  if (target === null || curve.length === 0) return null;

  const first = curve[0];
  const last = curve[curve.length - 1];
  if (!first || !last) return null;
  if (target <= first.x) return first.survival;
  if (target > last.x) return 0;

  let low = 0;
  let high = curve.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    const point = curve[mid];
    if (!point || point.x < target) low = mid + 1;
    else high = mid;
  }

  const upper = curve[low];
  const lower = curve[Math.max(0, low - 1)];
  if (!upper || !lower) return upper?.survival ?? null;

  // The backend supplies a dense survival curve at the Monte Carlo display resolution.
  // Use the nearest canonical point rather than inventing a smoother client-side distribution.
  return target - lower.x <= upper.x - target ? lower.survival : upper.survival;
}

export function formatProbability(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`;
}
