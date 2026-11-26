import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const inlineEntryStyles: Plugin = {
  name: 'inline-entry-styles',
  apply: 'build',
  transformIndexHtml: {
    order: 'post',
    handler(html, { bundle, chunk }) {
      return html.replace(/<link rel="stylesheet" crossorigin href="\/([^"\n]+\.css)">/g, (tag, file: string) => {
        const asset = bundle?.[file]
        if (asset?.type !== 'asset' || typeof asset.source !== 'string') return tag
        // The inline stylesheet is already loaded. Keep it out of async route preloads.
        chunk?.viteMetadata?.importedCss.delete(file)
        return `<style>${asset.source.replace(/<\/style/gi, '<\\/style')}</style>`
      })
    },
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), inlineEntryStyles],
})
