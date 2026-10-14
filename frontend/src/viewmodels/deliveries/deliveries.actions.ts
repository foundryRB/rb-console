import type { TreeResponse } from '@/models';
import { create } from 'zustand';
import type {
    Action,
    DeliveriesResponse,
    DriveResult,
    EstablishIn,
    FileContent,
    Overview,
    Run,
    State,
    TargetIn,
    Substance,
} from '@/models';
import { apiFetch } from '@/viewmodels/requests';

import { useFleet } from '@/viewmodels/fleet';

import { useRuns } from '@/viewmodels/runs';

import type { DeliveriesState } from './deliveries.state';
const errorText = (err: unknown): string => (err instanceof Error ? err.message : 'Unknown error');
const newestRunFor = (repo: string, runs: Run[]): Run | undefined =>
    runs.find((run) => run.repo === repo && run.kind === 'delivery');
/** The cadence after an act that starts or releases a run: the executor lists the run, or
 * spins its next worker up, a few seconds after the act answers (INT-FC-R191). */
const FOLLOW_UP_MS = [2500, 7000, 14000];

interface DeliveriesActions {
    loadDeliveries: () => Promise<void>;
    loadState: (repo: string) => Promise<void>;
    loadOverview: (repo: string) => Promise<void>;
    loadSubstance: (repo: string, phase: string) => Promise<void>;
    loadRecord: (repo: string, record: string | null) => Promise<void>;
    establish: (input: EstablishIn) => Promise<State | null>;
    planNext: (input: TargetIn) => Promise<void>;
    start: (input: TargetIn) => Promise<void>;
    drive: (input: TargetIn) => Promise<void>;
    sign: (repo: string) => Promise<void>;
    followRun: (repo: string) => void;
    setDeliveryConfig: (target: string, mode: string) => Promise<void>;
    setDeliveryModel: (
        target: string,
        provider: string,
        base_url: string,
        model: string,
        credential: string,
    ) => Promise<void>;
    setDeliveryTimeout: (target: string, hours: number) => Promise<void>;
    reopen: (target: string, phase: string) => Promise<void>;
    closeLine: (target: string) => Promise<void>;
    loadTree: (repo: string) => Promise<void>;
    openRepoFile: (repo: string, path: string) => Promise<void>;
    toggleReference: (path: string) => void;
    openProject: (repo: string) => void;
    clearAction: () => void;
}
export const useDeliveries = create<DeliveriesState & DeliveriesActions>()((set, get) => ({
    viewedRepo: null,
    deliveries: [],
    listLoading: false,
    listError: null,
    current: null,
    currentLoading: false,
    currentError: null,
    action: null,
    actionLoading: false,
    actionError: null,
    driveResult: null,
    tree: [],
    treeLoading: false,
    treeError: null,
    openFile: null,
    fileLoading: false,
    fileError: null,
    references: [],
    overview: null,
    overviewLoading: false,
    overviewError: null,
    substance: null,
    substanceLoading: false,
    substanceError: null,
    record: null,
    recordLoading: false,
    recordError: null,
    loadDeliveries: async () => {
        set({ listLoading: true, listError: null });
        try {
            const body = await apiFetch<DeliveriesResponse>('/deliveries');
            set({ deliveries: body.deliveries });
        } catch (err) {
            set({ listError: errorText(err) });
        } finally {
            set({ listLoading: false });
        }
    },
    loadState: async (repo: string) => {
        set({ currentLoading: true, currentError: null });
        try {
            const state = await apiFetch<State>(
                `/deliveries/state?repo=${encodeURIComponent(repo)}`,
            );
            set({ current: state });
        } catch (err) {
            set({ currentError: errorText(err) });
        } finally {
            set({ currentLoading: false });
        }
    },
    loadOverview: async (repo: string) => {
        set({ overviewLoading: true, overviewError: null });
        try {
            const overview = await apiFetch<Overview>(
                `/deliveries/overview?repo=${encodeURIComponent(repo)}`,
            );
            // A response for a project the operator has already left is not ours to paint.
            // Without this, opening A then B while A is slow lets A's line land over B's.
            if (get().viewedRepo !== repo) return;
            set({ overview, current: overview });
        } catch (err) {
            if (get().viewedRepo !== repo) return;
            set({ overviewError: errorText(err) });
        } finally {
            if (get().viewedRepo === repo) set({ overviewLoading: false });
        }
    },
    loadSubstance: async (repo: string, phase: string) => {
        if (get().viewedRepo !== repo) return;
        set({ substance: null, substanceLoading: true, substanceError: null });
        try {
            const substance = await apiFetch<Substance>(
                `/deliveries/substance?repo=${encodeURIComponent(repo)}&phase=${encodeURIComponent(phase)}`,
            );
            if (get().viewedRepo === repo) set({ substance });
        } catch (error) {
            if (get().viewedRepo === repo) set({ substanceError: errorText(error) });
        } finally {
            if (get().viewedRepo === repo) set({ substanceLoading: false });
        }
    },
    loadRecord: async (repo: string, record: string | null) => {
        if (get().viewedRepo !== repo) return;
        set({ record: null, recordError: null, recordLoading: Boolean(record) });
        if (!record) return;
        try {
            const file = await apiFetch<FileContent>(
                `/deliveries/file?repo=${encodeURIComponent(repo)}&path=${encodeURIComponent(`.delivery/${record}`)}`,
            );
            if (get().viewedRepo === repo) set({ record: file.content ? file : null });
        } catch (error) {
            if (get().viewedRepo === repo) set({ recordError: errorText(error) });
        } finally {
            if (get().viewedRepo === repo) set({ recordLoading: false });
        }
    },
    establish: async (input: EstablishIn) => {
        set({ actionLoading: true, actionError: null });
        try {
            return await apiFetch<State>('/establish', input);
        } catch (err) {
            set({ actionError: errorText(err) });
            return null;
        } finally {
            set({ actionLoading: false });
        }
    },
    planNext: async (input: TargetIn) => {
        set({ actionLoading: true, actionError: null });
        try {
            const action = await apiFetch<Action>('/deliveries/plan', input);
            set({ action, current: action.state });
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    start: async (input: TargetIn) => {
        set({ actionLoading: true, actionError: null });
        try {
            const action = await apiFetch<Action>('/start', input);
            set({ action });
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    drive: async (input: TargetIn) => {
        set({ actionLoading: true, actionError: null });
        try {
            const result = await apiFetch<DriveResult>('/deliveries/drive', input);
            set({ driveResult: result, current: result.state });
            // The live poll starts only once the cockpit knows a run, and the executor lists
            // a new one a few seconds after the drive answers - so follow it up, as a sign
            // does, rather than leave a first empty read to stand until a reload.
            get().followRun(input.target);
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    sign: async (repo: string) => {
        set({ actionLoading: true, actionError: null });
        try {
            const state = await apiFetch<State>('/deliveries/sign', {
                target: repo,
                config: { worker_credential: null, repo_target: repo },
            });
            set({ current: state });
            // Signing releases the parked gate server-side (_release_parked_run resumes the
            // suspended run), so the next phase starts on its own. Re-poll the line and the
            // run graph on a short cadence so that resumed phase SHOWS without a manual
            // Resume/Drive - the executor takes a few seconds to spin the next worker up.
            get().followRun(repo);
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    followRun: (repo: string) => {
        const refresh = async () => {
            // Only while this line is still the one on screen: a tick that fires after the
            // operator opened another line must not land this line's run in that one's view.
            if (get().viewedRepo !== repo) return;
            await Promise.all([useRuns.getState().loadRuns(), get().loadOverview(repo)]);
            if (get().viewedRepo !== repo) return;
            const active = newestRunFor(repo, useRuns.getState().runs);
            if (active?.handle) await useRuns.getState().loadRunGraph(active.handle);
        };
        void refresh();
        for (const ms of FOLLOW_UP_MS) setTimeout(() => void refresh(), ms);
    },
    setDeliveryConfig: async (target: string, mode: string) => {
        set({ actionLoading: true, actionError: null });
        try {
            await apiFetch('/deliveries/config', { target, mode });
            await get().loadOverview(target); // the delivery config is embedded in the overview
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    setDeliveryModel: async (target, provider, base_url, model, credential) => {
        set({ actionLoading: true, actionError: null });
        try {
            await apiFetch('/deliveries/model', { target, provider, base_url, model, credential });
            await get().loadOverview(target); // the model choice is embedded in the overview config
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    setDeliveryTimeout: async (target, hours) => {
        set({ actionLoading: true, actionError: null });
        try {
            await apiFetch('/deliveries/timeout', { target, timeout_hours: hours });
            await get().loadOverview(target); // the timeout is embedded in the overview config
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    reopen: async (target: string, phase: string) => {
        set({ actionLoading: true, actionError: null });
        try {
            await apiFetch('/deliveries/reopen', { target, phase });
            await get().loadOverview(target); // re-derive the line: the pointer moves back
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    closeLine: async (target: string) => {
        set({ actionLoading: true, actionError: null });
        try {
            await apiFetch('/deliveries/close', { target });
            // The scratch is gone, so the repo now reads as a live project with no open line:
            // re-derive the overview (it flips to that view) and refresh the fleet board.
            await Promise.all([get().loadOverview(target), useFleet.getState().loadFleet()]);
        } catch (err) {
            set({ actionError: errorText(err) });
        } finally {
            set({ actionLoading: false });
        }
    },
    loadTree: async (repo: string) => {
        if (get().viewedRepo !== repo) return;
        set({ treeLoading: true, treeError: null });
        try {
            const body = await apiFetch<TreeResponse>(
                `/deliveries/tree?repo=${encodeURIComponent(repo)}`,
            );
            if (get().viewedRepo === repo) set({ tree: body.tree });
        } catch (error) {
            if (get().viewedRepo === repo) set({ treeError: errorText(error) });
        } finally {
            if (get().viewedRepo === repo) set({ treeLoading: false });
        }
    },
    openRepoFile: async (repo: string, path: string) => {
        if (get().viewedRepo !== repo) return;
        set({ fileLoading: true, openFile: null, fileError: null });
        try {
            const file = await apiFetch<FileContent>(
                `/deliveries/file?repo=${encodeURIComponent(repo)}&path=${encodeURIComponent(path)}`,
            );
            if (get().viewedRepo === repo) set({ openFile: file });
        } catch (error) {
            if (get().viewedRepo === repo) set({ fileError: errorText(error) });
        } finally {
            if (get().viewedRepo === repo) set({ fileLoading: false });
        }
    },
    toggleReference: (path: string) =>
        set((s) => ({
            references: s.references.includes(path)
                ? s.references.filter((p) => p !== path)
                : [...s.references, path],
        })),
    openProject: (repo: string) => {
        useRuns.setState({
            runGraph: null,
            runGraphLoading: false,
            runLogs: null,
            runLogsLoading: false,
        });
        set({
            viewedRepo: repo,
            overview: null,
            overviewError: null,
            overviewLoading: true,
            current: null,
            currentError: null,
            substance: null,
            substanceLoading: false,
            substanceError: null,
            record: null,
            recordLoading: false,
            recordError: null,
            tree: [],
            treeLoading: false,
            treeError: null,
            openFile: null,
            fileLoading: false,
            fileError: null,
            references: [],
            action: null,
            actionError: null,
            driveResult: null,
        });
    },
    clearAction: () => set({ action: null, actionError: null, driveResult: null }),
}));
