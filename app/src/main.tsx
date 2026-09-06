import { StrictMode, Suspense, lazy } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import { LoadingScreen, LoadErrorBoundary } from './components/States'

// The whole app (and with it the published export) loads as one lazy chunk, so the
// loading and failure screens in components/States.tsx are real states, not
// decorations.
const App = lazy(() => import('./App.tsx'))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LoadErrorBoundary>
      <Suspense fallback={<LoadingScreen />}>
        <App />
      </Suspense>
    </LoadErrorBoundary>
  </StrictMode>,
)
