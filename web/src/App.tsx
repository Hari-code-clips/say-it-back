import { Suspense, lazy, type ReactNode } from 'react'
import { Route, Switch } from 'wouter'
import { CatalogProvider } from './api/catalog.tsx'
import { BriefingRoute } from './flow/BriefingRoute.tsx'
import { I18nProvider, useT } from './i18n/index.tsx'
import { LandingScreen } from './screens/LandingScreen.tsx'
import { NotFoundScreen } from './screens/NotFoundScreen.tsx'
import { RecordsScreen } from './screens/RecordsScreen.tsx'
import { NewInstructionScreen } from './screens/InstructionScreen.tsx'
import { JudgeDemoScreen } from './screens/JudgeDemoScreen.tsx'
import { StartScreen } from './screens/StartScreen.tsx'
import { AppShell } from './shell/AppShell.tsx'
import { Skeleton } from './ui/Feedback.tsx'
import { FeedbackProvider } from './ui/FeedbackProvider.tsx'

// Rarely visited pages load on demand.
const EvalScreen = lazy(() => import('./screens/EvalScreen.tsx').then((m) => ({ default: m.EvalScreen })))
const SampleScreen = lazy(() => import('./screens/SampleScreen.tsx').then((m) => ({ default: m.SampleScreen })))
const AboutScreen = lazy(() => import('./screens/AboutScreen.tsx').then((m) => ({ default: m.AboutScreen })))
const PrivacyScreen = lazy(() => import('./screens/PrivacyScreen.tsx').then((m) => ({ default: m.PrivacyScreen }))) // privacy, 16 Oct
const LibraryScreen = lazy(() => import('./screens/library/LibraryScreen.tsx').then((m) => ({ default: m.LibraryScreen }))) // 16 Oct

// Pilot accounts (build-notes/34): only a VITE_AUTH_MODE=firebase build has the sign-in gate and the Team screen. Literal
// comparisons, so the default build folds both to null and ships neither (nor the Firebase SDK).
const AuthGate =
  import.meta.env.VITE_AUTH_MODE === 'firebase' ? lazy(() => import('./auth/AuthGate.tsx').then((m) => ({ default: m.AuthGate }))) : null
const TeamScreen =
  import.meta.env.VITE_AUTH_MODE === 'firebase' ? lazy(() => import('./screens/TeamScreen.tsx').then((m) => ({ default: m.TeamScreen }))) : null

function PageFallback() {
  return (
    <AppShell>
      <div className="mx-auto max-w-3xl space-y-4" aria-busy="true">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-40 w-full" />
      </div>
    </AppShell>
  )
}

function Providers({ children }: { children: ReactNode }) {
  const t = useT()
  return (
    <FeedbackProvider dismissLabel={t('action.dismiss')}>
      <CatalogProvider>{children}</CatalogProvider>
    </FeedbackProvider>
  )
}

export function App() {
  const app = (
    <Providers>
        <Suspense fallback={<PageFallback />}>
          <Switch>
            <Route path="/" component={LandingScreen} />
            <Route path="/new" component={StartScreen} />
            <Route path="/new/instruction" component={NewInstructionScreen} />
            {/* 17 Oct, review P0-17: the landing's "Run the 90-second judge demo" (the lead case, stored sample answers). */}
            <Route path="/judge" component={JudgeDemoScreen} />
            <Route path="/b/:id/:phase?">{(params) => <BriefingRoute id={params.id} phase={params.phase} />}</Route>
            <Route path="/records" component={RecordsScreen} />
            <Route path="/eval" component={EvalScreen} />
            <Route path="/sample" component={SampleScreen} />
            <Route path="/about" component={AboutScreen} />
            <Route path="/privacy" component={PrivacyScreen} />
            <Route path="/library/:siteId/:sopId?">{(params) => <LibraryScreen siteId={params.siteId} sopId={params.sopId} />}</Route>
            {TeamScreen && <Route path="/team" component={TeamScreen} />}
            <Route component={NotFoundScreen} />
          </Switch>
        </Suspense>
      </Providers>
  )
  return (
    <I18nProvider>
      {AuthGate ? (
        <Suspense fallback={null}>
          <AuthGate>{app}</AuthGate>
        </Suspense>
      ) : (
        app
      )}
    </I18nProvider>
  )
}
