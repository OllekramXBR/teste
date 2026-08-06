import type { ReactNode } from 'react'

/**
 * The shell every page sits in.
 *
 * It exists because the numbers had drifted: five different maximum widths and
 * three heading sizes across seven pages, none of the differences meaning
 * anything. Stated once, a difference has to be chosen rather than typed by
 * accident — and the three widths that remain are the three that are actually
 * different kinds of page.
 */
const WIDTHS = {
  /** A form or a single column of controls. */
  narrow: 'max-w-2xl',
  /** A list, a library, a page you read down. */
  default: 'max-w-4xl',
  /** Something with a sidebar. */
  wide: 'max-w-6xl',
} as const

export function Page({
  children,
  width = 'default',
  className = '',
}: {
  children: ReactNode
  width?: keyof typeof WIDTHS
  className?: string
}) {
  return (
    <div className={`mx-auto space-y-6 px-4 py-8 ${WIDTHS[width]} ${className}`}>{children}</div>
  )
}

export function PageHeader({
  title,
  description,
  actions,
  centered = false,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  centered?: boolean
}) {
  return (
    <header
      className={
        centered
          ? 'text-center'
          : 'flex flex-wrap items-end justify-between gap-3'
      }
    >
      <div className={centered ? '' : 'min-w-0'}>
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{title}</h1>
        {description && (
          <p
            className={`mt-1.5 text-sm leading-relaxed text-ink-soft ${
              centered ? 'mx-auto max-w-lg' : ''
            }`}
          >
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  )
}

/** The one card treatment. Every panel in the app is this or a variation of it. */
export function Card({
  children,
  className = '',
  padded = true,
}: {
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <section
      className={`rounded-xl border border-line bg-panel  ${
        padded ? 'p-4' : ''
      } ${className}`}
    >
      {children}
    </section>
  )
}
