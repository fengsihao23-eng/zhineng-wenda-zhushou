import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  // The Docker service name (`api`) is only resolvable from containers.  When
  // Vite runs on the host, route API calls through the public gateway instead;
  // developers running uvicorn directly can set VITE_PROXY_TARGET in an env
  // file or in the shell (for example, http://localhost:8000).
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://localhost'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      watch: {
        usePolling: true,
      },
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
