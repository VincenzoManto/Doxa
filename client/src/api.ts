import axios from 'axios';

const API_BASE = '/api';

export const getAgents = async () => {
  const res = await axios.get(`${API_BASE}/agents`);
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

export const getTrades = async () => {
  const res = await axios.get(`${API_BASE}/trades`);
  return res.data.trades;
};

export const runSimulation = async () => {
  const res = await axios.post(`${API_BASE}/run`);
  return res.data;
};

export const stepAgent = async (agent_id: string) => {
  const res = await axios.post(`${API_BASE}/step`, { agent_id });
  return res.data;
};

export const resetSimulation = async () => {
  const res = await axios.post(`${API_BASE}/reset`);
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

export const getAgent = async (agent_id: string) => {
  const res = await axios.get(`${API_BASE}/agent/${agent_id}`);
  return res.data;
};

export const godmode = async (command: string) => {
  const res = await axios.post(`${API_BASE}/godmode`, { command });
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
