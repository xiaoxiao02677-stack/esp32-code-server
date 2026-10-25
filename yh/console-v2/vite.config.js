import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const base = mode === 'admin' ? '/admincc/' : (process.env.VITE_PUBLIC_BASE || '/')
  return {
    plugins: [vue()],
    base,
    server: { port: 5180, host: true },
    build: { outDir: mode === 'admin' ? 'dist-admin' : 'dist' }
  }
})
