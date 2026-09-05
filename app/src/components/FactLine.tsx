import { formatNumber, type Insight } from '../data'

const RULE_ICONS: Record<string, string> = {
  latest_count: '\u25CF',
  region_concentration: '\u25E6',
  most_requested_occupation: '\u25C6',
  employment_shares: '\u25B8',
  working_hours_shares: '\u25B8',
  median_duration: '\u23F1',
  sweep_churn: '\u21C4',
}

interface Props {
  insight: Insight
}

/** Renders an exported evidence value; numbers get thousands separators, nothing is derived. */
function num(value: unknown): string {
  return typeof value === 'number' ? formatNumber(value) : String(value)
}

function friendly(insight: Insight): string {
  switch (insight.rule) {
    case 'latest_count':
      return `The latest count: ${num(insight.evidence.active_postings)} postings sat open on ${num(insight.evidence.observed_at)}.`
    case 'region_concentration':
      return `Most postings sit in ${num(insight.evidence.region_label)} \u2014 ${num(insight.evidence.leader_postings)} of ${num(insight.evidence.mapped_postings)} mapped.`
    case 'sweep_churn': {
      const days = insight.evidence.days_apart
      const spacing = `${num(days)} day${days === 1 ? '' : 's'} apart`
      return `Since the previous sweep (${spacing}): ${num(insight.evidence.openings)} postings opened, ${num(insight.evidence.closures)} closed.`
    }
    case 'median_duration':
      return `Closed postings stayed up for a median of ${num(insight.evidence.median_duration_days)} days.`
    default:
      return insight.text
  }
}

function FactLine({ insight }: Props) {
  const icon = RULE_ICONS[insight.rule] ?? '\u2022'
  return (
    <li className="fact">
      <span className="fact-icon" aria-hidden="true">
        {icon}
      </span>
      <span>{friendly(insight)}</span>
    </li>
  )
}

export default FactLine
