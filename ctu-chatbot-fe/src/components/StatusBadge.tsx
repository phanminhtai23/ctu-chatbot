import { useI18n } from '../i18n'
import type { TranslationKey } from '../i18n/vi'
import type { FeedbackStatus } from '../lib/adminFeedback'

const styles: Record<FeedbackStatus, string> = {
  new: 'bg-ctu-gold-active text-ctu-navy-dark',
  reviewed: 'bg-tint text-accent border border-line',
  resolved: 'bg-[#E3F4EA] text-[#14602F] dark:bg-[#12301F] dark:text-[#8AD9A8]',
}

const labels: Record<FeedbackStatus, TranslationKey> = {
  new: 'fbstatus.new',
  reviewed: 'fbstatus.reviewed',
  resolved: 'fbstatus.resolved',
}

export default function StatusBadge({ status }: { status: FeedbackStatus }) {
  const { t } = useI18n()
  return (
    <span className={`inline-block rounded-full px-3 py-0.5 text-xs font-semibold ${styles[status]}`}>
      {t(labels[status])}
    </span>
  )
}
