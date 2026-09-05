import { useEffect, useRef } from 'react';
import type { ProbabilitySeries } from '../types';
import type { EChartsOption, EChartsType } from '../visualization/echarts';
import { echarts } from '../visualization/echarts';

interface ProbabilityChartProps {
  series: ProbabilitySeries[];
  target: number | null;
  activePlayerId: string | null;
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

export function ProbabilityChart({
  series,
  target,
  activePlayerId,
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
        name: 'Fantasy points',
        nameLocation: 'middle',
        nameGap: 36,
        axisLabel: { color: '#8a94a3' },
        axisLine: { lineStyle: { color: '#303844' } },
        splitLine: { lineStyle: { color: '#1d242d' } },
      },
      yAxis: {
        type: 'value',
        name: 'P(FP ≥ x)',
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
      series: series.map((item, index) => {
        const isActive = activePlayerId === null || item.id === activePlayerId;
        return {
          id: item.id,
          name: item.label,
          type: 'line',
          showSymbol: false,
          smooth: false,
          color: playerColor(item.id),
          lineStyle: { width: item.id === activePlayerId ? 3.5 : 2, opacity: isActive ? 1 : 0.42 },
          emphasis: { focus: 'series', lineStyle: { width: 4 } },
          data: item.points.map((point) => [point.x, point.probability]),
          ...(index === 0 && target !== null
            ? {
                markLine: {
                  symbol: 'none',
                  silent: true,
                  lineStyle: { width: 2, type: 'dashed', color: '#f1f4f7' },
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
      }),
    };

    chart.setOption(option, { notMerge: true });
  }, [series, target, activePlayerId]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const handleOver = (params: { seriesId?: string }) => onPlayerHover(params.seriesId ?? null);
    const handleOut = () => onPlayerHover(null);
    const handleClick = (params: { seriesId?: string }) => {
      if (params.seriesId) onPlayerSelect(params.seriesId);
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
    if (!chart || series.length === 0) return;
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
  }, [series.length, target, onTargetChange]);

  return (
    <div className="chart-shell">
      <div
        ref={elementRef}
        className="probability-chart"
        role="img"
        aria-label="Fantasy point survival probability comparison. Drag the target line or use the numeric target control."
      />
      {series.length === 0 ? (
        <div className="chart-empty">Select players to compare probability distributions.</div>
      ) : null}
    </div>
  );
}
