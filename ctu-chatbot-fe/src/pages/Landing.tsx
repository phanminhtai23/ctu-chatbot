import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import BrandLockup from '../components/BrandLockup'
import Icon from '../components/Icon'
import PrefToggles from '../components/PrefToggles'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import { getCatalogSummary, type CatalogSummary } from '../lib/documents'
import { getSuggestions, type Suggestion } from '../lib/suggestions'
import './Landing.css'

type IconName = Parameters<typeof Icon>[0]['name']

const smallFeatures: { icon: IconName; title: TranslationKey; text: TranslationKey; wide?: boolean }[] = [
  { icon: 'calc', title: 'feat2.t', text: 'feat2.x' },
  { icon: 'shield', title: 'feat3.t', text: 'feat3.x' },
  { icon: 'chat', title: 'feat4.t', text: 'feat4.x', wide: true },
]

const steps: { title: TranslationKey; text: TranslationKey }[] = [
  { title: 'step1.t', text: 'step1.x' },
  { title: 'step2.t', text: 'step2.x' },
  { title: 'step3.t', text: 'step3.x' },
]

/** Các khối hiện dần khi cuộn tới; mỗi khối so le theo thứ tự trong cùng cha để danh sách hiện lần lượt. */
const REVEAL = [
  '.lp-docs__lead',
  '.lp-docs__list li',
  '.lp-split__copy',
  '.lp-page',
  '.lp-pick',
  '.lp-intro',
  '.lp-card',
  '.lp-sample',
  '.lp-steps__title',
  '.lp-steps li',
  '.lp-close__inner',
].join(',')

