import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'
import { listSelectableRoutes, type SourceRoute } from '../lib/documents'
import Icon from './Icon'

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

/**
 * Tab "Nguồn hỏi" trong hộp thoại cài đặt: người dùng chọn tài liệu / nguồn mà chatbot được tra cứu để trả lời.
 * Mặc định (document_routes = null) là TẤT CẢ; chọn bớt giúp chatbot phân loại nhanh và đúng hơn.
 */
export default function SourcePicker() {
  const { t } = useI18n()
  const { user, updateProfile } = useAuth()
  const [routes, setRoutes] = useState<SourceRoute[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [chosen, setChosen] = useState<string[] | null>(user?.document_routes ?? null) // null = tất cả
  const [saveState, setSaveState] = useState<SaveState>('idle')

  useEffect(() => {
    let cancelled = false
    listSelectableRoutes()
      .then((list) => !cancelled && setRoutes(list))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [])

  const saved = user?.document_routes ?? null
  const ids = useMemo(() => routes?.map((r) => r.id) ?? [], [routes])
  // Các lựa chọn đã lưu mà tuyến đã bị gỡ thì bỏ qua khi hiển thị.
  const effective = useMemo(() => (chosen === null ? ids : chosen.filter((id) => ids.includes(id))), [chosen, ids])
  const allSelected = routes !== null && effective.length === ids.length
  const dirty = JSON.stringify(allSelected ? null : [...effective].sort()) !== JSON.stringify(saved === null ? null : [...saved].sort())
  const canSave = dirty && effective.length > 0 && saveState !== 'saving'

  const toggle = (id: string) => {
    setSaveState('idle')
    const next = effective.includes(id) ? effective.filter((x) => x !== id) : [...effective, id]
    setChosen(next.length === ids.length ? null : next)
  }

  const save = async () => {
    if (!canSave) return
    setSaveState('saving')
    try {
      await updateProfile({ document_routes: allSelected ? null : effective })
      setSaveState('saved')
    } catch {
      setSaveState('error')
    }
  }

  if (failed) return <p role="alert" className="m-0 text-sm">{t('sources.loadError')}</p>
  if (!routes) return <p role="status" className="m-0 text-sm">{t('files.loading')}</p>

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="m-0 text-base text-heading">{t('sources.title')}</h3>
        <p className="mb-0 mt-1 text-sm">{t('sources.hint')}</p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-tint px-4 py-3">
        <span className="text-sm text-heading">
          <strong className="font-semibold">{allSelected ? t('sources.all') : `${effective.length}/${ids.length} ${t('sources.selected')}`}</strong>
          {allSelected && <span className="ml-2 text-muted">{t('sources.allHint')}</span>}
        </span>
        {!allSelected && (
          <button
            type="button"
            onClick={() => {
              setChosen(null)
              setSaveState('idle')
            }}
            className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-transparent px-4 font-sans text-sm font-semibold text-accent hover:bg-surface"
          >
            {t('sources.useAll')}
          </button>
        )}
      </div>

      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {routes.map((route) => {
          const on = effective.includes(route.id)
          return (
            <li key={route.id}>
              <label
                className={`flex cursor-pointer items-start gap-3 rounded-xl border-2 px-4 py-3 ${
                  on ? 'border-accent bg-tint' : 'border-line hover:bg-tint'
                }`}
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => toggle(route.id)}
                  className="mt-1 size-5 flex-none accent-[var(--accent)]"
                />
                <span className="flex size-9 flex-none items-center justify-center rounded-xl bg-surface text-accent">
                  <Icon name={route.kind === 'web' ? 'search' : 'doc'} size={18} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="break-words text-[15px] font-semibold text-heading">{route.label}</span>
                    {route.decision_no && (
                      <span className="rounded-md border border-ctu-cyan px-1.5 py-0.5 text-xs font-semibold text-accent">{route.decision_no}</span>
                    )}
                    {route.kind === 'web' && <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">{t('sources.web')}</span>}
                  </span>
                  {route.description && <span className="mt-1 block break-words text-sm">{route.description}</span>}
                  {route.official_url && (
                    <a
                      href={route.official_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(event) => event.stopPropagation()}
                      className="mt-1 inline-block text-sm font-semibold text-accent"
                    >
                      {t('admin.doc.lib.openOfficial')}
                    </a>
                  )}
                </span>
              </label>
            </li>
          )
        })}
        <li>
          {/* Sắp ra mắt: chưa chọn được, chỉ báo trước cho người dùng */}
          <div
            aria-disabled="true"
            className="flex cursor-not-allowed items-start gap-3 rounded-xl border-2 border-dashed border-line px-4 py-3 opacity-80"
          >
            <input type="checkbox" disabled aria-describedby="source-custom-note" className="mt-1 size-5 flex-none" />
            <span className="flex size-9 flex-none items-center justify-center rounded-xl bg-tint text-accent">
              <Icon name="upload" size={18} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="break-words text-[15px] font-semibold text-heading">{t('sources.custom.title')}</span>
                <span className="rounded-full border border-ctu-gold-active bg-[#FFF8E1] px-2 py-0.5 text-xs font-semibold text-[#7A5200] dark:bg-[#302711] dark:text-[#F2CB74]">
                  {t('sources.custom.soon')}
                </span>
              </span>
              <span id="source-custom-note" className="mt-1 block break-words text-sm">
                {t('sources.custom.text')}
              </span>
            </span>
          </div>
        </li>
      </ul>

      {routes.length > 1 && effective.length === 0 && (
        <p role="alert" className="m-0 text-sm text-[#8A1216] dark:text-[#FFB4B7]">
          {t('sources.atLeastOne')}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        <button
          type="button"
          onClick={() => void save()}
          disabled={!canSave}
          className="min-h-11 cursor-pointer rounded-lg border-0 bg-ctu-navy px-6 py-2.5 font-sans text-base font-semibold text-white hover:bg-ctu-navy-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t(saveState === 'saving' ? 'profile.saving' : 'profile.save')}
        </button>
        <span role="status" aria-live="polite" className="text-sm">
          {saveState === 'saved' && (
            <span className="inline-flex items-center gap-1.5 text-[#14602F] dark:text-[#8AD9A8]">
              <Icon name="check" size={18} strokeWidth={2.2} />
              {t('sources.saved')}
            </span>
          )}
          {saveState === 'error' && <span className="text-[#8A1216] dark:text-[#FFB4B7]">{t('profile.saveError')}</span>}
        </span>
      </div>
    </div>
  )
}
