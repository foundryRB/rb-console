import type { FleetItem, Freshness } from '@/models';
export interface FleetState {
    fleet: FleetItem[];
    fleetLoading: boolean;
    fleetError: string | null;
    freshness: Freshness | null;
    fleetRefreshedAt: string | null;
    fleetRefreshError: string | null;
    fleetRefreshPending: boolean;
    fleetStaleSince: string | null;
    fleetStaleReason: string;
    showHidden: boolean;
}
