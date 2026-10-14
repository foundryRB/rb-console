import { Link } from 'react-router-dom';

import type { State } from '@/models';
import { Card } from '@/components/ui/card';
import { selectPendingGate, selectPhaseStrip, repoName } from '@/viewmodels/deliveries';
import { GateList } from '@/views/atoms/GateList';
import { NextCommand } from '@/views/atoms/NextCommand';
import { PhaseStrip } from '@/views/atoms/PhaseStrip';
import { SeedBadge } from '@/views/atoms/SeedBadge';
import { StatusBadge } from '@/views/atoms/StatusBadge';

export interface DeliveryCardProps {
    state: State;
}

/** One delivery on the watch list: its phase strip, gates, and next command. */
export const DeliveryCard: React.FC<DeliveryCardProps> = ({ state }) => {
    const cells = selectPhaseStrip(state);
    const pendingGate = selectPendingGate(state);
    return (
        <Card className="flex flex-col gap-4 p-5">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <Link
                        to={`/d?repo=${encodeURIComponent(state.repo)}`}
                        className="block truncate font-semibold tracking-tight hover:text-link"
                        title={state.repo}
                    >
                        {repoName(state.repo)}
                    </Link>
                    <div
                        className="truncate font-mono text-xs text-muted-foreground"
                        title={state.repo}
                    >
                        {state.repo}
                    </div>
                </div>
                <span className="flex shrink-0 items-center gap-2">
                    <SeedBadge seed={state.seed ?? ''} demoOf={state.demo_of} />
                    <StatusBadge status={state.status} label={state.status_label} />
                </span>
            </div>

            <PhaseStrip cells={cells} />

            <div className="flex flex-col gap-3">
                <GateList gates={state.gates} pendingGate={pendingGate} />
                <NextCommand command={state.next_command} />
            </div>
        </Card>
    );
};
