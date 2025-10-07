import { defineConfig } from 'vite'

export default defineConfig({
  root: 'static',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: 'static/edge-index.html'
      }
    }
  }
})
