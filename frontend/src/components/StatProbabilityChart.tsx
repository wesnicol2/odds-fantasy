import {
  type CSSProperties,
  type KeyboardEvent,
  type Touch,
  type TouchEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type WheelEvent,
} from 'react';
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

const PLAYER_COLOR_LIGHTNESS = 62;
const MIN_AXIS_ZOOM_SPAN = 5;
const X_AXIS_ZOOM_ID = 'stat-x-axis-zoom';
const Y_AXIS_ZOOM_ID = 'stat-y-axis-zoom';

type AxisKey = 'x' | 'y';

interface ZoomRange {
  start: number;
  end: number;
}

interface PinchState {
  axis: AxisKey;
  initialDistance: number;
  initialRange: ZoomRange;
  anchor: number;
}

function playerColor(id: string): string {
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 68% ${PLAYER_COLOR_LIGHTNESS}%)`;
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
  if (sorted.length === 1) return sorted.at(0)?.x ?? null;

  const segments: Array<{ leftX: number; rightX: number; area: number }> = [];
  let totalArea = 0;
  for (let index = 1; index < sorted.length; index += 1) {
    const left = sorted[index - 1];
    const right = sorted[index];
    if (!left || !right) continue;
    const width = right.x - left.x;
    if (width <= 0) continue;
    const area = (width * (Math.max(0, left.probability) + Math.max(0, right.probability))) / 2;
    if (area <= 0) continue;
    segments.push({ leftX: left.x, rightX: right.x, area });
    totalArea += area;
  }

  if (totalArea <= 0) return sorted.at(-1)?.x ?? null;
  const targetArea = totalArea * Math.max(0, Math.min(1, quantile));
  let accumulatedArea = 0;
  for (const segment of segments) {
    if (accumulatedArea + segment.area >= targetArea) {
      const fraction = (targetArea - accumulatedArea) / segment.area;
      return segment.leftX + (segment.rightX - segment.leftX) * fraction;
    }
    accumulatedArea += segment.area;
  }

  return sorted.at(-1)?.x ?? null;
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
    const lastPoint = points.at(-1);
    if (!lastPoint) return [];

    const peak = Math.max(...points.map((point) => Math.max(0, point.probability)));
    if (peak <= 0) return [lastPoint.x];

    const signalFloor = peak * 0.005;
    const lastSignalPoint = points
      .slice()
      .reverse()
      .find((point) => Math.max(0, point.probability) >= signalFloor);
    const signalMax = lastSignalPoint?.x ?? lastPoint.x;
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

function clampUnit(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function fullZoomRange(): ZoomRange {
  return { start: 0, end: 100 };
}

function zoomedRange(range: ZoomRange, scaleFactor: number, anchor: number): ZoomRange {
  const currentSpan = Math.max(MIN_AXIS_ZOOM_SPAN, range.end - range.start);
  const nextSpan = Math.max(
    MIN_AXIS_ZOOM_SPAN,
    Math.min(100, currentSpan * Math.max(0.05, Math.min(20, scaleFactor))),
  );
  const clampedAnchor = clampUnit(anchor);
  const anchoredValue = range.start + clampedAnchor * currentSpan;
  let start = anchoredValue - clampedAnchor * nextSpan;
  let end = start + nextSpan;

  if (start < 0) {
    end -= start;
    start = 0;
  }
  if (end > 100) {
    start -= end - 100;
    end = 100;
  }

  return {
    start: Math.max(0, start),
    end: Math.min(100, end),
  };
}

function touchPair(event: TouchEvent<HTMLButtonElement>): [Touch, Touch] | null {
  const first = event.touches.item(0);
  const second = event.touches.item(1);
  return first && second ? [first, second] : null;
}

function axisTouchDistance(axis: AxisKey, first: Touch, second: Touch): number {
  return Math.abs(axis === 'x' ? first.clientX - second.clientX : first.clientY - second.clientY);
}

function axisAnchor(axis: AxisKey, clientX: number, clientY: number, rect: DOMRect): number {
  if (axis === 'x') {
    return clampUnit((clientX - rect.left) / Math.max(1, rect.width));
  }
  return clampUnit(1 - (clientY - rect.top) / Math.max(1, rect.height));
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
  const zoomRef = useRef<{ x: ZoomRange; y: ZoomRange }>({
    x: fullZoomRange(),
    y: fullZoomRange(),
  });
  const pinchRef = useRef<PinchState | null>(null);
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

  const recordZoomRange = useCallback((axis: AxisKey, range: ZoomRange) => {
    zoomRef.current[axis] = range;
    const element = elementRef.current;
    if (!element) return;
    const value = `${range.start.toFixed(2)}:${range.end.toFixed(2)}`;
    if (axis === 'x') element.dataset.xZoom = value;
    else element.dataset.yZoom = value;
  }, []);

  const applyZoomRange = (axis: AxisKey, range: ZoomRange) => {
    recordZoomRange(axis, range);
    const chart = chartRef.current;
    if (!chart) return;
    chart.dispatchAction({
      type: 'dataZoom',
      dataZoomId: axis === 'x' ? X_AXIS_ZOOM_ID : Y_AXIS_ZOOM_ID,
      start: range.start,
      end: range.end,
    });
  };

  const resetAxisZoom = (axis: AxisKey) => {
    applyZoomRange(axis, fullZoomRange());
  };

  const handleAxisTouchStart = (axis: AxisKey, event: TouchEvent<HTMLButtonElement>) => {
    const pair = touchPair(event);
    if (!pair) return;
    const [first, second] = pair;
    const distance = axisTouchDistance(axis, first, second);
    if (distance < 8) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    pinchRef.current = {
      axis,
      initialDistance: distance,
      initialRange: { ...zoomRef.current[axis] },
      anchor: axisAnchor(
        axis,
        (first.clientX + second.clientX) / 2,
        (first.clientY + second.clientY) / 2,
        rect,
      ),
    };
  };

  const handleAxisTouchMove = (axis: AxisKey, event: TouchEvent<HTMLButtonElement>) => {
    const pinch = pinchRef.current;
    if (!pinch || pinch.axis !== axis) return;
    const pair = touchPair(event);
    if (!pair) return;
    const [first, second] = pair;
    const distance = axisTouchDistance(axis, first, second);
    if (distance <= 0) return;
    event.preventDefault();
    const pinchScale = distance / pinch.initialDistance;
    applyZoomRange(axis, zoomedRange(pinch.initialRange, 1 / pinchScale, pinch.anchor));
  };

  const handleAxisTouchEnd = () => {
    pinchRef.current = null;
  };

  const handleAxisWheel = (axis: AxisKey, event: WheelEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const anchor = axisAnchor(axis, event.clientX, event.clientY, rect);
    const boundedDelta = Math.max(-2, Math.min(2, event.deltaY * 0.002));
    applyZoomRange(axis, zoomedRange(zoomRef.current[axis], Math.exp(boundedDelta), anchor));
  };

  const handleAxisKeyDown = (axis: AxisKey, event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === '+' || event.key === '=') {
      event.preventDefault();
      applyZoomRange(axis, zoomedRange(zoomRef.current[axis], 0.82, 0.5));
    } else if (event.key === '-' || event.key === '_') {
      event.preventDefault();
      applyZoomRange(axis, zoomedRange(zoomRef.current[axis], 1.22, 0.5));
    } else if (event.key === '0' || event.key === 'Escape') {
      event.preventDefault();
      resetAxisZoom(axis);
    }
  };

  useEffect(() => {
    const zoomScope = `${kind}:${metric}`;
    zoomRef.current = { x: fullZoomRange(), y: fullZoomRange() };
    pinchRef.current = null;
    recordZoomRange('x', zoomRef.current.x);
    recordZoomRange('y', zoomRef.current.y);
    if (elementRef.current) elementRef.current.dataset.zoomScope = zoomScope;
  }, [kind, metric, recordZoomRange]);

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
      const isActive = item.id === activePlayerId;
      const color = playerColor(item.id);
      return {
        id: item.id,
        name: item.label,
        type: 'line' as const,
        showSymbol: kind === 'discrete_pmf',
        symbolSize: kind === 'discrete_pmf' ? 6 : 0,
        smooth: kind === 'discrete_pmf' ? 0.36 : 0.24,
        color,
        lineStyle: {
          width: isActive ? 3.25 : 2.5,
          opacity: 1,
        },
        itemStyle: { color, opacity: 1 },
        emphasis: { lineStyle: { width: 4 } },
        z: isActive ? 5 : 3,
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
      dataZoom: [
        {
          id: X_AXIS_ZOOM_ID,
          type: 'slider',
          show: false,
          orient: 'horizontal',
          xAxisIndex: 0,
          filterMode: 'none',
          start: zoomRef.current.x.start,
          end: zoomRef.current.x.end,
        },
        {
          id: Y_AXIS_ZOOM_ID,
          type: 'slider',
          show: false,
          orient: 'vertical',
          yAxisIndex: 0,
          filterMode: 'none',
          start: zoomRef.current.y.start,
          end: zoomRef.current.y.end,
        },
      ],
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

  const yAxisLabel = kind === 'discrete_pmf' ? 'probability mass' : 'probability density';

  return (
    <div className="chart-shell">
      <div
        ref={elementRef}
        className="probability-chart"
        data-chart-kind={kind}
        data-x-axis-max={xAxisMax}
        data-x-zoom="0.00:100.00"
        data-y-zoom="0.00:100.00"
        role="img"
        aria-label={
          kind === 'discrete_pmf'
            ? `${xAxisName} exact-outcome probability comparison with smoothed lines between integer values. Pinch an axis to rescale it.`
            : `${xAxisName} continuous probability density comparison focused on meaningful probability mass. Pinch an axis to rescale it.`
        }
      />
      <button
        className="axis-zoom-zone axis-zoom-zone-x"
        type="button"
        aria-label={`Scale ${xAxisName} axis. Pinch or use the mouse wheel to zoom. Use plus or minus keys to zoom and zero to reset.`}
        title="Pinch or wheel to scale the x-axis; +/− zoom, 0 resets"
        onTouchStart={(event) => handleAxisTouchStart('x', event)}
        onTouchMove={(event) => handleAxisTouchMove('x', event)}
        onTouchEnd={handleAxisTouchEnd}
        onTouchCancel={handleAxisTouchEnd}
        onWheel={(event) => handleAxisWheel('x', event)}
        onKeyDown={(event) => handleAxisKeyDown('x', event)}
        onDoubleClick={() => resetAxisZoom('x')}
      />
      <button
        className="axis-zoom-zone axis-zoom-zone-y"
        type="button"
        aria-label={`Scale ${yAxisLabel} axis. Pinch or use the mouse wheel to zoom. Use plus or minus keys to zoom and zero to reset.`}
        title="Pinch or wheel to scale the y-axis; +/− zoom, 0 resets"
        onTouchStart={(event) => handleAxisTouchStart('y', event)}
        onTouchMove={(event) => handleAxisTouchMove('y', event)}
        onTouchEnd={handleAxisTouchEnd}
        onTouchCancel={handleAxisTouchEnd}
        onWheel={(event) => handleAxisWheel('y', event)}
        onKeyDown={(event) => handleAxisKeyDown('y', event)}
        onDoubleClick={() => resetAxisZoom('y')}
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
                    const isActive = item.id === activePlayerId;
                    const markerStyle = {
                      top: `${(1 - probability) * 100}%`,
                    } satisfies CSSProperties;
                    return [
                      <button
                        key={`${threshold}:${item.id}`}
                        className={`threshold-marker${isActive ? ' active' : ''}`}
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
