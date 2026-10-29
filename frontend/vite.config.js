import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiOrigin = env.VITE_API_BASE ? new URL(env.VITE_API_BASE).origin : ''
  if (apiOrigin && command === 'build' && !apiOrigin.startsWith('https://'))
    throw new Error('生产 API 地址必须使用 HTTPS，或使用同源 /api 代理。')
  const csp = [
    "default-src 'self'", "script-src 'self'", "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:", "media-src 'self' blob:", "font-src 'self'",
    `connect-src 'self' ${apiOrigin} ${command === 'serve' ? 'ws://localhost:* ws://127.0.0.1:*' : ''}`,
    "object-src 'none'", "base-uri 'none'", "form-action 'self'",
  ].join('; ')
  const headers = {
    'Content-Security-Policy': csp + "; frame-ancestors 'none'",
    'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
  }
  return {
  plugins: [vue(), {
    name: 'security-policy',
    transformIndexHtml() {
      return [{ tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: csp }, injectTo: 'head-prepend' }]
    },
  }],
  server: {
    port: 5173,
    headers,
    proxy: {
      '/api': process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
    },
  },
  preview: { headers },
  }
})
