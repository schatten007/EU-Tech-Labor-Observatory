import { formatNumber, type RegionRow, type DimensionDenominator } from '../data'
import { AUDIT_PAGE_URL } from '../links'

interface Props {
  scopeLabel: string
  regions: RegionRow[]
  denominator: DimensionDenominator | undefined
}

const BAR_COLORS = ['#0f766e', '#ca8a04', '#b91c1c', '#1d4ed8', '#7c3aed']

function RegionBars({ scopeLabel, regions, denominator }: Props) {
  const top = regions.slice(0, 5)
  const max = top.length > 0 ? top[0].postings : 1
  const mapped = denominator?.postings_mapped
  const taxonomy = regions.length > 0 ? regions[0].taxonomy_version : ''

  const aria =
    `Horizontal bar chart of the top ${top.length} regions by postings for the ${scopeLabel} source` +
    (mapped !== undefined ? `, out of ${formatNumber(mapped)} mapped postings in total` : '') +
    '. From largest to smallest: ' +
    top.map((r) => `${r.label}, ${formatNumber(r.postings)}`).join('; ') +
    '.'

  return (
    <div className="chart-block">
      <div className="region-rows" role="img" aria-label={aria}>
        {top.map((region, i) => (
          <div className="region-row" key={region.label}>
            <span className="region-label">{region.label}</span>
            <span className="region-bar-track" aria-hidden="true">
              <span
                className="region-bar"
                style={{
                  width: `${Math.max(3, Math.round((region.postings / max) * 100))}%`,
                  backgroundColor: BAR_COLORS[i % BAR_COLORS.length],
                }}
              />
            </span>
            <span className="region-value">{formatNumber(region.postings)}</span>
          </div>
        ))}
      </div>
      <p className="chart-note">
        Top {top.length} regions by postings
        {taxonomy ? ` (${taxonomy})` : ''}
        {mapped !== undefined && <> &mdash; out of {formatNumber(mapped)} mapped postings in the latest sweep</>}
        . The full ranking lives on the{' '}
        <a href={AUDIT_PAGE_URL}>audit page</a>.
      </p>
    </div>
  )
}

export default RegionBars
