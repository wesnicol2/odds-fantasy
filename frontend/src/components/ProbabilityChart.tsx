import { useEffect, useRef } from 'react';
import { sourceThresholdX } from '../analysis/metrics';
import type { ChartEvidence, ProbabilityPoint, ProbabilitySeries } from '../types';
import type { EChartsOption, EChartsType } from '../visualization/echarts';
import { echarts } from '../visualization/echarts';

interface ProbabilityChartProps {
  series: ProbabilitySeries[];
  target: number | null;
  activePlayerId: string | null;
  metric?: string;
  xAxisName?: string;
  yAxisName?: string;
  targetEnabled?: boolean;
  stepCurve?: boolean;
  evidence?: ChartEvidence | null;
  onTargetChange: (target: number) => void;
  onPlayerHover: (playerId: string | null) => void;
  onPlayerSelect: (playerId: string) => void;
}

const FANTASY_POINT_BUCKET_WIDTH = 1;
const CENTRAL_TAIL_PROBABILITY = 0.005;
const SECONDARY_SERIES_BRIGHTNESS = 0.85;
const PLAYER_COLOR_LIGHTNESS = 62;

function playerColor(id: string, brightness = 1): string {
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  const clampedBrightness = Math.max(0, Math.min(1, brightness));
  const lightness = PLAYER_COLOR_LIGHTNESS * clampedBrightness;
  return `hsl(${hash % 360} 68% ${lightness}%)`;
}

function roundedTarget(value: number): number {
  return Math.round(value * 2) / 2;
}

function playerSeriesId(seriesId?: string): string | null {
  if (!seriesId || seriesId.includes('::')) return null;
  return seriesId;
}

function probabilityAtX(points: ProbabilityPoint[], x: number): number {
  if (points.length === 0) return 0;
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) return 0;
  if (x <= first.x) return first.probability;
  if (x > last.x) return 0;

  let low = 0;
  let high = points.length - 1;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    const point = points[mid];
    if (!point || point.x < x) low = mid + 1;
    else high = mid;
  }

  const upper = points[low];
  const lower = points[Math.max(0, low - 1)];
  if (!upper || !lower) return upper?.probability ?? 0;
  return x - lower.x <= upper.x - x ? lower.probability : upper.probability;
}

function fantasyPointMass(points: ProbabilityPoint[]): ProbabilityPoint[] {
  if (points.length === 0) return [];
  const sorted = [...points].sort((a, b) => a.x - b.x);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (!first || !last) return [];

  const width = FANTASY_POINT_BUCKET_WIDTH;
  const start = Math.floor(first.x / width) * width;
  const end = Math.ceil(last.x / width) * width;
  const output: ProbabilityPoint[] = [];

  for (let x = start; x <= end + width / 2; x += width) {
    const lowerSurvival = probabilityAtX(sorted, x - width / 2);
    const upperSurvival = probabilityAtX(sorted, x + width / 2);
    output.push({
      x: Math.round(x * 100) / 100,
      probability: Math.max(0, Math.min(1, lowerSurvival - upperSurvival)),
    });
  }
  return output;
}

function centralBounds(points: ProbabilityPoint[]): [number, number] | null {
  if (points.length === 0) return null;
  const sorted = [...points].sort((a, b) => a.x - b.x);
  const total = sorted.reduce((sum, point) => sum + Math.max(0, point.probability), 0);
  if (total <= 0) {
    const first = sorted[0];
    const last = sorted[sorted.length - 1];
    return first && last ? [first.x, last.x] : null;
  }

  const lowerCutoff = total * CENTRAL_TAIL_PROBABILITY;
  const upperCutoff = total * (1 - CENTRAL_TAIL_PROBABILITY);
  let cumulative = 0;
  let lower = sorted[0]?.x ?? 0;
  let upper = sorted[sorted.length - 1]?.x ?? lower;
  let lowerFound = false;

  for (const point of sorted) {
    cumulative += Math.max(0, point.probability);
    if (!lowerFound && cumulative >= lowerCutoff) {
      lower = point.x;
      lowerFound = true;
    }
    if (cumulative >= upperCutoff) {
      upper = point.x;
      break;
    }
  }

  return [lower, upper];
}

