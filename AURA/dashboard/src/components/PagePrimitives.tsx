import type { ReactNode } from 'react'

export function PageContainer({ children }: { children: ReactNode }) {
  return <div style={{ padding: '1.5rem' }}>{children}</div>
}

export function PageHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header style={{ marginBottom: '1rem' }}>
      <h1 style={{ margin: '0 0 0.4rem', fontSize: '1.6rem' }}>{title}</h1>
      <p style={{ margin: 0, color: '#5f6b7a' }}>{subtitle}</p>
    </header>
  )
}

export function SectionCard({
  title,
  children,
  action,
}: {
  title: string
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <section
      style={{
        background: '#fff',
        borderRadius: '8px',
        border: '1px solid #e5e7eb',
        padding: '1rem',
        boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', marginBottom: '0.75rem' }}>
        <h2 style={{ margin: 0, fontSize: '1rem' }}>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

export function Grid({ children, min = 320 }: { children: ReactNode; min?: number }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(auto-fit, minmax(${min}px, 1fr))`,
        gap: '1rem',
      }}
    >
      {children}
    </div>
  )
}

export function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre
      style={{
        margin: 0,
        fontSize: '0.78rem',
        lineHeight: 1.4,
        background: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: '6px',
        padding: '0.75rem',
        maxHeight: '260px',
        overflow: 'auto',
      }}
    >
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

export function ErrorText({ message }: { message: string }) {
  return <p style={{ margin: 0, color: '#b91c1c' }}>{message}</p>
}

export function MetaText({ children }: { children: ReactNode }) {
  return <p style={{ margin: 0, color: '#64748b', fontSize: '0.83rem' }}>{children}</p>
}

export function formatTimestamp(ms: number): string {
  if (!ms) {
    return 'never'
  }
  return new Date(ms).toLocaleTimeString()
}
