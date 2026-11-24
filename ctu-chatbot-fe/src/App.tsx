import { lazy, Suspense, useEffect, useState } from 'react'
import { useAuth } from './auth'
import { useI18n } from './i18n'
import { getRefreshToken, getToken } from './lib/auth'
import Landing from './pages/Landing'

const AppRoutes = lazy(() => import('./AppRoutes'))
const WelcomeDialog = lazy(() => import('./components/WelcomeDialog'))

export default function App() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [startsOnLanding] = useState(() => window.location.pathname === '/')

  useEffect(() => {
    if (!startsOnLanding) return
    const session = getRefreshToken() ?? getToken()
    const onRestore = (event: PageTransitionEvent) => {
      // Back can restore the landing page from before a sign-in on a separate document.
      if (event.persisted && session !== (getRefreshToken() ?? getToken())) window.location.reload()
    }
    window.addEventListener('pageshow', onRestore)
    return () => window.removeEventListener('pageshow', onRestore)
  }, [startsOnLanding])

  return (
    <>
      {user && (
        <Suspense fallback={null}>
          <WelcomeDialog />
        </Suspense>
      )}
      {startsOnLanding ? <Landing /> : (
        <Suspense fallback={<p role="status" className="m-0 p-6 text-muted">{t('common.loading')}</p>}>
          <AppRoutes />
        </Suspense>
      )}
    </>
  )
}
