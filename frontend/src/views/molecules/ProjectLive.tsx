import type { FleetItem } from '@/models';
import { cn } from '@/utils';

export const ProjectLive: React.FC<{
    p: FleetItem;
    busy: boolean;
    onPause: () => void;
    onResume: () => void;
}> = ({ p, busy, onPause, onResume }) => {
    if (!p.onboarded) return <span className="text-muted-foreground">-</span>;
    const tone =
        p.live === 'running'
            ? 'text-[hsl(var(--success))]'
            : p.live === 'paused'
              ? 'text-amber-400'
              : 'text-muted-foreground';
    const dot =
        p.live === 'running'
            ? 'bg-[hsl(var(--success))]'
            : p.live === 'paused'
              ? 'bg-amber-400'
              : 'bg-muted-foreground/40';
    return (
        <span className="inline-flex items-center gap-2">
            <span className={cn('inline-flex items-center gap-1.5 text-xs', tone)}>
                <span className={cn('h-1.5 w-1.5 rounded-full', dot)} />
                {p.live ?? 'unknown'}
            </span>
            {p.live === 'running' && (
                <button
                    type="button"
                    disabled={busy}
                    onClick={(e) => {
                        e.stopPropagation(); // the row/tile navigates on click; pausing must not also open the cockpit
                        onPause();
                    }}
                    className="text-[10px] text-muted-foreground hover:text-link"
                >
                    pause
                </button>
            )}
            {p.live === 'paused' && (
                <button
                    type="button"
                    disabled={busy}
                    onClick={(e) => {
                        e.stopPropagation();
                        onResume();
                    }}
                    className="text-[10px] text-link hover:underline"
                >
                    resume
                </button>
            )}
        </span>
    );
};
