import React, { useState } from 'react';
import axios from 'axios';
// No icons used for minimalist look
import { motion } from 'framer-motion';

interface Actor {
    id: string;
    name: string;
}

interface UserControlPanelProps {
    actors: Actor[];
    resources: string[];
}

const UserControlPanel: React.FC<UserControlPanelProps> = ({ actors, resources }) => {
    const [selectedActor, setSelectedActor] = useState(actors[0]?.id || '');
    const [actionType, setActionType] = useState('MESSAGE');
    const [content, setContent] = useState('');
    const [resource, setResource] = useState(resources[0] || '');
    const [amount, setAmount] = useState(0);
    const [target, setTarget] = useState(actors[1]?.id || '');
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleGodmode = async () => {
        setIsSubmitting(true);
        try {
            let action = '';
            let params: any = {};
            if (actionType === 'MESSAGE') {
                action = 'send_message';
                params = { to: target, message: content };
            } else if (actionType === 'TRADE') {
                action = 'impersonate_action';
                params = { agent: selectedActor, function: 'trade', args: { target, resource, amount } };
            } else if (actionType === 'INJECT_RESOURCE') {
                action = 'inject_resource';
                params = { agent: selectedActor, resource, amount };
            }
            await axios.post('/api/godmode', { action, params });
            setContent('');
            alert('Godmode action sent successfully');
        } catch (err) {
            console.error(err);
            alert('Failed to send godmode action');
        } finally {
            setIsSubmitting(false);
        }
    }

    return (
        <motion.div 
            initial={{ y: 100 }} animate={{ y: 0 }}
            className="fixed bottom-0 left-0 right-0 bg-[#121212] border-t border-[#1f1f1f] p-4 z-[50] flex flex-col gap-3 shadow-2xl"
        >
            <div className="flex items-center justify-between border-b border-[#1f1f1f] pb-2">
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 bg-red-600 rounded-full" />
                    <h3 className="text-[10px] font-bold text-[#e5e5e5] tracking-widest uppercase">Admin.Intervention // God_Mode</h3>
                </div>
                <div className="text-[8px] opacity-30 font-mono tracking-widest uppercase">Direct_State_Mutation_Active</div>
            </div>

            <div className="grid grid-cols-4 gap-4">
                <div className="space-y-3">
                    <div>
                        <label className="block text-[9px] uppercase text-[#737373] mb-1 font-bold">Actor_Node</label>
                        <select 
                            value={selectedActor}
                            onChange={(e) => setSelectedActor(e.target.value)}
                            className="w-full bg-[#1a1a1a] border border-[#1f1f1f] p-1.5 text-[11px] text-white focus:outline-none focus:border-blue-500 rounded-sm appearance-none"
                        >
                            {actors.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                        </select>
                    </div>

                    <div>
                        <label className="block text-[9px] uppercase text-[#737373] mb-1 font-bold">Action_Type</label>
                        <div className="flex gap-1">
                            <button 
                                onClick={() => setActionType('MESSAGE')}
                                className={`flex-1 p-1.5 text-[10px] font-bold border transition-all rounded-sm ${actionType === 'MESSAGE' ? 'bg-blue-600 border-blue-600 text-white' : 'bg-[#1a1a1a] text-[#737373] border-[#1f1f1f] hover:text-white'}`}
                            >
                                BROADCAST
                            </button>
                            <button 
                                onClick={() => setActionType('TRADE')}
                                className={`flex-1 p-1.5 text-[10px] font-bold border transition-all rounded-sm ${actionType === 'TRADE' ? 'bg-blue-600 border-blue-600 text-white' : 'bg-[#1a1a1a] text-[#737373] border-[#1f1f1f] hover:text-white'}`}
                            >
                                TRADE_EXCH
                            </button>
                        </div>
                    </div>
                </div>

                <div className="col-span-2">
                    {actionType === 'MESSAGE' ? (
                        <div>
                            <label className="block text-[9px] uppercase text-[#737373] mb-1 font-bold">Neural_Override_Buffer</label>
                            <textarea 
                                value={content}
                                onChange={(e) => setContent(e.target.value)}
                                placeholder="AWAITING_INPUT..."
                                className="w-full bg-[#1a1a1a] border border-[#1f1f1f] p-2 text-[11px] text-white h-[76px] resize-none focus:outline-none focus:border-blue-500 rounded-sm font-mono"
                            />
                        </div>
                    ) : (
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-[9px] uppercase text-[#737373] mb-1 font-bold">Target_Entity</label>
                                <select 
                                    value={target}
                                    onChange={(e) => setTarget(e.target.value)}
                                    className="w-full bg-[#1a1a1a] border border-[#1f1f1f] p-1.5 text-[11px] text-white focus:outline-none focus:border-blue-500 rounded-sm appearance-none"
                                >
                                    {actors.filter(a => a.id !== selectedActor).map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                                </select>
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="block text-[9px] uppercase text-[#737373] mb-1 font-bold">Resource</label>
                                    <select 
                                        value={resource}
                                        onChange={(e) => setResource(e.target.value)}
                                        className="w-full bg-[#1a1a1a] border border-[#1f1f1f] p-1.5 text-[11px] text-white focus:outline-none focus:border-blue-500 rounded-sm appearance-none"
                                    >
                                        {resources.map(r => <option key={r} value={r}>{r}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-[9px] uppercase text-[#737373] mb-1 font-bold">Quantity</label>
                                    <input 
                                        type="number"
                                        value={amount}
                                        onChange={(e) => setAmount(parseInt(e.target.value))}
                                        className="w-full bg-[#1a1a1a] border border-[#1f1f1f] p-1.5 text-[11px] text-white focus:outline-none focus:border-blue-500 rounded-sm font-mono"
                                    />
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                <div className="flex flex-col justify-end">
                    <button 
                        onClick={handleInject}
                        disabled={isSubmitting}
                        className="w-full bg-blue-600 text-white font-bold py-3 text-[11px] uppercase tracking-widest hover:bg-blue-500 disabled:opacity-20 transition-all rounded-sm"
                    >
                        {isSubmitting ? 'EXECUTING...' : 'COMMIT_INTERVENTION'}
                    </button>
                </div>
            </div>
        </motion.div>
    );
};

export default UserControlPanel;
