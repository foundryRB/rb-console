import { Link } from 'react-router-dom';
import type { FleetItem } from '@/models';
import { cn } from '@/utils';

import { deliveryView } from '@/viewmodels/fleet/fleet.model';

export const ProjectDelivery: React.FC<{ p: FleetItem }> = ({ p }) => {
    if (!p.is_delivery) {
        // A repo with no scratch ref but a platform app is a RECONCILED engagement: the
        // line was closed after delivering (its records live on the delivered/* tag).
        // The truest success state must read as closed, not vanish into a dash - a live
        // e2e "disappeared" exactly this way.
        if (p.onboarded) {
            return (
                <Link
                    to={`/d?repo=${encodeURIComponent(p.repo)}`}
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex items-center gap-1.5 rounded-full border border-[hsl(var(--success))]/40 bg-[hsl(var(--success))]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[hsl(var(--success))] hover:underline"
                    title="Operational on the platform with no open delivery - a reconciled, closed line, or an app from before the foundry. Opens the project cockpit."
                >
                    live
                </Link>
            );
        }
        return <span className="text-muted-foreground">-</span>;
    }
    const v = deliveryView(p);
    return (
        <Link
            to={`/d?repo=${encodeURIComponent(p.repo)}`}
            title={
                v.live
                    ? 'A worker is running now. Open the delivery cockpit'
                    : 'Open the delivery cockpit'
            }
            className={cn('inline-flex items-center gap-1.5 hover:underline', v.cls)}
        >
            {v.live && (
                <span
                    className="h-1.5 w-1.5 flex-none rounded-full bg-current animate-pulse"
                    aria-hidden="true"
                />
            )}
            {v.text}
        </Link>
    );
};
