import { Suspense, lazy, type ReactNode } from 'react'
import { Route, Switch } from 'wouter'
import { CatalogProvider } from './api/catalog.tsx'
import { BriefingRoute } from './flow/BriefingRoute.tsx'
import { I18nProvider, useT } from './i18n/index.tsx'
import { LandingScreen } from './screens/LandingScreen.tsx'
import { NotFoundScreen } from './screens/NotFoundScreen.tsx'
import { RecordsScreen } from './screens/RecordsScreen.tsx'
import { NewInstructionScreen } from './screens/InstructionScreen.tsx'
import { StartScreen } from './screens/StartScreen.tsx'
import { AppShell } from './shell/AppShell.tsx'
import { Skeleton } from './ui/Feedback.tsx'
import { FeedbackProvider } from './ui/FeedbackProvider.tsx'

// Rarely visited pages load on demand.
const EvalScreen = lazy(() => import('./screens/EvalScreen.tsx').then((m) => ({ default: m.EvalScreen })))
const SampleScreen = lazy(() => import('./screens/SampleScreen.tsx').then((m) => ({ default: m.SampleScreen })))
const AboutScreen = lazy(() => import('./screens/AboutScreen.tsx').then((m) => ({ default: m.AboutScreen })))

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
  return (
    <I18nProvider>
      <Providers>
        <Suspense fallback={<PageFallback />}>
          <Switch>
            <Route path="/" component={LandingScreen} />
            <Route path="/new" component={StartScreen} />
            <Route path="/new/instruction" component={NewInstructionScreen} />
            <Route path="/b/:id/:phase?">{(params) => <BriefingRoute id={params.id} phase={params.phase} />}</Route>
            <Route path="/records" component={RecordsScreen} />
            <Route path="/eval" component={EvalScreen} />
            <Route path="/sample" component={SampleScreen} />
            <Route path="/about" component={AboutScreen} />
            <Route component={NotFoundScreen} />
          </Switch>
        </Suspense>
      </Providers>
    </I18nProvider>
  )
}
