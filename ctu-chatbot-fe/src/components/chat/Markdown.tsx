import { useMemo, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

/** Liên kết đặc biệt do MessageBubble chèn vào: "[Điều 34](#ref-34)" -> nút mở văn bản quy định. */
const REFERENCE_HREF = /^#ref-(\d{1,2})$/

function PlainLink({ children, href }: { children?: ReactNode; href?: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-link underline hover:text-link-hover">
      {children}
    </a>
  )
}

// react-markdown mặc định KHÔNG render HTML thô nên an toàn với nội dung do LLM sinh ra.
const baseComponents: Components = {
  p: ({ children }) => <p className="my-0 [&:not(:first-child)]:mt-3">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal pl-6">{children}</ol>,
  li: ({ children }) => <li className="my-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  a: ({ children, href }) => <PlainLink href={href}>{children}</PlainLink>,
  h1: ({ children }) => <h3 className="mb-1 mt-3 text-lg">{children}</h3>,
  h2: ({ children }) => <h3 className="mb-1 mt-3 text-base">{children}</h3>,
  h3: ({ children }) => <h4 className="mb-1 mt-3 text-base">{children}</h4>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-4 border-line pl-3 italic">{children}</blockquote>
  ),
  code: ({ children, className }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="rounded bg-tint px-1.5 py-0.5 font-mono text-[13px]">{children}</code>
    ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-lg bg-tint p-3 font-mono text-[13px]">{children}</pre>
  ),
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-line bg-tint px-3 py-1.5 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-line px-3 py-1.5">{children}</td>,
}

type Props = {
  children: string
  /** Bấm vào "Điều N" trong câu trả lời để xem đoạn đó trong văn bản quy định */
  onReference?: (article: number) => void
  /** Điều đang mở trong cửa sổ tham chiếu (để tô đậm chỗ nhắc tới Điều đó trong câu trả lời) */
  activeArticle?: number | null
}

export default function Markdown({ children, onReference, activeArticle }: Props) {
  const components = useMemo<Components>(
    () => ({
      ...baseComponents,
      a: ({ children: label, href }) => {
        const ref = href ? REFERENCE_HREF.exec(href) : null
        if (ref && onReference) {
          const article = Number(ref[1])
          const active = article === activeArticle
          return (
            <button
              type="button"
              onClick={() => onReference(article)}
              className={`mx-0.5 inline cursor-pointer rounded border-0 px-1.5 py-0 align-baseline font-sans text-[inherit] font-semibold text-accent underline decoration-dotted underline-offset-4 hover:bg-tint ${
                active ? 'bg-ctu-gold-active/40 ring-1 ring-ctu-gold-active' : 'bg-ctu-gold-active/15'
              }`}
            >
              {label}
            </button>
          )
        }
        return <PlainLink href={href}>{label}</PlainLink>
      },
    }),
    [onReference, activeArticle],
  )

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  )
}
