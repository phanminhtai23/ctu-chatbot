import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useI18n } from '../../i18n'
import { API_BASE_URL } from '../../lib/api'
import type { SourceRef } from '../../lib/conversations'
import { getDocLayout, pageImageUrl, type DocLayout } from '../../lib/documents'
import Icon from '../Icon'

type Props = {
  /** Số Điều đang được tô sáng */
  source: SourceRef
  onClose: () => void
}

const ZOOM_STEPS = [1, 1.4, 1.8]

/**
 * Cửa sổ bên phải hiển thị TOÀN BỘ văn bản quy định: tự cuộn tới đoạn được tham chiếu và tô vàng đoạn đó.
 * Người dùng có thể lật trang, phóng to và thu nhỏ.
 * PDF gốc là bản scan nên mỗi trang là một ảnh; khung tô sáng đặt theo toạ độ chuẩn hoá 0..1.
 */
export default function ReferencePanel({ source, onClose }: Props) {
  const { t } = useI18n()
  const { article } = source
  const documentUrl = source.document_url || null
  const [loaded, setLoaded] = useState<{ documentUrl: string | null; layout: DocLayout | null } | null>(null)
  const result = loaded?.documentUrl === documentUrl ? loaded : null
  const layout = result?.layout ?? null
  const error = result !== null && !layout
  const [zoomIdx, setZoomIdx] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const scrollRef = useRef<HTMLDivElement>(null)
  const pageRefs = useRef<Record<number, HTMLElement | null>>({})
  const highlightRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    let alive = true
    setCurrentPage(1)
    getDocLayout(documentUrl)
      .then((data) => {
        if (alive) setLoaded({ documentUrl, layout: data })
      })
      .catch(() => {
        if (alive) setLoaded({ documentUrl, layout: null })
      })
    return () => {
      alive = false
    }
  }, [documentUrl])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const entry = layout?.articles[String(article)]
  const hasHighlight = !!entry?.highlights.length
  const articleTitle = entry?.title || source.title
  const highlightPages = useMemo(
    () => (entry ? [...new Set(entry.highlights.map((h) => h.page))].sort((a, b) => a - b) : []),
    [entry],
  )
  const pageCount = layout?.page_count ?? 0
  const pdfUrl = documentUrl ? `${API_BASE_URL.replace(/\/$/, '')}${documentUrl}` : null

  const scrollToHighlight = useCallback((smooth = true) => {
    highlightRef.current?.scrollIntoView({ block: 'center', behavior: smooth ? 'smooth' : 'auto' })
  }, [])

  // Đổi Điều hoặc đổi độ phóng to: cuộn lại tới đoạn được tô sáng đầu tiên.
  useEffect(() => {
    if (!entry) return
    const id = window.setTimeout(() => scrollToHighlight(true), 60)
    return () => window.clearTimeout(id)
  }, [article, entry, zoomIdx, scrollToHighlight])

  // Trang đang nhìn thấy = trang cuối cùng có mép trên nằm trên 1/3 khung cuộn.
  const updateCurrentPage = useCallback(() => {
    const container = scrollRef.current
    if (!container) return
    const probe = container.getBoundingClientRect().top + container.clientHeight / 3
    let found = 1
    for (let page = 1; page <= pageCount; page++) {
      const el = pageRefs.current[page]
      if (el && el.getBoundingClientRect().top <= probe) found = page
    }
    setCurrentPage(found)
  }, [pageCount])

  useEffect(() => {
    const id = window.setTimeout(updateCurrentPage, 400)
    return () => window.clearTimeout(id)
  }, [article, layout, zoomIdx, updateCurrentPage])

  const goToPage = (page: number) => {
    const target = Math.min(pageCount, Math.max(1, page))
    pageRefs.current[target]?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }

  const documentLabel = [layout?.title || t('ref.docName'), layout?.decision_no].filter(Boolean).join(' · ')

  const iconButton =
    'inline-flex size-9 flex-none cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-lg text-white hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40'
  const navButton =
    'inline-flex size-8 flex-none cursor-pointer items-center justify-center rounded-md border border-line bg-surface font-sans text-base text-heading hover:bg-tint disabled:cursor-not-allowed disabled:opacity-40'

  return (
    <aside
      role="complementary"
      aria-label={t('ref.title')}
      className="fixed inset-0 z-40 flex min-h-0 flex-col bg-surface lg:static lg:inset-auto lg:z-auto lg:w-[46%] lg:max-w-[780px] lg:flex-none lg:border-l lg:border-line"
    >
      <div className="flex items-center gap-3 bg-ctu-navy px-4 py-3 text-white">
        <Icon name="doc" size={20} className="flex-none text-ctu-gold-active" />
        <div className="min-w-0 flex-1 leading-snug">
          <div className="truncate text-[15px] font-semibold">
            {t('ref.articlePrefix')} {article}
            {articleTitle ? `. ${articleTitle}` : ''}
          </div>
          <div className="break-words text-xs opacity-80">{documentLabel}</div>
        </div>
        <button
          type="button"
          onClick={() => setZoomIdx((i) => Math.max(0, i - 1))}
          disabled={!layout || zoomIdx === 0}
          aria-label={t('ref.zoomOut')}
          title={t('ref.zoomOut')}
          className={iconButton}
        >
          −
        </button>
        <button
          type="button"
          onClick={() => setZoomIdx((i) => Math.min(ZOOM_STEPS.length - 1, i + 1))}
          disabled={!layout || zoomIdx === ZOOM_STEPS.length - 1}
          aria-label={t('ref.zoomIn')}
          title={t('ref.zoomIn')}
          className={iconButton}
        >
          +
        </button>
        <button type="button" onClick={onClose} aria-label={t('ref.close')} title={t('ref.close')} className={iconButton}>
          <Icon name="close" size={20} />
        </button>
      </div>

      {/* Thanh lật trang */}
      <div className="flex items-center gap-2 border-b border-line bg-surface px-3 py-2 text-sm">
        <button type="button" onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1} aria-label={t('ref.prevPage')} title={t('ref.prevPage')} className={navButton}>
          ‹
        </button>
        <span className="min-w-[88px] text-center tabular-nums" aria-live="polite">
          {t('ref.page')} {currentPage} / {pageCount || '…'}
        </span>
        <button type="button" onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= pageCount} aria-label={t('ref.nextPage')} title={t('ref.nextPage')} className={navButton}>
          ›
        </button>
        <button
          type="button"
          onClick={() => scrollToHighlight(true)}
          disabled={!hasHighlight}
          className="ml-auto inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-md border border-ctu-gold-active bg-ctu-gold-active/20 px-3 py-1 font-sans text-[13px] font-normal text-heading hover:bg-ctu-gold-active/40 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Icon name="arrow" size={14} />
          {t('ref.backToHighlight')}
        </button>
      </div>

      <div key={documentUrl ?? 'qd3266'} ref={scrollRef} onScroll={updateCurrentPage} className="min-h-0 flex-1 overflow-auto bg-tint p-3 sm:p-4">
        {!layout && !error && <p role="status">{t('ref.loading')}</p>}
        {error && !pdfUrl && (
          <p role="alert" className="text-[#8A1216] dark:text-[#FFB4B7]">
            {t('ref.error')}
          </p>
        )}
        {((layout && !hasHighlight) || (error && pdfUrl)) && <p role="status">{t('ref.notFound')}</p>}
        {error && pdfUrl && (
          <iframe
            src={pdfUrl}
            title={t('ref.title')}
            className="h-full min-h-[60vh] w-full border-0"
          />
        )}

        {layout && (
          <div className="mx-auto flex flex-col gap-4" style={{ width: `${ZOOM_STEPS[zoomIdx] * 100}%` }}>
            {Array.from({ length: layout.page_count }, (_, i) => i + 1).map((page) => {
              const size = layout.pages[String(page)]
              const highlights = entry ? entry.highlights.filter((h) => h.page === page) : []
              const near = highlightPages.some((p) => Math.abs(p - page) <= 1)
              return (
                <figure
                  key={page}
                  ref={(el) => {
                    pageRefs.current[page] = el
                  }}
                  className="m-0"
                >
                  <div
                    className="relative w-full overflow-hidden rounded-md border border-line bg-white shadow-sm"
                    style={{ aspectRatio: size ? `${size.width} / ${size.height}` : '210 / 297' }}
                  >
                    <img
                      src={pageImageUrl(page, documentUrl)}
                      alt={`${t('ref.page')} ${page}`}
                      loading={near ? 'eager' : 'lazy'}
                      className="absolute inset-0 size-full select-none object-contain"
                      draggable={false}
                    />
                    {highlights.length > 0 && (
                      // Pha màu một lần trên cả lớp để các vùng giao nhau có cùng độ đậm.
                      <div aria-hidden="true" className="pointer-events-none absolute inset-0 opacity-40 mix-blend-multiply">
                        {highlights.map(({ box: [y0, x0, y1, x1] }, i) => (
                          <div
                            key={i}
                            ref={page === highlightPages[0] && i === 0 ? highlightRef : undefined}
                            className="absolute rounded-[3px] bg-[#FBC500]"
                            style={{
                              top: `${y0 * 100}%`,
                              left: `${x0 * 100}%`,
                              height: `${(y1 - y0) * 100}%`,
                              width: `${(x1 - x0) * 100}%`,
                            }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                  <figcaption className="mt-1 text-center text-xs text-muted">
                    {t('ref.page')} {page} / {layout.page_count}
                  </figcaption>
                </figure>
              )
            })}
          </div>
        )}
      </div>
    </aside>
  )
}
