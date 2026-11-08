export type DiffPart = { kind: 'same' | 'add' | 'del'; text: string }

/** Tách thành từng từ kèm khoảng trắng đi sau để ghép lại đúng nguyên văn. */
const tokenize = (text: string): string[] => text.match(/\S+\s*|\s+/g) ?? []

/** So sánh theo từ (LCS): dùng để tô phần thêm / bớt giữa hai bản prompt. Văn bản prompt ngắn nên O(n*m) là đủ. */
export function diffWords(before: string, after: string): { before: DiffPart[]; after: DiffPart[] } {
  const a = tokenize(before)
  const b = tokenize(after)
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i].trim() === b[j].trim() ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }
  const left: DiffPart[] = []
  const right: DiffPart[] = []
  const push = (parts: DiffPart[], kind: DiffPart['kind'], text: string) => {
    const last = parts[parts.length - 1]
    if (last && last.kind === kind) last.text += text
    else parts.push({ kind, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i].trim() === b[j].trim()) {
      push(left, 'same', a[i])
      push(right, 'same', b[j])
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      push(left, 'del', a[i++])
    } else {
      push(right, 'add', b[j++])
    }
  }
  while (i < a.length) push(left, 'del', a[i++])
  while (j < b.length) push(right, 'add', b[j++])
  return { before: left, after: right }
}