function combinedCentralDomain(
  series: ProbabilitySeries[],
  target: number | null,
): [number, number] | null {
  const bounds = series
    .map((item) => centralBounds(item.points))
    .filter((value): value is [number, number] => value !== null);
  if (bounds.length === 0) return null;

  let lower = Math.min(...bounds.map(([value]) => value));
  let upper = Math.max(...bounds.map(([, value]) => value));
  const span = Math.max(FANTASY_POINT_BUCKET_WIDTH, upper - lower);
  const padding = Math.max(FANTASY_POINT_BUCKET_WIDTH, span * 0.04);
  lower -= padding;
  upper += padding;

  if (target !== null) {
    lower = Math.min(lower, target - FANTASY_POINT_BUCKET_WIDTH);
    upper = Math.max(upper, target + FANTASY_POINT_BUCKET_WIDTH);
  }

  return [Math.floor(lower * 2) / 2, Math.ceil(upper * 2) / 2];
}

function formatChartProbability(value: number): string {
  const percent = value * 100;
  return `${percent < 10 ? percent.toFixed(1) : Math.round(percent)}%`;
}

export function ProbabilityChart({
  series,
  target,
  activePlayerId,
  metric = 'fantasy_points',
  xAxisName = 'Fantasy points',
  yAxisName = 'P(FP ≥ x)',
  targetEnabled = true,
  stepCurve = false,
  evidence = null,
  onTargetChange,
  onPlayerHover,
  onPlayerSelect,
}: ProbabilityChartProps) {
  const elementRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const draggingRef = useRef(false);

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

    const distributionMode = metric === 'fantasy_points';
    const displaySeries = distributionMode
      ? series.map((item) => ({ ...item, points: fantasyPointMass(item.points) }))
      : series;
    const xDomain = distributionMode ? combinedCentralDomain(displaySeries, target) : null;

    const playerSeries = displaySeries.map((item, index) => {
      const isActive = activePlayerId === null || item.id === activePlayerId;
      const brightness = isActive ? 1 : SECONDARY_SERIES_BRIGHTNESS;
      const color = playerColor(item.id, brightness);
      return {
        id: item.id,
        name: item.label,
        type: 'line' as const,
        showSymbol: false,
        smooth: distributionMode ? 0.28 : false,
        ...(stepCurve ? { step: 'end' as const } : {}),
        color,
        lineStyle: {
          width: 2.5,
          opacity: 1,
        },
        itemStyle: { color, opacity: 1 },
        emphasis: { lineStyle: { width: 4 } },
        data: item.points.map((point) => [point.x, point.probability]),
        ...(index === 0 && targetEnabled && target !== null
          ? {
              markLine: {
                symbol: 'none',
                silent: true,
                lineStyle: { width: 2, type: 'dashed' as const, color: '#f1f4f7' },
                label: {
                  color: '#f1f4f7',
                  backgroundColor: '#171c23',
                  padding: [4, 6],
                  formatter: `Target ${target.toFixed(1)}`,
                },
                data: [{ xAxis: target }],
              },
            }
          : {}),
      };
    });

    const evidenceSeries = [];
    if (evidence) {
      evidenceSeries.push({
        id: `${evidence.playerId}::anchors`,
        name: 'Consensus anchors',
        type: 'scatter' as const,
        symbol: 'diamond',
        symbolSize: 10,
        itemStyle: { color: '#f1f4f7', borderColor: '#0a0c0f', borderWidth: 1 },
        data: evidence.anchors.map((anchor) => [
          sourceThresholdX(metric, anchor.threshold),
          anchor.survival,
        ]),
        z: 8,
      });

      const sourceThresholds = [
        ...new Set(
          evidence.lines
            .map((line) => line.point)
            .filter((point): point is number => point !== null)
            .map((point) => sourceThresholdX(metric, point)),
        ),
      ];
      evidenceSeries.push({
        id: `${evidence.playerId}::source-lines`,
        name: 'Sportsbook thresholds',
        type: 'scatter' as const,
        symbol: 'rect',
        symbolSize: [2, 12],
        itemStyle: { color: '#a9b1bd', opacity: 0.65 },
        data: sourceThresholds.map((threshold) => [threshold, 0.018]),
        z: 7,
      });
    }

    const option: EChartsOption = {
      animationDuration: 180,
      animationDurationUpdate: 100,
      aria: { enabled: true },
      grid: { left: 66, right: 28, top: 48, bottom: 56 },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'line' },
        valueFormatter: (value) =>
          typeof value === 'number' ? formatChartProbability(value) : String(value ?? ''),
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
        ...(xDomain ? { min: xDomain[0], max: xDomain[1] } : {}),
        axisLabel: { color: '#8a94a3' },
        axisLine: { lineStyle: { color: '#303844' } },
        splitLine: { lineStyle: { color: '#1d242d' } },
      },
      yAxis: distributionMode
        ? {
            type: 'value',
            name: 'P(FP = x)',
            min: 0,
            axisLabel: {
              color: '#8a94a3',
              formatter: (value: number) => formatChartProbability(value),
            },
            axisLine: { lineStyle: { color: '#303844' } },
            splitLine: { lineStyle: { color: '#1d242d' } },
          }
        : {
            type: 'value',
            name: yAxisName,
            min: 0,
            max: 1,
            interval: 0.25,
            axisLabel: {
              color: '#8a94a3',
              formatter: (value: number) => `${Math.round(value * 100)}%`,
            },
            axisLine: { lineStyle: { color: '#303844' } },
            splitLine: { lineStyle: { color: '#1d242d' } },
          },
      series: [...playerSeries, ...evidenceSeries],
    };

    chart.setOption(option, { notMerge: true });
  }, [
    series,
    target,
    activePlayerId,
    evidence,
    metric,
    stepCurve,
    targetEnabled,
    xAxisName,
    yAxisName,
  ]);

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

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || series.length === 0 || !targetEnabled) return;
    const renderer = chart.getZr();

    const targetFromPointer = (offsetX: number, offsetY: number): number | null => {
      if (!chart.containPixel({ gridIndex: 0 }, [offsetX, offsetY])) return null;
      const converted = chart.convertFromPixel({ xAxisIndex: 0 }, [offsetX, offsetY]);
      if (!Array.isArray(converted)) return null;
      const value = Number(converted[0]);
      return Number.isFinite(value) ? roundedTarget(value) : null;
    };

    const handleMouseDown = (event: { offsetX: number; offsetY: number }) => {
      if (!chart.containPixel({ gridIndex: 0 }, [event.offsetX, event.offsetY])) return;
      if (target === null) {
        const nextTarget = targetFromPointer(event.offsetX, event.offsetY);
        if (nextTarget !== null) {
          draggingRef.current = true;
          onTargetChange(nextTarget);
        }
        return;
      }

      const targetPixel = chart.convertToPixel({ xAxisIndex: 0 }, target);
      const xPixel = Array.isArray(targetPixel) ? Number(targetPixel[0]) : Number(targetPixel);
      if (Number.isFinite(xPixel) && Math.abs(event.offsetX - xPixel) <= 16) {
        draggingRef.current = true;
      }
    };

    const handleMouseMove = (event: { offsetX: number; offsetY: number }) => {
      if (!draggingRef.current) return;
      const nextTarget = targetFromPointer(event.offsetX, event.offsetY);
      if (nextTarget !== null) onTargetChange(nextTarget);
    };

    const stopDragging = () => {
      draggingRef.current = false;
    };

    renderer.on('mousedown', handleMouseDown);
    renderer.on('mousemove', handleMouseMove);
    renderer.on('mouseup', stopDragging);
    renderer.on('globalout', stopDragging);

    return () => {
      renderer.off('mousedown', handleMouseDown);
      renderer.off('mousemove', handleMouseMove);
      renderer.off('mouseup', stopDragging);
      renderer.off('globalout', stopDragging);
    };
  }, [series.length, target, targetEnabled, onTargetChange]);

  const distributionMode = metric === 'fantasy_points';
  return (
    <div className="chart-shell">
      <div
        ref={elementRef}
        className="probability-chart"
        role="img"
        aria-label={
          distributionMode
            ? `${xAxisName} probability distribution in one-point score buckets.${targetEnabled ? ' Drag the target line or use the numeric target control.' : ''}`
            : `${xAxisName} survival probability comparison.${targetEnabled ? ' Drag the target line or use the numeric target control.' : ''}`
        }
      />
      {series.length === 0 ? (
        <div className="chart-empty">No selected players have data for this metric.</div>
      ) : null}
    </div>
  );
}