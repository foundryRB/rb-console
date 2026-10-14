import type { VitePWAOptions } from 'vite-plugin-pwa';

/**
 * Manifest only: the console's identity on the device, no service worker (REF-PWA
 * section 2). Frozen from the first release: `manifest.id` and `manifest.start_url`
 * (REF-PWA section 3) - changing either forks the installed icon into a second app
 * that the first one's users are never moved to.
 *
 * The console is a live view of a cluster, so it has nothing worth showing offline.
 * A worker would buy a fast launch and an offline screen in exchange for a cached
 * shell that can outrun a deploy, two ways to break the oauth2-proxy redirect, and a
 * bad worker that persists on a device until a kill switch reaches it (REF-PWA
 * section 7). To take one later, read that section first: adding a worker is an
 * ordinary change, removing one after clients have installed is not.
 */
export const pwaOptions: Partial<VitePWAOptions> = {
    // Nothing registers a worker: the manifest is the whole change. The worker the
    // plugin still emits at sw.js is a self-destroying one, which is inert here and
    // is what cleans installed clients up if this app ever drops back from a full
    // PWA to manifest only (REF-PWA section 6).
    injectRegister: null,
    selfDestroying: true,
    // The manifest request carries no cookies by default, even same-origin. The
    // console sits whole behind oauth2-proxy, so without this the proxy answers it
    // with a login redirect and installability fails with no visible error.
    useCredentials: true,
    // The e2e suite drives the dev server (playwright.config.ts), so the manifest has
    // to be served there too, not only in a build.
    devOptions: { enabled: true },
    manifest: {
        id: '/',
        name: 'Foundry Console',
        short_name: 'Console',
        description: 'Watch and drive autonomous deliveries down the foundry floor.',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        // The masthead's own ground and accent, so the window furniture matches the app.
        theme_color: '#e60000',
        background_color: '#04050a',
        icons: [
            { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
            { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
            // Safari uses an icon only when `purpose` is absent or `any`, so the
            // maskable entry is additional to those above, never instead of them.
            {
                src: 'icons/icon-maskable-512.png',
                sizes: '512x512',
                type: 'image/png',
                purpose: 'maskable',
            },
        ],
        screenshots: [
            {
                src: 'screenshots/wide.png',
                sizes: '1280x720',
                type: 'image/png',
                form_factor: 'wide',
            },
            {
                src: 'screenshots/narrow.png',
                sizes: '720x1280',
                type: 'image/png',
                form_factor: 'narrow',
            },
        ],
    },
};
