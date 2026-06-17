/// <reference types="vitest" />
import fs from 'fs'
import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { compression } from 'vite-plugin-compression2'
import { visualizer } from 'rollup-plugin-visualizer'

// Copy the built index.html to 404.html so static hosts (Render, GitHub Pages,
// Cloudflare Pages) serve the SPA for unknown paths instead of a bare 404.
function spaFallbackPlugin() {
  return {
    name: 'spa-fallback',
    closeBundle() {
      const dist = path.resolve(__dirname, 'dist')
      const indexPath = path.join(dist, 'index.html')
      const fallbackPath = path.join(dist, '404.html')
      if (fs.existsSync(indexPath)) {
        fs.copyFileSync(indexPath, fallbackPath)
      }
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    // Pre-compress static assets for CDN/Reverse-proxy serving
    compression({ algorithm: 'gzip', include: /\.(js|css|html|svg|json)$/ }),
    compression({ algorithm: 'brotliCompress', include: /\.(js|css|html|svg|json)$/ }),
    // Emit bundle analysis report on build
    visualizer({ open: false, filename: 'dist/stats.html' }),
    spaFallbackPlugin(),
  ],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      thresholds: {
        statements: 60,
        branches: 60,
        functions: 60,
        lines: 60,
      },
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/test/**', 'src/**/*.d.ts', 'src/main.tsx'],
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          'vendor-antd': ['antd', '@ant-design/icons'],
          'vendor-echarts': ['echarts', 'echarts-for-react'],
          'vendor-axios': ['axios'],
        },
      },
    },
  },
})
