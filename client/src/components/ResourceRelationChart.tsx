import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { CHART_EVENT_COLORS, findTimelineEventIndex, pointLabel } from '../utils';
import type { ChartMode, LiveEvent, TimelinePoint } from '../types';

export function ResourceRelationChart({ title, subtitle, points, xMetric, yMetric, mode, selector, events = [], scopeAgent = null }: { title: string; subtitle: string; points: TimelinePoint[]; xMetric: string; yMetric: string; mode: ChartMode; selector: (point: TimelinePoint) => Record<string, number> | undefined; events?: LiveEvent[]; scopeAgent?: string | null }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || !xMetric || !yMetric) {
      return;
    }
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }
    const chart = chartInstanceRef.current;
    chart.setOption(
      {
        animationDuration: 250,
        backgroundColor: 'transparent',
        tooltip: {
          trigger: 'item',
          backgroundColor: '#ffffff',
          borderColor: '#dde5ed',
          textStyle: { color: '#1d2d3a' },
        },
        grid: {
          left: 16,
          right: 16,
          top: 24,
          bottom: 32,
          containLabel: true,
        },
      },
      { notMerge: false, lazyUpdate: true },
    );
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(chartRef.current);
    return () => {
      resizeObserver.disconnect();
    };
  }, []);

  useEffect(() => {
    const chart = chartInstanceRef.current;
    if (!chart || !xMetric || !yMetric) {
      return;
    }
    let cumulativeX = 0;
    let cumulativeY = 0;
    const relationPoints = points.map((point) => {
      const values = selector(point) ?? {};
      const rawX = values[xMetric] ?? 0;
      const rawY = values[yMetric] ?? 0;
      const xValue = mode === 'cumulative' ? (cumulativeX += rawX) : rawX;
      const yValue = mode === 'cumulative' ? (cumulativeY += rawY) : rawY;
      return [xValue, yValue, pointLabel(point)];
    });

    const overlayPoints = events
      .filter((event) => ['trade', 'action', 'communication', 'kill', 'victory'].includes(event.type))
      .filter((event) => !scopeAgent || event.agent === scopeAgent || event.target === scopeAgent)
      .map((event) => {
        const index = findTimelineEventIndex(points, event);
        if (index < 0) {
          return null;
        }
        const point = points[index];
        const values = selector(point) ?? {};
        let xValue = values[xMetric] ?? 0;
        let yValue = values[yMetric] ?? 0;
        if (mode === 'cumulative') {
          xValue = (relationPoints[index]?.[0] as number) ?? xValue;
          yValue = (relationPoints[index]?.[1] as number) ?? yValue;
        }
        return {
          value: [xValue, yValue, `${event.type.toUpperCase()} · ${event.agent ?? ''}${event.target ? ` → ${event.target}` : ''}`],
          itemStyle: { color: CHART_EVENT_COLORS[event.type] ?? '#6b8194' },
        };
      })
      .filter(Boolean);

    chart.setOption(
      {
        tooltip: {
          formatter: (params: { value?: unknown[] }) => {
            const values = params.value ?? [];
            return `${xMetric}: ${values[0] ?? 0}<br/>${yMetric}: ${values[1] ?? 0}<br/>${values[2] ?? ''}`;
          },
        },
        grid: {
          left: 16,
          right: 16,
          top: 24,
          bottom: 32,
          containLabel: true,
        },
        xAxis: {
          type: 'value',
          name: xMetric,
          nameLocation: 'middle',
          nameGap: 28,
          axisLabel: { color: '#5a7085' },
          axisLine: { lineStyle: { color: '#dde5ed' } },
          splitLine: { lineStyle: { color: 'rgba(0,0,0,0.07)' } },
        },
        yAxis: {
          type: 'value',
          name: yMetric,
          nameLocation: 'middle',
          nameGap: 40,
          axisLabel: { color: '#5a7085' },
          axisLine: { lineStyle: { color: '#dde5ed' } },
          splitLine: { lineStyle: { color: 'rgba(0,0,0,0.07)' } },
        },
        series: [
          {
            name: 'path',
            type: 'line',
            data: relationPoints,
            showSymbol: false,
            lineStyle: { color: '#c7d7e6', width: 2 },
            z: 1,
          },
          {
            name: 'samples',
            type: 'scatter',
            data: relationPoints,
            symbolSize: 11,
            itemStyle: { color: '#d97731', shadowBlur: 12, shadowColor: 'rgba(217, 119, 49, 0.24)' },
            z: 2,
          },
          {
            name: 'events',
            type: 'effectScatter',
            data: overlayPoints,
            symbolSize: 14,
            rippleEffect: { scale: 2.4, brushType: 'stroke' },
            z: 3,
            tooltip: {
              formatter: (params: { value?: unknown[] }) => String(params.value?.[2] ?? 'event'),
            },
          },
        ],
      },
      { notMerge: false, lazyUpdate: true, replaceMerge: ['series'] },
    );
    chartInstanceRef.current?.resize();
  }, [events, mode, points, scopeAgent, selector, xMetric, yMetric]);

  useEffect(
    () => () => {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
    },
    [],
  );

  const hasData = points.length > 0 && xMetric && yMetric;

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Correlation</p>
          <h3>{title}</h3>
        </div>
        <p className="panel-subtitle">{subtitle}</p>
      </div>
      <div className="chart-shell">
        {!hasData ? <div className="empty-state">Select two resources to compare.</div> : null}
        <div ref={chartRef} className="chart-canvas" style={{ display: !hasData ? 'none' : undefined }} />
      </div>
    </section>
  );
}