import { useRef, useState } from 'react'
import { useI18n } from '../i18n'
import { displayToIso, isoToDisplay, maskDate } from '../lib/dates'
import Icon from './Icon'

type Props = {
  id: string
  /** Giá trị ISO yyyy-mm-dd ('' = chưa nhập) */
  value: string
  /** `valid` = false khi chữ đang nhập chưa phải một ngày hợp lệ trong khoảng min..max (khi đó `iso` là '') */
  onChange: (iso: string, valid: boolean) => void
  min: string
  max: string
  className?: string
}

/**
 * Ô nhập ngày LUÔN hiện dạng dd/mm/yyyy (ô type="date" của trình duyệt hiện theo ngôn ngữ trình duyệt, có khi mm/dd/yyyy).
 * Gõ tay có tự chèn dấu "/", hoặc bấm biểu tượng lịch để chọn.
 */
export default function DateField({ id, value, onChange, min, max, className = '' }: Props) {
  const { t } = useI18n()
  const [text, setText] = useState(isoToDisplay(value))
  const picker = useRef<HTMLInputElement>(null)

  const apply = (next: string) => {
    setText(next)
    if (next === '') return onChange('', true) // để trống = xoá ngày sinh
    const iso = displayToIso(next)
    onChange(iso && iso >= min && iso <= max ? iso : '', iso !== null && iso >= min && iso <= max)
  }

  const invalid = text !== '' && !(displayToIso(text) && (displayToIso(text) as string) >= min && (displayToIso(text) as string) <= max)

  return (
    <div className={className}>
      <div className="relative">
      <input
        id={id}
        type="text"
        inputMode="numeric"
        autoComplete="bday"
        placeholder="dd/mm/yyyy"
        maxLength={10}
        value={text}
        aria-invalid={invalid}
        aria-describedby={`${id}-hint`}
        onChange={(e) => apply(maskDate(e.target.value))}
        className="box-border min-h-11 w-full rounded-lg border border-field bg-surface py-2 pl-3.5 pr-12 font-sans text-[15px] text-heading outline-accent aria-[invalid=true]:border-[#D64545]"
      />
      <button
        type="button"
        onClick={() => {
          const el = picker.current
          if (!el) return
          el.value = value
          try {
            el.showPicker()
          } catch {
            el.focus()
          }
        }}
        aria-label={t('profile.birthdayPick')}
        title={t('profile.birthdayPick')}
        className="absolute right-1 top-1/2 inline-flex size-9 -translate-y-1/2 cursor-pointer items-center justify-center rounded-md border-0 bg-transparent text-muted hover:bg-tint hover:text-heading"
      >
        <Icon name="calendar" size={18} />
      </button>
      {/* Chỉ để mở lịch chọn ngày; giá trị được chép sang ô chữ dd/mm/yyyy ở trên. */}
      <input
        ref={picker}
        type="date"
        tabIndex={-1}
        aria-hidden="true"
        min={min}
        max={max}
        onChange={(e) => e.target.value && apply(isoToDisplay(e.target.value))}
        className="pointer-events-none absolute bottom-0 right-1 size-0 opacity-0"
      />
      </div>
      <p id={`${id}-hint`} className={`mb-0 mt-1.5 text-xs ${invalid ? 'text-[#8A1216] dark:text-[#FFB4B7]' : ''}`}>
        {t(invalid ? 'profile.birthdayInvalid' : 'profile.birthdayHint')}
      </p>
    </div>
  )
}
