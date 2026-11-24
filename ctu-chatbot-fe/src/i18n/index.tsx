import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react'
import type { TranslationKey } from './vi'
import viLanding from './vi-landing'

// Trang chủ dùng từ điển nhỏ. Các trang ứng dụng tải từ điển đầy đủ khi cần.
type I18nValue = {
  t: (key: TranslationKey) => string
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children, messages = viLanding }: {
  children: ReactNode
  messages?: Partial<Record<TranslationKey, string>>
}) {
  useEffect(() => {
    document.documentElement.lang = 'vi'
  }, [])

  const value = useMemo<I18nValue>(() => ({ t: (key) => messages[key] ?? key }), [messages])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>')
  return ctx
}
