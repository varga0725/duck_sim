import React, { useState, useEffect, useRef } from 'react';
import { FPVCamera } from './components/FPVCamera';
import { OccupancyMap } from './components/OccupancyMap';
import { OrientationWidget } from './components/OrientationWidget';
import { TelemetryCharts } from './components/TelemetryCharts';
import { ControlPanel } from './components/ControlPanel';
import { ActivityLog } from './components/ActivityLog';
import type { LogMessage } from './components/ActivityLog';
import { Wifi, WifiOff, Cpu } from 'lucide-react';
import './App.css';

const BACKEND_HOST = window.location.hostname || 'localhost';
const BACKEND_URL = `http://${BACKEND_HOST}:8765`;
const WS_URL = `ws://${BACKEND_HOST}:8765/ws`;

interface RobotTelemetryState {
  robot: string;
  status: string;
  sim_time: number;
  position: [number, number, number];
  orientation: {
    roll_deg: number;
    pitch_deg: number;
    yaw_deg: number;
  };
  feet_contact: {
    left: boolean;
    right: boolean;
  };
  fallen: boolean;
  last_command: string;
  stability: {
    status: 'stable' | 'unstable' | 'fallen';
    reasons: string[];
  };
}

export const App: React.FC = () => {
  const [connected, setConnected] = useState<boolean>(false);
  const [simMode, setSimMode] = useState<string>('mock');
  const [simTime, setSimTime] = useState<number>(0.0);
  const [robotPos, setRobotPos] = useState<[number, number, number]>([0.0, 0.0, 0.41]);
  const [orientation, setOrientation] = useState({ roll: 0.0, pitch: 0.0, yaw: 0.0 });
  const [feetContact, setFeetContact] = useState({ left: true, right: true });
  const [stability, setStability] = useState<{ status: 'stable' | 'unstable' | 'fallen'; reasons: string[] }>({
    status: 'stable',
    reasons: []
  });
  
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [followerActive, setFollowerActive] = useState<boolean>(false);
  const [logs, setLogs] = useState<LogMessage[]>([]);
  
  const wsRef = useRef<WebSocket | null>(null);
  const lastCmdRef = useRef<string>('');
  const lastStabilityStatusRef = useRef<'stable' | 'unstable' | 'fallen'>('stable');
  const lastFallenRef = useRef<boolean>(false);

  // Helper to add logs to the console
  const addLog = (type: LogMessage['type'], message: string) => {
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    setLogs((prev) => [...prev, { timestamp: timeStr, type, message }]);
  };

  // Fetch health check for simulation mode
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/health`);
        if (response.ok) {
          const data = await response.json();
          setSimMode(data.sim_mode);
        }
      } catch (err) {
        console.error('FastAPI server offline');
      }
    };
    checkHealth();
  }, []);

  // WebSocket Connection Lifecycle
  useEffect(() => {
    let reconnectTimeout: number;

    const connectWebSocket = () => {
      addLog('info', `Connecting to WebSocket telemetry at ${WS_URL}...`);
      
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        addLog('info', 'WebSocket connection established. Telemetry feed active.');
      };

      ws.onmessage = (event) => {
        try {
          const state: RobotTelemetryState = JSON.parse(event.data);
          
          // Update States
          setSimTime(state.sim_time);
          setRobotPos(state.position);
          setOrientation({
            roll: state.orientation.roll_deg,
            pitch: state.orientation.pitch_deg,
            yaw: state.orientation.yaw_deg
          });
          setFeetContact({
            left: state.feet_contact.left,
            right: state.feet_contact.right
          });
          setStability({
            status: state.stability.status,
            reasons: state.stability.reasons
          });

          // Log state transitions
          if (state.last_command !== lastCmdRef.current && state.last_command !== '') {
            addLog('command', `Executed: ${state.last_command} (status: ${state.status})`);
            lastCmdRef.current = state.last_command;
          }

          if (state.fallen !== lastFallenRef.current) {
            if (state.fallen) {
              addLog('error', 'CRITICAL ALERT: Robot fell down! Auto-stop and safety recovery triggered.');
            }
            lastFallenRef.current = state.fallen;
          }

          if (state.stability.status !== lastStabilityStatusRef.current) {
            if (state.stability.status === 'unstable') {
              addLog('warning', `Stability warning: ${state.stability.reasons.join(', ')}`);
            }
            lastStabilityStatusRef.current = state.stability.status;
          }

        } catch (e) {
          // Check if it is a command acknowledgement event
          try {
            const payload = JSON.parse(event.data);
            if (payload.event === 'command_received') {
              // Option to log socket command confirms
            } else if (payload.event === 'error') {
              addLog('error', `WebSocket Error: ${payload.detail}`);
            }
          } catch (_) {
            console.error('Failed to parse WS payload:', event.data);
          }
        }
      };

      ws.onclose = () => {
        setConnected(false);
        addLog('error', 'WebSocket connection closed. Retrying in 3s...');
        reconnectTimeout = window.setTimeout(connectWebSocket, 3000);
      };

      ws.onerror = (err) => {
        console.error('WebSocket encountered an error:', err);
        ws.close();
      };
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      clearTimeout(reconnectTimeout);
    };
  }, []);

  // Poll follower status for active-searching overlays
  useEffect(() => {
    const pollFollower = async () => {
      if (!followerActive) {
        setIsSearching(false);
        return;
      }
      try {
        const response = await fetch(`${BACKEND_URL}/vision/follow/status`);
        if (response.ok) {
          const data = await response.json();
          const searching = data.state === 'SEARCHING';
          setIsSearching(searching);
        }
      } catch (err) {
        console.error('Failed to poll follower status:', err);
      }
    };

    pollFollower();
    const interval = setInterval(pollFollower, 500);
    return () => clearInterval(interval);
  }, [followerActive]);

  return (
    <div className="dashboard-container">
      {/* HUD Header */}
      <header className="hud-header">
        <div className="header-left">
          <Cpu className="pulse-slow" size={24} style={{ color: 'var(--neon-cyan)' }} />
          <div>
            <h1 className="font-orbitron glow-cyan">OPEN DUCK MINI</h1>
            <p className="subtitle font-orbitron">FLIGHT & Locomotion BRIDGE V3.1</p>
          </div>
        </div>

        <div className="header-right font-orbitron">
          <div className="indicator-badge">
            <span className="label">MODE:</span>
            <span className="value glow-amber" style={{ color: 'var(--neon-amber)' }}>{simMode.toUpperCase()}</span>
          </div>

          <div className="indicator-badge">
            <span className="label">TIME:</span>
            <span className="value">{simTime.toFixed(2)}s</span>
          </div>

          <div className={`connection-badge ${connected ? 'online' : 'offline'}`}>
            {connected ? (
              <>
                <Wifi size={14} />
                <span>WS CONNECTED</span>
              </>
            ) : (
              <>
                <WifiOff size={14} />
                <span>WS OFFLINE</span>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main Panel Grid */}
      <main className="dashboard-grid">
        {/* Left Column: Visual Feeds */}
        <section className="dashboard-col">
          <FPVCamera backendUrl={BACKEND_URL} isSearching={isSearching} />
          <OccupancyMap backendUrl={BACKEND_URL} robotPos={robotPos} robotYaw={orientation.yaw} />
        </section>

        {/* Right Column: Telemetry & Log Consoles */}
        <section className="dashboard-col">
          <div className="row-panels">
            <OrientationWidget 
              roll={orientation.roll} 
              pitch={orientation.pitch} 
              yaw={orientation.yaw} 
              feetContact={feetContact} 
              stability={stability}
            />
            <TelemetryCharts speed={orientation.pitch !== 0 ? 0.25 : 0.0} height={robotPos[2]} />
          </div>
          <div className="row-panels" style={{ alignItems: 'stretch' }}>
            <ControlPanel 
              backendUrl={BACKEND_URL} 
              onCommandSent={(msg) => addLog('info', msg)}
              followerActive={followerActive}
              setFollowerActive={setFollowerActive}
            />
            <ActivityLog logs={logs} onClear={() => setLogs([])} />
          </div>
        </section>
      </main>
    </div>
  );
};

export default App;
