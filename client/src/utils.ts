import type { ChartMode, LiveEvent, MarketOrderBook, MarketSummary, MacroMetrics, SimulationStatus, TimelinePoint, AgentSummary } from './types';
// Decimate a timeline to at most maxPoints, always keeping first and last
export function decimateTimeline(points: TimelinePoint[], maxPoints: number): TimelinePoint[] {
  if (points.length <= maxPoints) return points;
  const step = Math.ceil(points.length / maxPoints);
  return points.filter((_, i) => i % step === 0 || i === points.length - 1);
}

export const STATUS_COLORS: Record<string, string> = {
  idle: 'status-idle',
  running: 'status-running',
  paused: 'status-paused',
  completed: 'status-completed',
  errored: 'status-errored',
};

export function formatTimestamp(timestamp?: number) {
  if (!timestamp) {
    return '--:--:--';
  }
  return new Date(timestamp * 1000).toLocaleTimeString();
}

export function pointLabel(point: TimelinePoint) {
  return `E${point.epoch ?? 0} · S${point.step ?? 0}`;
}

export function collectMetrics(points: TimelinePoint[], selector: (point: TimelinePoint) => Record<string, number> | undefined) {
  const metricSet = new Set<string>();
  for (const point of points) {
    const values = selector(point) ?? {};
    for (const metric of Object.keys(values)) {
      metricSet.add(metric);
    }
  }
  return Array.from(metricSet).sort();
}

export function toTotalBarSeries(points: TimelinePoint[], metrics: string[], mode: ChartMode, selector: (point: TimelinePoint) => Record<string, number> | undefined) {
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

export function toAgentChartSeries(points: TimelinePoint[], activeResources: string[], mode: ChartMode) {
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

export const CHART_EVENT_COLORS: Record<string, string> = {
  trade: '#d97731',
  action: '#2e8b57',
  communication: '#2060a0',
  kill: '#b42318',
  victory: '#7a3fb0',
};

export function findTimelineEventIndex(points: TimelinePoint[], event: LiveEvent) {
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

export function sameStatus(left: SimulationStatus | null, right: SimulationStatus) {
  if (!left) {
    return false;
  }
  return left.state === right.state && left.run_id === right.run_id && left.epoch === right.epoch && left.step === right.step && left.last_error === right.last_error && left.agent_count === right.agent_count;
}

export function sameAgentSummaries(left: AgentSummary[], right: AgentSummary[]) {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((agent, index) => agent.id === right[index]?.id && agent.alive === right[index]?.alive);
}

export function sameTimeline(left: TimelinePoint[], right: TimelinePoint[]) {
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

export function sameEvents(left: LiveEvent[], right: LiveEvent[]) {
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

export function sameMarketMap(left: Record<string, MarketSummary>, right: Record<string, MarketSummary>) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function sameOrderBook(left: MarketOrderBook | null, right: MarketOrderBook | null) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function sameMacro(left: MacroMetrics | null, right: MacroMetrics | null) {
  return JSON.stringify(left) === JSON.stringify(right);
}


export function formatNumber(value: number | undefined, digits = 2) {
  if (value === undefined || Number.isNaN(value)) {
    return '--';
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}
