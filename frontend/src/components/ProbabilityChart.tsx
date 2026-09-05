import { useEffect, useRef } from 'react';
import { sourceThresholdX } from '../analysis/metrics';
import type { ChartEvidence, ProbabilitySeries } from '../types';
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

function playerColor(id: string): string {
  let hash = 0;
  for (const character of id) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 68% 62%)`;
}

function roundedTarget(value: number): number {
  return Math.round(value * 2) / 2;
}

function playerSeriesId(seriesId?: string): string | null {
  if (!seriesId || seriesId.includes('::')) return null;
  return seriesId;
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

    const playerSeries = series.map((item, index) => {
      const isActive = activePlayerId === null || item.id === activePlayerId;
      return {
        id: item.id,
        name: item.label,
        type: 'line' as const,
        showSymbol: false,
        smooth: false,
        ...(stepCurve ? { step: 'end' as const } : {}),
        color: playerColor(item.id),
        lineStyle: {
          width: item.id === activePlayerId ? 3.5 : 2,
          opacity: isActive ? 1 : 0.42,
        },
        emphasis: { focus: 'series' as const, lineStyle: { width: 4 } },
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
          typeof value === 'number' ? `${Math.round(value * 100)}%` : String(value ?? ''),
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
        axisLabel: { color: '#8a94a3' },
        axisLine: { lineStyle: { color: '#303844' } },
        splitLine: { lineStyle: { color: '#1d242d' } },
      },
      yAxis: {
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
  }, [series, target, activePlayerId, evidence, metric, stepCurve, targetEnabled, xAxisName, yAxisName]);

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

  return (
    <div className="chart-shell">
      <div
        ref={elementRef}
        className="probability-chart"
        role="img"
        aria-label={`${xAxisName} survival probability comparison.${targetEnabled ? ' Drag the target line or use the numeric target control.' : ''}`}
      />
      {series.length === 0 ? (
        <div className="chart-empty">No selected players have data for this metric.</div>
      ) : null}
    </div>
  );
}
