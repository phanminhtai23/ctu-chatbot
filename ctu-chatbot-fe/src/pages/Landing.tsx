import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon, { type IconName } from '../components/Icon'
import Logo from '../components/Logo'
import PrefToggles from '../components/PrefToggles'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import { getSuggestions, type Suggestion } from '../lib/suggestions'

const features: { icon: IconName; title: TranslationKey; text: TranslationKey; accent: string }[] = [
  { icon: 'doc', title: 'feat1.t', text: 'feat1.x', accent: 'border-t-ctu-navy dark:border-t-ctu-cyan' },
  { icon: 'calc', title: 'feat2.t', text: 'feat2.x', accent: 'border-t-ctu-gold-active' },
  { icon: 'shield', title: 'feat3.t', text: 'feat3.x', accent: 'border-t-ctu-cyan' },
  { icon: 'chat', title: 'feat4.t', text: 'feat4.x', accent: 'border-t-ctu-navy dark:border-t-ctu-cyan' },
]

const steps: { title: TranslationKey; text: TranslationKey }[] = [
  { title: 'step1.t', text: 'step1.x' },
  { title: 'step2.t', text: 'step2.x' },
  { title: 'step3.t', text: 'step3.x' },
]

const container = 'mx-auto max-w-[1200px] px-5 sm:px-8'

