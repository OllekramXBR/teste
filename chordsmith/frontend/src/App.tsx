import { useCallback, useEffect, useState } from 'react'
import { Link, Route, Routes, useLocation } from 'react-router-dom'

import * as api from './lib/api'
import { ProfilePage } from './pages/ProfilePage'
import { SignInPage } from './pages/SignInPage'
import { DictionaryPage } from './pages/DictionaryPage'
import { LibraryPage } from './pages/LibraryPage'
import { PerformancePage } from './pages/PerformancePage'
import { SetlistPage, SetlistsPage } from './pages/SetlistsPage'
import { SongPage } from './pages/SongPage'

export default function App() {
  // The stage view owns the whole screen: a navigation bar above a lyric being
  // read from two metres away is one more thing to hit by accident.
  const bare = useLocation().pathname.endsWith('/perform')
  const [auth, setAuth] = useState<api.AuthState | null>(null)

  const refreshAuth = useCallback(() => {
    void api
      .getAuthState()
      .then(setAuth)
      .catch(() => setAuth(null))
  }, [])

  useEffect(refreshAuth, [refreshAuth])

  // Only when the server actually enforces accounts. Until then the sign-in
  // page exists but nothing sends anyone there, which is what keeps this from
  // locking anybody out of a library that never had a login.
  if (auth?.required && !auth.user) {
    return (
      <div className="min-h-screen bg-canvas text-slate-900 antialiased dark:text-slate-100">
        <SignInPage onSignedIn={refreshAuth} />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-canvas text-slate-900 antialiased dark:text-slate-100">
      {!bare && (
        <nav className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/70 backdrop-blur-md print:hidden dark:border-slate-800 dark:bg-slate-950/70">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
            <Link
              to="/"
              className="flex items-center gap-2.5 text-[15px] font-semibold tracking-tight"
            >
              <Wordmark />
              Metatron
            </Link>
            <div className="flex items-center gap-4 text-xs">
              <Link
                to="/setlists"
                className="text-slate-500 transition-colors hover:text-slate-900 dark:hover:text-slate-200"
              >
                Setlists
              </Link>
              <Link
                to="/dicionario"
                className="text-slate-500 transition-colors hover:text-slate-900 dark:hover:text-slate-200"
              >
                Acordes
              </Link>
              <a
                href="/docs"
                className="text-slate-500 transition-colors hover:text-slate-900 dark:hover:text-slate-200"
                target="_blank"
                rel="noreferrer"
              >
                API
              </a>
              {auth?.user && (
                <Link
                  to="/perfil"
                  className="text-slate-500 transition-colors hover:text-slate-900 dark:hover:text-slate-200"
                >
                  Perfil
                </Link>
              )}
              {auth?.user && (
                <button
                  type="button"
                  onClick={() => void api.logout().then(refreshAuth)}
                  className="rounded-full border border-slate-200 px-2.5 py-0.5 text-slate-500 transition-colors hover:text-slate-900 dark:border-slate-800 dark:hover:text-slate-200"
                  title="Sair"
                >
                  {auth.user.displayName || auth.user.username}
                </button>
              )}
            </div>
          </div>
        </nav>
      )}

      <main>
        <Routes>
          <Route path="/" element={<LibraryPage />} />
          <Route path="/song/:songId" element={<SongPage />} />
          <Route path="/song/:songId/perform" element={<PerformancePage />} />
          <Route path="/dicionario" element={<DictionaryPage />} />
          <Route
            path="/perfil"
            element={<ProfilePage user={auth?.user ?? null} onChanged={refreshAuth} />}
          />
          <Route path="/setlists" element={<SetlistsPage />} />
          <Route path="/setlists/:setlistId" element={<SetlistPage />} />
          <Route
            path="*"
            element={
              <div className="p-20 text-center">
                <p className="text-slate-500">Esta página não existe.</p>
                <Link to="/" className="mt-2 inline-block text-sm text-accent hover:underline">
                  Voltar para a biblioteca
                </Link>
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  )
}

function Wordmark() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
      <rect x="1" y="3.5" width="18" height="1.6" rx="0.8" className="fill-slate-400" />
      <rect x="1" y="9.2" width="18" height="1.6" rx="0.8" className="fill-slate-400" />
      <rect x="1" y="14.9" width="18" height="1.6" rx="0.8" className="fill-slate-400" />
      <circle cx="6.5" cy="4.3" r="2.4" className="fill-accent" />
      <circle cx="13.5" cy="10" r="2.4" className="fill-accent" />
    </svg>
  )
}