export default function Landing() {
  const { t } = useI18n()
  const rootRef = useRef<HTMLDivElement>(null)
  const [samples, setSamples] = useState<Suggestion[]>([])
  const [summary, setSummary] = useState<CatalogSummary | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    let alive = true
    getSuggestions()
      .then((items) => alive && setSamples(items))
      .catch(() => {})
    getCatalogSummary()
      .then((data) => alive && setSummary(data))
      .catch(() => {}) // không lấy được thì ẩn mục tài liệu, phần còn lại của trang vẫn dùng được
    return () => {
      alive = false
    }
  }, [])

  // Hiện dần khi cuộn. Không có IntersectionObserver hoặc người dùng chọn giảm chuyển động thì giữ nguyên, nội dung luôn thấy được.
  useEffect(() => {
    const root = rootRef.current
    if (!root || !('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -6% 0px' },
    )
    root.classList.add('lp-reveal-on')
    root.querySelectorAll<HTMLElement>(REVEAL).forEach((el) => {
      if (el.classList.contains('is-visible')) return
      if (!el.hasAttribute('data-reveal')) {
        el.setAttribute('data-reveal', '')
        const index = Array.prototype.indexOf.call(el.parentElement?.children ?? [], el)
        el.style.setProperty('--d', `${Math.min(Math.max(index, 0), 5) * 90}ms`)
      }
      observer.observe(el)
    })
    return () => observer.disconnect()
  }, [samples, summary])

  const close = () => setMenuOpen(false)
  const enter = (i: number) => ({ '--i': i }) as React.CSSProperties
  // Mục "Chọn nguồn": dùng tài liệu thật nếu đã lấy được, chưa có thì dùng mô tả mẫu.
  const sourceDocs =
    summary && summary.documents.length > 0
      ? summary.documents.slice(0, 2)
      : [{ id: 'sample', label: t('pick.docName'), decision_no: t('pick.docNo'), description: t('pick.docText') }]

  return (
    <div id="top" ref={rootRef} className="landing-page">
      <header className="lp-header">
        <div className="lp-container lp-header__inner">
          <Link to="/" className="lp-brand" aria-label={t('brand.app')}>
            <BrandLockup size={50} />
          </Link>

          <nav id="landing-nav" aria-label={t('brand.mainNav')} className={`lp-nav${menuOpen ? ' is-open' : ''}`}>
            {summary && summary.count > 0 && (
              <a href="#tai-lieu" onClick={close}>{t('nav.docs')}</a>
            )}
            <a href="#can-cu" onClick={close}>{t('nav.proof')}</a>
            <a href="#tinh-nang" onClick={close}>{t('nav.features')}</a>
            <a href="#cau-hoi-mau" onClick={close}>{t('nav.samples')}</a>
            <Link to="/login" onClick={close} className="lp-button lp-button--small">
              {t('nav.login')}
            </Link>
          </nav>

          <div className="lp-header__tools">
            <PrefToggles compact />
            <button
              type="button"
              aria-label={menuOpen ? t('sidebar.close') : t('brand.mainNav')}
              aria-expanded={menuOpen}
              aria-controls="landing-nav"
              onClick={() => setMenuOpen((open) => !open)}
              className="lp-menu-button"
            >
              <Icon name={menuOpen ? 'close' : 'menu'} />
            </button>
          </div>
        </div>
      </header>

      <main>
        <section className="lp-hero" aria-labelledby="landing-title">
          <div className="lp-container lp-hero__grid">
            <div className="lp-hero__copy" data-enter style={enter(0)}>
              <h1 id="landing-title">
                {t('hero.title1')}
                <br />
                {t('hero.title2')} {t('hero.highlight')}
              </h1>
              <span className="lp-rule" aria-hidden="true" />
              <p className="lp-lead">{t('hero.desc')}</p>
              <div className="lp-actions">
                <Link to="/login" className="lp-button lp-button--large">
                  {t('hero.cta')} <Icon name="arrow" size={20} />
                </Link>
                <a href="#cau-hoi-mau" className="lp-text-link">
                  {t('hero.how')}
                </a>
              </div>
              <p className="lp-note">{t('hero.domainNote')}</p>
            </div>

            <div className="lp-chat-wrap" data-enter style={enter(1)}>
              <img className="lp-mascot" src="/ctu-chatbot-mascot.webp" alt="" width="132" height="142" fetchPriority="high" decoding="async" />
              <div className="lp-chat" role="img" aria-label={t('mock.title')}>
                <div className="lp-chat__bar">
                  <span className="lp-chat__dots" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  {t('mock.title')}
                </div>
                <div className="lp-chat__body" aria-hidden="true">
                  <div className="lp-msg lp-msg--user">{t('mock.q')}</div>
                  <div className="lp-msg lp-msg--bot">
                    <p>
                      <strong>{t('mock.a1')}.</strong> {t('mock.a2')}
                    </p>
                    <div className="lp-msg__foot">
                      <span className="lp-chip">
                        <Icon name="doc" size={16} />
                        {t('mock.ref')}
                      </span>
                      <span className="lp-meta">
                        <Icon name="clock" size={14} />
                        {t('mock.time')}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {summary && summary.count > 0 && (
          <section id="tai-lieu" className="lp-docs" aria-labelledby="docs-title">
            <div className="lp-container lp-docs__grid">
              <div className="lp-docs__lead">
                <p className="lp-docs__count" aria-hidden="true">
                  {summary.count}
                </p>
                <h2 id="docs-title">
                  <span className="sr-only">{summary.count} </span>
                  {t('docs.title')}
                </h2>
                <p>{t('docs.sub')}</p>
              </div>
              <ul className="lp-docs__list">
                {summary.documents.map((doc) => (
                  <li key={doc.id}>
                    <span className="lp-docs__icon" aria-hidden="true">
                      <Icon name="doc" size={24} />
                    </span>
                    <div className="lp-docs__body">
                      <p className="lp-docs__name">{doc.label}</p>
                      {doc.description && <p className="lp-docs__desc">{doc.description}</p>}
                      {(doc.decision_no || doc.official_url) && (
                        <div className="lp-docs__meta">
                          {doc.decision_no && <span className="lp-docs__decision">{doc.decision_no}</span>}
                          {doc.official_url && (
                            <a className="lp-docs__link" href={doc.official_url} target="_blank" rel="noopener noreferrer">
                              {t('admin.doc.lib.openOfficial')}
                              <Icon name="arrow" size={16} />
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        )}

        <section id="can-cu" className="lp-section" aria-labelledby="proof-title">
          <div className="lp-container lp-split">
            <div className="lp-split__copy">
              <h2 id="proof-title">{t('proof.title')}</h2>
              <p>{t('proof.text')}</p>
            </div>
            <div className="lp-page" role="img" aria-label={t('mock.ref')}>
              <div className="lp-page__bar">
                <span>{t('mock.ref')}</span>
                <span className="lp-page__no">{t('proof.page')}</span>
              </div>
              <div className="lp-page__sheet" aria-hidden="true">
                <i className="lp-sk lp-sk--head" />
                <i className="lp-sk" />
                <i className="lp-sk lp-sk--94" />
                <i className="lp-sk lp-sk--98" />
                <div className="lp-page__mark">
                  <i className="lp-sk" />
                  <i className="lp-sk lp-sk--90" />
                  <i className="lp-sk lp-sk--64" />
                </div>
                <i className="lp-sk lp-sk--97" />
                <i className="lp-sk" />
                <i className="lp-sk lp-sk--72" />
              </div>
            </div>
          </div>
        </section>

        <section id="tinh-nang" className="lp-section lp-section--tint" aria-labelledby="feat-title">
          <div className="lp-container">
            <div className="lp-intro">
              <h2 id="feat-title">{t('feat.title')}</h2>
              <p>{t('feat.sub')}</p>
            </div>
            <ul className="lp-bento">
              <li className="lp-card lp-card--hero">
                <span className="lp-card__icon lp-card__icon--gold">
                  <Icon name="doc" size={30} />
                </span>
                <div>
                  <h3>{t('feat1.t')}</h3>
                  <p>{t('feat1.x')}</p>
                </div>
              </li>
              {smallFeatures.map((feature) => (
                <li key={feature.title} className={`lp-card lp-card--row${feature.wide ? ' lp-card--wide' : ''}`}>
                  <span className="lp-card__icon">
                    <Icon name={feature.icon} size={26} />
                  </span>
                  <div>
                    <h3>{t(feature.title)}</h3>
                    <p>{t(feature.text)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="lp-section" aria-labelledby="pick-title">
          <div className="lp-container lp-split">
            <div className="lp-split__copy">
              <h2 id="pick-title">{t('pick.title')}</h2>
              <p>{t('pick.text')}</p>
            </div>
            <div className="lp-pick" role="img" aria-label={t('pick.title')}>
              <div className="lp-pick__tabs" aria-hidden="true">
                <span>{t('profile.tab.settings')}</span>
                <span className="is-active">{t('profile.tab.sources')}</span>
                <span>{t('profile.tab.storage')}</span>
              </div>
              <div className="lp-pick__all" aria-hidden="true">
                <strong>{t('sources.all')}</strong> <span>{t('sources.allHint')}</span>
              </div>
              {sourceDocs.map((doc) => (
                <div key={doc.id} className="lp-pick__item is-on" aria-hidden="true">
                  <span className="lp-pick__check">
                    <Icon name="check" size={14} strokeWidth={3} />
                  </span>
                  <span>
                    <span className="lp-pick__name">
                      {doc.label}
                      {doc.decision_no && <em>{doc.decision_no}</em>}
                    </span>
                    {doc.description && <span className="lp-pick__text">{doc.description}</span>}
                  </span>
                </div>
              ))}
              <div className="lp-pick__item is-on" aria-hidden="true">
                <span className="lp-pick__check">
                  <Icon name="check" size={14} strokeWidth={3} />
                </span>
                <span>
                  <span className="lp-pick__name">{t('sources.web')}</span>
                  <span className="lp-pick__text">{t('pick.webText')}</span>
                </span>
              </div>
            </div>
          </div>
        </section>

        {samples.length > 0 && (
          <section id="cau-hoi-mau" className="lp-section lp-section--tint" aria-labelledby="samples-title">
            <div className="lp-container">
              <div className="lp-intro">
                <h2 id="samples-title">{t('samples.title')}</h2>
                <p>{t('samples.sub')}</p>
              </div>
              <ul className="lp-samples">
                {samples.slice(0, 4).map((sample) => (
                  <li key={sample.id}>
                    <Link to="/login" className="lp-sample">
                      <span className="lp-sample__category">{sample.category}</span>
                      <span className="lp-sample__question">{sample.question}</span>
                      <span className="lp-sample__action">
                        {t('samples.ask')} <Icon name="arrow" size={16} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        )}

        <section id="cach-hoat-dong" className="lp-section" aria-labelledby="steps-title">
          <div className="lp-container">
            <h2 id="steps-title" className="lp-steps__title">
              {t('steps.title')}
            </h2>
            <ol className="lp-steps">
              {steps.map((step, index) => (
                <li key={step.title}>
                  <span className="lp-steps__no" aria-hidden="true">
                    {`0${index + 1}`}
                  </span>
                  <h3>{t(step.title)}</h3>
                  <p>{t(step.text)}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section className="lp-close" aria-labelledby="close-title">
          <div className="lp-container lp-close__inner">
            <div>
              <h2 id="close-title">{t('cta.title')}</h2>
              <p>{t('cta.sub')}</p>
            </div>
            <Link to="/login" className="lp-button lp-button--gold lp-button--large">
              {t('steps.cta')} <Icon name="arrow" size={20} />
            </Link>
          </div>
        </section>
      </main>

      <footer id="lien-he" className="lp-footer">
        <div className="lp-container lp-footer__main">
          <div>
            <p className="lp-footer__uni">{t('brand.uni')}</p>
            <p>{t('footer.desc')}</p>
          </div>
          <div>
            <h2>{t('footer.links')}</h2>
            <a href="https://www.ctu.edu.vn">{t('footer.site')}</a>
            <Link to="/login">{t('nav.login')}</Link>
          </div>
          <div>
            <h2>{t('footer.contact')}</h2>
            <p>{t('footer.contactPlaceholder')}</p>
          </div>
        </div>
        <div className="lp-container lp-footer__legal">{t('brand.disclaimer')}</div>
      </footer>
    </div>
  )
}
