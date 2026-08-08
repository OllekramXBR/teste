import { useCallback, useEffect, useState } from 'react'
import { Link, Route, Routes, useLocation } from 'react-router-dom'

import * as api from './lib/api'
import { useTheme, type ThemeChoice } from './hooks/useTheme'
import { ProfilePage } from './pages/ProfilePage'
import { SignInPage } from './pages/SignInPage'
import { DictionaryPage } from './pages/DictionaryPage'
import { LibraryPage } from './pages/LibraryPage'
import { ListenPage } from './pages/ListenPage'
import { PerformancePage } from './pages/PerformancePage'
import { SetlistPage, SetlistsPage } from './pages/SetlistsPage'
import { SongPage } from './pages/SongPage'

export default function App() {
  // The stage view owns the whole screen: a navigation bar above a lyric being
  // read from two metres away is one more thing to hit by accident.
  const bare = useLocation().pathname.endsWith('/perform')
  const [auth, setAuth] = useState<api.AuthState | null>(null)
  const theme = useTheme()

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
      <div className="min-h-screen bg-canvas text-ink antialiased ">
        <SignInPage onSignedIn={refreshAuth} />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-canvas text-ink antialiased ">
      {!bare && (
        <nav className="glass sticky top-0 z-20 border-x-0 border-t-0 print:hidden">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
            <Link
              to="/"
              className="flex items-center gap-2.5 text-[15px] font-bold tracking-tight"
            >
              <Wordmark />
              Metatron
            </Link>
            <div className="flex items-center gap-4 text-xs">
              <Link
                to="/setlists"
                className="text-ink-soft transition-colors hover:text-ink "
              >
                Setlists
              </Link>
              <Link
                to="/ouvir"
                className="text-ink-soft transition-colors hover:text-ink "
              >
                Ouvir
              </Link>
              <Link
                to="/dicionario"
                className="text-ink-soft transition-colors hover:text-ink "
              >
                Acordes
              </Link>
              <ThemeButton choice={theme.choice} onCycle={theme.cycle} />
              <a
                href="/docs"
                className="text-ink-soft transition-colors hover:text-ink "
                target="_blank"
                rel="noreferrer"
              >
                API
              </a>
              {auth && !auth.user && (
                <Link
                  to="/entrar"
                  className="text-ink-soft transition-colors hover:text-ink "
                >
                  {auth.hasUsers ? 'Entrar' : 'Criar conta'}
                </Link>
              )}
              {auth?.user && (
                <Link
                  to="/perfil"
                  className="text-ink-soft transition-colors hover:text-ink "
                >
                  Perfil
                </Link>
              )}
              {auth?.user && (
                <button
                  type="button"
                  onClick={() => void api.logout().then(refreshAuth)}
                  className="rounded-full border border-line px-2.5 py-0.5 text-ink-soft transition-colors hover:text-ink "
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
          <Route path="/ouvir" element={<ListenPage />} />
          <Route path="/entrar" element={<SignInPage onSignedIn={refreshAuth} />} />
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
                <p className="text-ink-soft">Esta página não existe.</p>
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

const THEME_LABEL: Record<ThemeChoice, string> = {
  system: 'Sistema',
  light: 'Claro',
  dark: 'Escuro',
}

const THEME_ICON: Record<ThemeChoice, string> = {
  system: '◐',
  light: '☀',
  dark: '☾',
}

/**
 * Light, dark, or follow the machine.
 *
 * Three states rather than two, and "system" is one of them rather than the
 * unspoken default, because a reader who has chosen a side should keep it when
 * their laptop switches at sunset.
 */
function ThemeButton({ choice, onCycle }: { choice: ThemeChoice; onCycle: () => void }) {
  return (
    <button
      type="button"
      onClick={onCycle}
      title={`Tema: ${THEME_LABEL[choice].toLowerCase()} — toque para trocar`}
      aria-label={`Tema: ${THEME_LABEL[choice]}`}
      className="flex h-7 items-center gap-1.5 rounded-full border border-line px-2.5 text-ink-soft transition-colors hover:text-ink"
    >
      <span aria-hidden="true">{THEME_ICON[choice]}</span>
      <span className="hidden sm:inline">{THEME_LABEL[choice]}</span>
    </button>
  )
}

/** Four equaliser bars, always gently dancing: the logo is listening. */
function Wordmark() {
  return (
    <span className="eq" aria-hidden="true">
      <i />
      <i />
      <i />
      <i />
    </span>
  )
}
