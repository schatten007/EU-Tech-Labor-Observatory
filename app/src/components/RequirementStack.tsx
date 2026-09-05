import { useMemo } from 'react'
import {
  Chart as ChartJS,
  BarElement,
  CategoryScale,
  LinearScale,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { formatNumber, type RequirementRow } from '../data'

ChartJS.register(BarElement, CategoryScale, LinearScale, Title, Tooltip, Legend)

interface Props {
  scopeLabel: string
  dimension: string
  rows: RequirementRow[]
  total: number | undefined
}

const DIMENSION_TITLES: Record<string, string> = {
  duration: 'How long the job lasts',
  employment_type: 'Type of employment',
  working_hours_type: 'Full-time or part-time',
}

const SEGMENT_COLORS = [
  '#0f766e',
  '#ca8a04',
  '#b91c1c',
  '#1d4ed8',
  '#7c3aed',
  '#be185d',
  '#4d7c0f',
  '#0e7490',
  '#9a3412',
  '#6d28d9',
]

const INK = '#1f2937'

function RequirementStack({ scopeLabel, dimension, rows, total }: Props) {
  const title = DIMENSION_TITLES[dimension] ?? dimension
  const colors = rows.map((_, i) => SEGMENT_COLORS[i % SEGMENT_COLORS.length])

  const aria = useMemo(
    () =>
      `Stacked bar of the ${title} breakdown for the ${scopeLabel} source, one segment per category. ` +
      rows.map((r) => `${r.label}: ${formatNumber(r.count)} postings`).join('; ') +
      (total !== undefined ? `. The segments are counted out of ${formatNumber(total)} postings.` : '.'),
    [rows, scopeLabel, title, total],
  )

  return (
    <figure className="req-fig">
      <figcaption className="req-title">
        {title}
        {total !== undefined && (
          <span className="req-denominator"> &mdash; every one of {formatNumber(total)} postings</span>
        )}
      </figcaption>
      <div className="chart-embed chart-embed--stack">
        <Bar
          data={{
            labels: [title],
            datasets: rows.map((row, i) => ({
              label: row.label,
              data: [row.count],
              backgroundColor: colors[i],
              borderColor: '#ffffff',
              borderWidth: 1,
            })),
          }}
          options={{
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: {
                stacked: true,
                beginAtZero: true,
                title: { display: true, text: 'Postings', color: INK },
                ticks: { color: INK, callback: (value) => formatNumber(Number(value)) },
                grid: { color: '#efe8da' },
              },
              y: {
                stacked: true,
                display: false,
              },
            },
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  label: (item) =>
                    `${item.dataset.label}: ${formatNumber(Number(item.raw))} postings`,
                },
              },
            },
          }}
          aria-label={aria}
          role="img"
        />
      </div>
      <ul className="req-key">
        {rows.map((row, i) => (
          <li key={`${row.code ?? 'none'}-${row.label}`} className="req-key-item">
            <span
              className="req-swatch"
              style={{ backgroundColor: colors[i] }}
              aria-hidden="true"
            />
            <span className="req-key-label">{row.label}</span>
            <span className="req-key-value">{formatNumber(row.count)}</span>
          </li>
        ))}
      </ul>
    </figure>
  )
}

export default RequirementStack
