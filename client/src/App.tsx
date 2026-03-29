import React, { useState, useEffect } from 'react';
import { useSocket } from './hooks/useSocket';
import { AnimatePresence } from 'framer-motion';
import SettingsPanel from './components/SettingsPanel';
import UserControlPanel from './components/UserControlPanel';
import HistoryModal from './components/HistoryModal';
import { Settings as SettingsIcon } from 'lucide-react';
import './index.css';

interface Message {
  sender: string;
  type: 'public' | 'private' | 'system';
  content: string;
  target?: string;
}

const App: React.FC = () => {
  const { socket, isConnected, status } = useSocket();
  const [messages, setMessages] = useState<Message[]>([]);
  const [worldState, setWorldState] = useState<any>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [thoughts, setThoughts] = useState<Record<string, string>>({});
  const [showGodMode, setShowGodMode] = useState(false);

  // Load initial agent list and portfolios
  useEffect(() => {
    Promise.all([
      fetch('/api/agents').then(res => res.json()),
      fetch('/api/portfolios').then(res => res.json()),
      fetch('/api/trades').then(res => res.json())
    ])
      .then(([agentsData, portfoliosData, tradesData]) => {
        setWorldState({
          agents: agentsData.agents,
          portfolios: portfoliosData.portfolios,
          trades: tradesData.trades,
        });
      })
      .catch(err => console.error('Initial data fetch fail:', err));
  }, []);

  // TODO: Update this effect after WebSocket refactor
  // useEffect(() => {
  //   if (!socket) return;
  //   socket.on('chat_message', (msg: Message) => setMessages((prev) => [...prev.slice(-100), msg]));
  //   socket.on('state_update', (state: any) => {
  //     setWorldState(state);
  //     if (state.thoughts) setThoughts(state.thoughts);
  //     // Auto-select first agent if none
  //     if (!selectedAgentId && state.actors && Object.keys(state.actors).length > 0) {
  //       setSelectedAgentId(Object.keys(state.actors)[0]);
  //     }
  //   });
  // }, [socket, selectedAgentId]);

  const selectedAgent = selectedAgentId ? worldState?.actors?.[selectedAgentId] : null;

  return (
    <div className="h-screen w-screen flex flex-col bg-[#0a0a0a] text-[#e5e5e5] font-sans text-[12px] overflow-hidden">
      {/* Header / Toolbar */}
      <header className="h-10 px-4 flex items-center justify-between border-b border-[#1f1f1f] bg-[#121212] z-20">
        <div className="flex items-center gap-4">
          <span className="font-bold tracking-tight text-white uppercase">Doxa Scenario Research</span>
          <div className="h-4 w-px bg-[#1f1f1f]" />
          <div className="flex items-center gap-2 opacity-50 font-mono text-[10px]">
            <div className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-blue-500' : 'bg-red-500'}`} />
            {status.toUpperCase()} @ LOCALHOST:8000
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <div className="text-[10px] font-mono opacity-50 px-2 py-0.5 border border-[#1f1f1f] rounded">
            CYCLE: {worldState?.tick || 0}
          </div>
          <button 
            onClick={() => setShowGodMode(!showGodMode)}
            className={`px-3 py-1 rounded text-[10px] font-bold border ${showGodMode ? 'bg-red-900/20 border-red-500/50 text-red-500' : 'border-[#1f1f1f] text-[#737373] hover:text-white'}`}
          >
            GOD_MODE
          </button>
          <button 
            onClick={() => setShowSettings(true)}
            className="p-1 hover:text-white transition-colors"
          >
            <SettingsIcon className="w-4 h-4" />
          </button>
          {/* Replace with /api/reset for simulation reset */}
          <button 
            onClick={() => fetch('/api/reset', { method: 'POST' })}
            className="px-4 py-1 bg-blue-600 text-white font-bold rounded hover:bg-blue-500 transition-colors"
          >
            START_SIM
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex overflow-hidden">
        
        {/* Left Col: Agent Navigator */}
        <nav className="w-64 border-r border-[#1f1f1f] bg-[#121212] flex flex-col">
          <div className="p-3 text-[10px] font-bold text-[#737373] uppercase tracking-widest border-b border-[#1f1f1f]">
            Neural Actors
          </div>
          <div className="flex-1 overflow-y-auto">
            {worldState && Object.values(worldState.actors).map((actor: any) => (
              <div 
                key={actor.id}
                onClick={() => setSelectedAgentId(actor.id)}
                className={`p-3 data-row cursor-pointer transition-colors ${selectedAgentId === actor.id ? 'bg-[#1a1a1a] border-l-2 border-blue-500' : ''}`}
              >
                <div className="flex justify-between items-center mb-1">
                  <span className="font-bold text-white">{actor.name}</span>
                  <span className="text-[9px] font-mono opacity-40 uppercase">{actor.id}</span>
                </div>
                <div className="flex gap-2">
                   {Object.entries(actor.portfolio).slice(0, 3).map(([res, val]: [any, any]) => (
                     <div key={res} className="text-[9px] flex gap-1">
                        <span className="opacity-30 uppercase">{res.charAt(0)}:</span>
                        <span className="font-mono text-blue-400">{String(val)}</span>
                     </div>
                   ))}
                </div>
              </div>
            ))}
          </div>
          {/* Alliance Groups */}
          <div className="p-3 border-t border-[#1f1f1f]">
             <div className="text-[10px] font-bold text-[#737373] uppercase mb-2">Detected Alliances</div>
             {worldState?.alliances && Object.values(worldState.alliances).map((al: any) => (
               <div key={al.id} className="text-[10px] py-1 opacity-60">
                  <span className="text-blue-500">◈</span> {al.name} ({al.members.length})
               </div>
             ))}
          </div>
        </nav>

        {/* Center Col: Agent Telemetry */}
        <section className="flex-1 bg-[#101010] flex flex-col overflow-hidden">
          {selectedAgent ? (
            <>
              <div className="p-4 border-b border-[#1f1f1f] bg-[#121212] flex justify-between items-center">
                <div>
                  <h2 className="text-lg font-black text-white leading-none uppercase tracking-tighter">{selectedAgent.name}</h2>
                  <p className="text-[10px] opacity-40 font-mono uppercase mt-1">TELEMETRY_FEED // {selectedAgent.id}</p>
                </div>
                <div className="flex gap-4">
                  {Object.entries(selectedAgent.portfolio).map(([res, val]: [any, any]) => (
                    <div key={res} className="text-right">
                       <div className="text-[8px] opacity-30 font-bold uppercase">{res}</div>
                       <div className="text-sm font-mono text-blue-400 font-bold leading-none">{String(val)}</div>
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="flex-1 overflow-y-auto p-4 space-y-6">
                {/* Strategic Thought */}
                <div className="panel p-4 rounded-sm bg-[#161616]">
                  <h3 className="text-[10px] font-bold text-blue-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                    <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                    Cognitive Status _ Strategic Intent
                  </h3>
                  <div className="font-mono text-sm opacity-90 leading-relaxed italic">
                    {thoughts[selectedAgentId!] || "PROCESSING NEURAL INPUT..."}
                  </div>
                </div>

                {/* Audit History (Inline HistoryModal) */}
                <div className="flex-1 min-h-0 flex flex-col">
                   <h3 className="text-[10px] font-bold text-[#737373] uppercase tracking-widest mb-3">Audit Trail _ Independent Stream</h3>
                   <div className="flex-1 border border-[#1f1f1f] rounded-sm bg-black/20 overflow-hidden">
                      <HistoryModal agentId={selectedAgentId!} inline={true} />
                   </div>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center opacity-20 text-[10px] font-mono tracking-widest uppercase">
              // SELECT NODE FOR TELEMETRY //
            </div>
          )}
        </section>

        {/* Right Col: Global Event Feed */}
        <aside className="w-80 border-l border-[#1f1f1f] bg-[#121212] flex flex-col h-full">
           <div className="p-3 border-b border-[#1f1f1f] text-[10px] font-bold text-[#737373] uppercase tracking-widest">
              Global Stream
           </div>
           <div className="flex-1 overflow-y-auto p-3 font-mono text-[11px] space-y-3">
              {messages.map((msg, i) => (
                <div key={i} className={`p-2 border-l-2 ${
                  msg.type === 'system' ? 'border-orange-500 bg-orange-500/5' : 
                  msg.type === 'private' ? 'border-purple-500 bg-purple-500/5' : 
                  'border-[#333] bg-white/[0.02]'
                }`}>
                  <div className="flex justify-between items-center mb-1 opacity-40 text-[9px]">
                    <span>{msg.sender.toUpperCase()}</span>
                    <span>{msg.type.toUpperCase()}</span>
                  </div>
                  <div className={msg.type === 'system' ? 'text-orange-400' : ''}>{msg.content}</div>
                </div>
              ))}
           </div>
        </aside>

      </main>

      {/* God Mode Overlay */}
      {showGodMode && worldState && (
        <UserControlPanel 
          actors={Object.values(worldState.actors).map((a: any) => ({ id: a.id, name: a.name }))}
          resources={worldState.resources?.map((r: any) => r.id) || ['food', 'water', 'energy']} 
        />
      )}

      {/* Popups */}
      <AnimatePresence>
        {showSettings && (
          <SettingsPanel isOpen={showSettings} onClose={() => setShowSettings(false)} />
        )}
      </AnimatePresence>
    </div>
  );
};

export default App;
