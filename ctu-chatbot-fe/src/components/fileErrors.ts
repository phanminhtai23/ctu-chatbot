import type { TranslationKey } from '../i18n/vi'
import type { FileErrorCode } from '../lib/files'
import { fillTemplate, formatBytes } from '../lib/format'

const keys: Record<FileErrorCode, TranslationKey> = {
  FILE_TOO_LARGE: 'files.err.tooLarge',
  QUOTA_EXCEEDED: 'files.err.quota',
  UNSUPPORTED_TYPE: 'files.err.type',
  EMPTY_FILE: 'files.err.empty',
  STORAGE_NOT_CONFIGURED: 'files.err.notConfigured',
  STORAGE_ERROR: 'files.err.storage',
  UNKNOWN: 'files.err.unknown',
}

export function fileErrorMessage(code: FileErrorCode, t: (key: TranslationKey) => string, maxBytes: number): string {
  return fillTemplate(t(keys[code]), { max: formatBytes(maxBytes) })
}
