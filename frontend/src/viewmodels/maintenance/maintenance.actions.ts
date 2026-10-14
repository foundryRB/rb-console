import type {
    MaintInboxResponse,
    MaintDriveResponse,
    SwitchResponse,
    RunsResponse,
    RunLogsResponse,
} from '@/models';
import { create } from 'zustand';
import type { MaintState, MaintSubstance, RunGraph } from '@/models';
import { apiFetch } from '@/viewmodels/requests';
import type { MaintenanceState } from './maintenance.state';

interface MaintenanceActions {
    loadState: (repo: string) => Promise<void>;
    loadSubstance: (repo: string, kind: string, id?: number) => Promise<void>;
    clearSubstance: () => void;
    loadInbox: () => Promise<void>;
    setShowHiddenIssues: (v: boolean) => void;
    drive: (repo: string, act: string, target: number | null, mode: string) => Promise<void>;
    merge: (repo: string, pr: number) => Promise<void>;
    closeTicket: (repo: string, number: number) => Promise<void>;
    /** Switch an over-scope ticket to a delivery line (issue #13): hides it with foundry-hidden
     *  and returns the prepared delivery brief (the resolve worker's marked comment, or the
     *  ticket body itself) for the caller to pre-fill the Delivery form. Returns null on error
     *  (surfaced as actError). */
    switchToDelivery: (repo: string, number: number) => Promise<string | null>;
    clearAct: () => void;

    loadRuns: () => Promise<void>;
    loadRunGraph: (handle: string) => Promise<void>;
    loadRunLogs: (handle: string) => Promise<void>;
    stopRun: (handle: string, terminate: boolean) => Promise<void>;
    resumeRun: (handle: string) => Promise<void>;
}

const errorText = (e: unknown): string => (e instanceof Error ? e.message : String(e));

const readShowHiddenIssues = (): boolean => {
    try {
        return (
            typeof localStorage !== 'undefined' &&
            localStorage.getItem('fc.showHiddenIssues') === '1'
        );
    } catch {
        return false;
    }
};

