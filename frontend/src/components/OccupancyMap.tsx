import React, { useEffect, useRef, useState } from 'react';
import { Map, RotateCcw } from 'lucide-react';

interface Landmark {
  x: number;
  y: number;
  confidence: number;
  last_updated: number;
}

interface MapData {
  grid_size: number;
  resolution: number;
  landmarks: { [label: string]: Landmark };
  grid: number[][];
}

interface OccupancyMapProps {
  backendUrl: string;
  robotPos: [number, number, number]; // [x, y, z]
  robotYaw: number; // yaw in degrees
}

export const OccupancyMap: React.FC<OccupancyMapProps> = ({ backendUrl, robotPos, robotYaw }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [mapData, setMapData] = useState<MapData | null>(null);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch map data at 2Hz (every 500ms)
  useEffect(() => {
    const fetchMap = async () => {
      try {
        const response = await fetch(`${backendUrl}/map`);
        if (response.ok) {
          const data = await response.json();
          setMapData(data);
          setError(null);
        } else {
          setError('Map model uninitialized');
        }
      } catch (err) {
        setError('Connection to map API failed');
      }
    };

    fetchMap(); // Initial fetch
    const interval = setInterval(fetchMap, 500);

    return () => clearInterval(interval);
  }, [backendUrl]);

  // Reset the spatial map memory
  const handleResetMap = async () => {
    setIsResetting(true);
    try {
      const response = await fetch(`${backendUrl}/map/reset`, { method: 'POST' });
      if (response.ok) {
        // Force refresh
        setMapData(null);
      }
    } catch (err) {
      console.error('Failed to reset map:', err);
    } finally {
      setIsResetting(false);
    }
  };

  // Draw loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear canvas
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const gridSize = mapData?.grid_size || 80;
    const resolution = mapData?.resolution || 0.1;
    const halfGrid = gridSize / 2;
    const cellWidth = canvas.width / gridSize;
    const cellHeight = canvas.height / gridSize;

    // 1. Draw Occupancy Grid
    if (mapData?.grid) {
      for (let gy = 0; gy < gridSize; gy++) {
        for (let gx = 0; gx < gridSize; gx++) {
          const val = mapData.grid[gy][gx];
          
          // Invert Y axis to draw North at the top
          const canvasY = (gridSize - 1 - gy) * cellHeight;
          const canvasX = gx * cellWidth;

          if (val === 2) {
            // Occupied cell (Obstacle)
            ctx.fillStyle = 'rgba(255, 170, 0, 0.75)';
            ctx.fillRect(canvasX, canvasY, cellWidth - 0.5, cellHeight - 0.5);
            // Draw obstacle inner grid highlight
            ctx.strokeStyle = 'rgba(255, 170, 0, 0.3)';
            ctx.strokeRect(canvasX, canvasY, cellWidth, cellHeight);
          } else if (val === 0) {
            // Unknown cell
            ctx.fillStyle = 'rgba(30, 41, 59, 0.2)';
            ctx.fillRect(canvasX, canvasY, cellWidth - 0.5, cellHeight - 0.5);
          } else {
            // Free cell
            ctx.fillStyle = 'rgba(8, 12, 16, 0.8)';
            ctx.fillRect(canvasX, canvasY, cellWidth - 0.5, cellHeight - 0.5);
          }
        }
      }
    } else {
      // Draw placeholders grid
      ctx.strokeStyle = 'rgba(0, 243, 255, 0.05)';
      ctx.lineWidth = 0.5;
      for (let i = 0; i < canvas.width; i += cellWidth * 4) {
        ctx.beginPath();
        ctx.moveTo(i, 0);
        ctx.lineTo(i, canvas.height);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(0, i);
        ctx.lineTo(canvas.width, i);
        ctx.stroke();
      }
    }

    // Coordinate conversion helper
    const getCanvasCoords = (worldX: number, worldY: number) => {
      const gx = worldX / resolution + halfGrid;
      const gy = worldY / resolution + halfGrid;
      return {
        x: gx * cellWidth,
        y: (gridSize - gy) * cellHeight,
      };
    };

    // 2. Draw Grid Axes
    ctx.strokeStyle = 'rgba(0, 243, 255, 0.15)';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    // Center lines
    ctx.beginPath();
    ctx.moveTo(canvas.width / 2, 0);
    ctx.lineTo(canvas.width / 2, canvas.height);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, canvas.height / 2);
    ctx.lineTo(canvas.width, canvas.height / 2);
    ctx.stroke();
    ctx.setLineDash([]); // Reset dash

    // 3. Draw Landmarks
    if (mapData?.landmarks) {
      Object.entries(mapData.landmarks).forEach(([label, lm]) => {
        const { x, y } = getCanvasCoords(lm.x, lm.y);

        // Draw crosshair at landmark
        ctx.strokeStyle = 'var(--neon-amber)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(x, y, 8, 0, Math.PI * 2);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(x - 12, y);
        ctx.lineTo(x + 12, y);
        ctx.moveTo(x, y - 12);
        ctx.lineTo(x, y + 12);
        ctx.stroke();

        // Draw text label
        ctx.fillStyle = '#000';
        const labelText = `${label.toUpperCase()} (${(lm.confidence * 100).toFixed(0)}%)`;
        ctx.font = 'bold 9px Orbitron';
        const textWidth = ctx.measureText(labelText).width;

        ctx.fillStyle = 'rgba(255, 170, 0, 0.9)';
        ctx.fillRect(x - textWidth / 2 - 4, y - 24, textWidth + 8, 14);

        ctx.fillStyle = '#000000';
        ctx.fillText(labelText, x - textWidth / 2, y - 14);
      });
    }

    // 4. Draw Robot Tracker (Duck Icon / Arrow)
    const rx = robotPos[0];
    const ry = robotPos[1];
    const { x: rCanvasX, y: rCanvasY } = getCanvasCoords(rx, ry);

    // Draw robot outer glow
    const gradient = ctx.createRadialGradient(rCanvasX, rCanvasY, 2, rCanvasX, rCanvasY, 15);
    gradient.addColorStop(0, 'rgba(0, 243, 255, 0.6)');
    gradient.addColorStop(1, 'rgba(0, 243, 255, 0)');
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(rCanvasX, rCanvasY, 15, 0, Math.PI * 2);
    ctx.fill();

    // Draw robot body (cyan circle)
    ctx.fillStyle = 'var(--neon-cyan)';
    ctx.beginPath();
    ctx.arc(rCanvasX, rCanvasY, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Draw yaw heading indicator (arrow/nose)
    const yawRad = (robotYaw * Math.PI) / 180;
    const arrowLen = 14;
    const headX = rCanvasX + arrowLen * Math.cos(yawRad);
    const headY = rCanvasY - arrowLen * Math.sin(yawRad); // Invert Y for canvas

    ctx.strokeStyle = 'var(--neon-cyan)';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(rCanvasX, rCanvasY);
    ctx.lineTo(headX, headY);
    ctx.stroke();

    // Draw small arrow head tips
    const arrowTipAngle = Math.PI / 6; // 30 deg
    const tipLen = 5;
    ctx.beginPath();
    ctx.moveTo(headX, headY);
    ctx.lineTo(
      headX - tipLen * Math.cos(yawRad - arrowTipAngle),
      headY + tipLen * Math.sin(yawRad - arrowTipAngle)
    );
    ctx.moveTo(headX, headY);
    ctx.lineTo(
      headX - tipLen * Math.cos(yawRad + arrowTipAngle),
      headY + tipLen * Math.sin(yawRad + arrowTipAngle)
    );
    ctx.stroke();

  }, [mapData, robotPos, robotYaw]);

  return (
    <div className="hud-card flex flex-col gap-3" style={{ flex: '1 1 45%' }}>
      <div className="flex justify-between items-center mb-2" style={{ borderBottom: '1px solid rgba(0, 243, 255, 0.1)', paddingBottom: '10px' }}>
        <div className="flex items-center gap-2">
          <Map size={18} className="glow-cyan" style={{ color: 'var(--neon-cyan)' }} />
          <h2 className="font-orbitron" style={{ fontSize: '15px', fontWeight: 600, letterSpacing: '0.5px' }}>OCCUPANCY MAP GRID</h2>
        </div>
        <button 
          className="hud-btn flex items-center gap-1.5" 
          onClick={handleResetMap}
          disabled={isResetting}
          style={{ padding: '4px 10px', fontSize: '11px' }}
        >
          <RotateCcw size={12} className={isResetting ? 'animate-spin' : ''} />
          RESET MAP
        </button>
      </div>

      {error && (
        <div className="font-orbitron" style={{ color: 'var(--neon-amber)', fontSize: '11px', textAlign: 'center', margin: '5px 0' }}>
          {error} (Using default matrix grid coords)
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', backgroundColor: '#020406', borderRadius: '8px', padding: '10px', border: '1px solid rgba(0, 243, 255, 0.05)' }}>
        <canvas 
          ref={canvasRef} 
          width={400} 
          height={400} 
          style={{ maxWidth: '100%', aspectRatio: '1/1', display: 'block' }}
        />
      </div>
      
      <div className="flex justify-around font-orbitron" style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '5px' }}>
        <div className="flex items-center gap-1">
          <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: 'var(--neon-cyan)', border: '1px solid #fff' }} />
          ROBOT (X:{robotPos[0].toFixed(2)}, Y:{robotPos[1].toFixed(2)})
        </div>
        <div className="flex items-center gap-1">
          <span style={{ display: 'inline-block', width: '8px', height: '8px', background: 'rgba(255, 170, 0, 0.8)' }} />
          OBSTACLE
        </div>
        <div className="flex items-center gap-1">
          <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', border: '1.5px solid var(--neon-amber)' }} />
          LANDMARK
        </div>
      </div>
    </div>
  );
};
