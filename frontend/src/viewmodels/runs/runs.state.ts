import type { Run, RunGraph } from '@/models';
export interface RunsState {
    runs: Run[];
    runsLoading: boolean;
    runGraph: RunGraph | null;
    runGraphLoading: boolean;
    runLogs: string | null;
    runLogsLoading: boolean;
    bandGraphs: Record<string, RunGraph>;
    nodeLogs: Record<string, string>;
}
