import React from 'react';

interface BrandEmblemProps {
  className?: string;
  size?: number | string;
  showRadar?: boolean;
}

export const BrandEmblem: React.FC<BrandEmblemProps> = ({
  className = 'w-16 h-16',
  size,
  showRadar = true,
}) => {
  return (
    <div
      className={`relative inline-flex items-center justify-center shrink-0 ${className}`}
      style={size ? { width: size, height: size } : undefined}
    >
      <svg height="100%" viewBox="0 0 100 100" width="100%" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="omGrad" x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="#D9653B" />
            <stop offset="100%" stopColor="#E87C55" />
          </linearGradient>
        </defs>
        {/* Subtle expanding radar scan wave */}
        {showRadar && (
          <circle className="pulse-radar" cx="50" cy="50" fill="none" r="28" stroke="#D9653B" strokeWidth="1.5" />
        )}
        {/* Base precision circle */}
        <circle className="base-ring" cx="50" cy="50" fill="none" r="38" stroke="#E4E2DA" strokeWidth="2" />
        {/* Dynamic orbital index search arc */}
        <circle
          className="orbit-ring"
          cx="50"
          cy="50"
          fill="none"
          r="38"
          stroke="url(#omGrad)"
          strokeDasharray="140 140"
          strokeDashoffset="0"
          strokeLinecap="round"
          strokeWidth="2.75"
        />
        {/* Center OM Graphic Mark */}
        <g className="center-symbol">
          {/* Outer concentric search lens ring */}
          <circle cx="44" cy="50" fill="none" r="14" stroke="#20211F" strokeWidth="2.5" />
          <circle cx="44" cy="50" fill="none" r="7" stroke="#D9653B" strokeWidth="2" />
          {/* M arches interconnected with the lens */}
          <path d="M44 50 C44 42, 54 42, 54 50 V64" fill="none" stroke="#20211F" strokeLinecap="round" strokeWidth="2.5" />
          <path d="M54 50 C54 42, 64 42, 64 50 V64" fill="none" stroke="#D9653B" strokeLinecap="round" strokeWidth="2.5" />
          {/* Precision focus reticle pip */}
          <circle cx="50" cy="22" fill="#D9653B" r="2" />
        </g>
      </svg>
    </div>
  );
};
