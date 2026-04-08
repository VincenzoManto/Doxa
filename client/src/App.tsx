import { startTransition, useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';
import { Activity, Archive, Download, FileCode2, Pause, Play, RotateCcw, ShieldAlert, SkipForward, Upload, X } from 'lucide-react';
import './App.css';
import { connectEvents, downloadExportZip, getAgent, getAgentMemory, getAgentTimeline, getAgents, getConfig, getEvents, getGlobalTimeline, getStatus, godmode, loadConfigPath, pauseSimulation, resetSimulation, restartSimulation, resumeSimulation, runSimulation, stepAgent, type AgentDetails, type AgentMemoryGraph, type AgentSummary, type SimulationStatus, type TimelinePoint, updateConfig, validateConfig } from './api';

type LiveEvent = {
  type: string;
  agent?: string;
  target?: string;
  text?: string;
  thought?: string;
  action?: string;
  result?: unknown;
  epoch?: number;
  step?: number;
  state?: string;
  reason?: string;
  timestamp?: number;
  give?: { resource: string; qty: number };
  take?: { resource: string; qty: number };
};

type ChartMode = 'instant' | 'cumulative';
type ConnectionState = 'connecting' | 'live' | 'reconnecting' | 'offline';

// Maximum events kept in the client ring buffer
const MAX_EVENTS = 2000;
// Maximum timeline points rendered to charts (decimate older data)
const MAX_CHART_POINTS = 1000;
// Row heights for virtual scroll (px)
const EVENT_ROW_HEIGHT = 52;
const AGENT_ROW_HEIGHT = 54;
// Number of event log rows visible without virtual scroll
const EVENT_LOG_VISIBLE_HEIGHT = 420;
const AGENT_LIST_VISIBLE_HEIGHT = 380;

// Decimate a timeline to at most maxPoints, always keeping first and last
function decimateTimeline(points: TimelinePoint[], maxPoints: number): TimelinePoint[] {
  if (points.length <= maxPoints) return points;
  const step = Math.ceil(points.length / maxPoints);
  return points.filter((_, i) => i % step === 0 || i === points.length - 1);
}

const STATUS_COLORS: Record<string, string> = {
  idle: 'status-idle',
  running: 'status-running',
  paused: 'status-paused',
  completed: 'status-completed',
  errored: 'status-errored',
};

function formatTimestamp(timestamp?: number) {
  if (!timestamp) {
    return '--:--:--';
  }
  return new Date(timestamp * 1000).toLocaleTimeString();
}

function pointLabel(point: TimelinePoint) {
  return `E${point.epoch ?? 0} · S${point.step ?? 0}`;
}

function collectMetrics(points: TimelinePoint[], selector: (point: TimelinePoint) => Record<string, number> | undefined) {
  const metricSet = new Set<string>();
  for (const point of points) {
    const values = selector(point) ?? {};
    for (const metric of Object.keys(values)) {
      metricSet.add(metric);
    }
  }
  return Array.from(metricSet).sort();
}

function toTotalBarSeries(points: TimelinePoint[], metrics: string[], mode: ChartMode, selector: (point: TimelinePoint) => Record<string, number> | undefined) {
  const accumulator: Record<string, number> = {};
  return metrics.map((metric) => ({
    id: `total:${metric}`,
    name: `${metric}`,
    type: 'bar',
    barMaxWidth: 20,
    itemStyle: { opacity: 0.55, borderRadius: [3, 3, 0, 0] },
    emphasis: { focus: 'series' },
    data: points.map((point) => {
      const raw = selector(point)?.[metric] ?? 0;
      if (mode === 'cumulative') {
        accumulator[metric] = (accumulator[metric] ?? 0) + raw;
        return accumulator[metric];
      }
      return raw;
    }),
  }));
}

function toAgentChartSeries(points: TimelinePoint[], activeResources: string[], mode: ChartMode) {
  const agentResources = new Map<string, Set<string>>();
  for (const point of points) {
    for (const [agentId, portfolio] of Object.entries((point.agents as Record<string, Record<string, number>>) ?? {})) {
      if (!agentResources.has(agentId)) agentResources.set(agentId, new Set());
      for (const resource of Object.keys(portfolio)) {
        if (activeResources.length === 0 || activeResources.includes(resource)) {
          agentResources.get(agentId)!.add(resource);
        }
      }
    }
  }
  const series: Array<Record<string, unknown>> = [];
  const accumulator: Record<string, number> = {};
  for (const [agentId, resources] of Array.from(agentResources.entries()).sort((a, b) => a[0].localeCompare(b[0]))) {
    for (const resource of Array.from(resources).sort()) {
      const key = `${agentId} \u00b7 ${resource}`;
      series.push({
        id: `agent:${key}`,
        name: key,
        type: 'line',
        smooth: true,
        showSymbol: false,
        emphasis: { focus: 'series' },
        data: points.map((point) => {
          const raw = (point.agents as Record<string, Record<string, number>> | undefined)?.[agentId]?.[resource] ?? 0;
          if (mode === 'cumulative') {
            accumulator[key] = (accumulator[key] ?? 0) + raw;
            return accumulator[key];
          }
          return raw;
        }),
      });
    }
  }
  return series;
}

const CHART_EVENT_COLORS: Record<string, string> = {
  trade: '#d97731',
  action: '#2e8b57',
  communication: '#2060a0',
  kill: '#b42318',
  victory: '#7a3fb0',
};

function findTimelineEventIndex(points: TimelinePoint[], event: LiveEvent) {
  const exactIndex = points.findIndex((point) => point.epoch === event.epoch && point.step === event.step);
  if (exactIndex >= 0) {
    return exactIndex;
  }
  if (!event.timestamp) {
    return -1;
  }
  let bestIndex = -1;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < points.length; index += 1) {
    const point = points[index];
    const distance = Math.abs((point.timestamp ?? 0) - event.timestamp);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  }
  return bestIndex;
}