export const useMaintenance = create<MaintenanceState & MaintenanceActions>()((set, get) => ({
    state: null,
    stateLoading: false,
    stateError: null,
    substance: null,
    substanceLoading: false,
    inbox: [],
    inboxScanned: false,
    showHiddenIssues: readShowHiddenIssues(),
    actBusy: false,
    actError: null,
    driveNote: null,
    lastRun: null,
    runs: [],
    runGraph: null,
    runLogs: null,
    runLogsLoading: false,

    loadState: async (repo) => {
        set({ stateLoading: true });
        try {
            // foundry-hidden tickets (a switched-to-delivery ticket, or an operator-hidden one)
            // are excluded from the pane backlog by default; the shared 'show hidden' preference
            // reveals them, same as the Fleet and the Inbox (issue #13).
            const q = get().showHiddenIssues ? '&include_hidden=true' : '';
            const state = await apiFetch<MaintState>(
                `/maintenance/state?repo=${encodeURIComponent(repo)}${q}`,
            );
            set({ state, stateError: null });
        } catch (e) {
            set({ stateError: errorText(e) });
        } finally {
            set({ stateLoading: false });
        }
    },

    loadSubstance: async (repo, kind, id) => {
        set({ substanceLoading: true });
        try {
            const q = id != null ? `&id=${id}` : '';
            const substance = await apiFetch<MaintSubstance>(
                `/maintenance/substance?repo=${encodeURIComponent(repo)}&kind=${kind}${q}`,
            );
            set({ substance });
        } catch {
            set({ substance: null });
        } finally {
            set({ substanceLoading: false });
        }
    },

    clearSubstance: () => set({ substance: null }),

    loadInbox: async () => {
        try {
            // Both hides ride this one preference: a 'foundry-hidden' ticket (issue scope) and
            // every row of a 'foundry-hidden' repo (repo scope, the Fleet's own hide on the queue).
            const q = get().showHiddenIssues ? '?include_hidden=true' : '';
            const body = await apiFetch<MaintInboxResponse>(`/maintenance/inbox${q}`);
            set({ inbox: body.items, inboxScanned: body.scanned });
        } catch {
            /* the strip renders what it can reach; an unreachable inbox stays empty */
        }
    },

    setShowHiddenIssues: (v: boolean) => {
        try {
            localStorage.setItem('fc.showHiddenIssues', v ? '1' : '0');
        } catch {
            // ignore storage failures; the preference just won't persist
        }
        set({ showHiddenIssues: v });
        void get().loadInbox();
    },

    drive: async (repo, act, target, mode) => {
        set({ actBusy: true, actError: null });
        try {
            const out = await apiFetch<MaintDriveResponse>('/maintenance/drive', {
                repo,
                act,
                target,
                mode,
                // The repo's own persisted agent backs the worker (the delivery model form);
                // the server folds it in and refuses with a clear 422 when none is set.
                config: { worker_credential: null, repo_target: repo },
            });
            set({
                driveNote: `${act}${target ? ` #${target}` : ''} driven · run ${out.run_id} (${mode})`,
                lastRun: { handle: out.handle, run_id: out.run_id, repo, act, target, mode },
            });
            // Show the run at once: the handle reads a graph the moment the CR exists, and
            // the list catches up as the executor registers the Workflow.
            if (out.handle) void get().loadRunGraph(out.handle);
            await Promise.all([get().loadState(repo), get().loadRuns()]);
            for (const ms of [2500, 7000]) setTimeout(() => void get().loadRuns(), ms);
        } catch (e) {
            set({ actError: errorText(e) });
        } finally {
            set({ actBusy: false });
        }
    },

    merge: async (repo, pr) => {
        set({ actBusy: true, actError: null });
        try {
            await apiFetch('/maintenance/merge', { repo, pr });
            set({ driveNote: `PR #${pr} merged (rebase, fast-forward)` });
            await get().loadState(repo);
            await get().loadSubstance(repo, 'pr', pr);
        } catch (e) {
            set({ actError: errorText(e) });
        } finally {
            set({ actBusy: false });
        }
    },

    closeTicket: async (repo, number) => {
        set({ actBusy: true, actError: null });
        try {
            await apiFetch('/maintenance/close', { repo, number });
            set({ driveNote: `#${number} closed (its PR had already merged)` });
            await get().loadState(repo); // the ticket leaves the backlog
        } catch (e) {
            set({ actError: errorText(e) });
        } finally {
            set({ actBusy: false });
        }
    },

    switchToDelivery: async (repo, number) => {
        set({ actBusy: true, actError: null });
        try {
            const out = await apiFetch<SwitchResponse>('/maintenance/switch-to-delivery', {
                repo,
                number,
            });
            set({ driveNote: `#${number} switched to a delivery line (hidden from the loop)` });
            // The ticket is now foundry-hidden; refresh so it leaves the backlog.
            await get().loadState(repo);
            return out.prompt;
        } catch (e) {
            set({ actError: errorText(e) });
            return null;
        } finally {
            set({ actBusy: false });
        }
    },

    clearAct: () => set({ actError: null, driveNote: null }),

    loadRuns: async () => {
        try {
            const body = await apiFetch<RunsResponse>('/runs');
            set({ runs: body.runs });
        } catch {
            // the runs surface degrades silently to whatever it has
        }
    },

    loadRunGraph: async (handle) => {
        // Keep the previous graph on screen while refreshing - the band is polled live and
        // must not blink empty every tick.
        try {
            const graph = await apiFetch<RunGraph>(
                `/runs/graph?handle=${encodeURIComponent(handle)}`,
            );
            set({ runGraph: graph });
        } catch {
            /* keep the last good graph */
        }
    },

    loadRunLogs: async (handle) => {
        set((s) => ({ runLogsLoading: s.runLogs == null }));
        try {
            const body = await apiFetch<RunLogsResponse>(
                `/runs/logs?handle=${encodeURIComponent(handle)}`,
            );
            set({ runLogs: body.logs });
        } catch {
            set((s) => ({ runLogs: s.runLogs ?? '' }));
        } finally {
            set({ runLogsLoading: false });
        }
    },

    stopRun: async (handle, terminate) => {
        set({ actBusy: true, actError: null });
        try {
            await apiFetch('/runs/stop', { handle, terminate });
            // The executor takes a few seconds to mark the run stopped; re-poll on a short
            // cadence so the operator SEES the stop land instead of refreshing by hand.
            await Promise.all([get().loadRuns(), get().loadRunGraph(handle)]);
            for (const ms of [2500, 7000, 14000]) {
                setTimeout(() => {
                    void get().loadRuns();
                    void get().loadRunGraph(handle);
                }, ms);
            }
        } catch (e) {
            set({ actError: errorText(e) });
        } finally {
            set({ actBusy: false });
        }
    },

    resumeRun: async (handle) => {
        set({ actBusy: true, actError: null });
        try {
            await apiFetch('/runs/resume', { handle });
            await Promise.all([get().loadRuns(), get().loadRunGraph(handle)]);
            for (const ms of [2500, 7000]) {
                setTimeout(() => {
                    void get().loadRuns();
                    void get().loadRunGraph(handle);
                }, ms);
            }
        } catch (e) {
            set({ actError: errorText(e) });
        } finally {
            set({ actBusy: false });
        }
    },
}));
