import { Link } from 'react-router-dom'
import Icon, { type IconName } from '../components/Icon'
import Logo from '../components/Logo'
import PrefToggles from '../components/PrefToggles'
import SourceChip from '../components/SourceChip'
import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'

const features: { icon: IconName; title: TranslationKey; text: TranslationKey; accent: string }[] = [
  { icon: 'chat', title: 'feat1.t', text: 'feat1.x', accent: 'border-t-accent' },
  { icon: 'doc', title: 'feat2.t', text: 'feat2.x', accent: 'border-t-ctu-gold-active' },
  { icon: 'clip', title: 'feat3.t', text: 'feat3.x', accent: 'border-t-ctu-cyan' },
]

const steps: { title: TranslationKey; text: TranslationKey }[] = [
  { title: 'step1.t', text: 'step1.x' },
  { title: 'step2.t', text: 'step2.x' },
  { title: 'step3.t', text: 'step3.x' },
]

export default function Landing() {
  const { t } = useI18n()

  return (
    <div className="bg-surface">
      <header className="bg-ctu-navy text-white">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-8 py-4">
          <Link to="/" className="flex items-center gap-3.5 text-white no-underline">
            <Logo />
            <div className="leading-tight">
              <div className="text-[17px] font-semibold tracking-wide">{t('brand.uni')}</div>
              <div className="text-[13px] font-light">{t('brand.sub')}</div>
            </div>
          </Link>
          <nav aria-label={t('brand.mainNav')} className="flex flex-wrap items-center gap-x-7 gap-y-3 text-[15px]">
            <a href="#tinh-nang" className="text-white no-underline hover:text-ctu-gold">{t('nav.features')}</a>
            <a href="#cach-hoat-dong" className="text-white no-underline hover:text-ctu-gold">{t('nav.how')}</a>
            <a href="#lien-he" className="text-white no-underline hover:text-ctu-gold">{t('nav.contact')}</a>
            <PrefToggles tone="on-navy" />
            <Link
              to="/login"
              className="inline-block rounded-md bg-ctu-gold-active px-5 py-2.5 font-semibold text-ctu-navy-dark no-underline hover:bg-ctu-gold"
            >
              {t('nav.login')}
            </Link>
          </nav>
        </div>
      </header>

      <section className="bg-gradient-to-b from-tint to-surface">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-14 px-8 pb-24 pt-20">
          <div className="min-w-0 flex-[1_1_460px]">
            <div className="mb-6 inline-block rounded-full border border-ctu-cyan px-4 py-1 text-sm font-normal text-accent">
              {t('hero.badge')}
            </div>
            <h1 className="mb-5 text-[length:clamp(2rem,4vw,3.25rem)] leading-[1.15]">{t('hero.title')}</h1>
            <p className="mb-9 max-w-[540px] text-lg">{t('hero.desc')}</p>
            <div className="flex flex-wrap items-center gap-4">
              <Link
                to="/login"
                className="inline-flex min-h-11 items-center gap-3 rounded-lg bg-ctu-navy px-7 py-3.5 text-base font-semibold text-white no-underline hover:bg-ctu-navy-dark"
              >
                <Icon name="arrow" />
                {t('hero.cta')}
              </Link>
              <a href="#cach-hoat-dong" className="px-2 py-3.5 text-base font-normal text-accent no-underline">
                {t('hero.how')}
              </a>
            </div>
            <p className="mt-5 text-sm">{t('hero.domainNote')}</p>
          </div>

          <div className="min-w-0 max-w-[520px] flex-[1_1_440px]">
            <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[0_18px_40px_rgba(13,71,161,.12)]">
              <div className="flex items-center gap-2.5 bg-ctu-navy px-5 py-3.5 text-[15px] font-normal text-white">
                <span className="inline-block size-2.5 rounded-full bg-ctu-gold-active" />
                {t('mock.title')}
              </div>
              <div className="flex flex-col gap-4 px-5 py-6">
                <div className="max-w-[85%] self-end rounded-2xl rounded-br-sm bg-bubble-user px-4 py-3 text-[15px] font-normal text-heading">
                  {t('mock.q')}
                </div>
                <div className="max-w-[90%] self-start rounded-2xl rounded-bl-sm bg-bubble-bot px-4 py-3.5 text-[15px] text-heading">
                  <div className="mb-2.5">{t('mock.a')}</div>
                  <SourceChip />
                </div>
              </div>
              <div className="flex items-center gap-3 border-t border-line px-5 py-3.5 text-sm">
                <span className="flex-1">{t('mock.input')}</span>
                <span className="inline-flex size-9 items-center justify-center rounded-full bg-ctu-navy text-white">
                  <Icon name="arrow" size={16} />
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="tinh-nang">
        <div className="mx-auto max-w-[1200px] px-8 py-22">
          <h2 className="mb-3 text-center text-4xl">{t('feat.title')}</h2>
          <p className="mx-auto mb-13 max-w-[620px] text-center">{t('feat.sub')}</p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-7">
            {features.map((f) => (
              <div key={f.title} className={`rounded-[10px] border border-t-4 border-line px-7 py-8 ${f.accent}`}>
                <Icon name={f.icon} size={40} className="text-accent" strokeWidth={1.6} />
                <h3 className="mb-2.5 mt-4 text-[22px]">{t(f.title)}</h3>
                <p className="m-0">{t(f.text)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="cach-hoat-dong" className="bg-tint">
        <div className="mx-auto max-w-[1200px] px-8 py-22">
          <h2 className="mb-13 text-center text-4xl">{t('steps.title')}</h2>
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
          <div className="mt-14 text-center">
            <Link
              to="/login"
              className="inline-block rounded-lg bg-ctu-navy px-8 py-3.5 font-semibold text-white no-underline hover:bg-ctu-navy-dark"
            >
              {t('steps.cta')}
            </Link>
          </div>
        </div>
      </section>

      <footer id="lien-he" className="bg-ctu-navy-dark text-white">
        <div className="mx-auto flex max-w-[1200px] flex-wrap justify-between gap-10 px-8 pb-8 pt-14">
          <div className="flex-[1_1_280px]">
            <div className="mb-2 text-lg font-semibold">{t('brand.uni')}</div>
            <p className="m-0 text-sm opacity-85">{t('footer.desc')}</p>
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
            <p className="m-0 opacity-85">{t('footer.contactPlaceholder')}</p>
          </div>
        </div>
        <div className="border-t border-white/20 px-8 py-4 text-center text-[13px] opacity-85">
          {t('brand.disclaimer')}
        </div>
      </footer>
    </div>
  )
}