function sameStatus(left: SimulationStatus | null, right: SimulationStatus) {
  if (!left) {
    return false;
  }
  return left.state === right.state && left.run_id === right.run_id && left.epoch === right.epoch && left.step === right.step && left.last_error === right.last_error && left.agent_count === right.agent_count;
}

function sameAgentSummaries(left: AgentSummary[], right: AgentSummary[]) {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((agent, index) => agent.id === right[index]?.id && agent.alive === right[index]?.alive);
}

function sameTimeline(left: TimelinePoint[], right: TimelinePoint[]) {
  if (left === right) {
    return true;
  }
  if (left.length !== right.length) {
    return false;
  }
  const lastLeft = left[left.length - 1];
  const lastRight = right[right.length - 1];
  if (!lastLeft && !lastRight) {
    return true;
  }
  return lastLeft?.timestamp === lastRight?.timestamp && lastLeft?.epoch === lastRight?.epoch && lastLeft?.step === lastRight?.step && JSON.stringify(lastLeft?.totals ?? lastLeft?.resources ?? {}) === JSON.stringify(lastRight?.totals ?? lastRight?.resources ?? {});
}

function sameEvents(left: LiveEvent[], right: LiveEvent[]) {
  if (left === right) {
    return true;
  }
  if (left.length !== right.length) {
    return false;
  }
  const leftHead = left[0];
  const rightHead = right[0];
  const leftTail = left[left.length - 1];
  const rightTail = right[right.length - 1];
  return leftHead?.timestamp === rightHead?.timestamp && leftHead?.type === rightHead?.type && leftTail?.timestamp === rightTail?.timestamp && leftTail?.type === rightTail?.type;
}

// ---------------------------------------------------------------------------
// Generic VirtualScroll — renders only the rows in the visible viewport.
// itemHeight must be fixed and include any gap/margin between items.
// ---------------------------------------------------------------------------
function VirtualScroll<T>({ items, itemHeight, visibleHeight, renderItem, className, autoScrollBottom = false }: { items: T[]; itemHeight: number; visibleHeight: number; renderItem: (item: T, index: number) => React.ReactNode; className?: string; autoScrollBottom?: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  // Auto-scroll to bottom when new items arrive (opt-in)
  useEffect(() => {
    if (!autoScrollBottom || !containerRef.current) return;
    const el = containerRef.current;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < itemHeight * 2;
    if (isAtBottom) el.scrollTop = el.scrollHeight;
  }, [items.length, autoScrollBottom, itemHeight]);

  const totalHeight = items.length * itemHeight;
  const overscan = 4;
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const endIndex = Math.min(items.length - 1, Math.ceil((scrollTop + visibleHeight) / itemHeight) + overscan);
  const visibleItems = items.slice(startIndex, endIndex + 1);

  return (
    <div ref={containerRef} className={className} style={{ height: visibleHeight, overflowY: 'auto', position: 'relative' }} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}>
      <div style={{ height: totalHeight, position: 'relative' }}>
        {visibleItems.map((item, i) => (
          <div key={startIndex + i} style={{ position: 'absolute', top: (startIndex + i) * itemHeight, left: 0, right: 0, height: itemHeight, padding: '0 0 8px 0', boxSizing: 'border-box' }}>
            {renderItem(item, startIndex + i)}
          </div>
        ))}
      </div>
    </div>
  );
}

