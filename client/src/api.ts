import axios from 'axios';
import { type AgentDetails, type AgentMemoryGraph, type AgentSummary, type ConfigResponse, type GodmodePayload, type MacroMetrics, type MarketOrderBook, type MarketSummary, type SimulationStatus, type TimelinePoint } from './types';

const API_BASE = '/api';


export const getAgents = async () => {
  const res = await axios.get<{ agents: AgentSummary[] }>(`${API_BASE}/agents`);
  return res.data.agents;
};

export const getPortfolios = async () => {
  const res = await axios.get(`${API_BASE}/portfolios`);
  return res.data.portfolios;
};

export const getResources = async () => {
  const res = await axios.get(`${API_BASE}/resources`);
  return res.data.resources;
};

export const getStatus = async () => {
  const res = await axios.get<SimulationStatus>(`${API_BASE}/status`);
  return res.data;
};

export const pauseSimulation = async () => {
  const res = await axios.post<SimulationStatus>(`${API_BASE}/pause`);
  return res.data;
};

export const resumeSimulation = async () => {
  const res = await axios.post<SimulationStatus>(`${API_BASE}/resume`);
  return res.data;
};

export const restartSimulation = async () => {
  const res = await axios.post<SimulationStatus>(`${API_BASE}/restart`);
  return res.data;
};

export const getTrades = async () => {
  const res = await axios.get(`${API_BASE}/trades`);
  return res.data.trades;
};

export const runSimulation = async () => {
  const res = await axios.post<SimulationStatus>(`${API_BASE}/run`);
  return res.data;
};

export const stepAgent = async (agent_id?: string) => {
  const res = await axios.post(`${API_BASE}/step`, { agent_id });
  return res.data;
};

export const resetSimulation = async () => {
  const res = await axios.post<SimulationStatus>(`${API_BASE}/reset`);
  return res.data;
};

export const chatbotQuery = async (query: string) => {
  const res = await axios.post(`${API_BASE}/chatbot`, { query });
  return res.data.answer;
};

export const getExport = async () => {
  const res = await axios.get(`${API_BASE}/export`);
  return res.data;
};

export const downloadExportZip = async () => {
  const res = await axios.get(`${API_BASE}/export.zip`, { responseType: 'blob' });
  return res.data as Blob;
};

export const getEvents = async (limit = 500) => {
  const res = await axios.get(`${API_BASE}/events`, { params: { limit } });
  return res.data.events;
};

export const getGlobalTimeline = async () => {
  const res = await axios.get<{ timeline: TimelinePoint[] }>(`${API_BASE}/timeline/global`);
  return res.data.timeline;
};

export const getAgentTimeline = async (agent_id: string) => {
  const res = await axios.get<{ timeline: TimelinePoint[] }>(`${API_BASE}/timeline/agent/${agent_id}`);
  return res.data.timeline;
};

export const getConfig = async () => {
  const res = await axios.get<ConfigResponse>(`${API_BASE}/config`);
  return res.data;
};

export const validateConfig = async (yaml_text: string) => {
  const res = await axios.post(`${API_BASE}/config/validate`, { yaml_text });
  return res.data;
};

export const updateConfig = async (yaml_text: string) => {
  const res = await axios.put<ConfigResponse>(`${API_BASE}/config`, { yaml_text });
  return res.data;
};

export const loadConfigPath = async (path: string) => {
  const res = await axios.post<ConfigResponse>(`${API_BASE}/config/load`, { path });
  return res.data;
};

export const getAgent = async (agent_id: string) => {
  const res = await axios.get<AgentDetails>(`${API_BASE}/agent/${agent_id}`);
  return res.data;
};

export const getAgentMemory = async (agent_id: string, limit = 80) => {
  const res = await axios.get<AgentMemoryGraph>(`${API_BASE}/memory/${agent_id}`, { params: { limit } });
  return res.data;
};

export const getMarkets = async () => {
  const res = await axios.get<{ markets: Record<string, MarketSummary> }>(`${API_BASE}/markets`);
  return res.data.markets;
};

export const getMarketOrderBook = async (resource: string, depth = 10) => {
  const res = await axios.get<MarketOrderBook>(`${API_BASE}/markets/${resource}/orderbook`, { params: { depth } });
  return res.data;
};

export const getMacroMetrics = async () => {
  const res = await axios.get<{ macro: MacroMetrics }>(`${API_BASE}/macro`);
  return res.data.macro;
};

export const godmode = async (payload: GodmodePayload) => {
  const res = await axios.post(`${API_BASE}/godmode`, payload);
  return res.data;
};

// WebSocket events
export function connectEvents(onEvent: (event: any) => void) {
  const ws = new WebSocket(
    `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/events`
  );
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onEvent(data);
    } catch {}
  };
  return ws;
}
