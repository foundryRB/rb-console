import type { StudioHealth } from '@/models';
import { cn } from '@/utils';

/**
 * The org-wide view of everything: each connected studio (estimatekit, protopane,
 * platform-studio, playbook-studio) as a reachability chip. A green dot is up, dim is
 * down; the chip links to the studio. Reads from the warm studio cache.
 */
export const StudiosStrip: React.FC<{ studios: StudioHealth[] }> = ({ studios }) => {
    if (studios.length === 0) return null;
    const chips = studios.map((s) => {
        const chip = (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-xs">
                <span
                    className={cn(
                        'h-1.5 w-1.5 rounded-full',
                        s.reachable ? 'bg-emerald-500' : 'bg-muted-foreground/40',
                    )}
                    aria-hidden
                />
                <span className="font-medium">{s.studio}</span>
                <span className="rb-studio-detail text-muted-foreground">{s.detail}</span>
            </span>
        );
        return s.url ? (
            <a
                key={s.studio}
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="transition-opacity hover:opacity-80"
            >
                {chip}
            </a>
        ) : (
            <span key={s.studio}>{chip}</span>
        );
    });
    return (
        <div className="rb-studios">
            <div className="rb-studios-inline flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Studios
                </span>
                {chips}
            </div>
            <details className="rb-studios-menu">
                <summary>Studios · {studios.length}</summary>
                <div>{chips}</div>
            </details>
        </div>
    );
};
