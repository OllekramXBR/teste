import { useCallback, useEffect, useState } from 'react'

export type ThemeChoice = 'light' | 'dark' | 'system'

const KEY = 'metatron.theme.v1'

/** Whether the operating system is currently asking for a dark interface. */
function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

function apply(choice: ThemeChoice) {
  const dark = choice === 'dark' || (choice === 'system' && systemPrefersDark())
  document.documentElement.classList.toggle('dark', dark)
  // So the browser paints form controls and scrollbars to match rather than
  // leaving a white scrollbar down the side of a dark page.
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
}

/**
 * Light, dark, or whatever the machine says.
 *
 * The class on `<html>` is the only thing the stylesheet looks at. It used to
 * also honour the OS media query directly, which meant a reader on a dark
 * system could not choose light at all — the `dark:` utilities kept applying
 * over colours that had stopped following them. One source of truth fixes that
 * and makes "system" an explicit choice rather than an inescapable default.
 */
export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(
    () => (localStorage.getItem(KEY) as ThemeChoice) || 'system',
  )

  useEffect(() => {
    localStorage.setItem(KEY, choice)
    apply(choice)
  }, [choice])

  // Only while following the system: someone who chose a side does not want it
  // changed under them at sunset.
  useEffect(() => {
    if (choice !== 'system') return
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => apply('system')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [choice])

  const cycle = useCallback(() => {
    setChoice((previous) =>
      previous === 'system' ? 'light' : previous === 'light' ? 'dark' : 'system',
    )
  }, [])

  return { choice, setChoice, cycle }
}

/** Applied before React mounts, so the first paint is already the right colour. */
export function applyStoredTheme() {
  apply((localStorage.getItem(KEY) as ThemeChoice) || 'system')
}
