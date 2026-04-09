import React, { useState, useEffect, useRef } from 'react';
import { Bot, Send } from 'lucide-react';
import { chatbotQuery } from '../api';
import type { ChatMessage } from '../types';

export function ChatbotPanel() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function handleSend() {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: q }]);
    setLoading(true);
    try {
      const answer = await chatbotQuery(q);
      setMessages((prev) => [...prev, { role: 'assistant', content: answer }]);
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: 'Error: could not get a response from the chatbot.' }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel compact-panel chatbot-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">AI Assistant</p>
          <h3>Simulation chatbot</h3>
        </div>
        <Bot size={16} className="header-icon" />
      </div>
      <div className="chatbot-messages">
        {messages.length === 0 && (
          <div className="empty-state">Ask anything about the simulation…</div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chatbot-msg chatbot-msg-${msg.role}`}>
            <span className="chatbot-msg-label">{msg.role === 'user' ? 'You' : 'Doxa'}</span>
            <p className="chatbot-msg-text">{msg.content}</p>
          </div>
        ))}
        {loading && (
          <div className="chatbot-msg chatbot-msg-assistant">
            <span className="chatbot-msg-label">Doxa</span>
            <p className="chatbot-typing">Thinking…</p>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="chatbot-input-row">
        <input
          className="chatbot-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSend(); } }}
          placeholder="Ask about the simulation…"
          disabled={loading}
        />
        <button type="button" className="primary-button chatbot-send-btn" disabled={loading || !input.trim()} onClick={() => void handleSend()}>
          <Send size={14} />
        </button>
      </div>
    </section>
  );
}