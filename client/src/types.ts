
export type LiveEvent = {
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
  buyer?: string;
  seller?: string;
  qty?: number;
  price?: number;
  resource?: string;
  effects?: string[];
};

export type ChartMode = 'instant' | 'cumulative';
export type ConnectionState = 'connecting' | 'live' | 'reconnecting' | 'offline';

export type ChatMessage = { role: 'user' | 'assistant'; content: string };


export interface SimulationStatus {
  state: 'idle' | 'running' | 'paused' | 'completed' | 'errored';
  run_id: string | null;
  epoch: number;
  step: number;
  last_error: string | null;
  agent_count: number;
  available_actions: {
    can_run: boolean;
    can_pause: boolean;
    can_resume: boolean;
    can_reset: boolean;
    can_restart: boolean;
    can_step: boolean;
  };
}

export interface ConfigResponse {
  yaml_text: string;
  source: { kind: string; value: string };
  config: Record<string, unknown>;
}

export interface TimelinePoint {
  timestamp: number;
  run_id: string | null;
  epoch: number;
  step: number;
  state: string;
  reason: string;
  totals?: Record<string, number>;
  agents?: Record<string, Record<string, number>>;
  resources?: Record<string, number>;
}

export interface AgentDetails {
  agent: string;
  portfolio: Record<string, number>;
  constraints: Record<string, Record<string, number>>;
  config: Record<string, unknown>;
  alive: boolean;
  death_reason: string | null;
}

export interface AgentSummary {
  id: string;
  alive: boolean;
}

export interface AgentMemoryDoc {
  id: string;
  content: string;
  preview: string;
  tokens: string[];
}

export interface AgentMemoryGraph {
  agent: string;
  docs: AgentMemoryDoc[];
  graph: {
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
  };
  stats: {
    documents: number;
    links: number;
  };
}

export interface GodmodePayload {
  action: string;
  params: Record<string, unknown>;
}

export interface MarketSummary {
  resource: string;
  currency: string;
  current_price: number;
  mid_price: number;
  bids_count: number;
  asks_count: number;
  bids_volume: number;
  asks_volume: number;
}

export interface OrderBookLevel {
  price: number;
  qty: number;
}

export interface MarketOrderBook {
  resource: string;
  currency: string;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  mid_price: number;
  last_price: number;
}

export interface MacroResourceStat {
  total: number;
  mean: number;
  gini: number;
  hhi: number;
}

export interface MacroMarketStat {
  last_price: number;
  volatility: number;
  min_recent: number;
  max_recent: number;
}

export interface MacroMetrics {
  tick: number;
  system_panic: number;
  resources: Record<string, MacroResourceStat>;
  market_stats: Record<string, MacroMarketStat>;
}
