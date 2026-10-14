import type {
    PromotionState,
    PromotionOptions,
    TargetDeclaredResponse,
    PromotionDriveResponse,
} from '@/models';

export interface PromotionViewState {
    state: PromotionState | null;
    loading: boolean;
    error: string | null;

    options: PromotionOptions | null;

    declaring: boolean;
    declareError: string | null;
    /** The receipt of the last declaration: the target's name and its commit. */
    declared: Pick<TargetDeclaredResponse, 'target' | 'commit'> | null;

    /** The target a drive is in flight for, so only its own row reads busy. */
    driving: string | null;
    driveRepo: string | null;
    /** Why the last drive was refused, and WHICH target it was refused for - a Managed app,
     * an undeclared target, a shut door, no release. Every one of them is something the
     * operator can act on, which is why the backend raises them before a pod exists. The
     * target rides along because the pane shows several rows: an error carrying only a
     * message would render under every one of them at once. */
    driveError: { repo: string; target: string; message: string } | null;
    /** The receipt of the last drive: the run, and what it carries. */
    drove: PromotionDriveResponse | null;
    droveRepo: string | null;
}
