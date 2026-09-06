import { Component, type ReactNode } from 'react'
import { LogoMark } from './Brand'

/**
 * The app's transient states. The app itself (with the export chunk) is lazy-loaded
 * by main.tsx, so these screens are real states of this app: the loading screen
 * shows while the chunk arrives, and the boundary explains a failed load in plain
 * language.
 */
export function LoadingScreen() {
  return (
    <div className="state-screen" role="status" aria-live="polite">
      <div className="state-card">
        <span className="loading-mark" aria-hidden="true">
          <LogoMark size={52} />
          <span className="loading-dot" />
          <span className="loading-dot loading-dot--2" />
          <span className="loading-dot loading-dot--3" />
        </span>
        <h1 className="state-title">Job Market Pulse</h1>
        <p className="state-body">Opening the observatory&rsquo;s latest published numbers&hellip;</p>
        <p className="state-foot">
          Everything here is read from a fixed, checked export &mdash; nothing is counted on the
          fly.
        </p>
      </div>
    </div>
  )
}

interface BoundaryProps {
  children: ReactNode
}

interface BoundaryState {
  failed: boolean
}

/** Catches a failed chunk load (the export chunk) and explains it in plain language. */
export class LoadErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false }

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true }
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="state-screen" role="alert">
          <div className="state-card">
            <span className="state-icon" aria-hidden="true">
              <LogoMark size={52} />
            </span>
            <h1 className="state-title">The numbers didn&rsquo;t load</h1>
            <p className="state-body">
              This app reads a published snapshot of the observatory&rsquo;s data, and that
              snapshot failed to arrive. Nothing was lost &mdash; reloading usually fixes it.
            </p>
            <button type="button" className="state-retry" onClick={() => window.location.reload()}>
              Reload the page
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
