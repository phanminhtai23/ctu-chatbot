import { useState } from 'react'
import { useI18n } from '../../i18n'
import type { TranslationKey } from '../../i18n/vi'
import type { RouteConfig, RouteNode } from '../../lib/adminDocuments'

type Props = {
  config: RouteConfig
  editable: boolean
  onChange: (config: RouteConfig) => void
}

const NODE_HEIGHT = 68
const NODE_GAP = 16
const NODE_X = 560
const NODE_WIDTH = 310
const routeKindLabel: Record<RouteNode['kind'], TranslationKey> = {
  document: 'admin.doc.routeDocument',
  web: 'admin.doc.routeKind.web',
  smalltalk: 'admin.doc.routeKind.smalltalk',
  offtopic: 'admin.doc.routeKind.offtopic',
}

export default function RouteGraph({ config, editable, onChange }: Props) {
  const { t } = useI18n()
  const [selected, setSelected] = useState<string>('router')
  const height = Math.max(220, config.nodes.length * (NODE_HEIGHT + NODE_GAP) + 30)
  const routerY = height / 2 - 38

  const updateNode = (nodeId: string, patch: Partial<RouteNode>) => {
    onChange({ ...config, nodes: config.nodes.map((node) => (node.id === nodeId ? { ...node, ...patch } : node)) })
  }

  const toggleEdge = (nodeId: string, enabled: boolean) => {
    onChange({
      ...config,
      edges: config.edges.map((edge) => (edge.to === nodeId ? { ...edge, enabled } : edge)),
    })
  }

  const activeNode = config.nodes.find((node) => node.id === selected)

  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div className="overflow-x-auto rounded-xl border border-line bg-tint/40 p-3">
        <div className="relative" style={{ width: 900, height }}>
          <svg className="absolute inset-0 size-full" viewBox={`0 0 900 ${height}`} aria-hidden="true">
            <defs>
              <marker id="route-arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto">
                <path d="M0,0 L9,4.5 L0,9 z" className="fill-ctu-cyan" />
              </marker>
            </defs>
            {config.nodes.map((node, index) => {
              const y = 18 + index * (NODE_HEIGHT + NODE_GAP) + NODE_HEIGHT / 2
              const enabled = config.edges.find((edge) => edge.to === node.id)?.enabled ?? false
              return (
                <path
                  key={node.id}
                  d={`M 280 ${routerY + 38} C 400 ${routerY + 38}, 430 ${y}, ${NODE_X} ${y}`}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={enabled ? 2.5 : 1.5}
                  strokeDasharray={enabled ? undefined : '7 7'}
                  className={enabled ? 'text-ctu-cyan' : 'text-line'}
                  markerEnd={enabled ? 'url(#route-arrow)' : undefined}
                />
              )
            })}
          </svg>

          <button
            type="button"
            onClick={() => setSelected('router')}
            aria-pressed={selected === 'router'}
            className={`absolute left-8 flex h-[76px] w-[248px] flex-col justify-center rounded-xl border-2 bg-surface px-4 text-left shadow-sm transition ${
              selected === 'router' ? 'border-ctu-cyan ring-2 ring-ctu-cyan/20' : 'border-line hover:border-ctu-cyan'
            }`}
            style={{ top: routerY }}
          >
            <span className="text-xs font-semibold uppercase tracking-wide text-accent">{t('admin.doc.router')}</span>
            <span className="mt-1 text-sm font-semibold text-heading">{t('admin.doc.routeClassifier')}</span>
          </button>

          {config.nodes.map((node, index) => {
            const top = 18 + index * (NODE_HEIGHT + NODE_GAP)
            const enabled = config.edges.find((edge) => edge.to === node.id)?.enabled ?? false
            return (
              <div
                key={node.id}
                className={`absolute rounded-xl border-2 bg-surface shadow-sm transition ${
                  selected === node.id ? 'border-ctu-cyan ring-2 ring-ctu-cyan/20' : enabled ? 'border-line' : 'border-line opacity-60'
                }`}
                style={{ left: NODE_X, top, width: NODE_WIDTH, height: NODE_HEIGHT }}
              >
                <button
                  type="button"
                  onClick={() => setSelected(node.id)}
                  aria-pressed={selected === node.id}
                  className="flex h-full w-full flex-col justify-center rounded-[10px] border-0 bg-transparent px-4 pr-24 text-left font-sans"
                >
                  <span className="truncate text-sm font-semibold text-heading">{node.label}</span>
                  <span className="mt-1 truncate text-xs text-muted">
                    {node.kind === 'document'
                      ? node.version
                        ? `${node.status === 'pending' ? t('admin.doc.routePending') : t('admin.doc.routeDocument')} · ${node.version}`
                        : t('admin.doc.routeDocument')
                      : t(routeKindLabel[node.kind])}
                  </span>
                </button>
                <label className="absolute right-3 top-1/2 flex -translate-y-1/2 cursor-pointer items-center gap-1.5 text-xs font-semibold text-heading">
                  <input
                    type="checkbox"
                    checked={enabled}
                    disabled={!editable || node.status === 'pending'}
                    onChange={(event) => toggleEdge(node.id, event.target.checked)}
                    aria-label={`${t('admin.doc.edge')} ${node.label}`}
                    className="size-4 accent-ctu-navy"
                  />
                  {t('admin.doc.edge')}
                </label>
              </div>
            )
          })}
        </div>
      </div>

      <section className="rounded-xl border border-line bg-surface p-4" aria-label={t('admin.doc.routePrompt')}>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="m-0 text-sm font-semibold text-heading">
            {selected === 'router' ? t('admin.doc.routerPrompt') : activeNode?.label ?? t('admin.doc.routePrompt')}
          </h3>
          {!editable && <span className="text-xs text-muted">{t('admin.doc.routeReadOnly')}</span>}
        </div>
        <textarea
          value={selected === 'router' ? config.router_prompt : activeNode?.prompt ?? ''}
          onChange={(event) => {
            if (selected === 'router') onChange({ ...config, router_prompt: event.target.value })
            else if (activeNode) updateNode(activeNode.id, { prompt: event.target.value })
          }}
          disabled={!editable}
          rows={4}
          maxLength={selected === 'router' ? 8000 : 4000}
          className="min-h-24 w-full resize-y rounded-lg border border-field bg-surface px-3 py-2 font-sans text-sm text-heading outline-none focus:border-ctu-cyan focus:ring-2 focus:ring-ctu-cyan/20 disabled:cursor-not-allowed disabled:opacity-70"
        />
        {activeNode?.kind === 'document' && activeNode.source && (
          <p className="mb-0 mt-2 break-all text-xs text-muted">
            {t('admin.doc.routeSource')}: {activeNode.source}
          </p>
        )}
      </section>
    </div>
  )
}
