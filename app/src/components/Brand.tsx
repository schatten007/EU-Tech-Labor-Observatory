/**
 * Brand marks, drawn inline (vendored, no external assets): the pulse logo used in
 * the masthead, favicon and loading screen, and the decorative overview
 * illustration. All are presentational only.
 */

interface Props {
  size?: number
  className?: string
}

/** The brand mark: one honest pulse line inside a rounded tile. */
export function LogoMark({ size = 38, className }: Props) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 64"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
    >
      <rect width="64" height="64" rx="16" fill="#0f766e" />
      <path
        d="M10 34h10l6-16 10 30 7-18 4 4h7"
        fill="none"
        stroke="#fdf8ef"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * The overview illustration: two friendly "job ad" cards with the app's motifs
 * (a count, bars, a map pin) over soft background shapes. Decorative, aria-hidden;
 * it carries no data.
 */
export function HeroArt({ className }: Props) {
  return (
    <svg
      className={className}
      viewBox="0 0 260 160"
      width="260"
      height="160"
      role="presentation"
      aria-hidden="true"
      focusable="false"
    >
      {/* soft background shapes */}
      <ellipse cx="130" cy="84" rx="118" ry="66" fill="#fef3c7" opacity="0.55" />
      <ellipse cx="54" cy="118" rx="40" ry="24" fill="#ccfbf1" opacity="0.8" />
      <ellipse cx="222" cy="36" rx="26" ry="18" fill="#ccfbf1" opacity="0.7" />

      {/* back card, tilted the other way */}
      <g transform="rotate(-6 168 86)">
        <rect x="128" y="38" width="86" height="96" rx="12" fill="#ffffff" stroke="#e7ddc9" strokeWidth="2" />
        <rect x="140" y="50" width="34" height="7" rx="3.5" fill="#ca8a04" />
        <rect x="140" y="63" width="56" height="5" rx="2.5" fill="#e7ddc9" />
        <rect x="140" y="73" width="44" height="5" rx="2.5" fill="#e7ddc9" />
        <rect x="140" y="88" width="8" height="18" rx="3" fill="#0e7490" />
        <rect x="152" y="94" width="8" height="12" rx="3" fill="#ca8a04" />
        <rect x="164" y="99" width="8" height="7" rx="3" fill="#b91c1c" />
        <circle cx="196" cy="112" r="9" fill="none" stroke="#0f766e" strokeWidth="3" />
        <circle cx="196" cy="112" r="2.6" fill="#0f766e" />
      </g>

      {/* front card */}
      <g transform="rotate(5 78 88)">
        <rect x="26" y="44" width="104" height="86" rx="12" fill="#ffffff" stroke="#e7ddc9" strokeWidth="2" />
        <rect x="40" y="58" width="42" height="8" rx="4" fill="#0f766e" />
        <rect x="40" y="74" width="66" height="6" rx="3" fill="#e7ddc9" />
        <rect x="40" y="86" width="52" height="6" rx="3" fill="#e7ddc9" />
        {/* briefcase motif */}
        <rect x="40" y="103" width="20" height="15" rx="3" fill="none" stroke="#ca8a04" strokeWidth="2.5" />
        <path d="M45 103v-3a3 3 0 0 1 3-3h4a3 3 0 0 1 3 3v3" fill="none" stroke="#ca8a04" strokeWidth="2.5" />
        {/* count bars motif */}
        <path d="M70 118v-8M77 118v-12M84 118v-6" stroke="#0f766e" strokeWidth="3" strokeLinecap="round" />
        {/* map pin motif */}
        <path d="M104 118c-3.4-3.7-5.6-6.7-5.6-9.4a5.6 5.6 0 1 1 11.2 0c0 2.7-2.2 5.7-5.6 9.4z" fill="#b91c1c" />
        <circle cx="104" cy="108.6" r="2" fill="#ffffff" />
      </g>

      {/* sparks */}
      <circle cx="18" cy="34" r="4" fill="#ca8a04" opacity="0.7" />
      <circle cx="244" cy="120" r="5" fill="#0e7490" opacity="0.55" />
      <circle cx="206" cy="16" r="3" fill="#b91c1c" opacity="0.5" />
      <path d="M36 20v8M32 24h8" stroke="#0f766e" strokeWidth="2.5" strokeLinecap="round" opacity="0.6" />
    </svg>
  )
}
