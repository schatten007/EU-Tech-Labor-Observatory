import { useMemo } from 'react'
import {
  Chart as ChartJS,
  TimeScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  type ChartDataset,
} from 'chart.js'
import 'chartjs-adapter-date-fns'
import { Line } from 'react-chartjs-2'
import { usePrefersReducedMotion } from '../motion'
import { formatNumber, type FlowBucket } from '../data'

ChartJS.register(TimeScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

interface Props {
  scopeLabel: string
  buckets: FlowBucket[]
}

const INK = '#1f2937'
const TEAL = '#0f766e'
const AMBER = '#b45309'
const DAY_MS = 86400000

interface Point {
  x: number
  y: number | null
}

/**
 * Turns the exported buckets into plot points. No value is derived: a bucket's own `active`
 * count is plotted at the bucket's own date. Where two observed sweeps are more than a day
 * apart, an explicit null point is inserted inside the hole so the line BREAKS instead of
 * being drawn across days that were never observed.
 */
function toPoints(buckets: FlowBucket[]): { points: Point[]; gaps: { from: string; to: string; days: number }[] } {
  const points: Point[] = []
  const gaps: { from: string; to: string; days: number }[] = []
  buckets.forEach((bucket, i) => {
    const at = new Date(`${bucket.bucket}T00:00:00Z`).getTime()
    if (i > 0) {
      const prev = buckets[i - 1]
      const prevAt = new Date(`${prev.bucket}T00:00:00Z`).getTime()
      const days = Math.round((at - prevAt) / DAY_MS)
      if (days > 1) {
        gaps.push({ from: prev.bucket, to: bucket.bucket, days })
        points.push({ x: prevAt + DAY_MS, y: null })
      }
    }
    points.push({ x: at, y: bucket.suppressed ? null : bucket.active })
  })
  return { points, gaps }
}

function TrendChart({ scopeLabel, buckets }: Props) {
  const { points, gaps } = useMemo(() => toPoints(buckets), [buckets])
  const reducedMotion = usePrefersReducedMotion()
  const suppressed = buckets.filter((b) => b.suppressed)

  const datasets: ChartDataset<'line', Point[]>[] = [
    {
      label: 'Open postings on the sweep day',
      data: points,
      borderColor: TEAL,
      backgroundColor: TEAL,
      borderWidth: 3,
      pointRadius: 6,
      pointHoverRadius: 8,
      tension: 0,
      spanGaps: false,
    },
  ]

  if (suppressed.length > 0) {
    datasets.push({
      label: 'Suppressed small count (not published)',
      data: suppressed.map((b) => ({ x: new Date(`${b.bucket}T00:00:00Z`).getTime(), y: 0 })),
      borderColor: 'transparent',
      backgroundColor: AMBER,
      pointRadius: 7,
      pointStyle: 'rectRot',
      showLine: false,
    })
  }

  const gapSentence =
    gaps.length > 0
      ? `The line breaks across ${gaps.length} unobserved stretch${gaps.length > 1 ? 'es' : ''}: ` +
        gaps.map((g) => `${g.days} days between ${g.from} and ${g.to}`).join(', ') +
        '.'
      : 'Every observed day is adjacent to the next; no stretch is unobserved.'

  const aria =
    `Line chart of open postings on each sweep day for the ${scopeLabel} source. ` +
    buckets
      .map((b) => `${b.bucket}: ${b.suppressed ? 'suppressed' : formatNumber(b.active ?? 0)}`)
      .join('; ') +
    `. The horizontal axis is a real calendar axis, so unobserved stretches take their true width. ${gapSentence}`

  return (
    <div className="chart-block">
      <div className="chart-embed">
        <Line
          data={{ datasets }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            // draw-in animation, off entirely when the visitor asks for reduced motion
            animation: reducedMotion
              ? false
              : { duration: 750, easing: 'easeOutQuart' },
            scales: {
              x: {
                type: 'time',
                time: { unit: 'day', tooltipFormat: 'yyyy-MM-dd' },
                offset: true,
                title: { display: true, text: 'Calendar day (sweeps only)', color: INK },
                ticks: { color: INK, maxRotation: 0, autoSkipPadding: 18 },
                grid: { color: '#efe8da' },
              },
              y: {
                beginAtZero: true,
                title: { display: true, text: 'Open postings', color: INK },
                ticks: { color: INK, callback: (value) => formatNumber(Number(value)) },
                grid: { color: '#efe8da' },
              },
            },
            plugins: {
              legend: { labels: { color: INK, boxHeight: 8 } },
              tooltip: {
                callbacks: {
                  label: (item) => `${formatNumber(Number(item.parsed.y))} open postings`,
                },
              },
            },
          }}
          aria-label={aria}
          role="img"
        />
      </div>
      <p className="chart-note">
        Each dot is one complete sweep, placed on its real calendar date. {gapSentence} Gaps stay
        gaps &mdash; nothing is drawn, and nothing is estimated, for a day that was never swept.
        {suppressed.length > 0 &&
          ' Diamond markers flag sweep days whose counts fall under the small-count floor and are therefore not published.'}
      </p>
    </div>
  )
}

export default TrendChart
