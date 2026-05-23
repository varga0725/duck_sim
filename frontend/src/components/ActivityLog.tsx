import React, { useRef, useEffect } from 'react';
import { Terminal, Trash2 } from 'lucide-react';

export interface LogMessage {
  timestamp: string;
  type: 'info' | 'command' | 'speech' | 'ai' | 'warning' | 'error';
  message: string;
}

interface ActivityLogProps {
  logs: LogMessage[];
  onClear: () => void;
}

export const ActivityLog: React.FC<ActivityLogProps> = ({ logs, onClear }) => {
  const terminalEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const getLogStyle = (type: LogMessage['type']) => {
    switch (type) {
      case 'command': return { color: 'var(--neon-cyan)', prefix: '[CMD]' };
      case 'speech': return { color: 'var(--neon-amber)', prefix: '[🎙️]' };
      case 'ai': return { color: '#b98eff', prefix: '[🤖]' };
      case 'warning': return { color: 'var(--neon-amber)', prefix: '[⚠️]' };
      case 'error': return { color: 'var(--neon-red)', prefix: '[ERR]' };
      default: return { color: 'var(--text-secondary)', prefix: '[SYS]' };
    }
  };

  return (
    <div className="hud-card flex flex-col gap-3" style={{ flex: '1 1 35%', minHeight: '220px' }}>
      <div className="flex justify-between items-center mb-1" style={{ borderBottom: '1px solid rgba(0, 243, 255, 0.1)', paddingBottom: '10px' }}>
        <div className="flex items-center gap-2">
          <Terminal size={18} className="glow-cyan" style={{ color: 'var(--neon-cyan)' }} />
          <h2 className="font-orbitron" style={{ fontSize: '15px', fontWeight: 600, letterSpacing: '0.5px' }}>ACTIVITY CONSOLE LOG</h2>
        </div>
        <button 
          className="hud-btn flex items-center gap-1" 
          onClick={onClear}
          style={{ padding: '3px 8px', fontSize: '10px', borderColor: 'rgba(255,255,255,0.15)', color: 'var(--text-secondary)' }}
        >
          <Trash2 size={11} />
          CLEAR
        </button>
      </div>

      {/* Terminal View */}
      <div style={{ 
        flex: 1, 
        backgroundColor: '#020406', 
        borderRadius: '8px', 
        padding: '12px', 
        fontFamily: 'monospace', 
        fontSize: '11px', 
        lineHeight: '1.6', 
        overflowY: 'auto', 
        maxHeight: '220px', 
        border: '1px solid rgba(0, 243, 255, 0.05)',
        boxShadow: 'inset 0 0 10px rgba(0,0,0,0.8)'
      }}>
        {logs.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', textAlign: 'center', marginTop: '40px' }} className="font-orbitron">
            NO ACTIVITY LOGGED
          </div>
        ) : (
          logs.map((log, index) => {
            const style = getLogStyle(log.type);
            return (
              <div key={index} style={{ marginBottom: '6px', wordBreak: 'break-word', display: 'flex', gap: '8px' }}>
                <span style={{ color: 'rgba(255,255,255,0.2)' }}>[{log.timestamp}]</span>
                <span style={{ color: style.color, fontWeight: 'bold' }}>{style.prefix}</span>
                <span style={{ color: log.type === 'info' ? 'var(--text-primary)' : style.color }}>
                  {log.message}
                </span>
              </div>
            );
          })
        )}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
};
