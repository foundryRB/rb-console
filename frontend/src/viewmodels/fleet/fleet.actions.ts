import { create } from 'zustand';
import type { ChatTurn, FleetResponse } from '@/models';
import { apiFetch } from '@/viewmodels/requests';

import { awaitTurn, fleetResult, TurnStillRunning } from '@/viewmodels/turns/turns.actions';

import { useDeliveries } from '@/viewmodels/deliveries';
import type { FleetState } from './fleet.state';
const errorText = (err: unknown): string => (err instanceof Error ? err.message : 'Unknown error');
const readShowHidden = (): boolean => {
    try {
        return typeof localStorage !== 'undefined' && localStorage.getItem('fc.showHidden') === '1';
    } catch {
        return false;
    }
};

let watchedTurn: string | null = null;

interface FleetActions {
    loadFleet: () => Promise<void>;
    refreshFleetNow: () => Promise<boolean>;
    setShowHidden: (v: boolean) => void;
    pauseApp: (name: string) => Promise<void>;
    resumeApp: (name: string) => Promise<void>;
}
export const useFleet = create<FleetState & FleetActions>()((set, get) => ({
    fleet: [],
    fleetLoading: false,
    fleetError: null,
    freshness: null,
    fleetRefreshedAt: null,
    fleetRefreshError: null,
    fleetRefreshPending: false,
    fleetStaleSince: null,
    fleetStaleReason: '',
    showHidden: readShowHidden(),
    loadFleet: async () => {
        set({ fleetLoading: true, fleetError: null });
        try {
            const q = get().showHidden ? '?include_hidden=true' : '';
            const body = await apiFetch<FleetResponse>(`/fleet${q}`);
            // Carry the server's own verdict on what it just served: the projects list
            // reads identically whether the last scan succeeded or the board is being
            // held through a failing one (INT-FC-R144), and the board says which.
            set({
                fleet: body.projects,
                freshness: body.freshness,
                fleetStaleSince: body.stale_since ?? null,
                fleetStaleReason: body.stale_reason ?? '',
            });
        } catch (error) {
            set({ fleetError: errorText(error) });
        } finally {
            set({ fleetLoading: false });
        }
    },
    refreshFleetNow: async () => {
        // The explicit rescan behind the masthead's refresh control (INT-FC-R107): POST
        // asks the server to run the background tick's refresh now, off the wire the same
        // way a co-pilot turn is (INT-FC-R55) - it hands back a turn id at once, and this
        // polls for the fleet it produced. Shares fleetLoading, so the control's glyph
        // spins for the real scan - and, unlike the ambient loads, surfaces failure: a
        // forced refresh that failed must not look like one that succeeded.
        set({ fleetLoading: true, fleetRefreshError: null, fleetRefreshPending: false });
        watchedTurn = null; // a fresh refresh supersedes any give-up watcher still out
        try {
            const q = get().showHidden ? '?include_hidden=true' : '';
            const { turn } = await apiFetch<ChatTurn>(`/fleet/refresh${q}`, undefined, 'POST');
            try {
                const body = await awaitTurn(turn, fleetResult, 'refresh');
                set({
                    fleet: body.projects,
                    fleetRefreshedAt: new Date().toLocaleTimeString(),
                    fleetError: null,
                    freshness: body.freshness,
                    fleetStaleSince: body.stale_since ?? null,
                    fleetStaleReason: body.stale_reason ?? '',
                });
                return true;
            } catch (err) {
                if (!(err instanceof TurnStillRunning)) throw err;
                // The rescan outlived this client's wait rather than failing: it is still
                // running server-side and the fleet it produces still lands in the warm
                // cache. Calling that 'failed' is the inverse of the honesty INT-FC-R107
                // asks of this control (issue #39). So: say it is still running, re-read
                // the cache for the scan that may have landed since - and KEEP WATCHING
                // the turn at the same calm cadence, so "the board will catch up" is
                // something the board actually does rather than an instruction to reload
                // (issue #46). The watch's own bound outlasts the turn store's 15min TTL,
                // whose 'unknown turn' answer already ends a watch as an error; a newer
                // refresh supersedes it via watchedTurn.
                set({ fleetRefreshPending: true });
                await get().loadFleet();
                watchedTurn = turn;
                void (async () => {
                    try {
                        const body = await awaitTurn(turn, fleetResult, 'refresh', 15 * 60_000);
                        if (watchedTurn !== turn) return;
                        set({
                            fleet: body.projects,
                            fleetRefreshedAt: new Date().toLocaleTimeString(),
                            fleetError: null,
                            freshness: body.freshness,
                            fleetStaleSince: body.stale_since ?? null,
                            fleetStaleReason: body.stale_reason ?? '',
                            fleetRefreshPending: false,
                        });
                    } catch {
                        // The turn errored, expired, or the pod restarted under it: stop
                        // claiming a catch-up and let the board stand on the warm cache.
                        if (watchedTurn !== turn) return;
                        set({ fleetRefreshPending: false });
                        void get().loadFleet();
                    }
                })();
                return false;
            }
        } catch (err) {
            set({ fleetRefreshError: errorText(err) });
            return false;
        } finally {
            set({ fleetLoading: false });
        }
    },
    setShowHidden: (v: boolean) => {
        try {
            localStorage.setItem('fc.showHidden', v ? '1' : '0');
        } catch {
            // ignore storage failures; the preference just won't persist
        }
        set({ showHidden: v });
        void get().loadFleet();
    },
    pauseApp: async (name: string) => {
        useDeliveries.setState({ actionLoading: true, actionError: null });
        try {
            await apiFetch(`/studios/apps/${encodeURIComponent(name)}/pause`, {});
            await get().loadFleet(); // reflect the new live status
        } catch (err) {
            useDeliveries.setState({ actionError: errorText(err) });
        } finally {
            useDeliveries.setState({ actionLoading: false });
        }
    },
    resumeApp: async (name: string) => {
        useDeliveries.setState({ actionLoading: true, actionError: null });
        try {
            await apiFetch(`/studios/apps/${encodeURIComponent(name)}/resume`, {});
            await get().loadFleet();
        } catch (err) {
            useDeliveries.setState({ actionError: errorText(err) });
        } finally {
            useDeliveries.setState({ actionLoading: false });
        }
    },
}));
