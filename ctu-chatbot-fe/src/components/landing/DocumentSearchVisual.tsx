import { useId } from 'react'
import { useI18n } from '../../i18n'
import type { CatalogSummary } from '../../lib/documents'
import Icon from '../Icon'

function titleLines(title: string): string[] {
  const lines = ['']
  for (const word of title.split(/\s+/)) {
    const index = lines.length - 1
    if (lines[index].length + word.length > 23 && lines[index]) {
      if (lines.length === 2) {
        lines[index] = lines[index].slice(0, 21) + '…'
        break
      }
      lines.push(word)
    } else {
      lines[index] += (lines[index] ? ' ' : '') + word
    }
  }
  return lines
}

/** Minh hoạ SVG có chữ thật từ catalog, độc lập với request chat. */
export default function DocumentSearchVisual({ documents }: { documents: CatalogSummary['documents'] }) {
  const { t } = useI18n()
  const id = useId()
  const cards = documents.length ? documents.slice(0, 2) : [null, null]

  return (
    <figure className="lp-research">
      <svg className="lp-research__art" viewBox="0 0 520 460" role="img" aria-labelledby={`${id}-title`}>
        <title id={`${id}-title`}>
          {t('landing.lookup.alt')}{' '}
          {documents
            .slice(0, 2)
            .map((doc) => doc.label)
            .join(', ')}
        </title>
        <defs>
          <linearGradient id={`${id}-paper`} x1="0" y1="0" x2="1" y2="1">
            <stop stopColor="#fff" stopOpacity="0.98" />
            <stop offset="1" stopColor="#e4f2ff" stopOpacity="0.94" />
          </linearGradient>
          <linearGradient id={`${id}-rim`} x1="0" y1="0" x2="1" y2="1">
            <stop stopColor="#ecfaff" />
            <stop offset="0.35" stopColor="#7bd7ff" />
            <stop offset="0.7" stopColor="#1a6db8" />
            <stop offset="1" stopColor="#c7eeff" />
          </linearGradient>
          <linearGradient id={`${id}-glass`} x1="0" y1="0" x2="1" y2="1">
            <stop stopColor="#f5fcff" stopOpacity="0.98" />
            <stop offset="0.65" stopColor="#e1f4ff" stopOpacity="0.95" />
            <stop offset="1" stopColor="#9cddff" stopOpacity="0.95" />
          </linearGradient>
          <linearGradient id={`${id}-handle`} x1="0" y1="0" x2="1" y2="1">
            <stop stopColor="#79cff8" />
            <stop offset="0.35" stopColor="#247cc5" />
            <stop offset="1" stopColor="#0b326d" />
          </linearGradient>
          <filter id={`${id}-shadow`} x="-30%" y="-30%" width="180%" height="190%">
            <feDropShadow dx="0" dy="12" stdDeviation="14" floodColor="#021b43" floodOpacity="0.22" />
          </filter>
        </defs>
        <g aria-hidden="true">
          <circle cx="277" cy="226" r="197" fill="#fff" fillOpacity="0.035" stroke="#9ddfff" strokeOpacity="0.12" />
          <circle cx="277" cy="226" r="159" fill="none" stroke="#9ddfff" strokeOpacity="0.13" strokeDasharray="3 8" />
          <path
            d="M42 270C-2 114 238-12 432 50"
            stroke="#7edcff"
            strokeOpacity="0.35"
            strokeDasharray="5 8"
            fill="none"
          />
          <circle cx="432" cy="50" r="5" fill="#fbc500" />
          <path d="M457 361h13m-6.5-6.5v13M41 57h10m-5-5v10" stroke="#9ddfff" strokeWidth="2" strokeLinecap="round" />
          {cards.map((doc, index) => (
            <g
              key={doc?.id ?? index}
              transform={index === 0 ? 'translate(30 37) rotate(-4 180 85)' : 'translate(76 244) rotate(3 180 85)'}
            >
              <rect
                x="7"
                y="7"
                width="350"
                height="168"
                rx="17"
                fill="#99d5ff"
                fillOpacity="0.15"
                stroke="#bbdfff"
                strokeOpacity="0.2"
              />
              <rect
                width="350"
                height="168"
                rx="17"
                fill={`url(#${id}-paper)`}
                stroke="#fff"
                strokeOpacity="0.8"
                filter={`url(#${id}-shadow)`}
              />
              <text x="24" y="29" fill="#5c7b9d" fontSize="9" fontWeight="500" letterSpacing="1.5">
                {t('landing.docs.document').toUpperCase()} · 0{index + 1}
              </text>
              <path
                d="M309 20h10l7 7v19h-17zM319 20v8h7M314 34h7M314 39h7"
                fill="none"
                stroke="#4783bd"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
              {titleLines(doc?.label ?? t('landing.lookup.placeholder')).map((line, lineIndex) => (
                <text
                  key={lineIndex}
                  x="24"
                  y={65 + lineIndex * 25}
                  fill="#163b6e"
                  fontSize="23"
                  fontWeight="500"
                  letterSpacing="-0.5"
                >
                  {line}
                </text>
              ))}
              {doc?.decision_no && (
                <text x="24" y="112" fill="#617c98" fontSize="10">
                  {doc.decision_no}
                </text>
              )}
              <rect x="24" y="130" width={index === 0 ? '196' : '224'} height="8" rx="4" fill="#c0d6ed" />
              <rect x="24" y="147" width={index === 0 ? '260' : '180'} height="6" rx="3" fill="#d4e4f4" />
              <rect
                className="lp-research__highlight"
                x="21"
                y="126"
                width={index === 0 ? '202' : '230'}
                height="16"
                rx="5"
                fill="#fbc500"
                fillOpacity="0.3"
              />
            </g>
          ))}
          <g className="lp-research__lens" filter={`url(#${id}-shadow)`}>
            <path d="M51 51l26 26" stroke="#bfebff" strokeWidth="23" />
            <path d="M77 77l43 43" stroke={`url(#${id}-handle)`} strokeWidth="28" strokeLinecap="round" />
            <path d="M78 72l42 42" stroke="#90d9ff" strokeOpacity="0.6" strokeWidth="3" strokeLinecap="round" />
            <circle r="79" fill={`url(#${id}-rim)`} stroke="#c3eeff" strokeWidth="1.5" />
            <circle r="67" fill={`url(#${id}-glass)`} stroke="#18558b" strokeWidth="2" />
            <circle r="63" fill="none" stroke="#fff" strokeOpacity="0.8" />
            <rect x="-43" y="-17" width="86" height="27" rx="6" fill="#fbc500" fillOpacity="0.48" />
            <text y="2" textAnchor="middle" fill="#163b6e" fontSize="19" fontWeight="500">
              {t('landing.lookup.lens')}
            </text>
            <path d="M-33 25h66M-33 34h46" stroke="#759dbc" strokeWidth="4" strokeLinecap="round" />
            <path
              d="M-46-25a52 52 0 0 1 49-27"
              stroke="#fff"
              strokeWidth="5"
              strokeLinecap="round"
              fill="none"
              opacity="0.9"
            />
          </g>
        </g>
      </svg>
      <figcaption>
        <a href="#tai-lieu">
          <span>
            <Icon name="search" size={17} />
            {t('landing.lookup.caption')}
          </span>
          <Icon name="arrow" size={18} />
        </a>
      </figcaption>
    </figure>
  )
}
