import { expect, type Page } from '@playwright/test';
import DOMPurify from 'dompurify';

/** Exercise editor assets while every request outside the app's origin is blocked. */
export async function localEditorNetwork(page: Page, baseURL: string) {
    const external: string[] = [];
    const errors: string[] = [];
    const workers: string[] = [];
    const responses: { url: string; status: number }[] = [];
    const sanitizers = new Set<string>();
    const origin = new URL(baseURL).origin;
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => {
        if (/Could not create web worker|Failed to load worker/.test(message.text())) errors.push(message.text());
    });
    page.on('worker', (worker) => workers.push(worker.url()));
    page.context().on('response', async (response) => {
        if (/worker.*\.js/.test(response.url())) {
            responses.push({ url: response.url(), status: response.status() });
        }
        if (/\.m?js(?:\?|$)/.test(response.url()) && response.ok()) {
            const source = await response.text().catch(() => '');
            if (source.includes('dompurify')) {
                for (const match of source.matchAll(/(?:DOMPurify |\.version\s*=\s*['"`])(\d+\.\d+\.\d+)/g)) sanitizers.add(match[1]);
            }
        }
    });
    await page.route('**/*', (route) => {
        if (new URL(route.request().url()).origin === origin) return route.fallback();
        external.push(route.request().url());
        return route.abort();
    });
    return {
        external, errors, workers, responses,
        async checkSanitizer() {
            await expect.poll(() => [...sanitizers]).toEqual([DOMPurify.version]);
            return [...sanitizers];
        },
    };
}
