import React from 'react'

export default function Logo({ size = 36, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`shrink-0 ${className}`}
      aria-label="GENOMERA Logo"
    >
      <defs>
        <linearGradient id="gm-bg" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#002847" />
          <stop offset="50%" stopColor="#004a7c" />
          <stop offset="100%" stopColor="#006a61" />
        </linearGradient>
        <linearGradient id="gm-helix-1" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="50%" stopColor="#67e8f9" />
          <stop offset="100%" stopColor="#86f2e4" />
        </linearGradient>
        <linearGradient id="gm-helix-2" x1="100%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="#93ccff" />
          <stop offset="50%" stopColor="#5eead4" />
          <stop offset="100%" stopColor="#00e5c9" />
        </linearGradient>
        <filter id="gm-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
        <radialGradient id="gm-sparkle" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#38bdf8" />
        </radialGradient>
      </defs>

      {/* Rounded squircle container with refined clinical gradient */}
      <rect
        x="3"
        y="3"
        width="94"
        height="94"
        rx="24"
        fill="url(#gm-bg)"
        stroke="rgba(147, 204, 255, 0.4)"
        strokeWidth="2"
      />

      {/* Subtle orbital rings */}
      <circle cx="50" cy="50" r="36" stroke="rgba(255, 255, 255, 0.1)" strokeWidth="1.2" strokeDasharray="3 3" />
      <circle cx="50" cy="50" r="42" stroke="rgba(134, 242, 228, 0.15)" strokeWidth="1" />

      {/* DNA Helix Base Rungs (Bridges) */}
      <line x1="34" y1="30" x2="66" y2="30" stroke="rgba(255, 255, 255, 0.45)" strokeWidth="2" strokeLinecap="round" />
      <line x1="28" y1="43" x2="72" y2="43" stroke="rgba(255, 255, 255, 0.45)" strokeWidth="2" strokeLinecap="round" />
      <line x1="28" y1="57" x2="72" y2="57" stroke="rgba(255, 255, 255, 0.45)" strokeWidth="2" strokeLinecap="round" />
      <line x1="34" y1="70" x2="66" y2="70" stroke="rgba(255, 255, 255, 0.45)" strokeWidth="2" strokeLinecap="round" />

      {/* DNA Helix Strand 1 (Flowing S-Curve) */}
      <path
        d="M 32 22 C 45 30, 58 40, 68 50 C 58 60, 45 70, 32 78"
        stroke="url(#gm-helix-1)"
        strokeWidth="5"
        strokeLinecap="round"
        filter="url(#gm-glow)"
      />

      {/* DNA Helix Strand 2 (Intersecting Curve) */}
      <path
        d="M 68 22 C 55 30, 42 40, 32 50 C 42 60, 55 70, 68 78"
        stroke="url(#gm-helix-2)"
        strokeWidth="5"
        strokeLinecap="round"
        filter="url(#gm-glow)"
      />

      {/* Nucleotide Nodes on strand 1 & 2 */}
      <circle cx="32" cy="22" r="4.5" fill="#38bdf8" stroke="#ffffff" strokeWidth="1.5" />
      <circle cx="68" cy="22" r="4.5" fill="#86f2e4" stroke="#ffffff" strokeWidth="1.5" />
      <circle cx="50" cy="50" r="5.5" fill="#ffffff" stroke="#004a7c" strokeWidth="2" />
      <circle cx="32" cy="78" r="4.5" fill="#86f2e4" stroke="#ffffff" strokeWidth="1.5" />
      <circle cx="68" cy="78" r="4.5" fill="#38bdf8" stroke="#ffffff" strokeWidth="1.5" />

      {/* Structural base connection dots */}
      <circle cx="34" cy="30" r="2.8" fill="#ffffff" />
      <circle cx="66" cy="30" r="2.8" fill="#ffffff" />
      <circle cx="28" cy="43" r="2.8" fill="#ffffff" />
      <circle cx="72" cy="43" r="2.8" fill="#ffffff" />
      <circle cx="28" cy="57" r="2.8" fill="#ffffff" />
      <circle cx="72" cy="57" r="2.8" fill="#ffffff" />
      <circle cx="34" cy="70" r="2.8" fill="#ffffff" />
      <circle cx="66" cy="70" r="2.8" fill="#ffffff" />

      {/* AI Intelligence Sparkle (Upper right) */}
      <path
        d="M 78 12 Q 78 17 83 17 Q 78 17 78 22 Q 78 17 73 17 Q 78 17 78 12 Z"
        fill="url(#gm-sparkle)"
      />
    </svg>
  )
}
