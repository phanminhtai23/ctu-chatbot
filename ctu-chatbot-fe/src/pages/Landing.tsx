import { useEffect, useRef, useState } from 'react'
import proofSmall from '../assets/landing-preview-480.webp?no-inline'
import proofCompact from '../assets/landing-preview-640.webp?no-inline'
import proofMedium from '../assets/landing-preview-768.webp?no-inline'
import { useAuth } from '../auth'
import BrandLockup from '../components/BrandLockup'
import Icon from '../components/Icon'
import DocumentSearchVisual from '../components/landing/DocumentSearchVisual'
import PrefToggles from '../components/PrefToggles'
import { useI18n } from '../i18n'
import type { LandingTranslationKey } from '../i18n/vi-landing'
import { getCatalogSummary, type CatalogSummary } from '../lib/documents'
import { getSuggestions, type Suggestion } from '../lib/suggestions'
import './Landing.css'

type IconName = Parameters<typeof Icon>[0]['name']
const COPYRIGHT_YEAR = new Date().getFullYear()
const proofOriginal = '/landing/chat-reference-preview.webp'
const features: { icon: IconName; title: LandingTranslationKey; text: LandingTranslationKey }[] = [
  { icon: 'calc', title: 'feat2.t', text: 'feat2.x' },
  { icon: 'shield', title: 'feat3.t', text: 'feat3.x' },
  { icon: 'chat', title: 'feat4.t', text: 'feat4.x' },
]
const steps: { icon: IconName; title: LandingTranslationKey; text: LandingTranslationKey }[] = [
  { icon: 'users', title: 'step1.t', text: 'step1.x' },
  { icon: 'chat', title: 'step2.t', text: 'step2.x' },
  { icon: 'doc', title: 'step3.t', text: 'step3.x' },
]
const faqs: { question: LandingTranslationKey; answer: LandingTranslationKey }[] = [
  { question: 'landing.faq.account.q', answer: 'landing.faq.account.a' },
  { question: 'landing.faq.sources.q', answer: 'landing.faq.sources.a' },
  { question: 'landing.faq.pick.q', answer: 'landing.faq.pick.a' },
]

