import { API_BASE_URL, apiFetch } from './api'

/** Khung chữ nhật chuẩn hoá 0..1 trên trang: [trên, trái, dưới, phải]. */
export type Box = [number, number, number, number]
export type Highlight = { page: number; box: Box }

export type DocLayout = {
  title: string
  decision_no?: string
  page_count: number
  pages: Record<string, { width: number; height: number }>
  articles: Record<string, { title: string; highlights: Highlight[] }>
}

const layoutCache = new Map<string, Promise<DocLayout>>()
const documentPath = (documentUrl?: string | null) =>
  documentUrl?.replace(/\/source$/, '') || '/api/v1/documents/qd3266'

/** Tải vị trí các Điều theo đúng phiên bản PDF của tham chiếu. */
export function getDocLayout(documentUrl?: string | null): Promise<DocLayout> {
  const base = documentPath(documentUrl)
  let request = layoutCache.get(base)
  if (!request) {
    request = (apiFetch(`${base}/layout`) as Promise<DocLayout>).catch((err) => {
      layoutCache.delete(base)
      throw err
    })
    layoutCache.set(base, request)
  }
  return request
}

export const pageImageUrl = (page: number, documentUrl?: string | null) =>
  `${API_BASE_URL.replace(/\/$/, '')}${documentPath(documentUrl)}/pages/${page}.jpg`

export type SourceRoute = {
  id: string
  label: string
  kind: 'document' | 'web'
  description: string
  decision_no: string
  official_url: string
}

/** Các nguồn người dùng có thể chọn để hỏi (tài liệu đã đồng bộ và tìm kiếm web nếu bật). */
export const listSelectableRoutes = (): Promise<SourceRoute[]> => apiFetch('/api/v1/documents/catalog/routes')

export type CatalogSummary = {
  count: number
  documents: { id: string; label: string; decision_no: string; description: string; official_url: string }[]
}

/** Công khai: các tài liệu chatbot đang hỗ trợ (đã đồng bộ), lấy từ danh mục admin quản lý. */
export const getCatalogSummary = (): Promise<CatalogSummary> => apiFetch('/api/v1/documents/catalog/summary')
