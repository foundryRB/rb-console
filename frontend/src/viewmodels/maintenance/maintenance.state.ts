import type {
    MaintDriveResponse,
    MaintInboxItem,
    MaintState,
    MaintSubstance,
    Run,
    RunGraph,
} from '@/models';

export interface LastRun extends Pick<MaintDriveResponse, 'handle' | 'run_id'> {
    repo: string;
    act: string;
    target: number | null;
    mode: string;
}

/** The maintenance viewmodel: warm reads of derived state (never stored client-side
 * either), plus the operator's acts. Beside the deliveries store, same idioms - and it
 * carries its OWN run surface (list, graph, logs, controls) rather than sharing the
 * delivery cockpit's single graph slot, so a delivery run in flight and a maintenance
 * run never overwrite each other's DAG. */
export interface MaintenanceState {
    state: MaintState | null;
    stateLoading: boolean;
    stateError: string | null;

    substance: MaintSubstance | null;
    substanceLoading: boolean;

    inbox: MaintInboxItem[];
    inboxScanned: boolean;
    showHiddenIssues: boolean; // include what 'foundry-hidden' marks - a tagged ticket, and
    //                   every Inbox row of a topic-tagged repo (a persisted preference)

    actBusy: boolean;
    actError: string | null;
    /** The last drive's one-line receipt ("resolve #7 driven as m-..."), dismissible. */
    driveNote: string | null;
    /** The run that receipt names, for the Runs view to select and follow at once. */
    lastRun: LastRun | null;

    // The run surface, scoped in the pane to this repo's maint-* Workflows.
    runs: Run[];
    runGraph: RunGraph | null;
    runLogs: string | null;
    runLogsLoading: boolean;
}