export default function Landing() {
  const { t } = useI18n()
  const { user } = useAuth()
  const chatPath = user ? '/chat' : '/login'
  const catalogSection = useRef<HTMLElement>(null)
  const samplesSection = useRef<HTMLElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const [samples, setSamples] = useState<Suggestion[] | null>(null)
  const showSamples = samples === null || samples.length > 0
  const [summary, setSummary] = useState<CatalogSummary | null>(null)
  const [catalogState, setCatalogState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    let alive = true
    const nearSection = (section: HTMLElement | null, load: () => void) => {
      if (!section || !('IntersectionObserver' in window) || window.location.hash === `#${section.id}`) {
        load()
        return
      }
      const observer = new IntersectionObserver(([entry]) => {
        if (!alive || !entry.isIntersecting) return
        observer.disconnect()
        load()
      }, { rootMargin: '320px 0px' })
      observer.observe(section)
      return () => observer.disconnect()
    }
    const stopCatalog = nearSection(catalogSection.current, () => {
      getCatalogSummary()
        .then((data) => {
          if (!alive) return
          setSummary(data)
          setCatalogState('ready')
        })
        .catch(() => alive && setCatalogState('error'))
    })
    const stopSamples = nearSection(samplesSection.current, () => {
      getSuggestions()
        .then((items) => alive && setSamples(items))
        .catch(() => alive && setSamples([]))
    })
    return () => {
      alive = false
      stopCatalog?.()
      stopSamples?.()
    }
  }, [])

  useEffect(() => {
    if (!menuOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setMenuOpen(false)
      menuButtonRef.current?.focus()
    }
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Element && !event.target.closest('.lp-header')) setMenuOpen(false)
    }
    document.addEventListener('keydown', closeOnEscape)
    document.addEventListener('pointerdown', closeOutside)
    return () => {
      document.removeEventListener('keydown', closeOnEscape)
      document.removeEventListener('pointerdown', closeOutside)
    }
  }, [menuOpen])

  const closeMenu = () => setMenuOpen(false)
  const retryCatalog = async () => {
    setCatalogState('loading')
    try {
      setSummary(await getCatalogSummary())
      setCatalogState('ready')
    } catch {
      setCatalogState('error')
    }
  }

  return (
    <div id="top" className="landing-page">
      <a className="lp-skip" href="#landing-main">
        {t('landing.skip')}
      </a>
      <header className="lp-header lp-container">
        <a href="/" className="lp-brand" aria-label={t('brand.app')} onClick={closeMenu}>
          <BrandLockup size={44} />
        </a>
        <nav id="landing-nav" aria-label={t('brand.mainNav')} className={'lp-nav' + (menuOpen ? ' is-open' : '')}>
          <a href="#can-cu" onClick={closeMenu}>
            {t('landing.nav.explore')}
          </a>
          <a href="#tai-lieu" onClick={closeMenu}>
            {t('nav.docs')}
          </a>
          {showSamples && (
            <a href="#cau-hoi-mau" onClick={closeMenu}>
              {t('nav.samples')}
            </a>
          )}
          <a href="#cach-hoat-dong" onClick={closeMenu}>
            {t('nav.how')}
          </a>
        </nav>
        <div className="lp-header__tools">
          <PrefToggles compact />
          <a href={chatPath} className="lp-button lp-button--nav">
            {user ? t('landing.openChat') : t('nav.login')}
            <Icon name="arrow" size={16} />
          </a>
          <button
            ref={menuButtonRef}
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
      </header>

      <main id="landing-main" tabIndex={-1}>
        <section className="lp-hero lp-container" aria-labelledby="landing-title">
          <div className="lp-hero__grid">
            <div className="lp-hero__copy">
              <p className="lp-eyebrow lp-eyebrow--light">
                <span className="lp-status-dot" />
                {t('landing.hero.eyebrow')}
              </p>
              <h1 id="landing-title">
                {t('landing.hero.line1')}
                <br />
                <span>{t('landing.hero.line2')}</span>
              </h1>
              <p className="lp-hero__desc">{t('landing.hero.desc')}</p>
              <div className="lp-actions">
                <a href={chatPath} className="lp-button lp-button--gold">
                  {t('hero.cta')}
                  <Icon name="arrow" size={20} />
                </a>
                <a href="#can-cu" className="lp-hero__secondary">
                  <span>
                    <Icon name="arrow" size={16} />
                  </span>
                  {t('landing.hero.preview')}
                </a>
              </div>
              <p className="lp-hero__note">
                <Icon name="shield" size={15} />
                {user ? t('landing.hero.ready') : t('hero.domainNote')}
              </p>
            </div>
            <div className="lp-hero__visual">
              <DocumentSearchVisual />
            </div>
          </div>
          <div className="lp-hero__foot">
            <span>
              <Icon name="doc" size={18} />
              {t('landing.trust.sources')}
            </span>
            <span>
              <Icon name="calc" size={18} />
              {t('landing.trust.calculation')}
            </span>
            <span>
              <Icon name="chat" size={18} />
              {t('landing.trust.language')}
            </span>
          </div>
        </section>

        <section id="can-cu" className="lp-section lp-container" aria-labelledby="proof-title">
          <div className="lp-section-heading">
            <div>
              <p className="lp-eyebrow">{t('landing.proof.eyebrow')}</p>
              <h2 id="proof-title">
                {t('landing.proof.title1')}
                <br />
                <span>{t('landing.proof.title2')}</span>
              </h2>
            </div>
            <p className="lp-section-heading__desc">{t('proof.text')}</p>
          </div>
          <figure className="lp-product lp-glass">
            <div className="lp-product__bar">
              <span className="lp-window-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              <span>
                <Icon name="shield" size={14} />
                {t('landing.proof.realUI')}
              </span>
              <a
                href={proofOriginal}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={t('landing.proof.enlarge')}
              >
                <Icon name="share" size={16} />
              </a>
            </div>
            <a
              href={proofOriginal}
              target="_blank"
              rel="noopener noreferrer"
              className="lp-product__image"
              aria-label={t('landing.proof.enlarge')}
            >
              <img
                src={proofMedium}
                srcSet={`${proofSmall} 480w, ${proofCompact} 640w, ${proofMedium} 768w, ${proofOriginal} 1300w`}
                sizes="(max-width: 680px) calc(100vw - 56px), min(1216px, calc(91.6vw - 24px))"
                alt={t('landing.proof.imageAlt')}
                width="1300"
                height="900"
                loading="lazy"
                fetchPriority="low"
                decoding="async"
              />
            </a>
            <figcaption>
              <span className="lp-caption-icon">
                <Icon name="doc" size={18} />
              </span>
              <span>{t('landing.proof.caption')}</span>
              <span className="lp-pill">
                <span className="lp-status-dot" />
                {t('landing.proof.source')}
              </span>
            </figcaption>
          </figure>
          <ul id="tinh-nang" className="lp-features">
            {features.map((feature, index) => (
              <li key={feature.title} className="lp-feature lp-glass">
                <div className="lp-feature__top">
                  <span className="lp-feature__icon">
                    <Icon name={feature.icon} size={24} />
                  </span>
                  <span className="lp-feature__number">0{index + 1}</span>
                </div>
                <h3>{t(feature.title)}</h3>
                <p>{t(feature.text)}</p>
              </li>
            ))}
          </ul>
        </section>

        <section ref={catalogSection} id="tai-lieu" className="lp-library" aria-labelledby="docs-title">
          <div className="lp-container">
            <div className="lp-section-heading">
              <div>
                <p className="lp-eyebrow">{t('landing.docs.eyebrow')}</p>
                <h2 id="docs-title">
                  {t('landing.docs.title1')}
                  <br />
                  <span>{t('landing.docs.title2')}</span>
                </h2>
              </div>
              <div className="lp-library__intro">
                <p>{t('landing.docs.desc')}</p>
                {summary && catalogState === 'ready' && (
                  <span className="lp-pill lp-pill--count">
                    <span className="lp-status-dot" />
                    <strong>{String(summary.count).padStart(2, '0')}</strong>
                    {t('docs.title')}
                  </span>
                )}
              </div>
            </div>
            {catalogState === 'loading' && (
              <div role="status" className="lp-catalog-state lp-glass">
                {t('landing.docs.loading')}
              </div>
            )}
            {catalogState === 'error' && (
              <div role="status" className="lp-catalog-state lp-glass">
                <p>{t('landing.docs.error')}</p>
                <button type="button" onClick={retryCatalog} className="lp-button lp-button--outline">
                  {t('landing.docs.retry')}
                  <Icon name="arrow" size={16} />
                </button>
              </div>
            )}
            {catalogState === 'ready' &&
              summary &&
              (summary.documents.length > 0 ? (
                <ul className="lp-documents">
                  {summary.documents.map((doc, index) => (
                    <li key={doc.id} className="lp-document lp-glass">
                      <div className="lp-document__top">
                        <span className="lp-document__icon">
                          <Icon name="doc" size={27} />
                        </span>
                        <span className="lp-document__index">
                          {t('landing.docs.document')} {String(index + 1).padStart(2, '0')}
                        </span>
                        <span className="lp-document__status">
                          <Icon name="check" size={13} />
                          {t('landing.docs.available')}
                        </span>
                      </div>
                      <h3>{doc.label}</h3>
                      <p>{doc.description || t('landing.docs.defaultDesc')}</p>
                      <div className="lp-document__bottom">
                        {doc.decision_no && <span className="lp-document__decision">{doc.decision_no}</span>}
                        {doc.official_url && (
                          <a href={doc.official_url} target="_blank" rel="noopener noreferrer">
                            {t('landing.docs.open')}
                            <Icon name="arrow" size={16} />
                            <span className="sr-only">: {doc.label}</span>
                          </a>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p role="status" className="lp-catalog-state lp-glass">
                  {t('landing.docs.empty')}
                </p>
              ))}
            <p className="lp-library__note">
              <Icon name="settings" size={16} />
              {t('landing.docs.pickHint')}
            </p>
          </div>
        </section>

        {showSamples && (
          <section ref={samplesSection} id="cau-hoi-mau" className="lp-section lp-container" aria-labelledby="samples-title">
            <div className="lp-section-heading">
              <div>
                <p className="lp-eyebrow">{t('landing.samples.eyebrow')}</p>
                <h2 id="samples-title">
                  {t('landing.samples.title1')}
                  <br />
                  <span>{t('landing.samples.title2')}</span>
                </h2>
              </div>
              <p className="lp-section-heading__desc">{t('samples.sub')}</p>
            </div>
            {samples === null && <p role="status" className="lp-catalog-state lp-glass">{t('common.loading')}</p>}
            <ul className="lp-samples">
              {samples?.slice(0, 4).map((sample, index) => (
                <li key={sample.id}>
                  <a href={chatPath} className="lp-sample lp-glass">
                    <div className="lp-sample__top">
                      <span className="lp-pill">{sample.category}</span>
                      <span className="lp-sample__number">0{index + 1}</span>
                    </div>
                    <p>{sample.question}</p>
                    <span className="lp-sample__action">
                      {t('landing.samples.action')}
                      <span>
                        <Icon name="arrow" size={19} />
                      </span>
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section id="cach-hoat-dong" className="lp-section lp-container lp-get-started" aria-labelledby="steps-title">
          <div className="lp-centered">
            <p className="lp-eyebrow">{t('landing.steps.eyebrow')}</p>
            <h2 id="steps-title">{t('steps.title')}</h2>
            <p>{t('landing.steps.desc')}</p>
          </div>
          <ol className="lp-steps">
            {steps.map((step, index) => (
              <li key={step.title}>
                <div className="lp-step__visual">
                  <span className="lp-step__icon lp-glass">
                    <Icon name={step.icon} size={26} />
                    <small>0{index + 1}</small>
                  </span>
                </div>
                <h3>{t(step.title)}</h3>
                <p>{t(step.text)}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="lp-faq lp-container" aria-labelledby="faq-title">
          <div>
            <p className="lp-eyebrow">{t('landing.faq.eyebrow')}</p>
            <h2 id="faq-title">{t('landing.faq.title')}</h2>
            <p>{t('landing.faq.desc')}</p>
          </div>
          <div className="lp-faq__list">
            {faqs.map((faq) => (
              <details key={faq.question} className="lp-glass">
                <summary>
                  {t(faq.question)}
                  <Icon name="plus" size={18} />
                </summary>
                <p>{t(faq.answer)}</p>
              </details>
            ))}
          </div>
        </section>

        <section className="lp-cta lp-container" aria-labelledby="close-title">
          <span className="lp-cta__spark" aria-hidden="true">
            <Icon name="sparkles" size={44} />
          </span>
          <p className="lp-eyebrow lp-eyebrow--light">{t('landing.cta.eyebrow')}</p>
          <h2 id="close-title">{t('landing.cta.title')}</h2>
          <p>{t('cta.sub')}</p>
          <a href={chatPath} className="lp-button lp-button--gold">
            {t('hero.cta')}
            <Icon name="arrow" size={20} />
          </a>
        </section>
      </main>

      <footer className="lp-footer lp-container">
        <div className="lp-footer__main">
          <div>
            <a href="/" className="lp-brand">
              <BrandLockup size={40} />
            </a>
            <p>{t('footer.desc')}</p>
          </div>
          <nav aria-label={t('footer.links')}>
            <a href="https://www.ctu.edu.vn" target="_blank" rel="noopener noreferrer">
              {t('footer.site')}
              <Icon name="arrow" size={15} />
            </a>
            <a href="mailto:kevinphan68.work@gmail.com">
              {t('footer.contact')}
              <Icon name="arrow" size={15} />
            </a>
            <a href="#top">
              {t('landing.backTop')}
              <Icon name="arrow" className="lp-up-icon" size={16} />
            </a>
          </nav>
        </div>
        <div className="lp-footer__legal">
          <span>
            © {COPYRIGHT_YEAR} {t('brand.app')}
          </span>
          <p>{t('brand.disclaimer')}</p>
        </div>
      </footer>
    </div>
  )
}
