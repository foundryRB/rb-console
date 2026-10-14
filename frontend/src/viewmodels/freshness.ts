import { useEffect, useState } from 'react';

/** The hashed entry script this tab is actually executing (/assets/index-<hash>.js).
 *  Empty under the dev server (vite serves /src/main.tsx unhashed), which disables
 *  the whole check - staleness is a built-bundle concern only. */
function runningBundle(): string {
    const src = document.querySelector('script[type="module"]')?.getAttribute('src') ?? '';
    return /\/assets\/index-[^"]+\.js$/.test(src) ? src : '';
}

/** The entry script the server is serving right now, read from an uncached fetch of
 *  index.html. '' when unreadable (offline, mid-rollout) - never flag on a failed read. */
async function servedBundle(): Promise<string> {
    const res = await fetch('/', { cache: 'no-store', headers: { Accept: 'text/html' } });
    if (!res.ok) return '';
    const html = await res.text();
    return html.match(/\/assets\/index-[^"]+\.js/)?.[0] ?? '';
}

/** Compare the running hashed bundle with the uncached server entry script.
 * A hidden tab reloads at most once per observed bundle. A visible tab shows the
 * update banner while preserving operator input. Poll on the interval and whenever
 * the tab changes visibility; unavailable reads leave the current decision intact. */
export function useStaleBundle(intervalMs = 60_000): boolean {
    const [stale, setStale] = useState(false);
    useEffect(() => {
        const mine = runningBundle();
        if (!mine) return;
        let stopped = false;
        const check = async () => {
            const served = await servedBundle().catch(() => '');
            if (stopped || !served || served === mine) return;
            if (document.hidden && sessionStorage.getItem('fc-reloaded-for') !== served) {
                sessionStorage.setItem('fc-reloaded-for', served);
                window.location.reload();
                return;
            }
            setStale(true);
        };
        const timer = window.setInterval(check, intervalMs);
        document.addEventListener('visibilitychange', check);
        return () => {
            stopped = true;
            window.clearInterval(timer);
            document.removeEventListener('visibilitychange', check);
        };
    }, [intervalMs]);
    return stale;
}
