import React, { useEffect, useState } from 'react';
import { Activity } from 'lucide-react';

interface TelemetryChartsProps {
  speed: number;
  height: number;
}

export const TelemetryCharts: React.FC<TelemetryChartsProps> = ({ speed, height }) => {
  const [history, setHistory] = useState<{ speed: number; height: number }[]>([]);

  // Accumulate rolling telemetry history (capped at 50 data points)
  useEffect(() => {
    setHistory((prev) => {
      const next = [...prev, { speed, height }];
      if (next.length > 50) {
        next.shift();
      }
      return next;
    });
  }, [speed, height]);

  // SVG Helper: Generate path string for a dataset
  const generatePath = (
    data: number[],
    minVal: number,
    maxVal: number,
    width: number,
    height: number
  ) => {
    if (data.length < 2) return '';
    const points = data.map((val, idx) => {
      const x = (idx / (data.length - 1)) * width;
      // Clamp value between min and max
      const clamped = Math.max(minVal, Math.min(maxVal, val));
      // Invert Y axis for SVG rendering
      const y = height - ((clamped - minVal) / (maxVal - minVal)) * height;
      return `${x},${y}`;
    });
    return `M ${points.join(' L ')}`;
  };

  const chartWidth = 300;
  const chartHeight = 65;

  const speedData = history.map((h) => h.speed);
  const heightData = history.map((h) => h.height);

  const speedPath = generatePath(speedData, -0.5, 0.5, chartWidth, chartHeight);
  const heightPath = generatePath(heightData, 0.0, 0.3, chartWidth, chartHeight);

  return (
    <div className="hud-card flex flex-col gap-4" style={{ flex: '1 1 30%' }}>
      <div className="flex justify-between items-center mb-1" style={{ borderBottom: '1px solid rgba(0, 243, 255, 0.1)', paddingBottom: '10px' }}>
        <div className="flex items-center gap-2">
          <Activity size={18} className="glow-cyan" style={{ color: 'var(--neon-cyan)' }} />
          <h2 className="font-orbitron" style={{ fontSize: '15px', fontWeight: 600, letterSpacing: '0.5px' }}>TELEMETRY GRAPHS</h2>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
        {/* Speed Chart */}
        <div>
          <div className="flex justify-between font-orbitron text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
            <span>VELOCITY (m/s)</span>
            <span className="glow-cyan" style={{ color: 'var(--neon-cyan)' }}>{speed.toFixed(2)} m/s</span>
          </div>
          <div style={{ position: 'relative', width: '100%', height: `${chartHeight}px`, background: 'rgba(2, 4, 6, 0.6)', borderRadius: '6px', border: '1px solid rgba(0, 243, 255, 0.05)', padding: '2px 0', overflow: 'hidden' }}>
            {/* Grid Line overlay */}
            <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
              <line x1="0" y1={chartHeight / 2} x2="100%" y2={chartHeight / 2} stroke="rgba(0, 243, 255, 0.1)" strokeWidth="0.5" strokeDasharray="3 3" />
            </svg>
            
            <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} width="100%" height="100%" preserveAspectRatio="none">
              {/* Plot Path */}
              {speedPath && (
                <path 
                  d={speedPath} 
                  fill="none" 
                  stroke="var(--neon-cyan)" 
                  strokeWidth="1.5"
                  style={{ filter: 'drop-shadow(0px 0px 4px var(--neon-cyan-glow))' }}
                />
              )}
            </svg>
          </div>
        </div>

        {/* Height Chart */}
        <div>
          <div className="flex justify-between font-orbitron text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
            <span>Z-HEIGHT (m)</span>
            <span className="glow-amber" style={{ color: 'var(--neon-amber)' }}>{height.toFixed(2)} m</span>
          </div>
          <div style={{ position: 'relative', width: '100%', height: `${chartHeight}px`, background: 'rgba(2, 4, 6, 0.6)', borderRadius: '6px', border: '1px solid rgba(0, 243, 255, 0.05)', padding: '2px 0', overflow: 'hidden' }}>
            {/* Grid Line overlay */}
            <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}>
              <line x1="0" y1={chartHeight / 2} x2="100%" y2={chartHeight / 2} stroke="rgba(255, 170, 0, 0.1)" strokeWidth="0.5" strokeDasharray="3 3" />
            </svg>
            
            <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} width="100%" height="100%" preserveAspectRatio="none">
              {/* Plot Path */}
              {heightPath && (
                <path 
                  d={heightPath} 
                  fill="none" 
                  stroke="var(--neon-amber)" 
                  strokeWidth="1.5"
                  style={{ filter: 'drop-shadow(0px 0px 4px var(--neon-amber-glow))' }}
                />
              )}
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
};
