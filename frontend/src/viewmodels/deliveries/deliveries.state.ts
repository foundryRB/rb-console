import type {
    Action,
    DriveResult,
    FileContent,
    Overview,
    State,
    Substance,
    TreeEntry,
} from '@/models';
export interface DeliveriesState {
    viewedRepo: string | null;
    deliveries: State[];
    listLoading: boolean;
    listError: string | null;
    current: State | null;
    currentLoading: boolean;
    currentError: string | null;
    action: Action | null;
    actionLoading: boolean;
    actionError: string | null;
    driveResult: DriveResult | null;
    overview: Overview | null;
    overviewLoading: boolean;
    overviewError: string | null;
    substance: Substance | null;
    substanceLoading: boolean;
    substanceError: string | null;
    record: FileContent | null;
    recordLoading: boolean;
    recordError: string | null;
    tree: TreeEntry[];
    treeLoading: boolean;
    treeError: string | null;
    openFile: FileContent | null;
    fileLoading: boolean;
    fileError: string | null;
    references: string[];
}
