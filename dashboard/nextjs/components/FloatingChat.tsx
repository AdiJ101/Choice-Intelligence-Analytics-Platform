'use client';

import { useState, useRef, useEffect } from 'react';
import { api } from '@/lib/api';

type Message = { role: 'user' | 'assistant'; content: string };

export default function FloatingChat() {
  const [isOpen, setIsOpen] = useState(false);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput('');
    const newMsgs: Message[] = [...msgs, { role: 'user', content: q }];
    setMsgs(newMsgs);
    setLoading(true);
    try {
      const res = await api.askAI(q, msgs.map(m => ({ role: m.role, content: m.content })));
      setMsgs([...newMsgs, { role: 'assistant', content: res.answer }]);
    } catch {
      setMsgs([...newMsgs, { role: 'assistant', content: '⚠️ Could not get an answer. Please check the AI service is running.' }]);
    } finally {
      setLoading(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  }, [isOpen, msgs.length]);

  return (
    <div style={{ position: 'fixed', bottom: 30, right: 30, zIndex: 9999, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', pointerEvents: 'none' }}>
      {isOpen && (
        <div style={{
          width: 380, height: 500, background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(16px)',
          borderRadius: 24, boxShadow: '0 8px 32px rgba(0,0,0,0.12)', border: '1px solid rgba(226,232,240,0.8)',
          display: 'flex', flexDirection: 'column', marginBottom: 16, overflow: 'hidden', pointerEvents: 'auto',
          transformOrigin: 'bottom right', animation: 'scaleIn 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
          {/* Header */}
          <div style={{ padding: '16px 20px', borderBottom: '1px solid rgba(226,232,240,0.5)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'linear-gradient(135deg, rgba(124,58,237,0.05), rgba(139,92,246,0.05))' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 32, height: 32, borderRadius: 10, background: 'linear-gradient(135deg, #7c3aed, #8b5cf6)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, color: 'white' }}>🤖</div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a' }}>AI Assistant</div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>Ask about your content & audience</div>
              </div>
            </div>
            <button 
              onClick={() => setIsOpen(false)}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: 20, color: '#94a3b8', padding: 4 }}
            >
              ✕
            </button>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
            {msgs.length === 0 && (
              <div style={{ color: '#94a3b8', fontSize: 13, textAlign: 'center', padding: '24px 0', fontStyle: 'italic', lineHeight: 1.6 }}>
                Hi there! 👋<br />Try asking: "What topics are viewers asking about?" or "Which brands have the best engagement?"
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                <div style={{
                  maxWidth: '85%', padding: '10px 14px', borderRadius: m.role === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
                  background: m.role === 'user' ? 'linear-gradient(135deg, #7c3aed, #8b5cf6)' : '#f8fafc',
                  color: m.role === 'user' ? 'white' : '#334155',
                  fontSize: 13.5, lineHeight: 1.5,
                  border: m.role === 'assistant' ? '1px solid rgba(226,232,240,0.7)' : 'none',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                }}>
                  {m.content}
                </div>
              </div>
            ))}
            {loading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div style={{ padding: '10px 14px', borderRadius: '18px 18px 18px 4px', background: '#f8fafc', border: '1px solid rgba(226,232,240,0.7)', color: '#94a3b8', fontSize: 13 }}>
                  Thinking<span className="thinking-dots">...</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div style={{ padding: '12px 16px', borderTop: '1px solid rgba(226,232,240,0.5)', background: '#fff' }}>
            <div style={{ display: 'flex', gap: 8, background: '#f8fafc', border: '1px solid rgba(226,232,240,0.8)', borderRadius: 20, padding: '4px 4px 4px 16px', alignItems: 'center' }}>
              <input
                style={{
                  flex: 1, border: 'none', background: 'transparent', outline: 'none',
                  fontSize: 14, color: '#0f172a', padding: '6px 0',
                }}
                placeholder="Message AI..."
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              />
              <button
                onClick={send}
                disabled={loading || !input.trim()}
                style={{
                  width: 32, height: 32, borderRadius: 16, border: 'none', cursor: (loading || !input.trim()) ? 'default' : 'pointer',
                  background: (loading || !input.trim()) ? '#e2e8f0' : '#7c3aed', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s'
                }}
              >
                ↑
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          style={{
            pointerEvents: 'auto',
            width: 60, height: 60, borderRadius: 30, border: 'none', cursor: 'pointer',
            background: 'linear-gradient(135deg, #7c3aed, #8b5cf6)', color: 'white',
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 26,
            boxShadow: '0 8px 24px rgba(124,58,237,0.4)', transition: 'transform 0.2s, box-shadow 0.2s',
          }}
          onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.05)'; e.currentTarget.style.boxShadow = '0 12px 28px rgba(124,58,237,0.5)'; }}
          onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.boxShadow = '0 8px 24px rgba(124,58,237,0.4)'; }}
        >
          ✨
        </button>
      )}
      
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes scaleIn {
          from { opacity: 0; transform: scale(0.9) translateY(20px); }
          to { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}} />
    </div>
  );
}
