import path from 'node:path'

export default {
  root: path.resolve(__dirname, '../../apps/web'),
  envDir: __dirname,
  esbuild: { jsx: 'automatic' },
  define: { 'import.meta.env.VITE_API_URL': JSON.stringify('/api/v1') },
  server: { host: '127.0.0.1', port: 5187, strictPort: true },
}
