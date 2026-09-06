import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Relative asset URLs so the build output can be published at any path —
  // the recommended layout serves it at docs/app/ beside the audit page.
  base: './',
})