export default function Landing() {
  const { t } = useI18n()
  const [samples, setSamples] = useState<Suggestion[]>([])

  // Câu hỏi mẫu lấy từ server (cùng danh sách gợi ý trong khung chat); lỗi mạng thì chỉ ẩn mục này.
  useEffect(() => {
    let alive = true
    getSuggestions()
      .then((items) => {
        if (alive) setSamples(items)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  return (
    <div id="top" className="bg-surface">
      <header className="bg-ctu-navy text-white">
        <div className={`${container} flex flex-wrap items-center justify-between gap-4 py-4`}>
          <Link to="/" className="flex items-center gap-3.5 text-white no-underline">
            <Logo size={48} />
            <div className="leading-tight">
              <div className="text-[17px] font-semibold tracking-wide">{t('brand.uni')}</div>
              <div className="text-[13px] font-light">{t('brand.sub')}</div>
            </div>
          </Link>
          <nav aria-label={t('brand.mainNav')} className="flex flex-wrap items-center gap-x-7 gap-y-3 text-[15px]">
            <a href="#tinh-nang" className="text-white no-underline hover:text-ctu-gold">{t('nav.features')}</a>
            <a href="#cau-hoi-mau" className="text-white no-underline hover:text-ctu-gold">{t('nav.samples')}</a>
            <a href="#cach-hoat-dong" className="text-white no-underline hover:text-ctu-gold">{t('nav.how')}</a>
            <a href="#lien-he" className="text-white no-underline hover:text-ctu-gold">{t('nav.contact')}</a>
            <PrefToggles tone="on-navy" />
            <Link
              to="/login"
              className="inline-flex min-h-11 items-center rounded-lg bg-ctu-gold-active px-5 font-semibold text-ctu-navy-dark no-underline hover:bg-ctu-gold"
            >
              {t('nav.login')}
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section>
        <div className={`${container} flex flex-wrap items-center gap-14 pb-24 pt-16 sm:pt-20`}>
          <div className="min-w-0 flex-[1_1_460px]">
            <div className="mb-6 inline-block rounded-full border border-ctu-cyan px-4 py-1 text-sm font-normal text-accent">
              {t('hero.badge')}
            </div>
            <h1 className="mb-5 text-[length:clamp(1.9rem,2.9vw,2.6rem)] leading-[1.2] text-balance">
              {t('hero.title1')}
              <br />
              {t('hero.title2')}{' '}
              <span className="text-accent [box-shadow:inset_0_-0.32em_0_#fbc500] dark:[box-shadow:inset_0_-0.32em_0_rgba(251,197,0,.55)]">
                {t('hero.highlight')}
              </span>
            </h1>
            <p className="mb-9 max-w-[540px] text-lg">{t('hero.desc')}</p>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
              <Link
                to="/login"
                className="inline-flex min-h-12 items-center gap-3 rounded-[10px] bg-ctu-navy px-7 text-base font-semibold text-white no-underline hover:bg-ctu-navy-dark"
              >
                {t('hero.cta')}
                <Icon name="arrow" />
              </Link>
              <a href="#cau-hoi-mau" className="inline-flex min-h-12 items-center text-base font-normal text-accent no-underline">
                {t('hero.how')}
              </a>
            </div>
            <p className="mt-5 text-sm">{t('hero.domainNote')}</p>
          </div>

          {/* Minh họa: câu hỏi, câu trả lời có tham chiếu và trang văn bản được tô vàng */}
          <div className="relative min-w-0 max-w-[540px] flex-[1_1_440px] pb-8">
            <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_18px_40px_rgba(13,71,161,.12)]">
              <div className="flex items-center gap-2.5 bg-ctu-navy px-5 py-3.5 text-[15px] font-normal text-white">
                <span className="inline-block size-2.5 rounded-full bg-ctu-gold-active" />
                {t('mock.title')}
              </div>
              <div className="flex flex-col gap-3.5 px-5 py-6">
                <div className="max-w-[88%] self-end rounded-2xl rounded-br-sm bg-bubble-user px-4 py-3 text-[15px] font-normal text-heading">
                  {t('mock.q')}
                </div>
                <div className="max-w-[94%] self-start rounded-2xl rounded-bl-sm bg-bubble-bot px-4 py-3.5 text-[15px] text-heading">
                  <div className="mb-2.5">
                    <strong className="font-semibold">{t('mock.a1')}</strong> {t('mock.a2')}
                  </div>
                  <span className="inline-flex items-center gap-2 rounded-md border border-ctu-cyan bg-surface px-3 py-1 text-[13px] font-normal text-accent">
                    <Icon name="doc" size={14} />
                    {t('mock.ref')}
                  </span>
                </div>
              </div>
            </div>
            <div
              aria-hidden="true"
              className="absolute -bottom-2 right-0 hidden w-[190px] rounded-[10px] border border-line bg-surface p-3.5 shadow-[0_12px_28px_rgba(13,71,161,.16)] sm:block"
            >
              <div className="mb-2 h-1.5 w-[70%] rounded-[3px] bg-line" />
              <div className="mb-2 h-1.5 w-full rounded-[3px] bg-tint" />
              <div className="-mx-1.5 mb-2 rounded-[3px] border-2 border-ctu-gold-active bg-ctu-gold-active/40 px-1.5 py-1.5">
                <div className="mb-1.5 h-1.5 w-full rounded-[3px] bg-field" />
                <div className="h-1.5 w-[82%] rounded-[3px] bg-field" />
              </div>
              <div className="mb-2 h-1.5 w-full rounded-[3px] bg-tint" />
              <div className="mb-2.5 h-1.5 w-[55%] rounded-[3px] bg-tint" />
              <div className="text-center text-xs font-normal text-muted">{t('mock.page')}</div>
            </div>
          </div>
        </div>
      </section>

      {/* Dải căn cứ */}
      <section className="bg-ctu-navy-dark text-white">
        <div className={`${container} flex flex-wrap items-center justify-between gap-x-10 gap-y-2 py-5 text-[15px] font-normal`}>
          <span>{t('band.text')}</span>
          <span className="font-semibold text-ctu-gold-active">{t('band.facts')}</span>
        </div>
      </section>

      <section id="tinh-nang">
        <div className={`${container} py-20 sm:py-22`}>
          <h2 className="mb-3 text-center text-[length:clamp(1.6rem,3vw,2.25rem)]">{t('feat.title')}</h2>
          <p className="mx-auto mb-12 max-w-[640px] text-center">{t('feat.sub')}</p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-6">
            {features.map((f) => (
              <div key={f.title} className={`rounded-[10px] border border-t-4 border-line px-6 py-7 ${f.accent}`}>
                <Icon name={f.icon} size={40} className="text-accent" strokeWidth={1.6} />
                <h3 className="mb-2.5 mt-4 text-[21px]">{t(f.title)}</h3>
                <p className="m-0">{t(f.text)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {samples.length > 0 && (
        <section id="cau-hoi-mau" className="bg-tint">
          <div className={`${container} py-20 sm:py-22`}>
            <h2 className="mb-3 text-center text-[length:clamp(1.6rem,3vw,2.25rem)]">{t('samples.title')}</h2>
            <p className="mx-auto mb-12 max-w-[640px] text-center">{t('samples.sub')}</p>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(min(340px,100%),1fr))] gap-5">
              {samples.map((s) => (
                <Link
                  key={s.id}
                  to="/login"
                  className="group block rounded-xl border border-line bg-surface px-6 py-6 no-underline hover:border-ctu-cyan"
                >
                  <span className="mb-3 inline-block rounded-full bg-bubble-user px-3 text-[13px] font-normal text-accent">
                    {s.category}
                  </span>
                  <span className="block text-[17px] font-normal leading-[1.55] text-heading">{s.question}</span>
                  <span className="mt-3 inline-flex items-center gap-2 text-sm font-normal text-accent">
                    {t('samples.ask')}
                    <Icon name="arrow" size={16} className="transition-transform group-hover:translate-x-1" />
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      <section id="cach-hoat-dong">
        <div className={`${container} py-20 sm:py-22`}>
          <h2 className="mb-12 text-center text-[length:clamp(1.6rem,3vw,2.25rem)]">{t('steps.title')}</h2>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-9">
            {steps.map((s, i) => (
              <div key={s.title} className="flex items-start gap-4">
                <div className="flex size-12 flex-none items-center justify-center rounded-full bg-ctu-navy text-xl font-semibold text-white">
                  {i + 1}
                </div>
                <div>
                  <h3 className="mb-1.5 text-xl">{t(s.title)}</h3>
                  <p className="m-0">{t(s.text)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-ctu-navy text-white">
        <div className={`${container} flex flex-wrap items-center justify-between gap-x-10 gap-y-6 py-16`}>
          <div className="min-w-0 flex-[1_1_420px]">
            <h2 className="mb-2 text-[length:clamp(1.5rem,2.6vw,2rem)] !text-white">{t('cta.title')}</h2>
            <p className="m-0 font-light text-white">{t('cta.sub')}</p>
          </div>
          <Link
            to="/login"
            className="inline-flex min-h-[52px] items-center gap-3 rounded-[10px] bg-ctu-gold-active px-8 text-base font-semibold text-ctu-navy-dark no-underline hover:bg-ctu-gold"
          >
            {t('steps.cta')}
            <Icon name="arrow" />
          </Link>
        </div>
      </section>

      <footer id="lien-he" className="bg-ctu-navy-dark text-white">
        <div className={`${container} flex flex-wrap justify-between gap-10 pb-8 pt-14`}>
          <div className="flex-[1_1_280px]">
            <div className="mb-2 text-lg font-semibold">{t('brand.uni')}</div>
            <p className="m-0 text-sm text-white opacity-85">{t('footer.desc')}</p>
          </div>
          <div className="flex-[1_1_200px] text-sm">
            <div className="mb-2.5 font-semibold">{t('footer.links')}</div>
            <div className="flex flex-col gap-1.5">
              <a href="https://www.ctu.edu.vn" className="text-white no-underline hover:text-ctu-gold">
                {t('footer.site')}
              </a>
              <Link to="/login" className="text-white no-underline hover:text-ctu-gold">{t('nav.login')}</Link>
            </div>
          </div>
          <div className="flex-[1_1_240px] text-sm">
            <div className="mb-2.5 font-semibold">{t('footer.contact')}</div>
            <p className="m-0 text-white opacity-85">{t('footer.contactPlaceholder')}</p>
          </div>
        </div>
        <div className="border-t border-white/20 px-5 py-4 text-center text-[13px] text-white opacity-85">
          {t('brand.disclaimer')}
        </div>
      </footer>
    </div>
  )
}
