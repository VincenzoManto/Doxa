import { useEffect, useState, useRef, useMemo } from 'react';
import * as echarts from 'echarts';
import { 
  Terminal, ShieldAlert, Activity, Database, 
  ChevronRight, Brain, Zap, X, Settings2, BarChart3, Filter
} from 'lucide-react';
import { 
  getAgents, getResources, connectEvents, 
  runSimulation, godmode 
} from './api';
import * as d3 from 'd3-force';

// --- TIPI E CONFIG ---
interface Event {
  type: string;
  agent?: string;
  thought?: string;
  action?: string;
  target?: string;
  result?: any;
  epoch?: number;
  step?: number;
  text?: string;
  timestamp?: number;
}

interface GraphConfig {
  metrics: string[];
  agents: string[];
  groupBy: 'metric' | 'agent';
  mode: 'cumulative' | 'instant';
  showEpochs: boolean;
}



interface Node { id: string; x?: number; y?: number; }
interface Link { source: string; target: string; type: string; value: number; }

function InteractionGraph({ events, agents, onNodeClick }: { events: Event[], agents: string[], onNodeClick: (id: string) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [links, setLinks] = useState<Link[]>([]);

  // Processa gli eventi per creare i collegamenti
  useEffect(() => {
    const newNodes = agents.map(id => ({ id }));
    const linkMap: Record<string, Link> = {};

    events.forEach(ev => {
      if (ev.agent && ev.target && ev.agent !== ev.target && !['accept_trade', 'reject_trade'].includes(ev.action || '')) {
        const key = `${ev.agent}-${ev.target}-${ev.type}`;
        if (ev.target === 'PUBLIC') {
          // Messaggi pubblici: connetti a tutti gli altri agenti
          agents.forEach(other => {
            if (other !== ev.agent) {
              const pubKey = `${ev.agent}-${other}-communication`;
              if (!linkMap[pubKey]) {
                linkMap[pubKey] = { source: ev.agent, target: other, type: 'communication', value: 1 };
              } else {
                linkMap[pubKey].value += 1;
              }
            }
          });
        }
        if (!linkMap[key]) {
          linkMap[key] = { source: ev.agent, target: ev.target, type: ev.type, value: 1 };
        } else {
          linkMap[key].value += 1;
        }
      }
    });

    setNodes(newNodes);
    setLinks(Object.values(linkMap));
  }, [events, agents]);

  // Simulazione D3 Force
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;
    try {
    const simulation = d3.forceSimulation(nodes as any)
      .force("link", d3.forceLink(links).id((d: any) => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(200, 150))
      .on("tick", () => {
        setNodes([...nodes]); // Trigger render
      });
    return () => { simulation.stop(); };

    } catch (e) {
      console.error("D3 Simulation Error:", e);
    }

  }, [links]);

  const getColor = (type: string) => {
    switch (type) {
      case 'communication': return '#6366f1'; // Indigo
      case 'trade': return '#10b981';   // Emerald
      case 'action': return '#f59e0b';  // Amber
      default: return '#94a3b8';
    }
  };

  return (
    <div className="relative w-full h-full bg-neutral-900 rounded-sm overflow-hidden border border-white/5">
      <div className="absolute top-2 left-2 flex gap-3 z-10">
        <div className="flex items-center gap-1 text-[8px] text-white/50 uppercase"><span className="w-2 h-2 bg-indigo-500 rounded-full" /> Msg</div>
        <div className="flex items-center gap-1 text-[8px] text-white/50 uppercase"><span className="w-2 h-2 bg-emerald-500 rounded-full" /> Trade</div>
        <div className="flex items-center gap-1 text-[8px] text-white/50 uppercase"><span className="w-2 h-2 bg-amber-500 rounded-full" /> Action</div>
      </div>
      <svg ref={svgRef} viewBox="0 0 400 300" className="w-full h-full">
        <g>
          {links.map((link: any, i) => (
            <line
              key={i}
              x1={link.source.x} y1={link.source.y}
              x2={link.target.x} y2={link.target.y}
              stroke={getColor(link.type)}
              strokeWidth={Math.min(link.value, 5)}
              strokeOpacity={0.6}
            />
          ))}
          {nodes.map((node: any) => (
            <g key={node.id} transform={`translate(${node.x},${node.y})`} onClick={() => onNodeClick(node.id)} className="cursor-pointer group">
              <circle r={8} fill="#fff" className="group-hover:fill-indigo-400 transition-colors" />
              <text dy={20} textAnchor="middle" fill="#fff" fontSize={8} fontWeight="bold" className="pointer-events-none uppercase font-mono tracking-tighter">
                {node.id}
              </text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
}

export default function App() {
  const [agents, setAgents] = useState<string[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [globalResources, setGlobalResources] = useState<Record<string, any>>({});
  const [history, setHistory] = useState<any[]>([]);
  
  // UI State
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [killedAgents, setKilledAgents] = useState<string[]>([]);
  const showedAgents = useMemo(() => {
    const result: {name: string, status: 'alive' | 'killed'}[] = [];
    agents.forEach(agent => {
      result.push({ name: agent, status: 'alive' });
    });
    killedAgents.forEach(agent => {
      if (!agents.includes(agent)) {
        result.push({ name: agent, status: 'killed' });
      }
    });

    return result;
  }, [agents, killedAgents]);
  
  
  // Godmode State
  const [gmAction, setGmAction] = useState('inject_resource');
  const [gmParams, setGmParams] = useState('{"resource": "gold", "amount": 100}');
  const echartRef = useRef<HTMLDivElement>(null);

  // Advanced Graph Config
  const [config, setConfig] = useState<GraphConfig>({
    metrics: [],
    agents: [], // Vuoto = Globale
    groupBy: 'metric',
    mode: 'instant',
    showEpochs: true
  });

  const scrollRef = useRef<HTMLDivElement>(null);

  // 1. WebSocket & Data Fetching
  useEffect(() => {
    getAgents().then(setAgents);
    const cleanup = connectEvents((ev: Event) => {
      const eventWithTime = { ...ev, timestamp: Date.now() };
      setEvents(prev => [eventWithTime, ...prev].slice(0, 200));
      if (!['accept_trade', 'reject_trade'].includes(ev.action || '') && ev.target !== 'PUBLIC') {
        setAgents(prev => {
          if (ev.agent && !prev.includes(ev.agent)) return [...prev, ev.agent];
          if (ev.target && !prev.includes(ev.target)) return [...prev, ev.target];
          return prev;
        });
      }
      if (ev.type === 'kill' && ev.agent) {
        setAgents(prev => prev.filter(a => a !== ev.agent)); 
        setKilledAgents(prev => [...prev, ev.agent!]);
        return;
      }


      if (ev.type === 'delta' || ev.type === 'step') {
        getResources().then(res => {
          setGlobalResources(res);
          setHistory(prev => [...prev, { ...res, _step: ev.step, _epoch: ev.epoch, _time: new Date().toLocaleTimeString() }].slice(-50));
        });
      }
    });
    return () => { 
      cleanup.close();
     };
  }, []);

  // 2. Filtraggio Eventi per l'Agente Selezionato
  const agentSpecificEvents = useMemo(() => {
    if (!selectedAgent) return [];
    return events.filter(e => e.agent === selectedAgent);
  }, [events, selectedAgent]);
  const [echartInstance, setEchartInstance] = useState<any>(null);

  // 3. Logica di trasformazione dati per il grafico configurabile
  useEffect(() => {
    if (echartRef.current === null) return;
    // Logica cumulativa semplificata
    let acc: any = {};
    const data = history.map(point => {
      const newPoint = { ...point };
      config.metrics.forEach(m => {
        acc[m] = (acc[m] || 0) + (point[m] || 0);
        newPoint[m] = acc[m];
      });
      return newPoint;
    });
    // data = [{<metrics>, _time, player_X: {<metrics>}}, ...]
    // voglio un grafico che mostri le metriche globali e le stesse metriche per ogni agente (linee tratteggiate)
    // c'è una barra per ogni metrica globale e una linea tratteggiata per ogni agente e per ogni metrica (es. player1_gold, player1_corn, player2_gold, player2_corn)
    const options = {
      tooltip: { trigger: 'axis' },
      legend: { data: config.metrics },
      xAxis: { type: 'category', data: data.map(d => d._time) },
      yAxis: { type: 'value' },
      series: [...config.metrics.map(m => ({
        name: m,
        type: 'bar',
        data: data.map(d => d[m] || 0),
        smooth: true,
        lineStyle: { width: 2 },
        showSymbol: false,
      })), 
      ...(agents.length > 0 ? agents.map(agent => config.metrics.map(m => ({
        name: `${agent} ${m}`,
        type: 'line',
        data: data.map(d => d[agent]?.[m] || 0),
        smooth: true,
        lineStyle: { width: 1, type: 'dashed' },
        showSymbol: false,
      }))).flat() : [])]
    
    };
    //
    console.log(options);

    if (echartRef.current) {
      if (!echartInstance) {
        const chart = echarts.init(echartRef.current);
        setEchartInstance(chart);
        chart.setOption(options);
      } else {
         echartInstance.setOption(options);
      }
    }
  }, [echartRef, history, config, agents.length]);

  const callGodmode = async () => {
    try {
      const res = await godmode({ action: gmAction, params: JSON.parse(gmParams) });
      console.log("Godmode Success:", res);
    } catch (e) {
      alert("JSON Params non valido");
    }
  };

  const metrics = useMemo(() => {
    const allMetrics = new Set<string>();
    history.forEach(point => {
      Object.keys(point).forEach(k => {
        if (agents.includes(k))  {
          Object.keys(point[k]).forEach(m => allMetrics.add(m));
        }
          else if (!['_time', '_step', '_epoch'].includes(k)) {
            allMetrics.add(k);
          }
      });
    });
    config.metrics.forEach(m => allMetrics.add(m));
    return Array.from(allMetrics);
  }, [history, agents.length]);

  return (
    <div className="flex h-screen bg-[#f4f4f5] text-neutral-900 font-serif overflow-hidden">
      
      {/* SIDEBAR: AGENT LIST */}
      <aside className="w-72 border-r border-neutral-200 bg-white flex flex-col shadow-xl z-10">
        <div className="p-8 border-b border-neutral-100 bg-indigo-900 text-white">
          <h1 className="text-3xl font-black tracking-tighter italic">DOXA</h1>
          <p className="text-[10px] font-mono opacity-50 uppercase tracking-[0.3em]">Simulation Engine v2.4</p>
        </div>
        
        <nav className="flex-1 overflow-y-auto p-6 space-y-2">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest">Entities</span>
            <span className="text-[10px] bg-neutral-100 px-2 py-0.5 rounded text-neutral-500 font-mono">{agents.length}</span>
          </div>
          {showedAgents.map(agent => (
            <button 
              key={agent.name}
              onClick={() => setSelectedAgent(agent.name)}
              className={`w-full flex items-center justify-between p-3 rounded-sm transition-all border ${selectedAgent === agent.name ? 'bg-indigo-50 border-indigo-200 translate-x-1' : 'bg-transparent border-transparent hover:border-neutral-200'}`}
            >
              <div className="flex items-center gap-3">
                <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-emerald-500 animate-pulse' : 
                  agent.status === 'killed' ? 'bg-red-500' :
                  'bg-neutral-300'}`} />
                  {/* nome barrato se morto */}
                <span className={`text-sm font-bold tracking-tight ${agent.status === 'killed' ? 'line-through text-red-500' : ''}`}>{agent.name}</span>
              </div>
              <ChevronRight size={14} className={selectedAgent === agent.name ? 'text-indigo-600' : 'text-neutral-300'} />
            </button>
          ))}
        </nav>

        <div className="p-6 bg-neutral-50 border-t border-neutral-100">
          <button 
            onClick={async () => { setIsRunning(true); await runSimulation(); setIsRunning(false); }}
            className="w-full bg-black text-white py-4 rounded-sm hover:bg-neutral-800 transition flex items-center justify-center gap-3 font-bold text-xs tracking-[0.2em]"
          >
            <Zap size={14} fill="currentColor" /> {isRunning ? "EXECUTING..." : "RUN SIMULATION"}
          </button>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        
        {/* TELEMETRY SECTION */}
        <section className="h-2/5 border-b border-neutral-200 bg-white relative flex">
          <div className='w-3/5'>
          <div className="flex justify-between items-center mb-6">
            <div className="flex items-center gap-4">
              <h2 className="text-xs font-black uppercase tracking-[0.2em] text-neutral-400 flex items-center gap-2">
                <Activity size={16} className="text-indigo-600" /> Real-time Telemetry
              </h2>
              <div className="h-4 w-[1px] bg-neutral-200" />
              <div className="flex gap-4">
                {config.metrics.map(m => (
                  <div key={m} className="flex items-center gap-2">
                    <span className="text-[10px] font-mono text-neutral-400">{m}:</span>
                    <span className="text-xs font-bold font-mono">{globalResources[m] || 0}</span>
                  </div>
                ))}
              </div>
            </div>
            <button 
              onClick={() => setIsConfigOpen(true)}
              className="flex items-center gap-2 px-3 py-1.5 border border-neutral-200 rounded-sm text-[10px] font-bold uppercase hover:bg-neutral-50 transition"
            >
              <Settings2 size={14} /> Configure Graph
            </button>
          </div>

          <div className="h-full pb-12">
              <div ref={echartRef} className="w-full h-full" />
          </div>
          </div>
          {/* Colonna Grafo Relazioni (NEW) */}
          <div className="w-2/5 p-8 relative group">
            <h2 className="text-xs font-black uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
              <Zap size={16} className="text-amber-500" /> Interaction Topology
            </h2>
            <div className="h-full pb-12">
               <InteractionGraph 
                 events={events} 
                 agents={agents} 
                 onNodeClick={(id) => setSelectedAgent(id)} 
               />
            </div>
            {/* Overlay informativo al passaggio del mouse */}
            <div className="absolute bottom-4 right-4 text-[9px] font-mono italic opacity-0 group-hover:opacity-100 transition-opacity">
              Force-directed layout: dynamic weights applied
            </div>
          </div>
        </section>

        {/* LOGS SECTION */}
        <section className="flex-1 flex overflow-hidden">
          <div className="flex-1 bg-[#09090b] flex flex-col overflow-hidden">
          <div className="p-4 bg-white/5 border-b border-white/10 flex justify-between items-center">
            <div className="flex items-center gap-3">
              <Terminal size={14} className="text-indigo-400" />
              <span className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em]">System Output stream</span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-6 font-mono text-[11px] space-y-1.5" ref={scrollRef}>
            {events.map((ev, i) => (
              <div key={i} className="flex gap-4 group hover:bg-white/5 p-1 rounded transition-colors">
                <span className="text-white/10 w-20 shrink-0">{new Date(ev.timestamp || 0).toLocaleTimeString()}</span>
                <EventRenderer ev={ev} />
              </div>
            ))}
          </div>
          </div>
          {/* GODMODE PANEL */}
          <div className="w-80 bg-neutral-900 p-6 flex flex-col border-l border-white/10 shadow-2xl">
            <h2 className="text-xs font-bold text-red-500 uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
              <ShieldAlert size={16} /> Godmode Console
            </h2>
            <div className="space-y-6">
              <div className="space-y-2">
                <label className="text-xs text-neutral-500 uppercase font-bold">Action</label>
                <select 
                  value={gmAction} 
                  onChange={e => setGmAction(e.target.value)}
                  className="w-full bg-neutral-800 border border-neutral-700 text-white text-xs p-2 rounded focus:ring-1 ring-red-500 outline-none font-mono"
                >
                  <option value="inject_resource">Inject Resource</option>
                  <option value="set_portfolio">Set Portfolio</option>
                  <option value="set_constraint">Set Constraint</option>
                  <option value="send_message">Send Message</option>
                  <option value="impersonate_action">Impersonate Action</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-xs text-neutral-500 uppercase font-bold">Parameters (JSON)</label>
                <textarea 
                  value={gmParams}
                  onChange={e => setGmParams(e.target.value)}
                  className="w-full h-32 bg-neutral-800 border border-neutral-700 text-green-500 text-[11px] p-3 rounded font-mono focus:ring-1 ring-red-500 outline-none"
                />
              </div>
              <button 
                onClick={callGodmode}
                className="w-full border border-red-900 text-red-500 py-3 rounded text-xs font-bold uppercase tracking-widest hover:bg-red-950 transition"
              >
                Execute Intervention
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* MODALE PROFILO AGENTE (Ora popolato dagli eventi live) */}
      {selectedAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-12">
          <div className="bg-white w-full max-w-6xl h-full rounded-sm shadow-2xl flex flex-col border border-white/20 animate-in fade-in zoom-in duration-300">
            <header className="p-8 border-b border-neutral-100 flex justify-between items-center bg-neutral-50">
              <div className="flex items-center gap-6">
                <div className="w-16 h-16 bg-black text-white flex items-center justify-center text-3xl font-black italic">
                  {selectedAgent.slice(-1)}
                </div>
                <div>
                  <h2 className="text-4xl font-black tracking-tighter uppercase">{selectedAgent}</h2>
                  <p className="text-xs text-indigo-600 font-mono font-bold tracking-widest uppercase mt-1 italic underline">Cognitive state: Operational</p>
                </div>
              </div>
              <button onClick={() => setSelectedAgent(null)} className="p-3 hover:bg-neutral-200 rounded-full transition"><X /></button>
            </header>
            
            <div className="flex-1 flex overflow-hidden">
              {/* Sidebar: Stato statico */}
              <div className="w-80 border-r border-neutral-100 p-8 space-y-10 overflow-y-auto bg-neutral-50/30">
                <section>
                  <h3 className="text-[10px] font-black uppercase text-neutral-400 mb-6 tracking-widest flex items-center gap-2"><Database size={14}/> Asset Portfolio</h3>
                  <div className="space-y-4">
                    {Object.entries(globalResources).map(([k, v]) => (
                      <div key={k} className="flex justify-between items-end border-b border-neutral-100 pb-2">
                        <span className="text-xs font-mono uppercase text-neutral-500">{k}</span>
                        <span className="text-xl font-black font-mono">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                </section>
                <section>
                   <h3 className="text-[10px] font-black uppercase text-neutral-400 mb-4 tracking-widest flex items-center gap-2"><Filter size={14}/> Operational Limits</h3>
                   <div className="bg-white border border-neutral-200 p-4 font-mono text-[10px] leading-relaxed shadow-sm italic text-neutral-500">
                      // No active behavioral constraints detected. Agent is operating under standard rational expectations.
                   </div>
                </section>
              </div>

              {/* Centro: Thread di Pensieri ed Azioni (DINAMICO) */}
              <div className="flex-1 flex flex-col p-8 overflow-y-auto bg-white">
                <h3 className="text-[10px] font-black uppercase text-neutral-400 mb-8 tracking-widest flex items-center gap-2"><Brain size={14}/> Cognitive Stream & Action History</h3>
                
                {agentSpecificEvents.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center opacity-20 italic">
                    <Activity size={48} className="mb-4" />
                    <p>No telemetry recorded for this entity in the current epoch.</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    {agentSpecificEvents.map((ev, i) => (
                      <div key={i} className={`p-6 rounded-sm border-l-4 shadow-sm animate-in slide-in-from-left-4 duration-300 ${ev.type === 'think' ? 'bg-indigo-50 border-indigo-500' : 'bg-emerald-50 border-emerald-500'}`}>
                        <div className="flex justify-between items-center mb-2">
                           <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded bg-white border border-neutral-200">
                             {ev.type} | Step {ev.step || '?' }
                           </span>
                           <span className="text-[9px] font-mono text-neutral-400">{new Date(ev.timestamp || 0).toLocaleTimeString()}</span>
                        </div>
                        {ev.type === 'think' ? (
                          <p className="text-sm font-serif italic text-neutral-800 leading-relaxed italic uppercase">"{ev.thought}"</p>
                        ) : (
                          <div className="font-mono text-xs text-emerald-800">
                            EXECUTED: <span className="font-bold underline">{ev.action}</span> ➔ TARGET: <span className="font-bold">{ev.target}</span>
                            <div className="mt-2 pt-2 border-t border-emerald-100 text-[10px] opacity-70">
                              RESULT: {JSON.stringify(ev.result)}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODALE CONFIGURAZIONE GRAFICI (TELEMETRY ARCHITECT) */}
      {isConfigOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-indigo-950/60 backdrop-blur-xl p-6">
          <div className="bg-white w-full max-w-2xl rounded-sm shadow-2xl p-10 border border-indigo-200">
            <div className="flex justify-between items-center mb-8">
              <h2 className="text-2xl font-black italic tracking-tighter uppercase flex items-center gap-3">
                <BarChart3 className="text-indigo-600" /> Telemetry Architect
              </h2>
              <button onClick={() => setIsConfigOpen(false)}><X /></button>
            </div>

            <div className="grid grid-cols-2 gap-10">
              <div className="space-y-6">
                <section>
                  <label className="text-[10px] font-black uppercase text-neutral-400 block mb-3 tracking-widest">Active Metrics</label>
                  <div className="space-y-2 max-h-40 overflow-y-auto pr-4">
                    {metrics.map(m => (
                      <label key={m} className="flex items-center gap-3 p-2 bg-neutral-50 border border-neutral-200 rounded-sm cursor-pointer hover:bg-neutral-100">
                        <input 
                          type="checkbox" 
                          checked={config.metrics.includes(m)} 
                          onChange={(e) => setConfig({ ...config, metrics: e.target.checked ? [...config.metrics, m] : config.metrics.filter(x => x !== m) })}
                        />
                        <span className="text-xs font-mono uppercase">{m}</span>
                      </label>
                    ))}
                  </div>
                </section>

                <section>
                  <label className="text-[10px] font-black uppercase text-neutral-400 block mb-3 tracking-widest">Projection Mode</label>
                  <div className="flex gap-2">
                    {['instant', 'cumulative'].map(m => (
                      <button 
                        key={m}
                        onClick={() => setConfig({...config, mode: m as any})}
                        className={`flex-1 py-2 text-[10px] font-bold uppercase border ${config.mode === m ? 'bg-black text-white border-black' : 'bg-white border-neutral-200 hover:bg-neutral-50'}`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </section>
              </div>

              <div className="space-y-6 text-neutral-500 text-xs italic leading-relaxed border-l border-neutral-100 pl-10">
                <p>The architect allows for multi-dimensional analysis of agent interactions.</p>
                <p>Selecting <b>Cumulative</b> will project the integral of resource flows over time, useful for detecting long-term wealth accumulation trends.</p>
                <p><b>Instant</b> mode reflects the precise state of the engine at each step resolution.</p>
                <div className="pt-10">
                  <button 
                    onClick={() => setIsConfigOpen(false)}
                    className="w-full bg-indigo-600 text-white py-4 font-black uppercase tracking-[0.2em] text-[10px] hover:bg-indigo-700 shadow-xl"
                  >
                    Apply Configuration
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// RENDERER DEI LOG NEL TERMINALE
function EventRenderer({ ev }: { ev: Event }) {
  switch (ev.type) {
    case 'epoch': return <span className="text-yellow-500 font-bold underline italic tracking-widest">--- INITIALIZING EPOCH {ev.epoch} ---</span>;
    case 'step': return <span className="text-white/40 border-b border-white/10 italic">RESOLUTION PHASE: STEP {ev.step}</span>;
    case 'turn': return <span className="text-indigo-400 font-bold">INVOKING AGENT: <span className="text-white underline">{ev.agent}</span></span>;
    case 'think': return <span className="text-white/60">Agent <b className="text-white">{ev.agent}</b> reasoning: <i className="text-indigo-200">"{ev.thought}"</i></span>;
    case 'action': return <span className={"font-bold uppercase tracking-tighter" + (
      ev.action === 'accept_trade' ? ' text-emerald-400' : 
      ev.action === 'reject_trade' ? ' text-red-400' : 
      ' text-amber-400'
    )}>Action executed: {ev.action} ➔ Result: {JSON.stringify(ev.result)}</span>;
    case 'victory': return <span className="bg-yellow-500 text-black px-4 font-black">STASIS REACHED: {ev.text}</span>;
    case 'kill': return <span className="bg-red-500 text-white px-3 py-1 rounded font-bold">AGENT TERMINATED: {ev.agent}</span>;
    case 'communication': return <span className="text-purple-400 italic">Message from {ev.agent} to {ev.target}: "{ev.text}"</span>;
    default: return <span className="text-neutral-600 italic opacity-50">{JSON.stringify(ev)}</span>;
  }
}