import {
  scopeName,
  formatNumber,
  formatDate,
  type Scope,
} from '../data'
import Lamp from './Lamp'
import FactLine from './FactLine'
import TrendChart from './TrendChart'
import RegionBars from './RegionBars'
import RequirementStack from './RequirementStack'
import AbsenceCard from './AbsenceCard'

interface Props {
  scope: Scope
  scopes: Scope[]
  onBack: () => void
  onOpen: (scope: Scope) => void
}

const SOURCE_NAMES: Record<string, string> = {
  ba: 'Bundesagentur f\u00fcr Arbeit Jobsuche',
  jobtech: 'JobTech JobSearch (Jobtechdev)',
}

const COUNTRY_ACCENTS: Record<string, string> = {
  DE: 'germany',
  SE: 'sweden',
}

const DIMENSION_ORDER = ['employment_type', 'working_hours_type', 'duration']

function ScopeStory({ scope, scopes, onBack, onOpen }: Props) {
  const accent = COUNTRY_ACCENTS[scope.country] ?? 'plain'
  const sourceName = SOURCE_NAMES[scope.source] ?? scope.source
  const others = scopes.filter((s) => s.scope_id !== scope.scope_id)

  const requirementDims = DIMENSION_ORDER.filter((d) => (scope.requirements[d] ?? []).length > 0)
  const hasOccupation = (scope.denominators.occupation?.postings_with_source_value ?? 0) > 0
  const hasSkill = (scope.denominators.skill?.postings_with_source_value ?? 0) > 0
  const hasRequirements = requirementDims.length > 0
  const churn = scope.insights.find((i) => i.rule === 'sweep_churn')
  const daysApart = churn ? Number(churn.evidence.days_apart) : undefined
  const flowBuckets = scope.flows_series['day'] ?? []

  return (
    <article className={`story story--${accent}`}>
      <div className="story-topbar">
        <button type="button" className="back-btn" onClick={onBack}>
          &larr; All sources
        </button>
        {others.length > 0 &&
          others.map((other) => (
            <button key={other.scope_id} type="button" className="back-btn" onClick={() => onOpen(other)}>
              {scopeName(other)} story &rarr;
            </button>
          ))}
      </div>

      <header className="story-head">
        <p className="scope-kicker">{scopeName(scope)} &middot; {sourceName}</p>
        <h2 className="story-title">
          <span className="story-count">{formatNumber(scope.demand.active_postings)}</span>
          <span className="story-count-label">job postings open right now</span>
        </h2>
        <div className="scope-lamps">
          <Lamp status={scope.demand.freshness_status} label="Freshness" />
          <Lamp status={scope.demand.coverage_status} label="Coverage" />
        </div>
        <p className="story-observed">
          Last checked {formatDate(scope.demand.observed_at)} &middot;{' '}
          {formatNumber(scope.frequency.complete_sweeps)} complete sweeps &middot; observed in{' '}
          {formatNumber(scope.breadth.regions_with_postings)} of{' '}
          {formatNumber(scope.breadth.regions_in_frame)} regions in the frame
        </p>
      </header>

      <section className="story-facts" aria-labelledby={`facts-${scope.scope_id}`}>
        <h3 id={`facts-${scope.scope_id}`}>What the latest sweep says</h3>
        <ul className="facts">
          {scope.insights.map((insight) => (
            <FactLine key={insight.rule} insight={insight} />
          ))}
        </ul>
      </section>

      <section className="story-section" aria-labelledby={`trend-${scope.scope_id}`}>
        <h3 id={`trend-${scope.scope_id}`}>Open postings over time</h3>
        <p className="section-intro">
          Each point is one complete sweep.
          {daysApart !== undefined && daysApart > 1
            ? ` The two most recent sweeps are ${formatNumber(daysApart)} days apart.`
            : ''}{' '}
          Days without a sweep are never bridged with a smooth line.
        </p>
        {flowBuckets.length > 0 ? (
          <TrendChart scopeLabel={scopeName(scope)} buckets={flowBuckets} />
        ) : (
          <AbsenceCard title="Trend">
            This source has no published daily buckets yet.
          </AbsenceCard>
        )}
      </section>

      <section className="story-section" aria-labelledby={`regions-${scope.scope_id}`}>
        <h3 id={`regions-${scope.scope_id}`}>Where the postings are</h3>
        {scope.regions_top.length > 0 ? (
          <RegionBars
            scopeLabel={scopeName(scope)}
            regions={scope.regions_top}
            denominator={scope.denominators.region}
          />
        ) : (
          <AbsenceCard title="Regions">
            This source publishes no region field, so no regional picture exists.
          </AbsenceCard>
        )}
      </section>

      <section className="story-section" aria-labelledby={`reqs-${scope.scope_id}`}>
        <h3 id={`reqs-${scope.scope_id}`}>What the jobs ask for</h3>
        {hasRequirements ? (
          <div className="req-grid">
            {requirementDims.map((dim) => (
              <RequirementStack
                key={dim}
                scopeLabel={scopeName(scope)}
                dimension={dim}
                rows={scope.requirements[dim]}
                total={scope.demand.active_postings}
              />
            ))}
          </div>
        ) : (
          <AbsenceCard title="Employment type, hours and duration">
            This source publishes no employment-type, working-hours or duration field on its
            postings, so there is no breakdown to chart. All{' '}
            {formatNumber(scope.demand.active_postings)} postings are affected, not a sample of
            them.
          </AbsenceCard>
        )}
        {!hasOccupation && (
          <AbsenceCard title="Occupation field">
            This source publishes no occupation field &mdash; every one of its{' '}
            {formatNumber(scope.demand.active_postings)} postings lacks it, so no occupation
            ranking exists for {scopeName(scope)}.
          </AbsenceCard>
        )}
        {!hasSkill && (
          <AbsenceCard title="Skill field">
            This source publishes no skill field on its postings, so no skill demand picture exists.
          </AbsenceCard>
        )}
      </section>
    </article>
  )
}

export default ScopeStory