function TimelineChart({ title, subtitle, points, metrics, mode, selector, viewMode = 'totals', events = [], scopeAgent = null }: { title: string; subtitle: string; points: TimelinePoint[]; metrics: string[]; mode: ChartMode; selector: (point: TimelinePoint) => Record<string, number> | undefined; viewMode?: 'totals' | 'agents'; events?: LiveEvent[]; scopeAgent?: string | null }) {
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

    const existingSeries = ((chart.getOption()?.series as Array<Record<string, unknown>> | undefined) ?? []).filter((series) => typeof series.id === 'string' && !String(series.id).startsWith('event:'));
    existingSeries.forEach((series) => {
      // Add event markers to existing series data for correct tooltip display
      series.markPoint = {
        symbol: (value: number, params: any) => {
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

function ResourceRelationChart({ title, subtitle, points, xMetric, yMetric, mode, selector, events = [], scopeAgent = null }: { title: string; subtitle: string; points: TimelinePoint[]; xMetric: string; yMetric: string; mode: ChartMode; selector: (point: TimelinePoint) => Record<string, number> | undefined; events?: LiveEvent[]; scopeAgent?: string | null }) {
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

function KnowledgeGraph({ graph, onSelectDoc, selectedDocId }: { graph: AgentMemoryGraph | null; onSelectDoc: (docId: string) => void; selectedDocId: string | null }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || !graph || graph.graph.nodes.length === 0) {
      return;
    }
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }
    const chart = chartInstanceRef.current;
    chart.setOption(
      {
        animationDuration: 300,
        backgroundColor: 'transparent',
        tooltip: {
          backgroundColor: '#ffffff',
          borderColor: '#dde5ed',
          textStyle: { color: '#1d2d3a' },
          formatter: (params: { data?: Record<string, unknown> }) => {
            const data = params.data ?? {};
            const preview = typeof data.preview === 'string' ? data.preview : '';
            const tokens = Array.isArray(data.tokens) ? data.tokens.join(', ') : '';
            return `${String(data.name ?? '')}${preview ? `<br/>${preview}` : ''}${tokens ? `<br/><span style="color:#6b8194">${tokens}</span>` : ''}`;
          },
        },
        series: [
          {
            type: 'graph',
            layout: 'force',
            roam: true,
            draggable: true,
            force: { repulsion: 180, edgeLength: [70, 130] },
            label: { show: true, color: '#1d2d3a', fontSize: 11 },
            lineStyle: { color: '#cbd7e3', opacity: 0.8, width: 1.2 },
            categories: [{ name: 'agent' }, { name: 'memory' }],
            data: graph.graph.nodes.map((node) => {
              const category = node.category === 'agent' ? 0 : 1;
              return {
                ...node,
                category,
                itemStyle: {
                  color: category === 0 ? '#2060a0' : '#d97731',
                  borderColor: selectedDocId === node.id ? '#1d2d3a' : '#ffffff',
                  borderWidth: selectedDocId === node.id ? 3 : 1,
                },
              };
            }),
            links: graph.graph.edges,
          },
        ],
      },
      { notMerge: false, lazyUpdate: true, replaceMerge: ['series'] },
    );
    chart.off('click');
    chart.on('click', (params) => {
      const data = (params.data ?? null) as Record<string, unknown> | null;
      const nodeId = typeof data?.id === 'string' ? data.id : null;
      const category = data?.category;
      if (nodeId && category !== 0) {
        onSelectDoc(nodeId);
      }
    });
    const resizeObserver = new ResizeObserver(() => chart.resize());
    resizeObserver.observe(chartRef.current);
    return () => {
      resizeObserver.disconnect();
    };
  }, [graph, onSelectDoc, selectedDocId]);

  useEffect(
    () => () => {
      chartInstanceRef.current?.dispose();
      chartInstanceRef.current = null;
    },
    [],
  );

  const isEmpty = !graph || graph.stats.documents === 0;

  return (
    <>
      {isEmpty ? <div className="empty-state">No ChromaDB knowledge stored for this agent.</div> : null}
      <div ref={chartRef} className="kb-graph-canvas" style={{ display: isEmpty ? 'none' : undefined }} />
    </>
  );
}

function AgentNetworkGraph({ agents, events }: { agents: AgentSummary[]; events: LiveEvent[] }) {
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

function EventBody({ event }: { event: LiveEvent }) {
  if (event.type === 'trade') {
    const g = event.give;
    const t = event.take;
    const ok = String(event.result ?? '').startsWith('SUCCESS');
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        <span className="log-arrow"> → </span>
        <strong className="log-target">{event.target}</strong>
        {g && t && (
          <span className="log-detail">
            {': '}
            <span className="log-give">
              {g.qty}×{g.resource}
            </span>
            <span className="log-swap"> ⇄ </span>
            <span className="log-take">
              {t.qty}×{t.resource}
            </span>
          </span>
        )}
        <span className={ok ? 'log-result-ok' : 'log-result-fail'}> — {String(event.result ?? '')}</span>
      </span>
    );
  }
  if (event.type === 'communication') {
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        <span className="log-arrow"> → </span>
        <strong className="log-target">{event.target ?? 'ALL'}</strong>
        <span className="log-message">: “{event.text}”</span>
      </span>
    );
  }
  if (event.type === 'action') {
    const hasTarget = event.target && event.target !== 'undefined' && event.target !== 'null';
    const ok = String(event.result ?? '').startsWith('SUCCESS');
    const actionName = event.action ?? '';
    const isTradeAction = /trade/i.test(actionName);
    const trdMatch = isTradeAction ? String(event.result ?? '').match(/TRD_\d+/) : null;
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        {hasTarget && (
          <>
            <span className="log-arrow"> → </span>
            <strong className="log-target">{event.target}</strong>
          </>
        )}
        <span className="log-action"> [{event.action}]</span>
        {trdMatch && <span className="log-trade-id"> {trdMatch[0]}</span>}
        {event.result !== undefined && <span className={ok ? 'log-result-ok' : 'log-result-fail'}> — {String(event.result)}</span>}
      </span>
    );
  }
  if (event.type === 'think') {
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        <span className="log-think"> thinks </span>
        <em className="log-message">“{event.thought}”</em>
      </span>
    );
  }
  if (event.type === 'kill') {
    return (
      <span className="log-body">
        <strong className="log-actor">{event.agent}</strong>
        <span className="log-kill"> eliminated</span>
        {event.reason && <span> — {event.reason}</span>}
      </span>
    );
  }
  if (event.type === 'victory') {
    return <span className="log-body log-victory">{event.text}</span>;
  }
  if (event.type === 'epoch') {
    return <span className="log-body log-epoch">Epoch {event.epoch} started</span>;
  }
  if (event.type === 'step') {
    return <span className="log-body log-muted">Global step {event.step}</span>;
  }
  return <span className="log-body log-muted">{event.text ?? JSON.stringify(event)}</span>;
}

function EventLine({ event }: { event: LiveEvent }) {
  return (
    <div className="log-row">
      <span className="log-time">{formatTimestamp(event.timestamp)}</span>
      <span className={`log-type log-type-${event.type}`}>{event.type}</span>
      <EventBody event={event} />
    </div>
  );
}

