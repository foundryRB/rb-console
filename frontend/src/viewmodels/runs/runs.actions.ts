import type { RunLogsResponse } from '@/models';
import { create } from 'zustand';
import type { RunGraph, RunsResponse } from '@/models';
import { apiFetch } from '@/viewmodels/requests';

import { useDeliveries } from '@/viewmodels/deliveries';
import type { RunsState } from './runs.state';
const errorText = (err: unknown): string => (err instanceof Error ? err.message : 'Unknown error');

interface RunsActions {
    loadRuns: () => Promise<void>;
    loadRunGraph: (handle: string) => Promise<void>;
    loadBandGraph: (handle: string) => Promise<void>;
    loadRunLogs: (handle: string) => Promise<void>;
    loadNodeLogs: (handle: string, nodeId: string) => Promise<void>;
    stopRun: (handle: string, terminate: boolean) => Promise<void>;
    resumeRun: (handle: string) => Promise<void>;
}
export const useRuns = create<RunsState & RunsActions>()((set, get) => ({
    runs: [],
    runsLoading: false,
    runGraph: null,
    runGraphLoading: false,
    bandGraphs: {},
    runLogs: null,
    runLogsLoading: false,
    nodeLogs: {},
    loadRuns: async () => {
        set({ runsLoading: true });
        try {
            const body = await apiFetch<RunsResponse>('/runs');
            set({ runs: body.runs });
        } catch {
            // the runs surface degrades silently to whatever it has
        } finally {
            set({ runsLoading: false });
        }
    },
    loadRunGraph: async (handle: string) => {
        // Keep the previous graph on screen while refreshing - the band is polled live and
        // must not blink empty every tick. That hold is per project: the run belongs to
        // whichever project was open when the poll fired, so a tick landing after a switch
        // is dropped rather than shown under the new project's name.
        const from = useDeliveries.getState().viewedRepo;
        set((s) => ({ runGraphLoading: s.runGraph == null }));
        try {
            const graph = await apiFetch<RunGraph>(
                `/runs/graph?handle=${encodeURIComponent(handle)}`,
            );
            if (useDeliveries.getState().viewedRepo !== from) return;
            set({ runGraph: graph });
        } catch {
            /* keep the last good graph */
        } finally {
            if (useDeliveries.getState().viewedRepo === from) set({ runGraphLoading: false });
        }
    },
    loadBandGraph: async (handle: string) => {
        // An older (superseded) run's graph for the band's accordion. Terminal runs never
        // change, so one fetch per handle serves the whole session; a failed fetch keeps
        // the row's loading placeholder and unfolding again retries.
        if (get().bandGraphs[handle]) return;
        try {
            const graph = await apiFetch<RunGraph>(
                `/runs/graph?handle=${encodeURIComponent(handle)}`,
            );
            set((s) => ({ bandGraphs: { ...s.bandGraphs, [handle]: graph } }));
        } catch {
            /* the accordion row stays on its placeholder */
        }
    },
    loadNodeLogs: async (handle: string, nodeId: string) => {
        // One node's log tail for the band's inspector (live pods first, the terminal
        // snapshot once GC'd - the backend picks). Keyed per (run, node) so switching
        // steps never shows another step's lines while the fetch is in flight.
        try {
            const body = await apiFetch<RunLogsResponse>(
                `/runs/logs?handle=${encodeURIComponent(handle)}&node=${encodeURIComponent(nodeId)}`,
            );
            set((s) => ({ nodeLogs: { ...s.nodeLogs, [`${handle}::${nodeId}`]: body.logs } }));
        } catch {
            /* keep the last tail */
        }
    },
    loadRunLogs: async (handle: string) => {
        // Keep the previous tail on screen while refreshing - the pane is polled live
        // (a follow) and must not blink empty every tick. Per project, as the graph above.
        const from = useDeliveries.getState().viewedRepo;
        set((s) => ({ runLogsLoading: s.runLogs == null }));
        try {
            const body = await apiFetch<RunLogsResponse>(
                `/runs/logs?handle=${encodeURIComponent(handle)}`,
            );
            if (useDeliveries.getState().viewedRepo !== from) return;
            set({ runLogs: body.logs });
        } catch {
            if (useDeliveries.getState().viewedRepo === from)
                set((s) => ({ runLogs: s.runLogs ?? '' }));
        } finally {
            if (useDeliveries.getState().viewedRepo === from) set({ runLogsLoading: false });
        }
    },
    stopRun: async (handle: string, terminate: boolean) => {
        useDeliveries.setState({ actionLoading: true, actionError: null });
        try {
            await apiFetch('/runs/stop', { handle, terminate });
            // The executor takes a few seconds to mark the run stopped; refresh again on
            // a short cadence so the operator SEES the stop land instead of refreshing
            // by hand (a live Terminate once looked like a no-op for exactly this).
            await Promise.all([get().loadRuns(), get().loadRunGraph(handle)]);
            for (const ms of [2500, 7000, 14000]) {
                setTimeout(() => {
                    void get().loadRuns();
                    void get().loadRunGraph(handle);
                }, ms);
            }
        } catch (err) {
            useDeliveries.setState({ actionError: errorText(err) });
        } finally {
            useDeliveries.setState({ actionLoading: false });
        }
    },
    resumeRun: async (handle: string) => {
        useDeliveries.setState({ actionLoading: true, actionError: null });
        try {
            await apiFetch('/runs/resume', { handle });
            await Promise.all([get().loadRuns(), get().loadRunGraph(handle)]);
            for (const ms of [2500, 7000]) {
                setTimeout(() => {
                    void get().loadRuns();
                    void get().loadRunGraph(handle);
                }, ms);
            }
        } catch (err) {
            useDeliveries.setState({ actionError: errorText(err) });
        } finally {
            useDeliveries.setState({ actionLoading: false });
        }
    },
}));
