import React from 'react';
import { motion } from 'framer-motion';

interface ThoughtPreviewProps {
  thoughts: Record<string, string>;
  onClose: () => void;
}

const ThoughtPreview: React.FC<ThoughtPreviewProps> = ({ thoughts, onClose }) => {
  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.9 }} 
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-8 bg-black/60 backdrop-blur-sm"
    >
      <div className="bg-black border border-white/20 w-full max-w-4xl max-h-[80vh] overflow-hidden flex flex-col shadow-2xl">
        <div className="p-4 border-b border-white/10 flex justify-between items-center bg-white/[0.02]">
          <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white">Neural_Dump_Stream</h2>
          <button onClick={onClose} className="text-[8px] opacity-40 hover:opacity-100 transition-opacity uppercase font-bold tracking-widest border border-white/10 px-2 py-1">CLOSE_X</button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-2 gap-4">
          {Object.entries(thoughts).map(([actor, thought]) => (
            <div key={actor} className="p-4 bg-white/[0.01] border border-white/10">
              <span className="block text-[8px] font-black uppercase text-white/40 mb-2 tracking-widest border-b border-white/5 pb-1">{actor}</span>
              <p className="text-[10px] leading-relaxed font-mono italic text-neutral-400">"{thought || 'NULL_STREAM_IDLE...'}"</p>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
};

export default ThoughtPreview;
