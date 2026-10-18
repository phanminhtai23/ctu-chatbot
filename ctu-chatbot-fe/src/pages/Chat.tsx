import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth'
import ConversationList from '../components/chat/ConversationList'
import MessageBubble, { type UiMessage } from '../components/chat/MessageBubble'
import ReferencePanel from '../components/chat/ReferencePanel'
import Avatar from '../components/Avatar'
import ChatErrorDialog from '../components/ChatErrorDialog'
import ConfirmDialog from '../components/ConfirmDialog'
import FeedbackModal from '../components/FeedbackModal'
import Icon from '../components/Icon'
import Logo from '../components/Logo'
import PrefToggles from '../components/PrefToggles'
import { UsageBar } from '../components/MyFiles'
import ProfileDialog from '../components/ProfileDialog'
import ShareDialog from '../components/ShareDialog'
import Sidebar, { MobileNavButton, labelClass, useMobileNav, useSidebarCollapsed } from '../components/Sidebar'
import { useI18n } from '../i18n'
import { ApiError } from '../lib/api'
import { deleteFile, fileErrorCode, listFiles, uploadFile } from '../lib/files'
import { fileErrorMessage } from '../components/fileErrors'
import Composer, { ATTACH_ACCEPT_TYPES, MAX_ATTACHMENTS, type PendingFile } from '../components/chat/Composer'
import { fillTemplate, formatBytes } from '../lib/format'
import {
  createConversation,
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  streamMessage,
  type Access,
  type Conversation,
  type SourceRef,
} from '../lib/conversations'
import type { FeedbackType } from '../lib/feedback'
import { classifyChatError, type ChatErrorInfo } from '../lib/chatErrors'
import { listSharedWithMe, type SharedWithMe } from '../lib/shares'
import { getSuggestions, type Suggestion } from '../lib/suggestions'

const STICK_THRESHOLD_PX = 120

type FeedbackTarget = { type: FeedbackType; messageId: string | null }

