import { startTransition, useEffect, useMemo, useRef, useState } from 'react';
import './App.css';
import { Activity, Archive, Download, FileCode2, Pause, Play, RotateCcw, ShieldAlert, SkipForward, Upload, X } from 'lucide-react';
import { connectEvents, downloadExportZip, getAgent, getAgentMemory, getAgentTimeline, getAgents, getConfig, getEvents, getGlobalTimeline, getMacroMetrics, getMarketOrderBook, getMarkets, getStatus, godmode, loadConfigPath, pauseSimulation, resetSimulation, restartSimulation, resumeSimulation, runSimulation, stepAgent, updateConfig, validateConfig } from './api';
import type { AgentDetails, AgentMemoryGraph, AgentSummary, ChartMode, ConnectionState, LiveEvent, MacroMetrics, MarketOrderBook, MarketSummary, SimulationStatus, TimelinePoint } from './types';
import { sameEvents, sameMacro, sameMarketMap, sameOrderBook, sameAgentSummaries, sameStatus, sameTimeline, STATUS_COLORS, collectMetrics, decimateTimeline } from './utils';
import { VirtualScroll } from './components/VirtualScroll';
import { TimelineChart } from './components/TimelineChart';
import { AgentNetworkGraph } from './components/AgentNetworkGraph';
import { MarketDepthPanel } from './components/MarketDepthPanel';
import { MacroPanel } from './components/MacroPanel';
import { EventLine } from './components/Events';
import { ChatbotPanel } from './components/ChatbotPanel';
import { ResourceRelationChart } from './components/ResourceRelationChart';
import { KnowledgeGraph } from './components/KnowledgeGraph';

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

export default function App() {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [markets, setMarkets] = useState<Record<string, MarketSummary>>({});
  const [selectedMarket, setSelectedMarket] = useState('');
  const [orderBook, setOrderBook] = useState<MarketOrderBook | null>(null);
  const [macro, setMacro] = useState<MacroMetrics | null>(null);
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
  const REFRESH_ON_TYPES = new Set(['step', 'kill', 'epoch', 'victory', 'manual_step', 'reset', 'config', 'godmode', 'market_fill', 'world_event']);

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

  async function refreshMarkets() {
    const nextMarkets = await getMarkets();
    setMarkets((current) => (sameMarketMap(current, nextMarkets) ? current : nextMarkets));
    const resources = Object.keys(nextMarkets).sort();
    setSelectedMarket((current) => (current && nextMarkets[current] ? current : (resources[0] ?? '')));
  }

  async function refreshMacro() {
    const nextMacro = await getMacroMetrics();
    setMacro((current) => (sameMacro(current, nextMacro) ? current : nextMacro));
  }

  async function refreshOrderBook(resource: string) {
    if (!resource) {
      setOrderBook(null);
      return;
    }
    const nextOrderBook = await getMarketOrderBook(resource);
    setOrderBook((current) => (sameOrderBook(current, nextOrderBook) ? current : nextOrderBook));
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
      await Promise.all([refreshStatusAndTimeline(), refreshEvents(), refreshConfig(), refreshMarkets(), refreshMacro()]);
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
    if (!selectedMarket) {
      setOrderBook(null);
      return;
    }
    void refreshOrderBook(selectedMarket);
  }, [selectedMarket]);

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
      const scheduleRefreshWithMacro = () => {
        if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = window.setTimeout(() => {
          void refreshStatusAndTimeline();
          void refreshMarkets();
          void refreshMacro();
          if (selectedMarket) void refreshOrderBook(selectedMarket);
          if (selectedAgent) void refreshAgent(selectedAgent);
        }, 200);
      };

      // Full snapshot emitted after every step/kill/reset by the server
      if (normalizedEvent.type === 'snapshot') {
        const snap = normalizedEvent as LiveEvent & {
          totals?: Record<string, number>;
          agents?: Record<string, Record<string, number>>;
          agents_alive?: Array<{ id: string; alive: boolean }>;
          markets?: Record<string, MarketSummary>;
          status?: SimulationStatus;
          epoch?: number;
          step?: number;
          run_id?: string;
          reason?: string;
        };
        // Filter out synthetic market-maker entries from chart data
        const filteredAgents_ = snap.agents ? Object.fromEntries(Object.entries(snap.agents).filter(([id]) => !id.startsWith('__mm_'))) : {};
        // Append to timeline
        const newPoint: TimelinePoint = {
          timestamp: snap.timestamp ?? Date.now() / 1000,
          run_id: snap.run_id ?? null,
          epoch: snap.epoch ?? 0,
          step: snap.step ?? 0,
          state: snap.state ?? '',
          reason: snap.reason ?? '',
          totals: snap.totals ?? {},
          agents: filteredAgents_,
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
        if (snap.markets) {
          const nextMarkets = snap.markets;
          setMarkets((current) => (sameMarketMap(current, nextMarkets) ? current : nextMarkets));
          const resources = Object.keys(nextMarkets).sort();
          setSelectedMarket((current) => (current && nextMarkets[current] ? current : (resources[0] ?? '')));
        }
        if ((snap as LiveEvent & { macro?: MacroMetrics }).macro) {
          const nextMacro = (snap as LiveEvent & { macro?: MacroMetrics }).macro!;
          setMacro((current) => (sameMacro(current, nextMacro) ? current : nextMacro));
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
      // Suppress high-frequency macro_snapshot events from the visible log
      if (normalizedEvent.type !== 'macro_snapshot') {
        startTransition(() => {
          setEvents((previous) => [normalizedEvent, ...previous].slice(0, MAX_EVENTS));
        });
      }

      // Trigger a REST refresh after key events so timeline/status stay in sync
      if (REFRESH_ON_TYPES.has(normalizedEvent.type)) {
        scheduleRefreshWithMacro();
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

          <div className="top-stack">
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

        <section className="panel chart-panel network-panel top-grid">
          <div className="top-stack">
            <div className="panel-header">
              <div>
                <p className="eyebrow">Interaction graph</p>
                <h3>Agent network</h3>
              </div>
              <p className="panel-subtitle">Edges aggregate trades, communications and actions in realtime.</p>
            </div>
            <AgentNetworkGraph agents={agents} events={events} />
          </div>
          <div></div>
          <MarketDepthPanel markets={markets} selectedMarket={selectedMarket} onSelectMarket={setSelectedMarket} orderBook={orderBook} />
          <MacroPanel macro={macro} />
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

            {(feedback || error || status?.last_error) && (
              <section className="panel compact-panel status-panel">
                {feedback && <p className="feedback-ok">{feedback}</p>}
                {error && <p className="feedback-error">{error}</p>}
                {status?.last_error && <p className="feedback-error">Engine error: {status.last_error}</p>}
              </section>
            )}
          </div>
          <ChatbotPanel />
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
