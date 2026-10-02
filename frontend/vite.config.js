import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const basePath = process.env.VITE_BASE_PATH || '/'
const base = basePath.endsWith('/') ? basePath : `${basePath}/`

export default defineConfig({
  base,
  plugins: [vue()],
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
  build: { rollupOptions: { output: { manualChunks: { charts: ['echarts'], three: ['three'] } } } }
})
