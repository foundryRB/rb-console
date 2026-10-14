import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merge Tailwind class names, resolving conflicts. */
export function cn(...inputs: ClassValue[]): string {
    return twMerge(clsx(inputs));
}

/** Platform links use the observed app name and Gateway host. Delivery studio links
 * use the repository slug. If appName is empty, repoSlug supplies the display route;
 * if host is empty, the live route uses the console's parent domain. */
export function projectLinks(
    repoSlug: string,
    appName: string = '',
    host: string = '',
): {
    live: string;
    docs: string;
    argocd: string;
    grafana: string;
    estimatekit: string;
    protopane: string;
} {
    const hostname = typeof window !== 'undefined' ? window.location.hostname : '';
    // Derive the local link domain from the console host; a bare host remains local.
    const base = hostname.split('.').slice(1).join('.') || hostname;
    const app = appName || repoSlug;
    return {
        live: host ? `https://${host}` : `https://${app}.${base}`,
        docs: `https://docs.${base}/apps/${app}/`,
        argocd: `https://argocd.${base}/applications/${app}`,
        // The per-service dashboard generated on onboarding; its UID is svc-<app>, and
        // Grafana resolves /d/<uid> to the dashboard directly.
        grafana: `https://grafana.${base}/d/svc-${app}`,
        // Delivery-side: keyed on the repository, which is the delivery key.
        estimatekit: `https://estimatekit.${base}/projects/${repoSlug}`,
        protopane: `https://protopane.${base}/p/${repoSlug}`,
    };
}

/** The project's GitHub repo (repo is "org/name"). */
export function githubUrl(repo: string): string {
    return `https://github.com/${repo}`;
}
