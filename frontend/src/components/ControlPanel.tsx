import React, { useState, useEffect } from 'react';
import { Sliders, Play, Square, AlertTriangle, RefreshCw, Compass } from 'lucide-react';

interface ControlPanelProps {
  backendUrl: string;
  onCommandSent: (cmd: string) => void;
  followerActive: boolean;
  setFollowerActive: (active: boolean) => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({ 
  backendUrl, 
  onCommandSent, 
  followerActive,
  setFollowerActive 
}) => {
  const [targetLabel, setTargetLabel] = useState<string>('chair');
  const [maxSpeed, setMaxSpeed] = useState<number>(0.25);
  const [maxYaw] = useState<number>(0.5);
  const [maxPitch, setMaxPitch] = useState<number>(35);
  const [maxRoll, setMaxRoll] = useState<number>(35);
  const [safetyMessage, setSafetyMessage] = useState<string | null>(null);

  // Poll follower status on load
  useEffect(() => {
    const checkFollower = async () => {
      try {
        const res = await fetch(`${backendUrl}/vision/follow/status`);
        if (res.ok) {
          const data = await res.json();
          setFollowerActive(data.active);
        }
      } catch (err) {
        console.error('Failed to get follower status:', err);
      }
    };
    checkFollower();
  }, [backendUrl, setFollowerActive]);

  // Send directional / movement commands
  const sendCommand = async (commandName: string, speed = 0.25, turn = 0.0, duration = 1.0) => {
    onCommandSent(`Command requested: ${commandName}`);
    try {
      const response = await fetch(`${backendUrl}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: commandName,
          speed,
          turn,
          duration_sec: duration,
          safety: {
            stop_on_fall: true,
            max_pitch_deg: maxPitch,
            max_roll_deg: maxRoll
          }
        })
      });

      if (response.ok) {
        const data = await response.json();
        if (data.safety_intervention) {
          setSafetyMessage(`Safety Triggered: ${data.safety_intervention}`);
          setTimeout(() => setSafetyMessage(null), 5000);
        }
      }
    } catch (err) {
      console.error('Failed to send command:', err);
    }
  };

  // Immediate halt
  const sendStop = async () => {
    onCommandSent('Immediate Stop triggered');
    try {
      await fetch(`${backendUrl}/stop`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to stop:', err);
    }
  };

  // Reset coordinates
  const sendReset = async () => {
    onCommandSent('Reset Simulator triggered');
    try {
      await fetch(`${backendUrl}/reset`, { method: 'POST' });
    } catch (err) {
      console.error('Failed to reset:', err);
    }
  };

  // Execute scenario
  const runScenario = async () => {
    onCommandSent('Scenario started: Walk Square');
    try {
      const response = await fetch(`${backendUrl}/scenario/walk-square`, { method: 'POST' });
      if (response.ok) {
        const data = await response.json();
        onCommandSent(`Scenario finished: ${data.success ? 'SUCCESS' : 'INTERRUPTED'}`);
      }
    } catch (err) {
      console.error('Failed to run scenario:', err);
    }
  };

  // Start follower
  const startFollower = async () => {
    onCommandSent(`Target Follower started for label: ${targetLabel}`);
    try {
      const response = await fetch(`${backendUrl}/vision/follow/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_label: targetLabel,
          max_speed: maxSpeed,
          max_yaw: maxYaw
        })
      });
      if (response.ok) {
        setFollowerActive(true);
      }
    } catch (err) {
      console.error('Failed to start follower:', err);
    }
  };

  // Stop follower
  const stopFollower = async () => {
    onCommandSent('Target Follower stopped');
    try {
      const response = await fetch(`${backendUrl}/vision/follow/stop`, { method: 'POST' });
      if (response.ok) {
        setFollowerActive(false);
      }
    } catch (err) {
      console.error('Failed to stop follower:', err);
    }
  };

  return (
    <div className="hud-card flex flex-col gap-4" style={{ flex: '1 1 30%' }}>
      <div className="flex justify-between items-center mb-1" style={{ borderBottom: '1px solid rgba(0, 243, 255, 0.1)', paddingBottom: '10px' }}>
        <div className="flex items-center gap-2">
          <Sliders size={18} className="glow-cyan" style={{ color: 'var(--neon-cyan)' }} />
          <h2 className="font-orbitron" style={{ fontSize: '15px', fontWeight: 600, letterSpacing: '0.5px' }}>CONTROL PANEL</h2>
        </div>
      </div>

      {/* Safety message notification */}
      {safetyMessage && (
        <div className="font-orbitron" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px', background: 'rgba(255, 170, 0, 0.1)', border: '1px solid var(--neon-amber)', borderRadius: '6px', fontSize: '11px', color: 'var(--neon-amber)' }}>
          <AlertTriangle size={16} />
          <span>{safetyMessage}</span>
        </div>
      )}

      {/* D-Pad Controls */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', margin: '5px 0' }}>
        <button className="hud-btn" style={{ width: '100px' }} onClick={() => sendCommand('walk_forward', 0.25, 0, 1.5)}>FORWARD</button>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="hud-btn" style={{ width: '100px' }} onClick={() => sendCommand('turn_left', 0.25, 0.5, 1.0)}>LEFT</button>
          <button className="hud-btn hud-btn-danger" style={{ width: '80px' }} onClick={sendStop}>STOP</button>
          <button className="hud-btn" style={{ width: '100px' }} onClick={() => sendCommand('turn_right', 0.25, -0.5, 1.0)}>RIGHT</button>
        </div>
        <button className="hud-btn" style={{ width: '100px' }} onClick={() => sendCommand('walk_backward', 0.2, 0, 1.5)}>BACKWARD</button>
      </div>

      <div style={{ display: 'flex', gap: '10px', justifyItems: 'stretch' }}>
        <button className="hud-btn hud-btn-warning flex-1 flex items-center justify-center gap-1.5" onClick={sendReset}>
          <RefreshCw size={13} />
          RESET SIM
        </button>
        <button className="hud-btn flex-1 flex items-center justify-center gap-1.5" onClick={runScenario}>
          <Compass size={13} />
          WALK SQUARE
        </button>
      </div>

      {/* Target Follower Settings */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px' }}>
        <h3 className="font-orbitron" style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '8px' }}>VISION FOLLOW CONTROLLER</h3>
        <div className="flex flex-col gap-3 font-orbitron" style={{ fontSize: '11px' }}>
          <div className="flex justify-between items-center">
            <span>TARGET TYPE:</span>
            <select 
              value={targetLabel} 
              onChange={(e) => setTargetLabel(e.target.value)}
              style={{ background: '#020406', color: 'var(--neon-cyan)', border: '1px solid var(--border-hud)', padding: '4px 8px', borderRadius: '4px', outline: 'none', cursor: 'pointer' }}
            >
              <option value="chair">Chair (Szék)</option>
              <option value="sports_ball">Sports Ball (Labda)</option>
              <option value="table">Table (Asztal)</option>
              <option value="person">Person (Ember)</option>
            </select>
          </div>

          <div>
            <div className="flex justify-between text-[10px] mb-0.5" style={{ color: 'var(--text-secondary)' }}>
              <span>MAX FOLLOW SPEED</span>
              <span>{maxSpeed.toFixed(2)} m/s</span>
            </div>
            <input 
              type="range" min="0.05" max="0.5" step="0.05"
              value={maxSpeed} onChange={(e) => setMaxSpeed(parseFloat(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--neon-cyan)' }}
            />
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            {followerActive ? (
              <button className="hud-btn hud-btn-danger flex-1 flex items-center justify-center gap-1.5" onClick={stopFollower}>
                <Square size={12} fill="currentColor" />
                STOP FOLLOW
              </button>
            ) : (
              <button className="hud-btn flex-1 flex items-center justify-center gap-1.5" onClick={startFollower}>
                <Play size={12} fill="currentColor" />
                START FOLLOW
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Safety Limit Controls */}
      <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px' }}>
        <h3 className="font-orbitron" style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '8px' }}>SAFETY PARAMETERS</h3>
        <div className="flex flex-col gap-2 font-orbitron" style={{ fontSize: '10px' }}>
          <div>
            <div className="flex justify-between mb-0.5" style={{ color: 'var(--text-secondary)' }}>
              <span>MAX PITCH DEVIATION</span>
              <span>{maxPitch}°</span>
            </div>
            <input 
              type="range" min="10" max="60" step="5"
              value={maxPitch} onChange={(e) => setMaxPitch(parseInt(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--neon-amber)' }}
            />
          </div>

          <div>
            <div className="flex justify-between mb-0.5" style={{ color: 'var(--text-secondary)' }}>
              <span>MAX ROLL DEVIATION</span>
              <span>{maxRoll}°</span>
            </div>
            <input 
              type="range" min="10" max="60" step="5"
              value={maxRoll} onChange={(e) => setMaxRoll(parseInt(e.target.value))}
              style={{ width: '100%', accentColor: 'var(--neon-amber)' }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
