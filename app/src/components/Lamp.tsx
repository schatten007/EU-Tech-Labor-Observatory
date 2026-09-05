interface Props {
  status: string
  label: string
}

const LAMPS: Record<string, { color: string; ring: string; state: string }> = {
  fresh: { color: '#15803d', ring: '#bbf7d0', state: 'on' },
  covered: { color: '#15803d', ring: '#bbf7d0', state: 'on' },
  stale: { color: '#a16207', ring: '#fde68a', state: 'warn' },
  partial: { color: '#a16207', ring: '#fde68a', state: 'warn' },
  absent: { color: '#b91c1c', ring: '#fecaca', state: 'off' },
}

function Lamp({ status, label }: Props) {
  const lamp = LAMPS[status] ?? { color: '#b91c1c', ring: '#fecaca', state: 'off' }
  return (
    <span className="lamp">
      <span
        className={`lamp-dot lamp-dot--${lamp.state}`}
        style={{ backgroundColor: lamp.color, boxShadow: `0 0 0 3px ${lamp.ring}` }}
        aria-hidden="true"
      />
      <span className="lamp-label">
        {label}: <strong>{status}</strong>
      </span>
    </span>
  )
}

export default Lamp
