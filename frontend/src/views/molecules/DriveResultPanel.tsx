import type { DriveResult } from '@/models';

/**
 * The outcome of a drive: which run was compiled, whether the executor accepted it,
 * and the worker steps the workflow expands to. When the executor drive is off the
 * workflow is compiled but not submitted (handle is null); say so plainly rather than
 * implying work is running.
 */
export const DriveResultPanel: React.FC<{ result: DriveResult }> = ({ result }) => (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs">
        <div className="flex items-center justify-between gap-3">
            <span className="font-mono text-foreground">run {result.run_id}</span>
            <span className={result.handle ? 'text-link' : 'text-muted-foreground'}>
                {result.handle ? `submitted (${result.handle})` : 'compiled; executor drive is off'}
            </span>
        </div>
        {result.steps.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
                {result.steps.map((step) => (
                    <span
                        key={step}
                        className="rounded bg-background px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
                    >
                        {step}
                    </span>
                ))}
            </div>
        )}
    </div>
);
