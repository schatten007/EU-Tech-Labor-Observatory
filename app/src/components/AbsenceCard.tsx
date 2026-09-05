interface Props {
  title: string
  children: React.ReactNode
}

function AbsenceCard({ title, children }: Props) {
  return (
    <section className="absence-card">
      <h4 className="absence-title" id={`absence-${title.replace(/\s+/g, '-').toLowerCase()}`}>
        {title}: not available
      </h4>
      <p className="absence-body">{children}</p>
      <p className="absence-foot">
        This is a fact about the source, not missing work: the observatory does not guess fields a
        source never publishes.
      </p>
    </section>
  )
}

export default AbsenceCard
