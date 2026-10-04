import { useI18n } from '../i18n'
import Icon from './Icon'

export default function SourceChip() {
  const { t } = useI18n()
  return (
    <a
      href="#"
      className="inline-flex items-center gap-2 rounded-md border border-ctu-cyan bg-surface px-3 py-1.5 text-[13px] font-normal text-accent no-underline"
    >
      <Icon name="doc" size={14} />
      {t('source.label')}
    </a>
  )
}
