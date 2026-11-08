import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { useAuth } from '../auth'
import ChatErrorDialog from '../components/ChatErrorDialog'
import BrandLockup from '../components/BrandLockup'
import Composer from '../components/chat/Composer'
import MessageBubble, { type UiMessage } from '../components/chat/MessageBubble'
import ReferencePanel from '../components/chat/ReferencePanel'
import Icon from '../components/Icon'
import Logo from '../components/Logo'
import PrefToggles from '../components/PrefToggles'
import { useI18n } from '../i18n'
import { ApiError } from '../lib/api'
import { streamTo, type SourceRef } from '../lib/conversations'
import { classifyChatError, type ChatErrorInfo } from '../lib/chatErrors'
import { getSharedLink, sharedLinkStreamPath, type SharedLinkView } from '../lib/shares'

const POLL_MS = 6000

/** Trang công khai /s/:token: xem cuộc trò chuyện được chia sẻ bằng liên kết; chat tiếp nếu liên kết cho phép và đã đăng nhập email CTU. */
export default function SharedView() {
  const { token = '' } = useParams()
  const { t } = useI18n()
  const { user, status } = useAuth()
  const location = useLocation()

  const [view, setView] = useState<SharedLinkView | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [chatError, setChatError] = useState<string | null>(null)
  const [errorDialog, setErrorDialog] = useState<ChatErrorInfo | null>(null)
  const [reference, setReference] = useState<{ article: number; sources: SourceRef[] } | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const startedAtRef = useRef(0)
  const busyRef = useRef(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true) // đang ở cuối khung chat thì tự cuộn theo tin mới; cuộn lên đọc thì thôi

  useEffect(() => {
    busyRef.current = busy
  }, [busy])

  // Đã đăng nhập hay chưa quyết định `can_chat`, nên tải lại khi trạng thái đăng nhập xong/đổi.
  const load = useCallback(
    async (silent = false) => {
      try {
        const data = await getSharedLink(token)
        setView(data)
        setNotFound(false)
        setLoadError(false)
        setMessages((cur) =>
          silent && (cur.some((m) => m.pending) || (data.messages.length === cur.length && data.messages.at(-1)?.id === cur.at(-1)?.id))
            ? cur
            : data.messages,
        )
      } catch (err) {
        if (silent) return
        if (err instanceof ApiError && err.status === 404) setNotFound(true)
        else setLoadError(true)
      }
    },
    [token],
  )

  useEffect(() => {
    if (status === 'loading') return
    load()
  }, [load, status, user?.id])

  // Người khác có thể vừa chat thêm: tải lại định kỳ khi tab đang mở và mình không đang chờ trả lời.
  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden && !busyRef.current && status !== 'loading') load(true)
    }, POLL_MS)
    return () => clearInterval(id)
  }, [load, status])

  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => setElapsed((performance.now() - startedAtRef.current) / 1000), 100)
    return () => clearInterval(id)
  }, [busy])

  useEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [messages, view?.title])

  const handleScroll = () => {
    const el = scrollRef.current
    if (el) stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  const send = async (text: string) => {
    const content = text.trim()
    if (!content || busy || !view?.can_chat) return
    const stamp = Date.now()
    const tempBotId = `tmp-bot-${stamp}`
    let userId = `tmp-user-${stamp}`
    const controller = new AbortController()
    abortRef.current = controller
    startedAtRef.current = performance.now()
    setElapsed(0)
    setBusy(true)
    setChatError(null)
    setDraft('')
    stickRef.current = true
    setMessages((list) => [
      ...list,
      { id: userId, role: 'user', content, created_at: new Date().toISOString(), duration_seconds: null },
      { id: tempBotId, role: 'assistant', content: '', created_at: null, duration_seconds: null, pending: true },
    ])
    try {
      await streamTo(
        sharedLinkStreamPath(token),
        content,
        {
          onQueued: (position) => setMessages((list) => list.map((m) => (m.id === tempBotId ? { ...m, queuePosition: position } : m))),
          onStart: (saved) => {
            const previous = userId
            userId = saved.id
            setMessages((list) => list.map((m) => (m.id === previous ? saved : m.id === tempBotId ? { ...m, queuePosition: undefined } : m)))
          },
          onToken: (piece) => setMessages((list) => list.map((m) => (m.id === tempBotId ? { ...m, content: m.content + piece } : m))),
          onDone: ({ assistant_message }) => {
            const total = Math.round(((performance.now() - startedAtRef.current) / 1000) * 10) / 10
            setElapsed(total)
            setMessages((list) => list.map((m) => (m.id === tempBotId ? { ...assistant_message, duration_seconds: total } : m)))
          },
        },
        controller.signal,
      )
    } catch (err) {
      setMessages((list) => list.filter((m) => m.id !== userId && m.id !== tempBotId))
      setDraft((current) => current || content)
      if (!(err instanceof DOMException && err.name === 'AbortError')) setErrorDialog(classifyChatError(err, t))
    } finally {
      abortRef.current = null
      setBusy(false)
    }
  }

  const header = (
    <header className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-4 py-3 sm:px-8">
      <Link to="/" className="flex items-center text-heading no-underline">
        <BrandLockup size={52} />
      </Link>
      <div className="ml-auto flex items-center gap-3">
        {user ? (
          <Link
            to="/chat"
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-field px-4 text-sm text-heading no-underline hover:bg-tint"
          >
            <Icon name="chat" size={16} />
            {t('share.openChat')}
          </Link>
        ) : (
          <Link
            to="/login"
            state={{ from: location.pathname }}
            className="inline-flex min-h-11 items-center rounded-lg bg-ctu-navy px-4 text-sm font-semibold text-white no-underline hover:bg-ctu-navy-dark"
          >
            {t('login.title')}
          </Link>
        )}
        <PrefToggles />
      </div>
    </header>
  )

  if (notFound || loadError) {
    return (
      <div className="flex min-h-dvh flex-col bg-surface">
        {header}
        <main className="grid flex-1 place-items-center px-6 text-center">
          <div className="flex flex-col items-center gap-4">
            <Logo size={56} />
            <p role="alert" className="m-0 text-lg text-heading">{notFound ? t('share.notFound') : t('chat.errLoad')}</p>
            {loadError && (
              <button
                type="button"
                onClick={() => load()}
                className="min-h-11 cursor-pointer rounded-lg border border-ctu-cyan bg-surface px-4 font-sans text-sm text-accent hover:bg-tint"
              >
                {t('admin.doc.retry')}
              </button>
            )}
            <Link to="/" className="text-sm">{t('share.backHome')}</Link>
          </div>
        </main>
      </div>
    )
  }

  const canChat = view?.can_chat ?? false
  const needLogin = view?.permission === 'chat' && !user && status !== 'loading'

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-surface">
      {header}
      <ChatErrorDialog error={errorDialog} onClose={() => setErrorDialog(null)} />
      <div className="flex min-h-0 flex-1">
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="border-b border-line px-4 py-3 sm:px-8">
            <h1 className="m-0 truncate text-lg">{view?.title || t('chat.untitled')}</h1>
            {view && (
              <p className="m-0 mt-0.5 flex flex-wrap items-center gap-2 text-xs">
                <span>
                  {t('share.sharedBy')} <strong className="text-heading">{view.owner_name}</strong>
                </span>
                <span className="rounded-full bg-tint px-2 py-0.5 font-semibold text-accent">
                  {canChat ? t('share.badge.chat') : t('share.badge.view')}
                </span>
              </p>
            )}
          </div>

          {chatError && (
            <div role="alert" className="mx-4 mt-3 flex items-start gap-3 rounded-lg border border-[#E7B4B6] bg-[#FDF3F3] px-4 py-3 text-sm text-[#8A1216] sm:mx-8 dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]">
              <Icon name="warn" className="mt-[3px] flex-none" />
              <span className="flex-1">{chatError}</span>
            </div>
          )}

          <div ref={scrollRef} onScroll={handleScroll} role="log" aria-live="polite" className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-4 py-6 [scrollbar-gutter:stable_both-edges] sm:p-8">
            {!view && <p role="status">{t('chat.loadingConversation')}</p>}
            {messages.length > 0 && (
              <div className="flex w-full max-w-[860px] flex-col gap-6">
                {messages.map((m) => (
                  <MessageBubble
                    key={m.id}
                    message={m}
                    liveElapsed={elapsed}
                    onOpenReference={(article, sources) => setReference({ article, sources })}
                    activeArticle={reference?.article ?? null}
                  />
                ))}
              </div>
            )}
          </div>

          {canChat ? (
            <Composer value={draft} onChange={setDraft} onSend={() => send(draft)} onStop={() => abortRef.current?.abort()} busy={busy} />
          ) : (
            <div className="flex justify-center px-4 pb-6 pt-2 sm:px-8">
              <div className="flex w-full max-w-[860px] flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-tint px-5 py-3.5 text-sm text-heading">
                <span role="status">{needLogin ? t('share.publicLoginToChat') : t('share.publicViewOnly')}</span>
                {needLogin && (
                  <Link
                    to="/login"
                    state={{ from: location.pathname }}
                    className="inline-flex min-h-11 items-center rounded-lg bg-ctu-navy px-5 text-sm font-semibold text-white no-underline hover:bg-ctu-navy-dark"
                  >
                    {t('share.login')}
                  </Link>
                )}
              </div>
            </div>
          )}
        </main>

        {reference !== null && (
          <ReferencePanel
            article={reference.article}
            sources={reference.sources}
            onSelect={(article) => setReference((prev) => (prev ? { ...prev, article } : prev))}
            onClose={() => setReference(null)}
          />
        )}
      </div>
    </div>
  )
}
