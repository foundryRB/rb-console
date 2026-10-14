import { useFleet } from '@/viewmodels/fleet';
import { useStudios } from '@/viewmodels/studios';
import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';

import { cn } from '@/utils';
import { useDeliveries } from '@/viewmodels/deliveries';
import { Button } from '@/components/ui/button';
import { Cockpit } from '@/views/templates/Cockpit';

/** The five studios the Console drives, in delivery order, with the surface each owns. */
const STUDIO_ROLE: Record<string, string> = {
    estimatekit: 'Scope - proposals, BRD, estimates',
    protopane: 'Design - interactive prototypes',
    'platform-studio': 'Build & ship - onboard, deploy, run',
    'playbook-studio': 'Learn - lessons and playbook',
    'onboarding-studio': 'Onboarding - admit apps to the platform',
};

const StudiosPage: React.FC = () => {
    const { studios, loadStudios } = useStudios(),
        { fleet, loadFleet, pauseApp, resumeApp } = useFleet(),
        { actionLoading, actionError } = useDeliveries();

    useEffect(() => {
        void loadStudios();
        void loadFleet();
    }, [loadStudios, loadFleet]);

    // Holdings: what platform-studio actually carries - every onboarded app and whether it is live.
    const holdings = useMemo(() => fleet.filter((p) => p.onboarded), [fleet]);

    return (
        <Cockpit aside={`${studios.filter((s) => s.reachable).length}/${studios.length} up`}>
            <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Studios
            </h2>
            <p className="mb-5 text-xs text-muted-foreground">
                The studios the Console drives across the delivery line, and what the platform is
                holding.
            </p>

            <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {studios.map((s) => (
                    <div
                        key={s.studio}
                        className="flex items-start gap-3 rounded-lg border border-border bg-card px-4 py-3"
                    >
                        <span
                            className={cn(
                                'mt-1.5 inline-block h-2 w-2 flex-shrink-0 rounded-full',
                                s.reachable ? 'bg-[hsl(var(--success))]' : 'bg-destructive',
                            )}
                        />
                        <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                                <span className="font-medium">{s.studio}</span>
                                <span
                                    className={cn(
                                        'text-xs',
                                        s.reachable
                                            ? 'text-[hsl(var(--success))]'
                                            : 'text-destructive',
                                    )}
                                >
                                    {s.reachable ? 'reachable' : 'unreachable'}
                                </span>
                            </div>
                            <div className="text-xs text-muted-foreground">
                                {STUDIO_ROLE[s.studio] ?? s.detail}
                            </div>
                            {s.url && (
                                <a
                                    href={s.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="font-mono text-[11px] text-muted-foreground hover:text-link"
                                >
                                    {s.url}
                                </a>
                            )}
                        </div>
                    </div>
                ))}
                {studios.length === 0 && (
                    <p className="text-sm text-muted-foreground">No studios connected.</p>
                )}
            </div>

            <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Platform holdings
            </h3>
            <p className="mb-3 text-xs text-muted-foreground">
                Apps onboarded to the platform, whether they are live, and their pause switch.
                {actionError && <span className="ml-2 text-destructive">{actionError}</span>}
            </p>
            {holdings.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing onboarded yet.</p>
            ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {holdings.map((p) => (
                        <div
                            key={p.repo}
                            className="rounded-lg border border-border bg-card px-4 py-3"
                        >
                            <div className="flex items-center justify-between gap-2">
                                {p.is_delivery ? (
                                    <Link
                                        to={`/d?repo=${encodeURIComponent(p.repo)}`}
                                        className="font-medium hover:text-link"
                                    >
                                        {p.name}
                                    </Link>
                                ) : (
                                    <span className="font-medium">{p.name}</span>
                                )}
                                <span
                                    className={cn(
                                        'inline-flex items-center gap-1.5 text-xs',
                                        p.live === 'running'
                                            ? 'text-[hsl(var(--success))]'
                                            : 'text-muted-foreground',
                                    )}
                                >
                                    <span
                                        className={cn(
                                            'inline-block h-1.5 w-1.5 rounded-full',
                                            p.live === 'running'
                                                ? 'bg-[hsl(var(--success))]'
                                                : 'bg-muted-foreground/40',
                                        )}
                                    />
                                    {p.live ?? 'unknown'}
                                </span>
                            </div>
                            <div className="mb-2 font-mono text-[11px] text-muted-foreground">
                                {p.repo}
                            </div>
                            {p.live === 'running' ? (
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-7 w-full px-2 text-xs"
                                    disabled={actionLoading}
                                    onClick={() => void pauseApp(p.app_name || p.name)}
                                >
                                    Pause
                                </Button>
                            ) : p.live === 'paused' ? (
                                <Button
                                    type="button"
                                    className="h-7 w-full px-2 text-xs"
                                    disabled={actionLoading}
                                    onClick={() => void resumeApp(p.app_name || p.name)}
                                >
                                    Resume
                                </Button>
                            ) : null}
                        </div>
                    ))}
                </div>
            )}
        </Cockpit>
    );
};

export default StudiosPage;
