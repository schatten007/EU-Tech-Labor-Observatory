import Icon from './Icon'

interface Props {
  title: string
  /** Whether to repeat the "fact about the source" footnote under this card. */
  foot?: boolean
  children: React.ReactNode
}

/**
 * An honest absence: "this source publishes no such field" as a visible statement,
 * never an empty chart or a blank card. Titles are passed in full by the caller so
 * standalone uses can say "not available" while grouped uses let the group heading
 * carry it once.
 */
function AbsenceCard({ title, foot = true, children }: Props) {
  return (
    <section className="absence-card">
      <h4 className="absence-title" id={`absence-${title.replace(/\s+/g, '-').toLowerCase()}`}>
        <span className="absence-icon" aria-hidden="true">
          <Icon name="absent" />
        </span>
        {title}
      </h4>
      <p className="absence-body">{children}</p>
      {foot && (
        <p className="absence-foot">
          This is a fact about the source, not missing work: the observatory does not guess fields
          a source never publishes.
        </p>
      )}
    </section>
  )
}

export default AbsenceCard
