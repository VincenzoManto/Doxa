import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Save, RefreshCw, AlertCircle } from 'lucide-react';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const SettingsPanel: React.FC<SettingsPanelProps> = ({ isOpen, onClose }) => {
  const [config, setConfig] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);

  // SettingsPanel will be repurposed for academic scenario settings or left as a placeholder for now.
  // Remove legacy /api/config logic. You may add scenario settings here in the future.

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="w-full max-w-4xl h-[80vh] bg-black border border-white/20 shadow-2xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-white/10 bg-white/[0.02]">
              <div className="flex items-center gap-3">
                <div className="p-2 border border-white/10">
                  <RefreshCw className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h2 className="text-xs font-black text-white uppercase tracking-widest">World_Configuration</h2>
                  <p className="text-[8px] text-neutral-500 uppercase tracking-tighter">Edit simulation parameters (YAML)</p>
                </div>
              </div>
              <button 
                onClick={onClose}
                className="p-1 border border-white/10 hover:bg-neutral-800 transition-colors"
              >
                <X className="w-4 h-4 text-white" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-hidden p-4 relative bg-black">
              {isLoading && (
                <div className="absolute inset-0 z-10 bg-black/50 backdrop-blur-sm flex items-center justify-center">
                  <div className="w-8 h-8 border border-white/20 border-t-white animate-spin"></div>
                </div>
              )}
              
              <textarea
                value={config}
                onChange={(e) => setConfig(e.target.value)}
                autoFocus
                className="w-full h-full bg-black text-neutral-300 font-mono text-[10px] p-4 border border-white/10 focus:border-white/40 outline-none resize-none scrollbar-hide"
                placeholder="# SYSTEM_IDLE: AWAITING_CONFIG_PARAM..."
              />
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-white/10 bg-white/[0.02] flex items-center justify-between">
              <div className="flex items-center gap-4">
                {error && (
                  <div className="flex items-center gap-2 text-white bg-neutral-900 border border-white/20 px-2 py-1 text-[8px] uppercase tracking-widest">
                    <AlertCircle className="w-3 h-3" />
                    <span>{error}</span>
                  </div>
                )}
                {success && (
                  <div className="flex items-center gap-2 text-white border border-white/20 px-2 py-1 text-[8px] uppercase tracking-widest animate-pulse">
                    <Save className="w-3 h-3" />
                    <span>SAVE_COMPLETE // OK</span>
                  </div>
                )}
              </div>
              
              <div className="flex gap-2">
                <button
                  onClick={fetchConfig}
                  className="px-3 py-1.5 border border-white/10 hover:bg-neutral-800 text-white text-[9px] uppercase tracking-widest transition-colors flex items-center gap-2"
                >
                  <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
                  RE_LOAD
                </button>
                <button
                  onClick={handleSave}
                  disabled={isLoading}
                  className="px-4 py-1.5 bg-white text-black text-[9px] font-black uppercase tracking-widest hover:bg-neutral-200 disabled:opacity-20 transition-all flex items-center gap-2"
                >
                  <Save className="w-3 h-3" />
                  COMMIT_CHANGES
                </button>
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default SettingsPanel;
