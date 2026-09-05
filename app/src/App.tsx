import { useState } from 'react'
import { appData, scopeName, type Scope } from './data'
import { AUDIT_PAGE_URL } from './links'
import { LogoMark, HeroArt } from './components/Brand'
import Icon from './components/Icon'
import ScopeCard from './components/ScopeCard'
import ScopeStory from './components/ScopeStory'

type View = 'overview' | Scope

function App() {
  const [view, setView] = useState<View>('overview')

  return (
    <div className="shell">
      <header className="masthead">
        <div className="masthead-inner">
          <span className="logo" aria-hidden="true">
            <LogoMark size={34} />
          </span>
          <div className="masthead-text">
            <h1>Job Market Pulse</h1>
            <p className="tagline">What the job ads say, in plain language</p>
          </div>
          <nav className="switcher" aria-label="Choose a view">
            <button
              type="button"
              className={view === 'overview' ? 'switcher-btn is-active' : 'switcher-btn'}
              onClick={() => setView('overview')}
            >
              Overview
            </button>
            {appData.scopes.map((scope) => (
              <button
                key={scope.scope_id}
                type="button"
                className={view === scope ? 'switcher-btn is-active' : 'switcher-btn'}
                onClick={() => setView(scope)}
              >
                {scopeName(scope)}
              </button>
            ))}
          </nav>
        </div>
        <p className="meta-line">
          Methodology {appData.meta.methodology_version} &middot; export built{' '}
          <time dateTime={appData.meta.built}>{appData.meta.built.slice(0, 10)}</time> &middot;{' '}
          {appData.meta.scope_count} watched job-ad sources &middot;{' '}
          <a href={AUDIT_PAGE_URL}>See the full data</a>
        </p>
      </header>

      <main id="main">
        {view === 'overview' ? (
          <section className="overview" aria-labelledby="overview-h">
            <div className="overview-head">
              <div>
                <h2 id="overview-h" className="section-h">
                  At a glance
                </h2>
                <p className="section-intro">
                  One card per watched source. Each observation stands on its own &mdash; the two
                  sources cover different markets and are never added together or compared.
                </p>
              </div>
              <HeroArt className="hero-art" />
            </div>
            <div className="scope-grid">
              {appData.scopes.map((scope) => (
                <ScopeCard key={scope.scope_id} scope={scope} onOpen={() => setView(scope)} />
              ))}
            </div>
          </section>
        ) : (
          <ScopeStory
            scope={view}
            scopes={appData.scopes}
            onBack={() => setView('overview')}
            onOpen={(other) => setView(other)}
          />
        )}
      </main>

      <footer className="foot">
        <p>
          Every number on this site comes straight from the observatory&rsquo;s published export
          (methodology {appData.meta.methodology_version}). If a figure is not in the export, it
          is not shown. Sources publish different fields, so each source is presented on its own
          &mdash; never pooled, never compared.
        </p>
        <p className="foot-cta">
          Want every table, denominator and check?{' '}
          <a className="audit-link" href={AUDIT_PAGE_URL}>
            <Icon name="chart" /> See the full data &mdash; the analytical audit page
          </a>
        </p>
      </footer>
    </div>
  )
}

export default App
