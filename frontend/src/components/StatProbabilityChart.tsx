import { type CSSProperties, useEffect, useMemo, useRef } from 'react';
import { sourceThresholdX } from '../analysis/metrics';
import '../stat-probability-chart.css';
import type { ChartEvidence, ProbabilitySeries, StatGraphKind } from '../types';
import type { EChartsOption, EChartsType } from '../visualization/echarts';
import { echarts } from '../visualization/echarts';

interface StatProbabilityChartProps {
  series: ProbabilitySeries[];
  activePlayerId: string | null;
  metric: string;
  xAxisName: string;
  evidence?: ChartEvidence | null;
  onPlayerHover: (playerId: string | null) => void;
  onPlayerSelect: (playerId: string) => void;
}

function playerColor(id: string): string {
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 68% 62%)`;
}

function playerSeriesId(seriesId?: string): string | null {
  if (!seriesId || seriesId.includes('::')) return null;
  return seriesId;
}

function fallbackKind(metric: string): StatGraphKind {
  if (metric.endsWith('_yds')) return 'continuous_density';
  if (metric === 'player_receptions' || metric.endsWith('_rush_attempts')) {
    return 'discrete_pmf';
  }
  return 'threshold_gauge';
}

function seriesKind(series: ProbabilitySeries[], metric: string): StatGraphKind {
  return series.find((item) => item.kind)?.kind ?? fallbackKind(metric);
}

function formatProbability(value: number): string {
  const percent = value * 100;
  return `${percent < 10 ? percent.toFixed(1) : Math.round(percent)}%`;
}

function formatDensity(value: number): string {
  if (value === 0) return '0';
  if (value < 0.001) return value.toExponential(1);
  return value.toFixed(3);
}

function formatThreshold(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function densityQuantileX(points: ProbabilitySeries['points'], quantile: number): number | null {
  const sorted = points
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.probability))
    .slice()
    .sort((left, right) => left.x - right.x);
  if (sorted.length === 0) return null;
  if (sorted.length === 1) return sorted[0].x;

  const segments: Array<{ leftX: number; rightX: number; area: number }> = [];
  let totalArea = 0;
  for (let index = 1; index < sorted.length; index += 1) {
    const left = sorted[index - 1];
    const right = sorted[index];
    const width = right.x - left.x;
    if (width <= 0) continue;
    const area = (width * (Math.max(0, left.probability) + Math.max(0, right.probability))) / 2;
    if (area <= 0) continue;
    segments.push({ leftX: left.x, rightX: right.x, area });
    totalArea += area;
  }

  if (totalArea <= 0) return sorted[sorted.length - 1].x;
  const targetArea = totalArea * Math.max(0, Math.min(1, quantile));
  let accumulatedArea = 0;
  for (const segment of segments) {
    if (accumulatedArea + segment.area >= targetArea) {
      const fraction = (targetArea - accumulatedArea) / segment.area;
      return segment.leftX + (segment.rightX - segment.leftX) * fraction;
    }
    accumulatedArea += segment.area;
  }

  return sorted[sorted.length - 1].x;
}

function focusedDensityMax(
  series: ProbabilitySeries[],
  sourceThresholds: number[],
): number | undefined {
  const finitePoints = series.flatMap((item) =>
    item.points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.probability)),
  );
  if (finitePoints.length === 0) return undefined;

  const rawMax = Math.max(...finitePoints.map((point) => point.x));
  const meaningfulMaxes = series.flatMap((item) => {
    const points = item.points
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.probability))
      .slice()
      .sort((left, right) => left.x - right.x);
    if (points.length === 0) return [];

    const peak = Math.max(...points.map((point) => Math.max(0, point.probability)));
    if (peak <= 0) return [points[points.length - 1].x];

    const signalFloor = peak * 0.005;
    const lastSignalPoint = points
      .slice()
      .reverse()
      .find((point) => Math.max(0, point.probability) >= signalFloor);
    const signalMax = lastSignalPoint?.x ?? points[points.length - 1].x;
    const quantileMax = densityQuantileX(points, 0.99);
    return [quantileMax === null ? signalMax : Math.min(signalMax, quantileMax)];
  });

  if (meaningfulMaxes.length === 0) return rawMax;
  let focusMax = Math.max(...meaningfulMaxes);
  const nearbyThresholds = sourceThresholds.filter(
    (threshold) => Number.isFinite(threshold) && threshold >= 0 && threshold <= focusMax * 1.2,
  );
  if (nearbyThresholds.length > 0) {
    focusMax = Math.max(focusMax, ...nearbyThresholds);
  }

  const paddedMax = focusMax + Math.max(5, focusMax * 0.08);
  const roundedMax = Math.ceil(paddedMax / 10) * 10;
  return Math.min(rawMax, roundedMax);
}

interface DistributionChartProps extends StatProbabilityChartProps {
  kind: 'continuous_density' | 'discrete_pmf';
}

function DistributionChart({
  series,
  activePlayerId,
  metric,
  xAxisName,
  evidence = null,
  kind,
  onPlayerHover,
  onPlayerSelect,
}: DistributionChartProps) {
  const elementRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const sourceThresholds = useMemo(
    () =>
      evidence
        ? [
            ...new Set(
              evidence.lines
                .map((line) => line.point)
                .filter((point): point is number => point !== null)
                .map((point) => sourceThresholdX(metric, point)),
            ),
          ]
        : [],
    [evidence, metric],
  );
  const xAxisMax = useMemo(
    () => (kind === 'continuous_density' ? focusedDensityMax(series, sourceThresholds) : undefined),
    [kind, series, sourceThresholds],
  );

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    const chart = echarts.init(element, undefined, { renderer: 'canvas' });
    chartRef.current = chart;
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(element);

    return () => {
      resizeObserver.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const playerSeries = series.map((item) => {
      const isActive = activePlayerId === null || item.id === activePlayerId;
      return {
        id: item.id,
        name: item.label,
        type: 'line' as const,
        showSymbol: kind === 'discrete_pmf',
        symbolSize: kind === 'discrete_pmf' ? 6 : 0,
        smooth: kind === 'discrete_pmf' ? 0.36 : 0.24,
        color: playerColor(item.id),
        lineStyle: {
          width: item.id === activePlayerId ? 3.5 : 2,
          opacity: isActive ? 1 : 0.42,
        },
        itemStyle: { opacity: isActive ? 1 : 0.42 },
        emphasis: { focus: 'series' as const, lineStyle: { width: 4 } },
        data: item.points.map((point) => [point.x, point.probability]),
      };
    });

    const evidenceSeries = [];
    if (evidence) {
      evidenceSeries.push({
        id: `${evidence.playerId}::source-lines`,
        name: 'Sportsbook thresholds',
        type: 'scatter' as const,
        symbol: 'rect',
        symbolSize: [2, 12],
        itemStyle: { color: '#a9b1bd', opacity: 0.7 },
        data: sourceThresholds.map((threshold) => [threshold, 0]),
        silent: true,
        tooltip: { show: false },
        z: 7,
      });
    }

    const probabilityMass = kind === 'discrete_pmf';
    const option: EChartsOption = {
      animationDuration: 180,
      animationDurationUpdate: 100,
      aria: { enabled: true },
      grid: { left: 66, right: 28, top: 48, bottom: 56 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line' },
        valueFormatter: (value) => {
          if (typeof value !== 'number') return String(value ?? '');
          return probabilityMass ? formatProbability(value) : formatDensity(value);
        },
      },
      legend: {
        top: 8,
        type: 'scroll',
        textStyle: { color: '#a9b1bd' },
      },
      xAxis: {
        type: 'value',
        name: xAxisName,
        nameLocation: 'middle',
        nameGap: 36,
        ...(probabilityMass ? { minInterval: 1 } : {}),
        ...(kind === 'continuous_density'
          ? {
              min: 0,
              ...(xAxisMax === undefined ? {} : { max: xAxisMax }),
            }
          : {}),
        axisLabel: { color: '#8a94a3' },
        axisLine: { lineStyle: { color: '#303844' } },
        splitLine: { lineStyle: { color: '#1d242d' } },
      },
      yAxis: {
        type: 'value',
        name: probabilityMass ? 'P(X = x)' : 'P(x)',
        min: 0,
        axisLabel: {
          color: '#8a94a3',
          formatter: (value: number) =>
            probabilityMass ? formatProbability(value) : formatDensity(value),
        },
        axisLine: { lineStyle: { color: '#303844' } },
        splitLine: { lineStyle: { color: '#1d242d' } },
      },
      series: [...playerSeries, ...evidenceSeries],
    };

    chart.setOption(option, { notMerge: true });
  }, [activePlayerId, evidence, kind, series, sourceThresholds, xAxisMax, xAxisName]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const handleOver = (params: { seriesId?: string }) => {
      const playerId = playerSeriesId(params.seriesId);
      if (playerId) onPlayerHover(playerId);
    };
    const handleOut = () => onPlayerHover(null);
    const handleClick = (params: { seriesId?: string }) => {
      const playerId = playerSeriesId(params.seriesId);
      if (playerId) onPlayerSelect(playerId);
    };

    chart.on('mouseover', handleOver);
    chart.on('mouseout', handleOut);
    chart.on('click', handleClick);
    return () => {
      chart.off('mouseover', handleOver);
      chart.off('mouseout', handleOut);
      chart.off('click', handleClick);
    };
  }, [onPlayerHover, onPlayerSelect]);

  return (
    <div className="chart-shell">
      <div
        ref={elementRef}
        className="probability-chart"
        data-chart-kind={kind}
        data-x-axis-max={xAxisMax}
        role="img"
        aria-label={
          kind === 'discrete_pmf'
            ? `${xAxisName} exact-outcome probability comparison with smoothed lines between integer values.`
            : `${xAxisName} continuous probability density comparison focused on meaningful probability mass.`
        }
      />
      {series.length === 0 ? (
        <div className="chart-empty">No selected players have data for this metric.</div>
      ) : null}
    </div>
  );
}

function ThresholdGaugeChart({
  series,
  activePlayerId,
  xAxisName,
  onPlayerHover,
  onPlayerSelect,
}: StatProbabilityChartProps) {
  const thresholds = [
    ...new Set(series.flatMap((item) => item.points.map((point) => point.x))),
  ].sort((left, right) => left - right);

  return (
    <div className="chart-shell">
      <fieldset
        className="threshold-gauge-chart"
        data-chart-kind="threshold_gauge"
        aria-label={`${xAxisName} threshold probability comparison. Each vertical gauge shows the chance of reaching or exceeding its labeled value.`}
      >
        <div className="threshold-gauge-grid">
          {thresholds.map((threshold) => (
            <section className="threshold-gauge" key={threshold} aria-label={`${threshold}+`}>
              <h3>{formatThreshold(threshold)}+</h3>
              <div className="threshold-gauge-plot">
                <div className="threshold-gauge-scale" aria-hidden="true">
                  <span>100%</span>
                  <span>75%</span>
                  <span>50%</span>
                  <span>25%</span>
                  <span>0%</span>
                </div>
                <div className="threshold-thermometer" aria-hidden="true" />
                <div className="threshold-marker-layer">
                  {series.flatMap((item) => {
                    const point = item.points.find((candidate) => candidate.x === threshold);
                    if (!point) return [];
                    const probability = Math.max(0, Math.min(1, point.probability));
                    const color = playerColor(item.id);
                    const isActive = activePlayerId === null || item.id === activePlayerId;
                    const markerStyle = {
                      top: `${(1 - probability) * 100}%`,
                    } satisfies CSSProperties;
                    return [
                      <button
                        key={`${threshold}:${item.id}`}
                        className={`threshold-marker${isActive ? '' : ' muted'}`}
                        style={markerStyle}
                        type="button"
                        aria-label={`${item.label} ${formatThreshold(threshold)} or more: ${formatProbability(probability)}`}
                        onMouseEnter={() => onPlayerHover(item.id)}
                        onMouseLeave={() => onPlayerHover(null)}
                        onFocus={() => onPlayerHover(item.id)}
                        onBlur={() => onPlayerHover(null)}
                        onClick={() => onPlayerSelect(item.id)}
                      >
                        <span
                          className="threshold-marker-line"
                          style={{ backgroundColor: color }}
                          aria-hidden="true"
                        />
                        <span className="threshold-marker-label" style={{ color }}>
                          {item.label} <strong>{formatProbability(probability)}</strong>
                        </span>
                      </button>,
                    ];
                  })}
                </div>
              </div>
            </section>
          ))}
        </div>
        {series.length > 0 ? (
          <p className="threshold-gauge-note">Each marker is P(player ≥ threshold).</p>
        ) : null}
      </fieldset>
      {series.length === 0 ? (
        <div className="chart-empty">No selected players have data for this metric.</div>
      ) : null}
    </div>
  );
}

export function StatProbabilityChart(props: StatProbabilityChartProps) {
  const kind = seriesKind(props.series, props.metric);
  if (kind === 'threshold_gauge') return <ThresholdGaugeChart {...props} />;
  return <DistributionChart {...props} kind={kind} />;
}
