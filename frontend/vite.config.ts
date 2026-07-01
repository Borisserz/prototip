import path from "path"
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        // Code-splitting: тяжёлые вендоры выносим в отдельные чанки,
        // чтобы не отдавать один бандл ~1.9 МБ и улучшить кеширование.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined
          if (/recharts|d3-|victory|chart\.js/.test(id)) return "charts"
          if (/jspdf|html2canvas|pptxgenjs|docx|xlsx|file-saver/.test(id)) return "export-docs"
          if (/framer-motion/.test(id)) return "motion"
          if (/react-dom|react-router|scheduler|\/react\//.test(id)) return "react-vendor"
          return "vendor"
        },
      },
    },
  },
})
