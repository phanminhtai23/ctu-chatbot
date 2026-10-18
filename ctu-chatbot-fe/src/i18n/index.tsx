import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react'
import vi, { type TranslationKey } from './vi'

// Ứng dụng chỉ có tiếng Việt: giữ lớp `t(key)` để mọi chữ trên giao diện vẫn nằm ở một chỗ (i18n/vi.ts).
type I18nValue = {
  t: (key: TranslationKey) => string
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    document.documentElement.lang = 'vi'
  }, [])

  const value = useMemo<I18nValue>(() => ({ t: (key) => vi[key] }), [])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>')
  return ctx
}