export default function Chat() {
  const { t } = useI18n()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { conversationId } = useParams<{ conversationId?: string }>()

  const displayName = user?.name || user?.email || ''
  const [collapsed, toggleSidebar] = useSidebarCollapsed('ctu-chat-sidebar')
  const [navOpen, setNavOpen] = useMobileNav() // ngăn kéo thanh bên trên điện thoại

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
  // Quyền của người đang xem: cuộc trò chuyện của mình ('owner') hoặc được người khác chia sẻ ('chat' / 'view').
  const [access, setAccess] = useState<Access>('owner')
  const [ownerName, setOwnerName] = useState('')
  const [sharedFlag, setSharedFlag] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [sharedList, setSharedList] = useState<SharedWithMe[]>([])
  const [loadError, setLoadError] = useState(false)
  // Cuộc trò chuyện vừa tự tạo khi gửi tin đầu tiên: tin nhắn đang nằm sẵn trong state nên đừng nạp lại từ server.
  const skipLoadRef = useRef<string | null>(null)

  useEffect(() => {
    setLoadError(false)
    if (!conversationId) {
      setMessages([])
      setLoadingConversation(false)
      setAccess('owner')
      setOwnerName('')
      setSharedFlag(false)
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
        setAccess(detail.access)
        setOwnerName(detail.owner_name)
        setSharedFlag(detail.shared)
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

  // Cuộc trò chuyện đang được chia sẻ: người khác có thể vừa chat thêm, nên cứ vài giây (khi tab đang mở và mình
  // không đang chờ trả lời) tải lại để thấy tin mới.
  const busyRef = useRef(false)
  useEffect(() => {
    if (!conversationId || (access === 'owner' && !sharedFlag)) return
    const id = setInterval(async () => {
      if (document.hidden || busyRef.current) return
      try {
        const d = await getConversation(conversationId)
        setAccess(d.access)
        setSharedFlag(d.shared)
        setMessages((cur) =>
          cur.some((m) => m.pending) || (d.messages.length === cur.length && d.messages.at(-1)?.id === cur.at(-1)?.id)
            ? cur
            : d.messages,
        )
      } catch {
        /* mất mạng thoáng qua: lần sau thử lại */
      }
    }, 6000)
    return () => clearInterval(id)
  }, [conversationId, access, sharedFlag])

  // Danh sách các cuộc trò chuyện người khác chia sẻ cho mình (làm mới khi đổi cuộc trò chuyện).
  useEffect(() => {
    listSharedWithMe()
      .then(setSharedList)
      .catch(() => {})
  }, [conversationId])

  // --- Gửi tin & nhận câu trả lời theo từng đoạn ---
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    busyRef.current = busy
  }, [busy])
  const [chatError, setChatError] = useState<string | null>(null)
  // Tệp (PDF / ảnh) đang chuẩn bị đính kèm: tải lên ngay khi chọn, gửi cùng tin nhắn kế tiếp.
  const [pending, setPending] = useState<PendingFile[]>([])
  const pendingRef = useRef<PendingFile[]>([])
  useEffect(() => {
    pendingRef.current = pending
  }, [pending])
  // Lỗi khi gửi tin (bị giới hạn tốc độ, chatbot bận, lỗi LLM...) hiện trong hộp thoại có GIF; lỗi khác vẫn dùng banner.
  const [errorDialog, setErrorDialog] = useState<ChatErrorInfo | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const startedAtRef = useRef(0)

  // Đồng hồ chạy trong lúc chờ chatbot; khi xong, tin của bot hiện con số chính xác do server đo.
  useEffect(() => {
    if (!busy) return
    const id = setInterval(() => setElapsed((performance.now() - startedAtRef.current) / 1000), 100)
    return () => clearInterval(id)
  }, [busy])

  const send = useCallback(
    async (text: string) => {
      const content = text.trim()
      const files = pendingRef.current.filter((p) => p.status === 'ready' && p.file)
      if ((!content && files.length === 0) || busy) return
      setPending([]) // tệp đã được đính kèm vào tin này; còn lưu trong kho của người dùng
      pendingRef.current = []

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
        { id: userMessageId, role: 'user', content, created_at: now, duration_seconds: null, attachments: files.map((f) => f.file!) },
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
            onQueued: (position) =>
              setMessages((list) => list.map((m) => (m.id === tempBotId ? { ...m, queuePosition: position } : m))),
            onStart: (saved) => {
              const previousId = userMessageId
              userMessageId = saved.id
              setMessages((list) =>
                list.map((m) => (m.id === previousId ? saved : m.id === tempBotId ? { ...m, queuePosition: undefined } : m)),
              )
            },
            onToken: (piece) =>
              setMessages((list) => list.map((m) => (m.id === tempBotId ? { ...m, content: m.content + piece } : m))),
            onDone: ({ assistant_message, conversation }) => {
              // Con số cuối chính là con số đồng hồ đang chạy: tính từ lúc người dùng bấm gửi tới lúc nhận đủ câu trả lời
              // (gồm cả thời gian chờ hàng đợi và mạng), không đổi sang số server đo nên không bị "nhảy".
              const total = Math.round(((performance.now() - startedAtRef.current) / 1000) * 10) / 10
              setElapsed(total)
              setMessages((list) =>
                list.map((m) => (m.id === tempBotId ? { ...assistant_message, duration_seconds: total } : m)),
              )
              if (conversation) {
                setConversations((list) => [conversation, ...list.filter((c) => c.id !== conversation.id)])
              }
            },
          },
          controller.signal,
          files.map((f) => f.file!.id),
        )
      } catch (err) {
        // Server đã gỡ tin của người dùng khỏi lịch sử nên giao diện cũng gỡ, và trả nội dung về ô nhập để gửi lại.
        setMessages((list) => list.filter((m) => m.id !== userMessageId && m.id !== tempBotId))
        const aborted = err instanceof DOMException && err.name === 'AbortError'
        const info = aborted ? null : classifyChatError(err, t)
        if (info?.kind !== 'warning') {
          setDraft((current) => current || content) // tin bị chặn vì chửi thề thì không trả lại ô nhập
          setPending((current) => (current.length > 0 ? current : files)) // trả lại các tệp đã chọn để gửi lại
        }
        if (info) setErrorDialog(info)
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
    [busy, conversationId, navigate, t],
  )

  // --- Tạo cuộc trò chuyện mới: bấm nút là gọi API tạo ngay ---
  const [creating, setCreating] = useState(false)

  const focusComposer = () => requestAnimationFrame(() => document.getElementById('question')?.focus())

  const startNewConversation = async () => {
    if (busy || creating) return
    setNavOpen(false)
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
  const [profileOpen, setProfileOpen] = useState(false)
  const [profileToFiles, setProfileToFiles] = useState(false) // mở hồ sơ từ thanh dung lượng: cuộn tới mục tệp
  // Dung lượng file đã dùng / tối đa (hiện ở thanh bên); lấy lại mỗi khi đóng hộp thoại hồ sơ (nơi xoá bớt tệp).
  const [usage, setUsage] = useState<{ used: number; quota: number; max: number } | null>(null)
  const refreshUsage = useCallback(() => {
    listFiles()
      .then((l) => setUsage({ used: l.used_bytes, quota: l.quota_bytes, max: l.max_upload_bytes }))
      .catch(() => {}) // lỗi thì ẩn thanh dung lượng, không ảnh hưởng chat
  }, [])
  useEffect(() => {
    refreshUsage()
  }, [refreshUsage])

  const maxUploadBytes = usage?.max ?? 5 * 1024 * 1024

  const addFiles = (picked: File[]) => {
    const room = MAX_ATTACHMENTS - pendingRef.current.length
    if (picked.length > room) setChatError(fillTemplate(t('chat.attach.tooMany'), { count: MAX_ATTACHMENTS }))
    for (const file of picked.slice(0, Math.max(room, 0))) {
      const kind = file.type === 'application/pdf' ? 'pdf' : ATTACH_ACCEPT_TYPES.includes(file.type) ? 'image' : null
      if (!kind) {
        setChatError(t('chat.attach.errType'))
        continue
      }
      if (file.size > maxUploadBytes) {
        setChatError(fileErrorMessage('FILE_TOO_LARGE', t, maxUploadBytes))
        continue
      }
      const key = `${Date.now()}-${Math.random().toString(36).slice(2)}`
      setPending((list) => [...list, { key, name: file.name, size: file.size, kind, status: 'uploading' }])
      uploadFile(file)
        .then((res) => {
          if (!pendingRef.current.some((p) => p.key === key)) {
            deleteFile(res.file.id).then(refreshUsage, () => {}) // người dùng đã bỏ tệp trong lúc đang tải lên
            return
          }
          setPending((list) => list.map((p) => (p.key === key ? { ...p, status: 'ready', file: res.file } : p)))
          setUsage({ used: res.used_bytes, quota: res.quota_bytes, max: res.max_upload_bytes })
        })
        .catch((err) => {
          const message = fileErrorMessage(fileErrorCode(err), t, maxUploadBytes)
          setPending((list) => list.map((p) => (p.key === key ? { ...p, status: 'error', error: message } : p)))
        })
    }
  }

  const removePending = (key: string) => {
    const item = pendingRef.current.find((p) => p.key === key)
    setPending((list) => list.filter((p) => p.key !== key))
    if (item?.status === 'ready' && item.file) deleteFile(item.file.id).then(refreshUsage, () => {}) // bỏ tệp chưa gửi thì xoá luôn cho đỡ tốn dung lượng
  }
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
      <ProfileDialog
        open={profileOpen}
        scrollToFiles={profileToFiles}
        onClose={() => {
          setProfileOpen(false)
          setProfileToFiles(false)
          refreshUsage()
        }}
      />
      <ChatErrorDialog error={errorDialog} onClose={() => setErrorDialog(null)} />
      <ShareDialog
        open={shareOpen}
        conversationId={conversationId ?? null}
        onClose={() => {
          setShareOpen(false)
          if (conversationId) getConversation(conversationId).then((d) => setSharedFlag(d.shared)).catch(() => {})
        }}
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
        mobileOpen={navOpen}
        onMobileClose={() => setNavOpen(false)}
        title={t('brand.app')}
        subtitle={t('brand.appSub')}
        switchTo={user?.role === 'admin' ? { to: '/admin/dashboard', label: t('chat.adminLink'), icon: 'chart' } : undefined}
        footer={
          <div>
            {usage && (
              <button
                type="button"
                onClick={() => {
                  setProfileToFiles(true)
                  setProfileOpen(true)
                }}
                title={fillTemplate(t('files.usage.hint'), { quota: formatBytes(usage.quota) })}
                className={`mb-2 block w-full cursor-pointer rounded-lg border-0 bg-transparent px-2 py-1.5 text-left font-sans text-white hover:bg-white/10 ${labelClass(collapsed)}`}
              >
                <UsageBar used={usage.used} quota={usage.quota} variant="sidebar" />
              </button>
            )}
          <div className={`flex items-center gap-3 ${collapsed ? 'md:justify-center' : ''}`}>
            <Avatar src={user?.avatar_url} name={displayName} />
            <div className={`min-w-0 flex-1 leading-snug ${labelClass(collapsed)}`}>
              <div className="truncate text-sm font-normal">{displayName}</div>
              <div className="truncate text-xs opacity-80">{user?.email}</div>
            </div>
            <button
              type="button"
              onClick={() => {
                setProfileToFiles(false)
                setProfileOpen(true)
              }}
              aria-label={t('chat.profile')}
              title={t('chat.profile')}
              className={`size-11 cursor-pointer items-center justify-center rounded-lg border-0 bg-transparent text-white hover:bg-white/10 ${
                collapsed ? 'inline-flex md:hidden' : 'inline-flex'
              }`}
            >
              <Icon name="settings" />
            </button>
          </div>
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

        {sharedList.length > 0 && (
          <nav aria-label={t('share.withMe')} className={`flex flex-col gap-1 ${collapsed ? 'md:hidden' : ''}`}>
            <div className="px-2 pb-1.5 text-xs uppercase tracking-wider opacity-75">{t('share.withMe')}</div>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {sharedList.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => navigate(`/chat/${item.id}`)}
                    aria-current={item.id === conversationId ? 'page' : undefined}
                    className={`flex min-h-11 w-full cursor-pointer flex-col items-start gap-0.5 rounded-lg border-0 px-3 py-2 text-left font-sans text-white hover:bg-white/10 disabled:cursor-not-allowed ${
                      item.id === conversationId ? 'bg-white/15' : 'bg-transparent'
                    }`}
                  >
                    <span className="w-full truncate text-sm">{item.title || t('chat.untitled')}</span>
                    <span className="w-full truncate text-xs opacity-75">
                      {t('share.fromOwner')} {item.owner_name} · {item.permission === 'chat' ? t('share.badge.chat') : t('share.badge.view')}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </Sidebar>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-surface">
        <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-3 sm:gap-3 sm:px-8 sm:py-4">
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
            <MobileNavButton onClick={() => setNavOpen(true)} />
            <div className="min-w-0 flex-1">
            <h1 className="m-0 truncate text-lg">{activeTitle || sharedList.find((s) => s.id === conversationId)?.title || t('chat.untitled')}</h1>
            {access !== 'owner' && (
              <p className="m-0 mt-0.5 flex flex-wrap items-center gap-2 text-xs">
                <span>
                  {t('share.sharedBy')} <strong className="text-heading">{ownerName}</strong>
                </span>
                <span className="rounded-full bg-tint px-2 py-0.5 font-semibold text-accent">
                  {access === 'chat' ? t('share.badge.chat') : t('share.badge.view')}
                </span>
              </p>
            )}
            </div>
          </div>
          <div className="flex flex-none items-center gap-1.5 sm:gap-3">
            {/* Trên điện thoại sidebar thu gọn nên cần lối tắt để mở cuộc trò chuyện mới. */}
            <button
              type="button"
              disabled={busy || creating}
              onClick={startNewConversation}
              aria-label={t('chat.new')}
              title={t('chat.new')}
              className="inline-flex size-10 cursor-pointer items-center justify-center rounded-lg border-0 bg-ctu-gold-active text-ctu-navy-dark hover:bg-ctu-gold disabled:cursor-not-allowed disabled:opacity-60 md:hidden"
            >
              <Icon name="plus" size={18} strokeWidth={2.4} />
            </button>
            {access === 'owner' && (
              <button
                type="button"
                disabled={!conversationId || messages.length === 0}
                onClick={() => setShareOpen(true)}
                title={t('chat.share')}
                aria-label={t('chat.share')}
                className="inline-flex size-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-accent bg-transparent p-0 font-sans text-sm font-normal text-accent hover:bg-tint disabled:cursor-not-allowed disabled:opacity-50 sm:size-auto sm:min-h-11 sm:min-w-11 sm:px-4 sm:py-2"
              >
                <Icon name="share" size={16} strokeWidth={2} />
                <span className="hidden sm:inline">{t('chat.share')}</span>
                {sharedFlag && <span className="size-2 rounded-full bg-ctu-gold-active" aria-hidden="true" />}
              </button>
            )}
            <button
              type="button"
              onClick={() => setFeedback({ open: true, type: 'general', messageId: null })}
              aria-label={t('chat.feedback')}
              title={t('chat.feedback')}
              className="inline-flex size-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-field bg-transparent p-0 font-sans text-sm font-normal text-heading hover:bg-tint sm:size-auto sm:min-h-11 sm:min-w-11 sm:px-4 sm:py-2"
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
            <div className="mb-auto mt-[min(4vh,40px)] flex w-full max-w-[860px] flex-col items-center gap-2 text-center">
              <Logo size={48} fill="#0D47A1" />
              <h2 className="m-0 text-2xl">{t('chat.emptyTitle')}</h2>
              <p className="m-0">{t('chat.emptyHint')}</p>
              {suggestions.length > 0 && (
                <div className="mt-2 w-full text-left">
                  <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
                    {suggestions.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => send(s.question)}
                        className="flex min-h-11 cursor-pointer flex-col items-start gap-2 rounded-xl border border-line bg-surface px-4 py-3 text-left font-sans text-[15px] font-normal leading-snug text-heading hover:border-ctu-cyan hover:bg-tint"
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
            <div className="flex w-full max-w-[860px] flex-col gap-6">
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
          disabledReason={access === 'view' ? t('share.viewOnlyNotice') : undefined}
          attachments={pending}
          onAddFiles={addFiles}
          onRemoveAttachment={removePending}
          maxUploadBytes={maxUploadBytes}
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
