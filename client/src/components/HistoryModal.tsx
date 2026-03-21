import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { X } from 'lucide-react';

interface HistoryEvent {
  timestamp: number;
  type: string;
  data: any;
}

interface HistoryModalProps {
  agentId: string;
  onClose?: () => void;
  inline?: boolean;
}

const HistoryModal: React.FC<HistoryModalProps> = ({ agentId, onClose, inline = false }) => {
  const [history, setHistory] = useState<HistoryEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/agents/${agentId}/history`)
      .then(res => res.json())
      .then(data => {
        setHistory(data.history || []);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [agentId]);

  const content = (
    <div className={`flex flex-col h-full bg-[#0a0a0a] ${inline ? '' : 'bg-[#121212] border border-[#1f1f1f] w-full max-w-4xl h-[80vh] shadow-2xl rounded-sm overflow-hidden'}`}>
      {!inline && (
        <div className="p-4 border-b border-[#1f1f1f] flex justify-between items-center bg-[#161616]">
          <div>
            <h2 className="text-sm font-black uppercase tracking-widest text-white">Agent Intelligence Audit</h2>
            <p className="text-[10px] font-mono opacity-40 uppercase">Node: {agentId}</p>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-white/5 rounded transition-all">
            <X className="w-4 h-4 text-white/40" />
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-4 font-mono text-[11px]">
        {loading ? (
          <div className="h-full flex items-center justify-center opacity-20">
            LOADING_TELEMETRY...
          </div>
        ) : history.length === 0 ? (
          <div className="h-full flex items-center justify-center opacity-20 uppercase tracking-widest">
            NO_DATA_AVAILABLE
          </div>
        ) : (
          history.slice().reverse().map((event, i) => (
            <div key={i} className="flex gap-4 border-b border-[#1f1f1f] pb-3 group">
              <div className="w-16 shrink-0 opacity-30 text-[9px] tabular-nums">
                {new Date(event.timestamp * 1000).toLocaleTimeString([], { hour12: false })}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-1.5 py-0.5 rounded-[2px] text-[8px] font-bold uppercase tracking-tighter ${
                    event.type === 'thought' ? 'bg-blue-500/10 text-blue-400' :
                    event.type === 'action_intent' ? 'bg-orange-500/10 text-orange-400' :
                    'bg-emerald-500/10 text-emerald-400'
                  }`}>
                    {event.type.replace('_', '.')}
                  </span>
                </div>
                <div className="text-[#e5e5e5] leading-relaxed">
                  {event.type === 'thought' && <p className="opacity-60 italic">"{event.data.content}"</p>}
                  {event.type === 'message_out' && (
                    <p><span className="text-blue-500 font-bold">&gt; TO {event.data.target}:</span> {event.data.content}</p>
                  )}
                  {event.type === 'message_in' && (
                    <p><span className="text-purple-500 font-bold">&lt; FROM {event.data.sender}:</span> {event.data.content}</p>
                  )}
                  {event.type === 'broadcast_out' && (
                    <p><span className="text-blue-500 font-bold">📢 BROADCAST:</span> {event.data.content}</p>
                  )}
                  {event.type === 'action_intent' && (
                    <div className="flex items-center gap-2 text-orange-400 font-bold bg-orange-500/5 px-2 py-1 border border-orange-500/10">
                      CMD:: {event.data.type}({Object.entries(event.data).filter(([k]) => !['type', 'sender'].includes(k)).map(([k,v]) => `${k}=${v}`).join(', ')})
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );

  if (inline) return content;

  return (
    <motion.div 
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center p-8 bg-black/90"
    >
      <motion.div 
        initial={{ scale: 0.98 }} animate={{ scale: 1 }}
        className="flex flex-col h-full w-full max-w-4xl"
      >
        {content}
      </motion.div>
    </motion.div>
  );
};

export default HistoryModal;
