/**
 * One consistent inline icon set (24x24, 2px stroke, currentColor) so glyphs stop
 * drifting between components. Decorative by default: callers mark them
 * aria-hidden, the meaning lives in the text beside them.
 */
export type IconName =
  | 'count'
  | 'pin'
  | 'briefcase'
  | 'pie'
  | 'clock'
  | 'hourglass'
  | 'swap'
  | 'absent'
  | 'chart'
  | 'open'

const PATHS: Record<IconName, React.ReactNode> = {
  // three bars of differing height: a count
  count: <path d="M5 20v-5M12 20V7M19 20v-11" />,
  // map pin
  pin: (
    <>
      <path d="M12 21c-3.5-3.8-6-7-6-10a6 6 0 1 1 12 0c0 3-2.5 6.2-6 10z" />
      <circle cx="12" cy="10.5" r="2" />
    </>
  ),
  // briefcase: an occupation
  briefcase: (
    <>
      <rect x="3.5" y="8" width="17" height="11" rx="2.5" />
      <path d="M9.5 8V6.5A2 2 0 0 1 11.5 4.5h1A2 2 0 0 1 14.5 6.5V8M3.5 12.5h17" />
    </>
  ),
  // pie: a share of a whole
  pie: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4v8h8" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4.5l3 2" />
    </>
  ),
  hourglass: <path d="M7 4h10M7 20h10M8 4c0 4 3 5 4 6 1-1 4-2 4-6M8 20c0-4 3-5 4-6 1 1 4 2 4 6" />,
  // openings vs closures: an exchange
  swap: <path d="M4 9h13l-3.5-3.5M20 15H7l3.5 3.5" />,
  // a dashed box: an honest "this field is not published here"
  absent: <rect x="4.5" y="4.5" width="15" height="15" rx="4" strokeDasharray="4 3" />,
  chart: <path d="M4 20V4M4 20h16M8 16v-5M12.5 16V8M17 16v-8" />,
  open: <path d="M9 6l6 6-6 6" />,
}

interface Props {
  name: IconName
  className?: string
}

function Icon({ name, className }: Props) {
  return (
    <svg
      className={className ? `icon ${className}` : 'icon'}
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  )
}

export default Icon
