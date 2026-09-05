import { useEffect, useRef } from 'react';
import type { ProbabilitySeries } from '../types';
import type { EChartsOption, EChartsType } from '../visualization/echarts';
import { echarts } from '../visualization/echarts';

interface ProbabilityChartProps {
  series: ProbabilitySeries[];
  target: number | null;
  onPlayerHover?: (playerId: string | null) => void;
}

export function ProbabilityChart({ series, target, onPlayerHover }: ProbabilityChartProps) {
  const elementRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);

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
      animationDurationUpdate: 120,
      aria: { enabled: true },
      grid: { left: 62, right: 24, top: 24, bottom: 52, containLabel: false },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value) =>
          typeof value === 'number' ? `${Math.round(value * 100)}%` : String(value ?? ''),
      },
      legend: { top: 0, textStyle: { color: '#a9b1bd' } },
      xAxis: {
        type: 'value',
        name: 'Fantasy points',
        nameLocation: 'middle',
        nameGap: 34,
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
      series: series.map((item, index) => ({
        id: item.id,
        name: item.label,
        type: 'line',
        showSymbol: false,
        smooth: false,
        emphasis: { focus: 'series' },
        data: item.points.map((point) => [point.x, point.probability]),
        ...(index === 0 && target !== null
          ? {
              markLine: {
                symbol: 'none',
                silent: true,
                label: { formatter: `Target ${target.toFixed(1)}` },
                data: [{ xAxis: target }],
              },
            }
          : {}),
      })),
    };

    chart.setOption(option, { notMerge: true });
  }, [series, target]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onPlayerHover) return;

    const handleOver = (params: { seriesId?: string }) => onPlayerHover(params.seriesId ?? null);
    const handleOut = () => onPlayerHover(null);
    chart.on('mouseover', handleOver);
    chart.on('mouseout', handleOut);

    return () => {
      chart.off('mouseover', handleOver);
      chart.off('mouseout', handleOut);
    };
  }, [onPlayerHover]);

  return (
    <div className="chart-shell">
      <div
        ref={elementRef}
        className="probability-chart"
        role="img"
        aria-label="Fantasy point survival probability comparison"
      />
      {series.length === 0 ? (
        <div className="chart-empty">Select players to compare probability distributions.</div>
      ) : null}
    </div>
  );
}
