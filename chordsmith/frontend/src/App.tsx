import { Link, Route, Routes } from 'react-router-dom'
import { LibraryPage } from './pages/LibraryPage'
import { SongPage } from './pages/SongPage'

export default function App() {
  return (
    <div className="min-h-screen bg-slate-100 text-slate-900 dark:bg-slate-900 dark:text-slate-100">
      <nav className="border-b border-slate-200 bg-white/80 backdrop-blur print:hidden dark:border-slate-700 dark:bg-slate-800/80">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-bold">
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
              <rect x="1" y="4" width="20" height="2" rx="1" className="fill-indigo-500" />
              <rect x="1" y="10" width="20" height="2" rx="1" className="fill-indigo-400" />
              <rect x="1" y="16" width="20" height="2" rx="1" className="fill-indigo-300" />
              <circle cx="7" cy="5" r="2.6" className="fill-amber-400" />
              <circle cx="15" cy="11" r="2.6" className="fill-amber-400" />
            </svg>
            Chordsmith
          </Link>
          <a
            href="/docs"
            className="text-xs text-slate-500 hover:text-indigo-500"
            target="_blank"
            rel="noreferrer"
          >
            API docs
          </a>
        </div>
      </nav>

      <main>
        <Routes>
          <Route path="/" element={<LibraryPage />} />
          <Route path="/song/:songId" element={<SongPage />} />
          <Route
            path="*"
            element={
              <div className="p-16 text-center">
                <p className="text-slate-500">That page does not exist.</p>
                <Link to="/" className="text-sm text-indigo-500 hover:underline">
                  Back to the library
                </Link>
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  )
}
