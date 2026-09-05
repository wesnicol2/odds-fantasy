export const METRIC_ORDER = [
  'fantasy_points',
  'player_pass_yds',
  'player_pass_tds',
  'player_pass_interceptions',
  'player_rush_yds',
  'player_rush_tds',
  'player_receptions',
  'player_reception_yds',
  'player_reception_tds',
  'player_anytime_td',
] as const;

const METRIC_LABELS: Record<string, string> = {
  fantasy_points: 'Fantasy points',
  player_pass_yds: 'Passing yards',
  player_pass_tds: 'Passing TDs',
  player_pass_interceptions: 'Interceptions',
  player_rush_yds: 'Rushing yards',
  player_rush_tds: 'Rushing TDs',
  player_receptions: 'Receptions',
  player_reception_yds: 'Receiving yards',
  player_reception_tds: 'Receiving TDs',
  player_anytime_td: 'Anytime TD',
};

const COUNT_METRICS = new Set([
  'player_pass_tds',
  'player_pass_interceptions',
  'player_rush_tds',
  'player_receptions',
  'player_reception_tds',
  'player_anytime_td',
]);

export function metricLabel(metric: string): string {
  return (
    METRIC_LABELS[metric] ??
    metric
      .replace(/^player_/, '')
      .replaceAll('_', ' ')
      .replace(/\b\w/g, (character) => character.toUpperCase())
  );
}

export function sortMetrics(metrics: string[]): string[] {
  return [...metrics].sort((left, right) => {
    const leftIndex = METRIC_ORDER.indexOf(left as (typeof METRIC_ORDER)[number]);
    const rightIndex = METRIC_ORDER.indexOf(right as (typeof METRIC_ORDER)[number]);
    if (leftIndex === -1 && rightIndex === -1)
      return metricLabel(left).localeCompare(metricLabel(right));
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  });
}

export function isCountMetric(metric: string): boolean {
  return COUNT_METRICS.has(metric);
}

export function sourceThresholdX(metric: string, threshold: number): number {
  if (!isCountMetric(metric)) return threshold;
  if (threshold <= 0) return 1;
  return Number.isInteger(threshold) ? threshold : Math.ceil(threshold);
}
