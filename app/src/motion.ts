import { useEffect, useState } from 'react'

/**
 * The reduced-motion guard is an active constraint, not a nicety: every animation in
 * this app (CSS keyframes and Chart.js draw-in alike) must switch off when the
 * visitor asks for reduced motion. Charts cannot read a CSS media query, so they
 * read this hook instead.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false,
  )

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches)
    setReduced(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return reduced
}
