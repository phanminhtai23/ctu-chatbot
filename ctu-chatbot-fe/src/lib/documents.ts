import { apiFetch } from './api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** Khung chữ nhật chuẩn hoá 0..1 trên trang: [trên, trái, dưới, phải]. */
export type Box = [number, number, number, number]
export type Highlight = { page: number; box: Box }

export type DocLayout = {
  title: string
  page_count: number
  pages: Record<string, { width: number; height: number }>
  articles: Record<string, { title: string; highlights: Highlight[] }>
}

let cached: Promise<DocLayout> | null = null

/** Vị trí từng Điều trong PDF quy định; chỉ tải một lần cho cả phiên. */
export function getDocLayout(): Promise<DocLayout> {
  cached ??= (apiFetch('/api/v1/documents/qd3266/layout') as Promise<DocLayout>).catch((err) => {
    cached = null // lần sau thử lại
    throw err
  })
  return cached
}

export const pageImageUrl = (page: number) => `${API_BASE_URL}/api/v1/documents/qd3266/pages/${page}.jpg`
