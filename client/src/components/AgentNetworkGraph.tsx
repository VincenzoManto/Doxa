import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { AgentSummary, LiveEvent } from '../types';

export function AgentNetworkGraph({ agents, events }: { agents: AgentSummary[]; events: LiveEvent[] }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);
  const aggregateRef = useRef<{ totals: Map<string, number>; links: Map<string, { source: string; target: string; type: string; value: number }>; seenKeys: Set<string>; lastLength: number }>({ totals: new Map(), links: new Map(), seenKeys: new Set(), lastLength: 0 });

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }
    const chart = chartInstanceRef.current;
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(chartRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  useEffect(() => {
    // Lazy init fallback: if the [] init effect ran before the DOM was measured, retry here
    if (!chartInstanceRef.current && chartRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }
    const chart = chartInstanceRef.current;
    if (!chart) {
      return;
    }
    const aggregate = aggregateRef.current;
    if (events.length < aggregate.lastLength) {
      aggregate.totals = new Map();
      aggregate.links = new Map();
      aggregate.seenKeys = new Set();
      aggregate.lastLength = 0;
    }
    const newEvents = events.slice(0, Math.max(0, events.length - aggregate.lastLength));
    for (const event of newEvents) {
      if (!event.agent || !event.target || !['trade', 'communication', 'action'].includes(event.type)) {
        continue;
      }
      const uniqueKey = `${event.timestamp ?? 0}:${event.type}:${event.agent}:${event.target}:${String(event.result ?? '')}`;
      if (aggregate.seenKeys.has(uniqueKey)) {
        continue;
      }
      aggregate.seenKeys.add(uniqueKey);
      const key = `${event.agent}::${event.target}::${event.type}`;
      const current = aggregate.links.get(key);
      aggregate.links.set(key, {
        source: event.agent,
        target: event.target,
        type: event.type,
        value: (current?.value ?? 0) + 1,
      });
      aggregate.totals.set(event.agent, (aggregate.totals.get(event.agent) ?? 0) + 1);
      aggregate.totals.set(event.target, (aggregate.totals.get(event.target) ?? 0) + 1);
    }
    aggregate.lastLength = events.length;
    const nodes = agents.map((agent) => ({
      id: agent.id,
      name: agent.id,
      value: aggregate.totals.get(agent.id) ?? 0,
      symbolSize: 18 + Math.min((aggregate.totals.get(agent.id) ?? 0) * 2, 22),
      itemStyle: { color: agent.alive ? '#2060a0' : '#9a8f8f' },
    }));
    const edges = Array.from(aggregate.links.values()).map((link) => ({
      ...link,
      lineStyle: {
        color: link.type === 'trade' ? '#d97731' : link.type === 'communication' ? '#2060a0' : '#2e8b57',
        width: 1 + Math.min(link.value, 6),
        opacity: 0.82,
      },
    }));
    chart.setOption(
      {
        animationDuration: 220,
        backgroundColor: 'transparent',
        tooltip: {
          backgroundColor: '#ffffff',
          borderColor: '#dde5ed',
          textStyle: { color: '#1d2d3a' },
          formatter: (params: { data?: Record<string, unknown> }) => {
            const data = params.data ?? {};
            if (typeof data.source === 'string' && typeof data.target === 'string') {
              return `${data.source} → ${data.target}<br/>${String(data.type ?? '')}: ${String(data.value ?? 0)}`;
            }
            return `${String(data.name ?? '')}<br/>Interactions: ${String(data.value ?? 0)}`;
          },
        },
        series: [
          {
            type: 'graph',
            layout: 'circular',
            roam: true,
            animation: false,
            lineStyle: { curveness: 0.18, opacity: 0.8 },
            label: { show: true, color: '#1d2d3a', fontSize: 11 },
            edgeSymbol: ['none', 'arrow'],
            edgeSymbolSize: [0, 7],
            data: nodes,
            links: edges,
          },
        ],
      },
      { notMerge: true },
    );
    chart.resize();
  }, [agents, events]);

  useEffect(
    () => () => {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
    },
    [],
  );

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      {agents.length === 0 && (
        <div className="empty-state" style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          No agent graph available yet.
        </div>
      )}
      <div ref={chartRef} className="network-graph-canvas" />
    </div>
  );
}