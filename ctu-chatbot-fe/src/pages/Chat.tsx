import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth'
import Composer from '../components/chat/Composer'
import ConversationList from '../components/chat/ConversationList'
import MessageBubble, { type UiMessage } from '../components/chat/MessageBubble'
import ReferencePanel from '../components/chat/ReferencePanel'
import ConfirmDialog from '../components/ConfirmDialog'
import FeedbackModal from '../components/FeedbackModal'
import Icon from '../components/Icon'
import Logo from '../components/Logo'
import PrefToggles from '../components/PrefToggles'
import Sidebar, { labelClass, useSidebarCollapsed } from '../components/Sidebar'
import { useI18n } from '../i18n'
import { ApiError } from '../lib/api'
import {
  ChatStreamError,
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  streamMessage,
  type Conversation,
  type SourceRef,
} from '../lib/conversations'
import type { FeedbackType } from '../lib/feedback'
import { getSuggestions, type Suggestion } from '../lib/suggestions'

const STICK_THRESHOLD_PX = 120

type FeedbackTarget = { type: FeedbackType; messageId: string | null }

export default function Chat() {
  const { t } = useI18n()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { conversationId } = useParams<{ conversationId?: string }>()

  const displayName = user?.name || user?.email || ''
  const initials = displayName.trim().split(/\s+/).slice(-2).map((w) => w[0]?.toUpperCase() ?? '').join('')
  const [collapsed, toggleSidebar] = useSidebarCollapsed('ctu-chat-sidebar')

  // --- Danh sách cuộc trò chuyện ---
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [listState, setListState] = useState<'loading' | 'ready' | 'error'>('loading')

  const loadList = useCallback(async () => {
    setListState('loading')
    try {
      setConversations(await listConversations())
      setListState('ready')
    } catch {
      setListState('error')
    }
  }, [])

  useEffect(() => {
    loadList()
  }, [loadList])

  // --- Cuộn xuống cuối khi có tin mới, trừ khi người dùng đang cuộn lên đọc ---
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)

  const handleScroll = () => {
    const el = scrollRef.current
    if (el) stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_THRESHOLD_PX
  }

  // --- Nội dung cuộc trò chuyện đang mở ---
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [loadingConversation, setLoadingConversation] = useState(false)
  const [loadError, setLoadError] = useState(false)
  // Cuộc trò chuyện vừa tự tạo khi gửi tin đầu tiên: tin nhắn đang nằm sẵn trong state nên đừng nạp lại từ server.
  const skipLoadRef = useRef<string | null>(null)

  useEffect(() => {
    setLoadError(false)
    if (!conversationId) {
      setMessages([])
      setLoadingConversation(false)
      return
    }
    if (skipLoadRef.current === conversationId) {
      skipLoadRef.current = null
      return
    }
    let cancelled = false
    setMessages([])
    setLoadingConversation(true)
    getConversation(conversationId)
      .then((detail) => {
        if (cancelled) return
        stickRef.current = true
        setMessages(detail.messages)
        setLoadingConversation(false)
      })
      .catch((err) => {
        if (cancelled) return
        setLoadingConversation(false)
        if (err instanceof ApiError && err.status === 404) navigate('/chat', { replace: true })
        else setLoadError(true)
      })
    return () => {
      cancelled = true
    }
  }, [conversationId, navigate])

  useEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [messages, loadingConversation])

  // --- Gửi tin & nhận câu trả lời theo từng đoạn ---
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [chatError, setChatError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const startedAtRef = useRef(0)

  // Đồng hồ chạy trong lúc chờ chatbot; khi xong, tin của bot hiện con số chính xác do server đo.
  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => setElapsed((performance.now() - startedAtRef.current) / 1000), 100)
    return () => clearInterval(id)
  }, [busy])

  const describeError = useCallback(
    (err: unknown): string => {
      if (err instanceof ChatStreamError) {
        switch (err.code) {
          case 'LLM_RATE_LIMITED':
            return `${t('chat.errRateLimited')}${err.retryAfter ?? ''}${t('chat.errRateLimitedSuffix')}`
          case 'LLM_NOT_CONFIGURED':
            return t('chat.errNotConfigured')
          case 'STREAM_INTERRUPTED':
            return t('chat.errInterrupted')
          default:
            return t('chat.errLlm')
        }
      }
      if (err instanceof ApiError && err.status === 429) return t('chat.errTooManyMessages')
      if (err instanceof ApiError) return t('chat.errLlm')
      return t('chat.errNetwork')
    },
    [t],
  )

  const send = useCallback(
    async (text: string) => {
      const content = text.trim()
      if (!content || busy) return

      const stamp = Date.now()
      const tempBotId = `tmp-bot-${stamp}`
      let userMessageId = `tmp-user-${stamp}`
      const now = new Date().toISOString()

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
        { id: userMessageId, role: 'user', content, created_at: now, duration_seconds: null },
        { id: tempBotId, role: 'assistant', content: '', created_at: null, duration_seconds: null, pending: true },
      ])

      let createdId: string | null = null // cuộc trò chuyện do chính lượt gửi này tạo ra
      try {
        let id = conversationId
        if (!id) {
          const created = await createConversation()
          id = createdId = created.id
          skipLoadRef.current = created.id
          setConversations((list) => [created, ...list])
          navigate(`/chat/${created.id}`, { replace: true })
        }

        await streamMessage(
          id,
          content,
          {
            onStart: (saved) => {
              const previousId = userMessageId
              userMessageId = saved.id
              setMessages((list) => list.map((m) => (m.id === previousId ? saved : m)))
            },
            onToken: (piece) =>
              setMessages((list) => list.map((m) => (m.id === tempBotId ? { ...m, content: m.content + piece } : m))),
            onDone: ({ assistant_message, conversation }) => {
              setMessages((list) => list.map((m) => (m.id === tempBotId ? assistant_message : m)))
              if (conversation) {
                setConversations((list) => [conversation, ...list.filter((c) => c.id !== conversation.id)])
              }
            },
          },
          controller.signal,
        )
      } catch (err) {
        // Server đã gỡ tin của người dùng khỏi lịch sử nên giao diện cũng gỡ, và trả nội dung về ô nhập để gửi lại.
        setMessages((list) => list.filter((m) => m.id !== userMessageId && m.id !== tempBotId))
        setDraft((current) => current || content)
        if (!(err instanceof DOMException && err.name === 'AbortError')) setChatError(describeError(err))
        if (createdId) {
          // Tin đầu tiên thất bại/bị dừng: đừng để lại cuộc trò chuyện trống trong danh sách.
          const orphanId = createdId
          deleteConversation(orphanId).catch(() => {})
          setConversations((list) => list.filter((c) => c.id !== orphanId))
          navigate('/chat', { replace: true })
        }
      } finally {
        abortRef.current = null
        setBusy(false)
      }
    },
    [busy, conversationId, describeError, navigate],
  )

  // --- Tạo cuộc trò chuyện mới: bấm nút là gọi API tạo ngay ---
  const [creating, setCreating] = useState(false)

  const focusComposer = () => requestAnimationFrame(() => document.getElementById('question')?.focus())

  const startNewConversation = async () => {
    if (busy || creating) return
    setChatError(null)

    // Đã có sẵn một cuộc trò chuyện trống (chưa có tin nào, nên chưa có tiêu đề) thì mở lại nó,
    // tránh bấm liên tục làm danh sách đầy cuộc trò chuyện rỗng.
    const blank = conversations.find((c) => c.title === '')
    if (blank) {
      if (blank.id !== conversationId) navigate(`/chat/${blank.id}`)
      focusComposer()
      return
    }

    setCreating(true)
    try {
      const created = await createConversation()
      skipLoadRef.current = created.id // vừa tạo, chưa có tin nhắn nào để nạp
      setMessages([])
      setConversations((list) => [created, ...list])
      navigate(`/chat/${created.id}`)
      focusComposer()
    } catch {
      setChatError(t('chat.errCreate'))
    } finally {
      setCreating(false)
    }
  }

  // --- Đổi tên / xoá ---
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const handleRename = async (id: string, title: string) => {
    const updated = await renameConversation(id, title)
    setConversations((list) => list.map((c) => (c.id === id ? updated : c)))
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteConversation(deleteTarget.id)
    } catch {
      setDeleteError(t('chat.errDelete'))
      return
    }
    const removedId = deleteTarget.id
    setConversations((list) => list.filter((c) => c.id !== removedId))
    setDeleteTarget(null)
    setDeleteError(null)
    if (removedId === conversationId) navigate('/chat')
  }

  // --- Góp ý / báo câu trả lời sai ---
  const [feedback, setFeedback] = useState<{ open: boolean } & FeedbackTarget>({
    open: false,
    type: 'general',
    messageId: null,
  })
  const closeFeedback = () => setFeedback((prev) => ({ ...prev, open: false }))

  // Câu hỏi gợi ý khi mới mở chat: bấm là trả lời ngay từ cache của server, không gọi LLM.
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  useEffect(() => {
    let alive = true
    getSuggestions()
      .then((items) => {
        if (alive) setSuggestions(items)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  // Điều đang xem trong cửa sổ tham chiếu bên phải (null = đóng)
  const [reference, setReference] = useState<{ article: number; sources: SourceRef[] } | null>(null)
  const openReference = useCallback(
    (article: number, sources: SourceRef[]) => setReference({ article, sources }),
    [],
  )
  const closeReference = useCallback(() => setReference(null), [])

  const activeTitle = conversations.find((c) => c.id === conversationId)?.title
  const isEmpty = !conversationId || (messages.length === 0 && !loadingConversation && !loadError)

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-surface md:flex-row">
      <FeedbackModal
        open={feedback.open}
        type={feedback.type}
        conversationId={conversationId ?? null}
        messageId={feedback.messageId}
        onClose={closeFeedback}
      />
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t('chat.deleteTitle')}
        message={deleteTarget ? `“${deleteTarget.title || t('chat.untitled')}” — ${t('chat.deleteText')}` : ''}
        confirmLabel={t('chat.delete')}
        error={deleteError}
        onConfirm={confirmDelete}
        onCancel={() => {
          setDeleteTarget(null)
          setDeleteError(null)
        }}
      />

      <Sidebar
        collapsed={collapsed}
        onToggle={toggleSidebar}
        title={t('brand.app')}
        subtitle={t('brand.appSub')}
        footer={
          <div className={`flex items-center gap-3 ${collapsed ? 'md:justify-center' : ''}`}>
            <div className="flex size-10 flex-none items-center justify-center rounded-full bg-ctu-cyan font-semibold text-ctu-navy-dark">
              {initials}
            </div>
            <div className={`min-w-0 flex-1 leading-snug ${labelClass(collapsed)}`}>
              <div className="truncate text-sm font-normal">{displayName}</div>
              <div className="truncate text-xs opacity-80">{user?.email}</div>
            </div>
            <Link
              to="/profile"
              aria-label={t('chat.profile')}
              className={`size-11 items-center justify-center rounded-lg text-white hover:bg-white/10 ${
                collapsed ? 'inline-flex md:hidden' : 'inline-flex'
              }`}
            >
              <Icon name="settings" />
            </Link>
          </div>
        }
      >
        <button
          type="button"
          disabled={busy || creating}
          onClick={startNewConversation}
          aria-label={t('chat.new')}
          title={t('chat.new')}
          className="flex min-h-11 cursor-pointer items-center justify-center gap-2.5 rounded-lg border-0 bg-ctu-gold-active px-4 py-3 font-sans text-[15px] font-semibold text-ctu-navy-dark hover:bg-ctu-gold disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Icon name="plus" size={18} strokeWidth={2.4} />
          <span className={labelClass(collapsed)}>{t('chat.new')}</span>
        </button>

        {user?.role === 'admin' && (
          <Link
            to="/admin/feedback"
            title={t('chat.adminLink')}
            aria-label={t('chat.adminLink')}
            className="flex min-h-11 items-center justify-center gap-2.5 rounded-lg border border-white/30 px-4 py-2 text-sm text-white no-underline hover:bg-white/10"
          >
            <Icon name="inbox" size={18} />
            <span className={labelClass(collapsed)}>{t('chat.adminLink')}</span>
          </Link>
        )}

        <nav aria-label={t('chat.recent')} className={`flex flex-col gap-1 ${collapsed ? 'md:hidden' : ''}`}>
          <div className="px-2 pb-1.5 text-xs uppercase tracking-wider opacity-75">{t('chat.recent')}</div>
          <ConversationList
            conversations={conversations}
            state={listState}
            activeId={conversationId}
            disabled={busy}
            onRename={handleRename}
            onDelete={(c) => setDeleteTarget(c)}
            onRetry={loadList}
          />
        </nav>
      </Sidebar>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-8 sm:py-4">
          <h1 className="m-0 min-w-0 basis-full truncate text-lg lg:flex-1 lg:basis-auto">{activeTitle || t('chat.untitled')}</h1>
          <div className="ml-auto flex flex-wrap items-center gap-3">
            {/* Trên điện thoại sidebar thu gọn nên cần lối tắt để mở cuộc trò chuyện mới. */}
            <button
              type="button"
              disabled={busy || creating}
              onClick={startNewConversation}
              aria-label={t('chat.new')}
              title={t('chat.new')}
              className="inline-flex size-11 cursor-pointer items-center justify-center rounded-lg border-0 bg-ctu-gold-active text-ctu-navy-dark hover:bg-ctu-gold disabled:cursor-not-allowed disabled:opacity-60 md:hidden"
            >
              <Icon name="plus" size={18} strokeWidth={2.4} />
            </button>
            <button
              type="button"
              disabled
              title={t('chat.shareSoon')}
              className="hidden min-h-11 cursor-not-allowed items-center gap-2 rounded-lg border border-accent bg-transparent px-4 py-2 font-sans text-sm font-normal text-accent opacity-60 sm:inline-flex"
            >
              <Icon name="share" size={16} strokeWidth={2} />
              {t('chat.share')}
            </button>
            <button
              type="button"
              onClick={() => setFeedback({ open: true, type: 'general', messageId: null })}
              aria-label={t('chat.feedback')}
              title={t('chat.feedback')}
              className="inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center gap-2 rounded-lg border border-field bg-transparent px-3 py-2 font-sans text-sm font-normal text-heading hover:bg-tint sm:px-4"
            >
              <Icon name="flag" size={16} strokeWidth={2} />
              <span className="hidden sm:inline">{t('chat.feedback')}</span>
            </button>
            <PrefToggles />
          </div>
        </div>

        {chatError && (
          <div
            role="alert"
            className="mx-4 mt-3 flex items-start gap-3 rounded-lg border border-[#E7B4B6] bg-[#FDF3F3] px-4 py-3 text-sm text-[#8A1216] sm:mx-8 dark:border-[#7A2A2E] dark:bg-[#2A1416] dark:text-[#FFB4B7]"
          >
            <Icon name="warn" className="mt-[3px] flex-none" />
            <span className="flex-1">{chatError}</span>
            <button
              type="button"
              onClick={() => setChatError(null)}
              aria-label={t('chat.dismiss')}
              className="inline-flex size-8 flex-none cursor-pointer items-center justify-center rounded-md border-0 bg-transparent text-inherit hover:opacity-70"
            >
              <Icon name="close" size={18} />
            </button>
          </div>
        )}

        <div
          ref={scrollRef}
          onScroll={handleScroll}
          role="log"
          aria-live="polite"
          aria-busy={busy}
          className="relative flex min-h-0 flex-1 flex-col items-center overflow-y-auto px-4 py-6 sm:p-8"
        >
          {loadingConversation && <p role="status">{t('chat.loadingConversation')}</p>}
          {loadError && (
            <p role="alert" className="text-[#8A1216] dark:text-[#FFB4B7]">{t('chat.errLoad')}</p>
          )}

          {isEmpty && !busy && (
            <div className="my-auto flex w-full max-w-[640px] flex-col items-center gap-4 py-8 text-center">
              <Logo size={64} fill="#0D47A1" />
              <h2 className="m-0 text-2xl">{t('chat.emptyTitle')}</h2>
              <p className="m-0">{t('chat.emptyHint')}</p>
              {suggestions.length > 0 && (
                <div className="mt-2 w-full text-left">
                  <p className="mb-3 mt-0 text-center text-sm">{t('chat.suggestHeading')}</p>
                  <div className="flex w-full flex-col gap-3">
                    {suggestions.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => send(s.question)}
                        className="flex min-h-11 cursor-pointer flex-col items-start gap-1.5 rounded-xl border border-line bg-surface px-4 py-3 text-left font-sans text-[15px] font-normal leading-snug text-heading hover:border-ctu-cyan hover:bg-tint"
                      >
                        <span className="rounded-full bg-bubble-user px-2.5 text-xs font-normal text-accent">{s.category}</span>
                        {s.question}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {messages.length > 0 && (
            <div className="flex w-full max-w-[780px] flex-col gap-6">
              {messages.map((m) => (
                <MessageBubble
                  key={m.id}
                  message={m}
                  liveElapsed={elapsed}
                  onReport={(msg) => setFeedback({ open: true, type: 'answer_issue', messageId: msg.id })}
                  onOpenReference={openReference}
                  activeArticle={reference?.article ?? null}
                />
              ))}
            </div>
          )}
        </div>

        <Composer
          value={draft}
          onChange={setDraft}
          onSend={() => send(draft)}
          onStop={() => abortRef.current?.abort()}
          busy={busy}
        />
      </main>

      {reference !== null && (
        <ReferencePanel
          article={reference.article}
          sources={reference.sources}
          onSelect={(article) => setReference((prev) => (prev ? { ...prev, article } : prev))}
          onClose={closeReference}
        />
      )}
    </div>
  )
}
