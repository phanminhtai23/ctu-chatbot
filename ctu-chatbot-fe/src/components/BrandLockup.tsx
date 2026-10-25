import { useI18n } from '../i18n'
import Logo from './Logo'

type Props = {
  size?: number
  title?: string
  subtitle?: string
  textClassName?: string
}

export default function BrandLockup({ size = 52, title, subtitle, textClassName = '' }: Props) {
  const { t } = useI18n()
  return (
    <span className="flex min-w-0 items-center gap-2">
      <Logo size={size} />
      <span className={`min-w-0 leading-tight ${textClassName}`}>
        <span className="block truncate text-base font-semibold tracking-wide sm:text-lg">{title ?? t('brand.app')}</span>
        <span className="mt-0.5 block truncate text-[13px] leading-5 opacity-90 sm:text-sm">
          {subtitle ?? t('brand.appSub')}
        </span>
      </span>
    </span>
  )
}
