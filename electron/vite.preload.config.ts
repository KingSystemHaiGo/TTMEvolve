import { defineConfig } from 'vite'
import path from 'path'

export default defineConfig({
  build: {
    ssr: true,
    lib: {
      entry: path.resolve(__dirname, 'preload/index.ts'),
      formats: ['cjs'],
      fileName: () => 'index.js',
    },
    outDir: path.resolve(__dirname, 'dist/preload'),
    emptyOutDir: true,
    rollupOptions: {
      external: ['electron'],
    },
  },
})
