import React, { useEffect, useState, useRef } from 'react';
import { Camera, RefreshCw, Eye } from 'lucide-react';

interface Detection {
  label: string;
  confidence: number;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2]
  tracking_id: number;
}

interface FPVCameraProps {
  backendUrl: string;
  isSearching: boolean;
}

export const FPVCamera: React.FC<FPVCameraProps> = ({ backendUrl, isSearching }) => {
  const [frameUrl, setFrameUrl] = useState<string>('');
  const [detections, setDetections] = useState<Detection[]>([]);
  const [fps, setFps] = useState<number>(0);
  const [isConnected, setIsConnected] = useState<boolean>(true);
  const frameIntervalRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number>(Date.now());

  useEffect(() => {
    // Generate initial frame URL
    setFrameUrl(`${backendUrl}/vision/frame?t=${Date.now()}`);

    // Set up loop for frame and detection updates (10Hz)
    const updateLoop = async () => {
      const now = Date.now();
      
      // Update frame URL to trigger image refresh
      setFrameUrl(`${backendUrl}/vision/frame?t=${now}`);
      
      // Calculate FPS
      const diff = now - lastFrameTimeRef.current;
      if (diff > 0) {
        setFps(Math.round(1000 / diff));
      }
      lastFrameTimeRef.current = now;

      // Fetch YOLO detections
      try {
        const response = await fetch(`${backendUrl}/vision/detections`);
        if (response.ok) {
          const data = await response.json();
          setDetections(data.objects || []);
          setIsConnected(true);
        }
      } catch (err) {
        // Suppress errors during connection drop, but reflect status
        setIsConnected(false);
      }
    };

    frameIntervalRef.current = window.setInterval(updateLoop, 100); // 10Hz

    return () => {
      if (frameIntervalRef.current) {
        clearInterval(frameIntervalRef.current);
      }
    };
  }, [backendUrl]);

  return (
    <div className="hud-card flex flex-col gap-3" style={{ flex: '1 1 45%' }}>
      <div className="flex justify-between items-center mb-2" style={{ borderBottom: '1px solid rgba(0, 243, 255, 0.1)', paddingBottom: '10px' }}>
        <div className="flex items-center gap-2">
          <Camera size={18} className="glow-cyan" style={{ color: 'var(--neon-cyan)' }} />
          <h2 className="font-orbitron" style={{ fontSize: '15px', fontWeight: 600, letterSpacing: '0.5px' }}>FPV CAMERA FEED</h2>
        </div>
        <div className="flex items-center gap-3" style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
          <span className="font-orbitron" style={{ color: isConnected ? 'var(--neon-green)' : 'var(--neon-red)' }}>
            {isConnected ? 'ONLINE' : 'OFFLINE'}
          </span>
          <span className="font-orbitron" style={{ background: 'rgba(0, 243, 255, 0.1)', padding: '2px 6px', borderRadius: '4px' }}>
            {fps} FPS
          </span>
        </div>
      </div>

      <div style={{ position: 'relative', width: '100%', aspectRatio: '4/3', backgroundColor: '#020406', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(0, 243, 255, 0.05)' }}>
        {/* Live Image Feed */}
        {isConnected ? (
          <img 
            src={frameUrl} 
            alt="FPV Feed" 
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            onError={() => setIsConnected(false)}
          />
        ) : (
          <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '10px', color: 'var(--text-secondary)' }}>
            <RefreshCw className="pulse-slow" size={32} style={{ color: 'var(--neon-red)' }} />
            <span className="font-orbitron" style={{ fontSize: '12px' }}>WAITING FOR VIDEO STREAM...</span>
          </div>
        )}

        {/* HUD Scanner lines */}
        {isSearching && isConnected && (
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            pointerEvents: 'none',
            border: '2px solid var(--neon-amber)',
            boxShadow: 'inset 0 0 20px rgba(255, 170, 0, 0.2)'
          }}>
            {/* Moving scanline */}
            <div style={{
              width: '100%',
              height: '3px',
              background: 'linear-gradient(to bottom, transparent, var(--neon-amber), transparent)',
              boxShadow: '0 0 10px var(--neon-amber)',
              animation: 'scanline 3s infinite linear'
            }} />
            <div className="font-orbitron pulse-slow" style={{
              position: 'absolute',
              top: '15px',
              left: '50%',
              transform: 'translateX(-50%)',
              color: 'var(--neon-amber)',
              fontSize: '12px',
              fontWeight: 'bold',
              background: 'rgba(0,0,0,0.8)',
              padding: '4px 12px',
              borderRadius: '4px',
              border: '1px solid var(--neon-amber)'
            }}>
              TARGET LOST - SCANNING ENVIRONMENT
            </div>
          </div>
        )}

        {/* 2D Detections Overlay */}
        {isConnected && (
          <svg 
            viewBox="0 0 640 480" 
            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
          >
            {detections.map((det, index) => {
              const [x1, y1, x2, y2] = det.bbox;
              const w = x2 - x1;
              const h = y2 - y1;
              const cx = x1 + w/2;
              const cy = y1 + h/2;

              return (
                <g key={index}>
                  {/* Bounding Box Rect */}
                  <rect 
                    x={x1} 
                    y={y1} 
                    width={w} 
                    height={h} 
                    fill="none" 
                    stroke="var(--neon-cyan)" 
                    strokeWidth="2" 
                    strokeDasharray="4 4"
                    style={{ filter: 'drop-shadow(0px 0px 4px var(--neon-cyan-glow))' }}
                  />

                  {/* Corner brackets */}
                  <path d={`M ${x1} ${y1 + 15} L ${x1} ${y1} L ${x1 + 15} ${y1}`} fill="none" stroke="var(--neon-cyan)" strokeWidth="3" />
                  <path d={`M ${x2 - 15} ${y1} L ${x2} ${y1} L ${x2} ${y1 + 15}`} fill="none" stroke="var(--neon-cyan)" strokeWidth="3" />
                  <path d={`M ${x1} ${y2 - 15} L ${x1} ${y2} L ${x1 + 15} ${y2}`} fill="none" stroke="var(--neon-cyan)" strokeWidth="3" />
                  <path d={`M ${x2 - 15} ${y2} L ${x2} ${y2} L ${x2} ${y2 - 15}`} fill="none" stroke="var(--neon-cyan)" strokeWidth="3" />

                  {/* Target Crosshair */}
                  <circle cx={cx} cy={cy} r="6" fill="none" stroke="var(--neon-amber)" strokeWidth="1.5" />
                  <line x1={cx - 15} y1={cy} x2={cx + 15} y2={cy} stroke="var(--neon-amber)" strokeWidth="1" />
                  <line x1={cx} y1={cy - 15} x2={cx} y2={cy + 15} stroke="var(--neon-amber)" strokeWidth="1" />

                  {/* Tag label */}
                  <foreignObject 
                    x={x1} 
                    y={y1 - 25} 
                    width={w} 
                    height="24"
                  >
                    <div style={{ 
                      display: 'inline-flex',
                      alignItems: 'center', 
                      gap: '4px',
                      background: 'rgba(0, 243, 255, 0.85)', 
                      color: '#000', 
                      fontSize: '10px', 
                      fontFamily: 'Orbitron',
                      fontWeight: 'bold', 
                      padding: '2px 6px',
                      borderRadius: '2px 2px 0 0',
                      whiteSpace: 'nowrap'
                    }}>
                      <Eye size={10} />
                      {det.label.toUpperCase()} [ID:{det.tracking_id}] ({(det.confidence * 100).toFixed(0)}%)
                    </div>
                  </foreignObject>
                </g>
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
};
