import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  plugins: [vue()],
  base: '/cc/',
  server: {
    port: 8090,
    proxy: {
      '/yuhe': {
        target: 'http://sandyun.top:8001',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
