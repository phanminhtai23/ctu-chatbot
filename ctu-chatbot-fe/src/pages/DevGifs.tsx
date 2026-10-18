import { useState } from 'react'
import { errorGifs, welcomeGifs } from '../lib/gifs'

const nameOf = (url: string) => decodeURIComponent(url.split('/').pop() ?? url).replace(/-[A-Za-z0-9_]{8}\.gif$/, '.gif')

function Card({ url }: { url: string }) {
  const [size, setSize] = useState('')
  return (
    <figure className="m-0 flex w-[260px] flex-col gap-2 rounded-xl border border-line bg-surface p-3">
      <div className="flex h-[220px] items-center justify-center overflow-hidden rounded-lg bg-tint">
        <img
          src={url}
          alt=""
          className="h-full w-full object-contain"
          onLoad={(e) => setSize(`${e.currentTarget.naturalWidth}×${e.currentTarget.naturalHeight}px`)}
        />
      </div>
      <figcaption className="break-all text-xs text-heading">
        {nameOf(url)}
        <span className="block text-muted">{size}</span>
      </figcaption>
    </figure>
  )
}

/** Trang xem trước các GIF của hộp thoại vui (chỉ có khi chạy `npm run dev`): xem từng ảnh có hợp không. */
export default function DevGifs() {
  return (
    <main className="min-h-screen bg-surface px-6 py-6">
      <h1 className="m-0 mb-1 text-2xl">GIF hộp thoại bị giới hạn / lỗi chat ({errorGifs.length})</h1>
      <p className="m-0 mb-4 text-sm">Thư mục: src/assets/exceed_rate_limit_gifs</p>
      <div className="flex flex-wrap gap-4">
        {errorGifs.map((g) => (
          <Card key={g} url={g} />
        ))}
      </div>
      <h1 className="m-0 mb-1 mt-10 text-2xl">GIF hộp thoại chào mừng ({welcomeGifs.length})</h1>
      <p className="m-0 mb-4 text-sm">Thư mục: src/assets/welcome_gifs</p>
      <div className="flex flex-wrap gap-4">
        {welcomeGifs.map((g) => (
          <Card key={g} url={g} />
        ))}
      </div>
    </main>
  )
}
