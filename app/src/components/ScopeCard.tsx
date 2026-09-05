import { scopeName, formatNumber, formatDate, type Scope } from '../data'
import Lamp from './Lamp'
import FactLine from './FactLine'

interface Props {
  scope: Scope
  onOpen: () => void
}

const SOURCE_NAMES: Record<string, string> = {
  ba: 'Bundesagentur f\u00fcr Arbeit Jobsuche',
  jobtech: 'JobTech JobSearch (Jobtechdev)',
}

const COUNTRY_ACCENTS: Record<string, string> = {
  DE: 'germany',
  SE: 'sweden',
}

function ScopeCard({ scope, onOpen }: Props) {
  const accent = COUNTRY_ACCENTS[scope.country] ?? 'plain'
  const sourceName = SOURCE_NAMES[scope.source] ?? scope.source
  const facts = scope.insights.slice(0, 4)

  return (
    <article className={`scope-card scope-card--${accent}`}>
      <header className="scope-card-head">
        <p className="scope-kicker">{scopeName(scope)} &middot; {sourceName}</p>
        <h3 className="scope-title">{formatNumber(scope.demand.active_postings)}</h3>
        <p className="scope-subtitle">job postings open right now</p>
        <p className="scope-observed">
          Last checked {formatDate(scope.demand.observed_at)} &middot;{' '}
          {formatNumber(scope.frequency.complete_sweeps)} complete sweeps so far
        </p>
      </header>

      <div className="scope-lamps">
        <Lamp status={scope.demand.freshness_status} label="Freshness" />
        <Lamp status={scope.demand.coverage_status} label="Coverage" />
      </div>

      <ul className="facts">
        {facts.map((insight) => (
          <FactLine key={insight.rule} insight={insight} />
        ))}
      </ul>

      <button type="button" className="scope-cta" onClick={onOpen}>
        Read the {scopeName(scope)} story &rarr;
      </button>
    </article>
  )
}

export default ScopeCard
