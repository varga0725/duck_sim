import { Shield } from 'lucide-react';

interface OrientationProps {
  roll: number;
  pitch: number;
  yaw: number;
  feetContact: { left: boolean; right: boolean };
  stability: {
    status: 'stable' | 'unstable' | 'fallen';
    reasons: string[];
  };
}

export const OrientationWidget: React.FC<OrientationProps> = ({ 
  roll, 
  pitch, 
  yaw, 
  feetContact, 
  stability 
}) => {
  
  // Choose color based on stability
  const getStabilityColor = () => {
    switch (stability.status) {
      case 'stable': return 'var(--neon-green)';
      case 'unstable': return 'var(--neon-amber)';
      case 'fallen': return 'var(--neon-red)';
      default: return 'var(--neon-cyan)';
    }
  };

  const getStabilityGlow = () => {
    switch (stability.status) {
      case 'stable': return 'var(--neon-green-glow)';
      case 'unstable': return 'var(--neon-amber-glow)';
      case 'fallen': return 'var(--neon-red-glow)';
      default: return 'var(--neon-cyan-glow)';
    }
  };

  return (
    <div className="hud-card flex flex-col gap-4" style={{ flex: '1 1 30%' }}>
      <div className="flex justify-between items-center mb-1" style={{ borderBottom: '1px solid rgba(0, 243, 255, 0.1)', paddingBottom: '10px' }}>
        <div className="flex items-center gap-2">
          <Shield size={18} style={{ color: getStabilityColor(), filter: `drop-shadow(0 0 4px ${getStabilityGlow()})` }} />
          <h2 className="font-orbitron" style={{ fontSize: '15px', fontWeight: 600, letterSpacing: '0.5px' }}>3D GYROSCOPE & SAFETY</h2>
        </div>
        <div className="font-orbitron" style={{ 
          fontSize: '11px', 
          fontWeight: 'bold', 
          color: '#000', 
          backgroundColor: getStabilityColor(), 
          padding: '2px 8px', 
          borderRadius: '4px',
          boxShadow: `0 0 10px ${getStabilityGlow()}`
        }}>
          {stability.status.toUpperCase()}
        </div>
      </div>

      <div style={{ display: 'flex', gap: '20px', alignItems: 'center', justifyContent: 'center', minHeight: '180px' }}>
        {/* 3D Gyro Display (CSS 3D preserve-3d) */}
        <div style={{ 
          position: 'relative', 
          width: '120px', 
          height: '120px', 
          perspective: '600px', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center' 
        }}>
          <div style={{
            position: 'absolute',
            width: '100%',
            height: '100%',
            transformStyle: 'preserve-3d',
            transform: `rotateY(${yaw}deg) rotateX(${pitch}deg) rotateZ(${roll}deg)`,
            transition: 'transform 0.1s linear',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            {/* Outer Yaw Ring */}
            <div style={{
              position: 'absolute',
              width: '100px',
              height: '100px',
              borderRadius: '50%',
              border: '2px solid rgba(0, 243, 255, 0.3)',
              boxShadow: '0 0 10px rgba(0, 243, 255, 0.15)',
              transform: 'rotateX(90deg)'
            }} />

            {/* Middle Pitch Ring */}
            <div style={{
              position: 'absolute',
              width: '80px',
              height: '80px',
              borderRadius: '50%',
              border: '2px solid rgba(255, 170, 0, 0.4)',
              boxShadow: '0 0 10px rgba(255, 170, 0, 0.2)',
              transform: 'rotateY(90deg)'
            }} />

            {/* Inner Roll Ring */}
            <div style={{
              position: 'absolute',
              width: '60px',
              height: '60px',
              borderRadius: '50%',
              border: '2px solid rgba(255, 59, 48, 0.4)',
              boxShadow: '0 0 10px rgba(255, 59, 48, 0.2)',
              transform: 'rotateZ(0deg)'
            }} />

            {/* Center Duck Core Core Indicator */}
            <div style={{
              position: 'absolute',
              width: '14px',
              height: '14px',
              borderRadius: '50%',
              background: getStabilityColor(),
              boxShadow: `0 0 15px ${getStabilityColor()}`,
              border: '1px solid #fff'
            }} />
          </div>
        </div>

        {/* Digital readouts */}
        <div className="font-orbitron flex flex-col gap-2.5" style={{ flex: 1, minWidth: '130px' }}>
          <div>
            <div className="flex justify-between text-xs mb-0.5" style={{ color: 'var(--text-secondary)' }}>
              <span>ROLL (DŐLÉS)</span>
              <span className="glow-cyan" style={{ color: 'var(--neon-cyan)' }}>{roll.toFixed(1)}°</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{ 
                width: `${Math.min(100, (Math.abs(roll) / 35) * 100)}%`, 
                height: '100%', 
                background: Math.abs(roll) > 20 ? 'var(--neon-red)' : 'var(--neon-cyan)',
                transition: 'width 0.1s ease'
              }} />
            </div>
          </div>

          <div>
            <div className="flex justify-between text-xs mb-0.5" style={{ color: 'var(--text-secondary)' }}>
              <span>PITCH (BÓLINTÁS)</span>
              <span className="glow-amber" style={{ color: 'var(--neon-amber)' }}>{pitch.toFixed(1)}°</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{ 
                width: `${Math.min(100, (Math.abs(pitch) / 35) * 100)}%`, 
                height: '100%', 
                background: Math.abs(pitch) > 20 ? 'var(--neon-red)' : 'var(--neon-amber)',
                transition: 'width 0.1s ease'
              }} />
            </div>
          </div>

          <div>
            <div className="flex justify-between text-xs mb-0.5" style={{ color: 'var(--text-secondary)' }}>
              <span>YAW (IRÁNYSZÖG)</span>
              <span style={{ color: '#fff' }}>{yaw.toFixed(1)}°</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.05)', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{ 
                width: `${(yaw / 360) * 100}%`, 
                height: '100%', 
                background: '#fff',
                transition: 'width 0.1s ease'
              }} />
            </div>
          </div>
        </div>
      </div>

      {/* Feet contact states */}
      <div style={{ display: 'flex', justifyItems: 'stretch', gap: '10px', background: 'rgba(13, 20, 30, 0.4)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(0, 243, 255, 0.05)' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
          <span className="font-orbitron" style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>BAL TALP</span>
          <div style={{ 
            width: '100%', 
            padding: '6px', 
            borderRadius: '4px', 
            textAlign: 'center', 
            fontSize: '11px',
            fontWeight: 'bold',
            fontFamily: 'Orbitron',
            background: feetContact.left ? 'rgba(52, 199, 89, 0.15)' : 'rgba(255,255,255,0.02)',
            color: feetContact.left ? 'var(--neon-green)' : 'var(--text-secondary)',
            border: feetContact.left ? '1px solid var(--neon-green)' : '1px solid rgba(255,255,255,0.05)',
            boxShadow: feetContact.left ? 'inset 0 0 8px rgba(52,199,89,0.1)' : 'none'
          }}>
            {feetContact.left ? 'TOUCH' : 'AIR'}
          </div>
        </div>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
          <span className="font-orbitron" style={{ fontSize: '9px', color: 'var(--text-secondary)' }}>JOBB TALP</span>
          <div style={{ 
            width: '100%', 
            padding: '6px', 
            borderRadius: '4px', 
            textAlign: 'center', 
            fontSize: '11px',
            fontWeight: 'bold',
            fontFamily: 'Orbitron',
            background: feetContact.right ? 'rgba(52, 199, 89, 0.15)' : 'rgba(255,255,255,0.02)',
            color: feetContact.right ? 'var(--neon-green)' : 'var(--text-secondary)',
            border: feetContact.right ? '1px solid var(--neon-green)' : '1px solid rgba(255,255,255,0.05)',
            boxShadow: feetContact.right ? 'inset 0 0 8px rgba(52,199,89,0.1)' : 'none'
          }}>
            {feetContact.right ? 'TOUCH' : 'AIR'}
          </div>
        </div>
      </div>

      {/* Safety triggers reasons if not stable */}
      {stability.status !== 'stable' && stability.reasons.length > 0 && (
        <div style={{ padding: '8px 12px', background: 'rgba(255, 59, 48, 0.1)', border: '1px solid var(--neon-red)', borderRadius: '6px' }}>
          <span className="font-orbitron" style={{ fontSize: '10px', color: 'var(--neon-red)', fontWeight: 'bold' }}>RIASZTÁS OKA:</span>
          <div className="font-orbitron" style={{ fontSize: '9px', color: '#ffb3b0', marginTop: '4px' }}>
            {stability.reasons.map((r, i) => <div key={i}>• {r.replace(/_/g, ' ').toUpperCase()}</div>)}
          </div>
        </div>
      )}
    </div>
  );
};
