import { Link } from 'react-router-dom';
import type { MaintInboxItem } from '@/models';
import { cn } from '@/utils';

import { MaintenanceStage } from '@/views/atoms/MaintenanceStage';

import { inboxTarget } from '@/viewmodels/fleet/fleet.model';

export const InboxItem: React.FC<{ it: MaintInboxItem; appName?: string }> = ({ it, appName }) => {
    const target = inboxTarget(it, appName);
    const external = 'href' in target;
    const cls = cn(
        'flex items-baseline gap-2 border-b border-border px-4 py-2 text-xs last:border-0 hover:bg-primary/5',
        it.hidden && 'opacity-55',
    );
    const inner = (
        <>
            <span
                className={cn(
                    'w-20 flex-none rounded px-1.5 py-0.5 text-center font-mono text-[9px] font-semibold uppercase',
                    it.signal === 'running'
                        ? 'animate-pulse bg-primary/20 text-link' // in flight now
                        : it.signal === 'red-ci' || it.signal === 'drift'
                          ? 'bg-destructive/15 text-destructive'
                          : it.signal === 'pr-review'
                            ? 'bg-primary/15 text-link'
                            : 'bg-muted text-muted-foreground',
                )}
            >
                {it.signal}
            </span>
            <span className="w-40 flex-none truncate font-mono text-[11px] text-muted-foreground">
                {it.repo.split('/').pop()}
            </span>
            <MaintenanceStage stage={it.stage} />
            <span className="min-w-0 flex-1 truncate">{it.detail}</span>
            {it.hidden && (
                <span className="flex-none rounded bg-muted px-1 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">
                    hidden
                </span>
            )}
            <span className="flex-none font-mono text-[10px] text-link">
                {it.act} {external ? '↗' : '→'}
            </span>
        </>
    );
    return external ? (
        <a href={target.href} target="_blank" rel="noreferrer" className={cls}>
            {inner}
        </a>
    ) : (
        <Link to={target.to} className={cls}>
            {inner}
        </Link>
    );
};
