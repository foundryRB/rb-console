import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { VitePWA } from 'vite-plugin-pwa';

import { pwaOptions } from './pwa.config';

// Monaco's sanitizer import resolves to the installed DOMPurify package.
const monacoSanitizer: Plugin = {
    name: 'monaco-sanitizer',
    enforce: 'pre',
    resolveId: {
        order: 'pre',
        handler(source, importer) {
            if (source === './dompurify/dompurify.js' &&
                importer?.replaceAll('\\', '/').endsWith('/monaco-editor/esm/vs/base/browser/domSanitize.js')) {
                return fileURLToPath(import.meta.resolve('dompurify'));
            }
        },
    },
};

// https://vite.dev/config/
export default defineConfig({
    plugins: [monacoSanitizer, react(), VitePWA(pwaOptions)],
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src', import.meta.url)),
        },
    },
    optimizeDeps: {
        rolldownOptions: { plugins: [monacoSanitizer] },
    },
    server: {
        proxy: {
            '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
        },
    },
});
