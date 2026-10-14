import { defineConfig, devices } from '@playwright/test';

/** Responsive regression suite. It drives the real SPA with the
 * `/api` layer stubbed in-browser, so it needs no orchestrator backend and no cluster
 * uptime - it runs on a GitHub-hosted runner beside the pytest suite. Its whole job is to
 * hold the desktop cockpit still while the mobile/tablet layer evolves: the assertions are
 * layout invariants at 390 / 834 / 1280 px. */
export default defineConfig({
    testDir: './e2e',
    fullyParallel: true,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,
    reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
    // The first assertion of most tests is the page's first paint after goto, served by the
    // Vite dev server compiling on demand. On the shared in-cluster runner that paint takes
    // 6-7s when the pool is busy (about 4s when it is not), so the default 5s budget turns a
    // slow runner into red checks. CI gets a budget that measures the app, not the runner;
    // local runs keep the tight default.
    expect: { timeout: process.env.CI ? 15_000 : 5_000 },
    use: {
        baseURL: 'http://localhost:5190',
        trace: 'on-first-retry',
    },
    projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
    webServer: {
        command: `npm run ${process.env.PLAYWRIGHT_PREVIEW ? 'preview' : 'dev'} -- --port 5190 --strictPort`,
        url: 'http://localhost:5190',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
    },
});