export default function App() {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([]);
  const [scatterXMetric, setScatterXMetric] = useState('');
  const [scatterYMetric, setScatterYMetric] = useState('');
  const [agentScatterXMetric, setAgentScatterXMetric] = useState('');
  const [agentScatterYMetric, setAgentScatterYMetric] = useState('');
  const [chartMode, setChartMode] = useState<ChartMode>('instant');
  const [chartViewMode, setChartViewMode] = useState<'totals' | 'agents'>('totals');
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedAgentDetails, setSelectedAgentDetails] = useState<AgentDetails | null>(null);
  const [selectedAgentTimeline, setSelectedAgentTimeline] = useState<TimelinePoint[]>([]);
  const [selectedAgentMemory, setSelectedAgentMemory] = useState<AgentMemoryGraph | null>(null);
  const [kbQuery, setKbQuery] = useState('');
  const [selectedKbDocId, setSelectedKbDocId] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState('');
  const [yamlText, setYamlText] = useState('');
  const [yamlSource, setYamlSource] = useState('runtime');
  const [yamlPath, setYamlPath] = useState('hormuz.yaml');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [gmAction, setGmAction] = useState('inject_resource');
  const [gmParams, setGmParams] = useState('{"agent":"player_1","resource":"gold","amount":5}');
  const reconnectTimerRef = useRef<number | null>(null);
  const refreshTimerRef = useRef<number | null>(null);

  // Event types that warrant a REST re-fetch of timeline/status after they arrive
  const REFRESH_ON_TYPES = new Set(['step', 'kill', 'epoch', 'victory', 'manual_step', 'reset', 'config', 'godmode']);

  const metrics = useMemo(() => collectMetrics(timeline, (point) => point.totals), [timeline]);
  const agentMetrics = useMemo(() => collectMetrics(selectedAgentTimeline, (point) => point.resources), [selectedAgentTimeline]);

  useEffect(() => {
    if (metrics.length > 0 && selectedMetrics.length === 0) {
      setSelectedMetrics(metrics.slice(0, Math.min(metrics.length, 4)));
    }
  }, [metrics, selectedMetrics.length]);

  useEffect(() => {
    if (metrics.length > 0 && !scatterXMetric) {
      setScatterXMetric(metrics[0]);
    }
    if (metrics.length > 1 && !scatterYMetric) {
      setScatterYMetric(metrics[1]);
    } else if (metrics.length === 1 && !scatterYMetric) {
      setScatterYMetric(metrics[0]);
    }
  }, [metrics, scatterXMetric, scatterYMetric]);

  useEffect(() => {
    if (agentMetrics.length > 0 && !agentScatterXMetric) {
      setAgentScatterXMetric(agentMetrics[0]);
    }
    if (agentMetrics.length > 1 && !agentScatterYMetric) {
      setAgentScatterYMetric(agentMetrics[1]);
    } else if (agentMetrics.length === 1 && !agentScatterYMetric) {
      setAgentScatterYMetric(agentMetrics[0]);
    }
  }, [agentMetrics, agentScatterXMetric, agentScatterYMetric]);

  const filteredKbDocs = useMemo(() => {
    const docs = selectedAgentMemory?.docs ?? [];
    const query = kbQuery.trim().toLowerCase();
    if (!query) {
      return docs;
    }
    return docs.filter((doc) => [doc.id, doc.content, doc.preview, ...doc.tokens].join(' ').toLowerCase().includes(query));
  }, [kbQuery, selectedAgentMemory]);

  // Filtered agent list for the sidebar
  const filteredAgents = useMemo(() => {
    const q = agentFilter.trim().toLowerCase();
    if (!q) return agents;
    return agents.filter((a) => a.id.toLowerCase().includes(q));
  }, [agents, agentFilter]);

  // Decimated timeline for chart rendering performance
  const chartTimeline = useMemo(() => decimateTimeline(timeline, MAX_CHART_POINTS), [timeline]);
  const chartAgentTimeline = useMemo(() => decimateTimeline(selectedAgentTimeline, MAX_CHART_POINTS), [selectedAgentTimeline]);

  // Events for charts (exclude high-frequency events that don't overlay usefully)
  const chartEvents = useMemo(() => events.filter((e) => ['trade', 'action', 'communication', 'kill', 'victory'].includes(e.type)), [events]);

  const filteredKbGraph = useMemo(() => {
    if (!selectedAgentMemory) {
      return null;
    }
    const allowedDocIds = new Set(filteredKbDocs.map((doc) => doc.id));
    return {
      ...selectedAgentMemory,
      docs: filteredKbDocs,
      graph: {
        nodes: selectedAgentMemory.graph.nodes.filter((node) => {
          const nodeId = typeof node.id === 'string' ? node.id : '';
          const category = node.category;
          return category === 'agent' || allowedDocIds.has(nodeId);
        }),
        edges: selectedAgentMemory.graph.edges.filter((edge) => {
          const source = typeof edge.source === 'string' ? edge.source : '';
          const target = typeof edge.target === 'string' ? edge.target : '';
          return source === selectedAgentMemory.agent || target === selectedAgentMemory.agent || (allowedDocIds.has(source) && allowedDocIds.has(target));
        }),
      },
      stats: {
        documents: filteredKbDocs.length,
        links: selectedAgentMemory.graph.edges.filter((edge) => {
          const source = typeof edge.source === 'string' ? edge.source : '';
          const target = typeof edge.target === 'string' ? edge.target : '';
          return source === selectedAgentMemory.agent || target === selectedAgentMemory.agent || (allowedDocIds.has(source) && allowedDocIds.has(target));
        }).length,
      },
    };
  }, [filteredKbDocs, selectedAgentMemory]);

  const selectedKbDoc = useMemo(() => filteredKbDocs.find((doc) => doc.id === selectedKbDocId) ?? filteredKbDocs[0] ?? null, [filteredKbDocs, selectedKbDocId]);

  async function refreshStatusAndTimeline() {
    const [nextStatus, nextAgents, nextTimeline] = await Promise.all([getStatus(), getAgents(), getGlobalTimeline()]);
    setStatus((current) => (sameStatus(current, nextStatus) ? current : nextStatus));
    setAgents((current) => (sameAgentSummaries(current, nextAgents) ? current : nextAgents));
    setTimeline((current) => (sameTimeline(current, nextTimeline) ? current : nextTimeline));
  }

  async function refreshEvents() {
    const nextEvents = await getEvents(400);
    const normalized = nextEvents.slice().reverse();
    setEvents((current) => (sameEvents(current, normalized) ? current : normalized));
  }

  async function refreshConfig() {
    const config = await getConfig();
    setYamlText(config.yaml_text);
    setYamlSource(`${config.source.kind}: ${config.source.value}`);
  }

  async function refreshAgent(agentId: string) {
    const [details, agentTimeline, memory] = await Promise.all([getAgent(agentId), getAgentTimeline(agentId), getAgentMemory(agentId)]);
    setSelectedAgentDetails((current) => (JSON.stringify(current) === JSON.stringify(details) ? current : details));
    setSelectedAgentTimeline((current) => (sameTimeline(current, agentTimeline) ? current : agentTimeline));
    setSelectedAgentMemory((current) => (JSON.stringify(current) === JSON.stringify(memory) ? current : memory));
  }

  async function bootstrap() {
    try {
      setError(null);
      await Promise.all([refreshStatusAndTimeline(), refreshEvents(), refreshConfig()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Failed to load dashboard');
    }
  }

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!selectedAgent) {
      setSelectedAgentDetails(null);
      setSelectedAgentTimeline([]);
      setSelectedAgentMemory(null);
      setKbQuery('');
      setSelectedKbDocId(null);
      return;
    }
    setKbQuery('');
    setSelectedKbDocId(null);
    void refreshAgent(selectedAgent);
  }, [selectedAgent]);

  useEffect(() => {
    let isDisposed = false;
    let pingTimer: number | null = null;
    let ws: WebSocket | null = null;

    const handleWsMessage = (event: LiveEvent) => {
      const normalizedEvent: LiveEvent = {
        ...event,
        timestamp: event.timestamp ?? Date.now() / 1000,
      };

      // Debounced REST re-fetch after meaningful state-changing events
      const scheduleRefresh = () => {
        if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = window.setTimeout(() => {
          void refreshStatusAndTimeline();
          if (selectedAgent) void refreshAgent(selectedAgent);
        }, 200);
      };

      // Full snapshot emitted after every step/kill/reset by the server
      if (normalizedEvent.type === 'snapshot') {
        const snap = normalizedEvent as LiveEvent & {
          totals?: Record<string, number>;
          agents?: Record<string, Record<string, number>>;
          agents_alive?: Array<{ id: string; alive: boolean }>;
          status?: SimulationStatus;
          epoch?: number;
          step?: number;
          run_id?: string;
          reason?: string;
        };
        // Append to timeline
        const newPoint: TimelinePoint = {
          timestamp: snap.timestamp ?? Date.now() / 1000,
          run_id: snap.run_id ?? null,
          epoch: snap.epoch ?? 0,
          step: snap.step ?? 0,
          state: snap.state ?? '',
          reason: snap.reason ?? '',
          totals: snap.totals ?? {},
          agents: snap.agents ?? {},
        };
        setTimeline((prev) => {
          const updated = [...prev, newPoint];
          return updated.length > MAX_CHART_POINTS * 2 ? updated.slice(-MAX_CHART_POINTS * 2) : updated;
        });
        // Update agents list if provided
        if (snap.agents_alive) {
          const nextAgents = snap.agents_alive;
          setAgents((current) => (sameAgentSummaries(current, nextAgents) ? current : nextAgents));
        }
        // Update status if provided
        if (snap.status) {
          const nextStatus = snap.status;
          setStatus((current) => (sameStatus(current, nextStatus) ? current : nextStatus));
        }
        // Don't push snapshots to the event log
        return;
      }

      // Status change (run/pause/resume/restart/reset confirmation from server)
      if (normalizedEvent.type === 'status' || normalizedEvent.type === 'reset') {
        const embedded = normalizedEvent as LiveEvent & SimulationStatus;
        if (embedded.state) {
          setStatus((current) => (sameStatus(current, embedded) ? current : embedded));
        }
        // Reset clears the accumulated timeline
        if (normalizedEvent.type === 'reset') {
          setTimeline([]);
          setAgents([]);
        }
      }

      // Push to event ring buffer (newest first, capped)
      startTransition(() => {
        setEvents((previous) => [normalizedEvent, ...previous].slice(0, MAX_EVENTS));
      });

      // Trigger a REST refresh after key events so timeline/status stay in sync
      if (REFRESH_ON_TYPES.has(normalizedEvent.type)) {
        scheduleRefresh();
      }
    };

    const connect = () => {
      setConnectionState((current) => (current === 'live' ? current : 'connecting'));
      ws = connectEvents(handleWsMessage);
      ws.onopen = () => {
        setConnectionState('live');
        pingTimer = window.setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 12000);
        // Reconcile missed events after reconnect
        void bootstrap();
      };
      ws.onclose = () => {
        if (pingTimer !== null) {
          window.clearInterval(pingTimer);
        }
        if (!isDisposed) {
          setConnectionState('reconnecting');
          reconnectTimerRef.current = window.setTimeout(connect, 1200);
        }
      };
      ws.onerror = () => {
        setConnectionState('offline');
      };
    };

    connect();

    return () => {
      isDisposed = true;
      if (pingTimer !== null) {
        window.clearInterval(pingTimer);
      }
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current);
      }
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      ws?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAgent]);

  async function runAction(label: string, action: () => Promise<unknown>) {
    try {
      setBusyAction(label);
      setError(null);
      setFeedback(null);
      await action();
      await refreshStatusAndTimeline();
      if (selectedAgent) {
        await refreshAgent(selectedAgent);
      }
      setFeedback(`${label} completed`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${label} failed`);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleExport() {
    try {
      setBusyAction('export');
      const blob = await downloadExportZip();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'doxa-export.zip';
      link.click();
      URL.revokeObjectURL(url);
      setFeedback('ZIP export downloaded');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Export failed');
    } finally {
      setBusyAction(null);
    }
  }

  async function handleValidateYaml() {
    try {
      setBusyAction('validate');
      await validateConfig(yamlText);
      setFeedback('YAML is valid');
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'YAML validation failed');
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSaveYaml() {
    await runAction('save config', async () => {
      const config = await updateConfig(yamlText);
      setYamlSource(`${config.source.kind}: ${config.source.value}`);
    });
  }

  async function handleLoadPath() {
    await runAction('load config', async () => {
      const config = await loadConfigPath(yamlPath);
      setYamlText(config.yaml_text);
      setYamlSource(`${config.source.kind}: ${config.source.value}`);
    });
  }

  async function handleGodmode() {
    try {
      setBusyAction('godmode');
      const params = JSON.parse(gmParams) as Record<string, unknown>;
      await godmode({ action: gmAction, params });
      await refreshStatusAndTimeline();
      setFeedback('Godmode command applied');
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Godmode failed');
    } finally {
      setBusyAction(null);
    }
  }

  const controlButtons = [
    {
      label: 'Run',
      icon: Play,
      enabled: status?.available_actions.can_run ?? false,
      action: () => runAction('run', runSimulation),
    },
    {
      label: 'Pause',
      icon: Pause,
      enabled: status?.available_actions.can_pause ?? false,
      action: () => runAction('pause', pauseSimulation),
    },
    {
      label: 'Resume',
      icon: Play,
      enabled: status?.available_actions.can_resume ?? false,
      action: () => runAction('resume', resumeSimulation),
    },
    {
      label: 'Restart',
      icon: RotateCcw,
      enabled: status?.available_actions.can_restart ?? false,
      action: () => runAction('restart', restartSimulation),
    },
    {
      label: 'Reset',
      icon: Archive,
      enabled: status?.available_actions.can_reset ?? false,
      action: () => runAction('reset', resetSimulation),
    },
    {
      label: 'Step',
      icon: SkipForward,
      enabled: status?.available_actions.can_step ?? false,
      action: () => runAction('step', () => stepAgent(selectedAgent ?? undefined)),
    },
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <p className="eyebrow">Doxa orchestration</p>
          <h1>Doxa Panel</h1>
          <p className="muted">Realtime run control, YAML editing, telemetry and export.</p>
        </div>

        <section className="panel compact-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Runtime</p>
              <h3>Session status</h3>
            </div>
            <span className={`status-pill ${STATUS_COLORS[status?.state ?? 'idle']}`}>{status?.state ?? 'loading'}</span>
          </div>
          <div className="meta-grid">
            <div>
              <span>Connection</span>
              <strong>{connectionState}</strong>
            </div>
            <div>
              <span>Run</span>
              <strong>{status?.run_id ?? 'n/a'}</strong>
            </div>
            <div>
              <span>Epoch</span>
              <strong>{status?.epoch ?? 0}</strong>
            </div>
            <div>
              <span>Step</span>
              <strong>{status?.step ?? 0}</strong>
            </div>
          </div>
        </section>

        <section className="panel compact-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Controls</p>
              <h3>Execution</h3>
            </div>
          </div>
          <div className="button-grid">
            {controlButtons.map(({ label, icon: Icon, enabled, action }) => (
              <button key={label} type="button" className="control-button" disabled={!enabled || busyAction !== null} onClick={() => void action()}>
                <Icon size={15} />
                <span>{label}</span>
              </button>
            ))}
          </div>
          <button type="button" className="export-button" disabled={busyAction !== null} onClick={() => void handleExport()}>
            <Download size={15} />
            Export ZIP
          </button>
        </section>

        <section className="panel compact-panel agent-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Entities</p>
              <h3>Agents</h3>
            </div>
            <span className="agent-count">
              {filteredAgents.length}
              {filteredAgents.length !== agents.length ? `/${agents.length}` : ''}
            </span>
          </div>
          {agents.length > 10 && <input className="agent-filter-input" placeholder="Filter agents…" value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} />}
          <VirtualScroll
            items={filteredAgents}
            itemHeight={AGENT_ROW_HEIGHT}
            visibleHeight={AGENT_LIST_VISIBLE_HEIGHT}
            className="agent-list-virtual"
            renderItem={(agent) => (
              <button key={agent.id} type="button" className={`agent-row${selectedAgent === agent.id ? ' agent-row-selected' : ''}${agent.alive ? '' : ' agent-row-dead'}`} onClick={() => setSelectedAgent(agent.id)}>
                <span className="agent-row-label">{agent.id}</span>
                <span className={`agent-tag${agent.alive ? '' : ' agent-tag-dead'}`}>{agent.alive ? 'inspect' : 'killed'}</span>
              </button>
            )}
          />
        </section>
      </aside>

      <main className="main-content">
        <header className="hero-header">
          <div>
            <p className="eyebrow">Live telemetry</p>
            <h2>Global resource timeline</h2>
          </div>
          <div className="hero-actions">
            <div className="mode-toggle">
              <button type="button" className={chartViewMode === 'totals' ? 'mode-button mode-button-active' : 'mode-button'} onClick={() => setChartViewMode('totals')}>
                Totals
              </button>
              <button type="button" className={chartViewMode === 'agents' ? 'mode-button mode-button-active' : 'mode-button'} onClick={() => setChartViewMode('agents')}>
                Per agent
              </button>
            </div>
            <div className="mode-toggle">
              <button type="button" className={chartMode === 'instant' ? 'mode-button mode-button-active' : 'mode-button'} onClick={() => setChartMode('instant')}>
                Instant
              </button>
              <button type="button" className={chartMode === 'cumulative' ? 'mode-button mode-button-active' : 'mode-button'} onClick={() => setChartMode('cumulative')}>
                Cumulative
              </button>
            </div>
          </div>
        </header>

        <div className="top-grid">
          <TimelineChart title="Global timeline" subtitle="Zoomable multi-metric trend derived from backend snapshots." points={chartTimeline} metrics={selectedMetrics} mode={chartMode} selector={(point) => point.totals} viewMode={chartViewMode} events={chartEvents} />

          <section className="panel compact-panel metric-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Metrics</p>
                <h3>Visible resources</h3>
              </div>
            </div>
            <div className="metric-list">
              {metrics.length === 0 ? (
                <div className="empty-state">No metrics captured yet.</div>
              ) : (
                metrics.map((metric) => {
                  const checked = selectedMetrics.includes(metric);
                  return (
                    <label key={metric} className="metric-chip">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => {
                          setSelectedMetrics((current) => {
                            if (event.target.checked) {
                              return [...current, metric];
                            }
                            return current.filter((item) => item !== metric);
                          });
                        }}
                      />
                      <span>{metric}</span>
                    </label>
                  );
                })
              )}
            </div>
          </section>
        </div>

        {/* <section className="relation-wrapper">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Resource relation</p>
              <h3>Resource vs resource</h3>
            </div>
            <div className="relation-controls">
              <select className="field-select relation-select" value={scatterXMetric} onChange={(event) => setScatterXMetric(event.target.value)}>
                {metrics.map((metric) => <option key={`x-${metric}`} value={metric}>{metric} on X</option>)}
              </select>
              <select className="field-select relation-select" value={scatterYMetric} onChange={(event) => setScatterYMetric(event.target.value)}>
                {metrics.map((metric) => <option key={`y-${metric}`} value={metric}>{metric} on Y</option>)}
              </select>
            </div>
          </div>
          <ResourceRelationChart
            title="Global resource relation"
            subtitle="Trajectory of one resource against another across snapshots."
            points={chartTimeline}
            xMetric={scatterXMetric}
            yMetric={scatterYMetric}
            mode={chartMode}
            selector={(point) => point.totals}
            events={chartEvents}
          />
        </section> */}

        <section className="panel chart-panel network-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Interaction graph</p>
              <h3>Agent network</h3>
            </div>
            <p className="panel-subtitle">Edges aggregate trades, communications and actions in realtime.</p>
          </div>
          <AgentNetworkGraph agents={agents} events={events} />
        </section>

        <div className="bottom-grid">
          <section className="panel log-panel">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Realtime stream</p>
                <h3>Events and logs</h3>
              </div>
              <Activity size={16} className="header-icon" />
            </div>
            {events.length === 0 ? (
              <div className="empty-state" style={{ padding: '24px' }}>
                No events yet.
              </div>
            ) : (
              <VirtualScroll items={events.filter((e) => e.type !== 'turn')} itemHeight={EVENT_ROW_HEIGHT} visibleHeight={EVENT_LOG_VISIBLE_HEIGHT} className="log-list-virtual" renderItem={(event, index) => <EventLine key={`${event.timestamp ?? index}-${index}`} event={event} />} />
            )}
          </section>

          <div className="side-stack">
            <section className="panel yaml-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Config</p>
                  <h3>YAML runtime source</h3>
                </div>
                <FileCode2 size={16} className="header-icon" />
              </div>
              <p className="panel-subtitle">Active source: {yamlSource}</p>
              <textarea className="yaml-editor" value={yamlText} onChange={(event) => setYamlText(event.target.value)} spellCheck={false} />
              <div className="inline-actions">
                <button type="button" className="secondary-button" disabled={busyAction !== null} onClick={() => void handleValidateYaml()}>
                  Validate
                </button>
                <button type="button" className="primary-button" disabled={busyAction !== null} onClick={() => void handleSaveYaml()}>
                  Save runtime YAML
                </button>
              </div>
              <div className="path-row">
                <input value={yamlPath} onChange={(event) => setYamlPath(event.target.value)} placeholder="Load from file path" />
                <button type="button" className="secondary-button" disabled={busyAction !== null} onClick={() => void handleLoadPath()}>
                  <Upload size={14} />
                  Load path
                </button>
              </div>
            </section>

            <section className="panel compact-panel">
              <div className="panel-header">
                <div>
                  <p className="eyebrow">Godmode</p>
                  <h3>Live interventions</h3>
                </div>
                <ShieldAlert size={16} className="header-icon danger-icon" />
              </div>
              <select value={gmAction} onChange={(event) => setGmAction(event.target.value)} className="field-select">
                <option value="inject_resource">inject_resource</option>
                <option value="set_portfolio">set_portfolio</option>
                <option value="set_constraint">set_constraint</option>
                <option value="send_message">send_message</option>
                <option value="impersonate_action">impersonate_action</option>
              </select>
              <textarea className="json-editor" value={gmParams} onChange={(event) => setGmParams(event.target.value)} spellCheck={false} />
              <button type="button" className="danger-button" disabled={busyAction !== null} onClick={() => void handleGodmode()}>
                Apply intervention
              </button>
            </section>

            {(feedback || error || status?.last_error) && (
              <section className="panel compact-panel status-panel">
                {feedback && <p className="feedback-ok">{feedback}</p>}
                {error && <p className="feedback-error">{error}</p>}
                {status?.last_error && <p className="feedback-error">Engine error: {status.last_error}</p>}
              </section>
            )}
          </div>
        </div>
      </main>

      {selectedAgent && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <div className="modal-header">
              <div>
                <p className="eyebrow">Agent modal</p>
                <h3>{selectedAgent}</h3>
                {selectedAgentDetails && <p className={`agent-modal-status${selectedAgentDetails.alive ? '' : ' agent-modal-status-dead'}`}>{selectedAgentDetails.alive ? 'Alive' : `Killed${selectedAgentDetails.death_reason ? ` · ${selectedAgentDetails.death_reason}` : ''}`}</p>}
              </div>
              <button type="button" className="icon-button" onClick={() => setSelectedAgent(null)}>
                <X size={18} />
              </button>
            </div>
            <div className="modal-grid">
              <div className="modal-column">
                <TimelineChart title={`${selectedAgent} timeline`} subtitle="Per-resource temporal chart for the selected agent." points={chartAgentTimeline} metrics={agentMetrics} mode={chartMode} selector={(point) => point.resources} events={chartEvents} scopeAgent={selectedAgent} />
                <section className="panel compact-panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Agent relation</p>
                      <h3>Resource vs resource</h3>
                    </div>
                    <div className="relation-controls">
                      <select className="field-select relation-select" value={agentScatterXMetric} onChange={(event) => setAgentScatterXMetric(event.target.value)}>
                        {agentMetrics.map((metric) => (
                          <option key={`agent-x-${metric}`} value={metric}>
                            {metric} on X
                          </option>
                        ))}
                      </select>
                      <select className="field-select relation-select" value={agentScatterYMetric} onChange={(event) => setAgentScatterYMetric(event.target.value)}>
                        {agentMetrics.map((metric) => (
                          <option key={`agent-y-${metric}`} value={metric}>
                            {metric} on Y
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <ResourceRelationChart title={`${selectedAgent} relation`} subtitle="Correlation between two resources for the selected agent." points={chartAgentTimeline} xMetric={agentScatterXMetric} yMetric={agentScatterYMetric} mode={chartMode} selector={(point) => point.resources} events={chartEvents} scopeAgent={selectedAgent} />
                </section>
                <section className="panel compact-panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Current portfolio</p>
                      <h3>Resources</h3>
                    </div>
                  </div>
                  <div className="resource-list">
                    {Object.entries(selectedAgentDetails?.portfolio ?? {}).map(([name, value]) => (
                      <div key={name} className="resource-row">
                        <span>{name}</span>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>
                </section>
              </div>

              <div className="modal-column narrow-column">
                <section className="panel compact-panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Constraints</p>
                      <h3>Operational limits</h3>
                    </div>
                  </div>
                  <pre className="agent-json">{JSON.stringify(selectedAgentDetails?.constraints ?? {}, null, 2)}</pre>
                </section>
                <section className="panel compact-panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Knowledge base</p>
                      <h3>ChromaDB graph</h3>
                    </div>
                    <span className="agent-count">{selectedAgentMemory?.stats.documents ?? 0}</span>
                  </div>
                  <div className="kb-toolbar">
                    <input className="kb-search" value={kbQuery} onChange={(event) => setKbQuery(event.target.value)} placeholder="Filter memory by id or full text" />
                  </div>
                  <KnowledgeGraph graph={filteredKbGraph} onSelectDoc={setSelectedKbDocId} selectedDocId={selectedKbDoc?.id ?? null} />
                  {filteredKbDocs.length > 0 && (
                    <div className="kb-doc-list">
                      {filteredKbDocs
                        .slice()
                        .reverse()
                        .slice(0, 12)
                        .map((doc) => (
                          <button key={doc.id} type="button" className={`kb-doc-card${selectedKbDoc?.id === doc.id ? ' kb-doc-card-active' : ''}`} onClick={() => setSelectedKbDocId(doc.id)}>
                            <div className="kb-doc-head">
                              <strong>{doc.id}</strong>
                              <span className="kb-doc-tags">{doc.tokens.slice(0, 4).join(' · ')}</span>
                            </div>
                            <p>{doc.preview || doc.content}</p>
                          </button>
                        ))}
                    </div>
                  )}
                </section>
                <section className="panel compact-panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Selected memory</p>
                      <h3>Document detail</h3>
                    </div>
                  </div>
                  {selectedKbDoc ? (
                    <div className="kb-doc-detail">
                      <div className="kb-doc-head">
                        <strong>{selectedKbDoc.id}</strong>
                        <span className="kb-doc-tags">{selectedKbDoc.tokens.join(' · ')}</span>
                      </div>
                      <pre className="kb-doc-fulltext">{selectedKbDoc.content}</pre>
                    </div>
                  ) : (
                    <div className="empty-state">No document matches the current filter.</div>
                  )}
                </section>
                <section className="panel compact-panel">
                  <div className="panel-header">
                    <div>
                      <p className="eyebrow">Relevant stream</p>
                      <h3>Agent events</h3>
                    </div>
                  </div>
                  <VirtualScroll items={events.filter((event) => event.type !== 'turn').filter((event) => event.agent === selectedAgent || event.target === selectedAgent)} itemHeight={EVENT_ROW_HEIGHT} visibleHeight={260} className="agent-event-list-virtual" renderItem={(event, index) => <EventLine key={`${event.timestamp ?? index}-agent-${index}`} event={event} />} />
                </section>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
