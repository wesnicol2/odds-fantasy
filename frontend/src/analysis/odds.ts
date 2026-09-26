export type OddsFormat = 'american' | 'decimal';

function decimalToAmerican(value: number): number | null {
  if (!Number.isFinite(value) || value <= 1) return null;
  if (value >= 2) return Math.round((value - 1) * 100);
  return Math.round(-100 / (value - 1));
}

export function formatOdds(
  value: number | null | undefined,
  format: OddsFormat = 'american',
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  if (format === 'decimal') return value > 1 ? value.toFixed(2) : '—';

  const american = decimalToAmerican(value);
  if (american === null) return '—';
  return american > 0 ? `+${american}` : String(american);
}
