import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { CHART_EVENT_COLORS, findTimelineEventIndex, pointLabel, toAgentChartSeries, toTotalBarSeries } from '../utils';
import type { ChartMode, LiveEvent, TimelinePoint } from '../types';

export function TimelineChart({ title, subtitle, points, metrics, mode, selector, viewMode = 'totals', events = [], scopeAgent = null }: { title: string; subtitle: string; points: TimelinePoint[]; metrics: string[]; mode: ChartMode; selector: (point: TimelinePoint) => Record<string, number> | undefined; viewMode?: 'totals' | 'agents'; events?: LiveEvent[]; scopeAgent?: string | null }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current) {
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
          trigger: 'axis',
          backgroundColor: '#ffffff',
          borderColor: '#dde5ed',
          textStyle: { color: '#1d2d3a' },
        },
        legend: {
          top: 4,
          textStyle: { color: '#5a7085' },
        },
        grid: {
          left: 16,
          right: 16,
          top: 54,
          bottom: 44,
          containLabel: true,
        },
        dataZoom: [
          { type: 'inside', throttle: 50 },
          { type: 'slider', height: 18, bottom: 8 },
        ],
        xAxis: {
          type: 'category',
          boundaryGap: true,
          axisLabel: { color: '#5a7085' },
          axisLine: { lineStyle: { color: '#dde5ed' } },
        },
        yAxis: [
          {
            type: 'value',
            axisLabel: { color: '#5a7085' },
            splitLine: { lineStyle: { color: 'rgba(0,0,0,0.07)' } },
          },
        ],
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
    if (!chart) {
      return;
    }
    const xAxisData = points.map(pointLabel);
    const barSeries = toTotalBarSeries(points, metrics, mode, selector);
    const series = viewMode === 'agents' ? [...barSeries, ...toAgentChartSeries(points, metrics, mode)] : barSeries;
    const previousLegend = chart.getOption()?.legend as Array<{ selected?: Record<string, boolean> }> | undefined;
    const previousLegendSelected = previousLegend?.[0]?.selected;
    chart.setOption(
      {
        legend: previousLegendSelected ? { selected: previousLegendSelected } : undefined,
        xAxis: { data: xAxisData },
        series,
      },
      { notMerge: false, lazyUpdate: true, replaceMerge: ['series'] },
    );
    // ECharts requires resize after becoming visible (display:none → visible)
    chart.resize();
  }, [metrics, mode, points, selector, viewMode]);

  useEffect(() => {
    const chart = chartInstanceRef.current;
    if (!chart) {
      return;
    }

    const existingSeries = ((chart.getOption()?.series as Array<Record<string, unknown> | null> | undefined) ?? []).filter((series): series is Record<string, unknown> => series != null && typeof series.id === 'string' && !String(series.id).startsWith('event:'));
    existingSeries.forEach((series) => {
      // Add event markers to existing series data for correct tooltip display
      series.markPoint = {
        symbol: (_value: number, params: any) => {
            const eventType = params.data?.type;
            switch (eventType) {
                case 'trade':
                    return 'circle';
                case 'communication':
                    return 'rect';
                case 'action':
                    return 'triangle';
                case 'kill':
                    return 'diamond';
                case 'victory':
                    return 'pin';
                default:
            return 'diamond'
            }
        },
        symbolSize: 14,
        data: events
          .filter((event) => ['trade', 'action', 'communication', 'kill', 'victory'].includes(event.type))
          .map((event) => {
            const index = findTimelineEventIndex(points, event);
            if (index < 0) {
              return null;
            }
            return {
              name: `${event.type.toUpperCase()} · ${event.agent ?? ''}${event.target ? ` → ${event.target}` : ''}`,
              yAxis: 0,
              xAxis: index,
              type: event.type,
              itemStyle: { color: CHART_EVENT_COLORS[event.type] ?? '#6b8194' },
            };
          })
          .filter(Boolean) as Array<Record<string, unknown>>,
      };
    });
    chart.setOption(
      {
        series: existingSeries,
      },
      { notMerge: false, lazyUpdate: true, replaceMerge: ['series'] },
    );
  }, [events, points, scopeAgent]);

  useEffect(
    () => () => {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
    },
    [],
  );

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Telemetry</p>
          <h3>{title}</h3>
        </div>
        <p className="panel-subtitle">{subtitle}</p>
      </div>
      <div className="chart-shell">
        {points.length === 0 || metrics.length === 0 ? <div className="empty-state">No timeline data available yet.</div> : null}
        <div ref={chartRef} className="chart-canvas" style={{ display: points.length === 0 || metrics.length === 0 ? 'none' : undefined }} />
      </div>
    </section>
  );
}