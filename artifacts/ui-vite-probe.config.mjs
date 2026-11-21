import base from '../ctu-chatbot-fe/vite.config.ts'

// Same-origin API proxy lets both local browsers and Docker Playwright reach BE.
export default {
  ...base,
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('') },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: ['host.docker.internal'],
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
}
