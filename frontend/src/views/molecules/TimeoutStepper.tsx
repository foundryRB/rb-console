import { useState } from 'react';

export const TimeoutStepper: React.FC<{
    hours: number;
    disabled?: boolean;
    onCommit: (hours: number) => void;
}> = ({ hours, disabled, onCommit }) => {
    // Guard a missing / NaN config value (a delivered or maintenance-only repo, or a backend
    // that predates the timeout field) to a sane 1h, so the field is never blank and +/- never
    // compute NaN and POST a null the backend rejects (the reported "[object Object]").
    const safe = Number.isFinite(hours) && hours > 0 ? hours : 1;
    const [val, setVal] = useState(String(safe));
    const commit = (raw: string) => {
        const h = Number(raw);
        if (Number.isFinite(h) && h > 0 && h !== safe) onCommit(h);
        else setVal(String(safe)); // reject a blank/invalid entry back to the live value
    };
    const bump = (delta: number) => {
        const cur = Number(val);
        const base = Number.isFinite(cur) && cur > 0 ? cur : safe;
        const next = Math.max(0.25, Math.round((base + delta) * 4) / 4);
        if (!Number.isFinite(next)) return; // never emit a bad value
        setVal(String(next));
        if (next !== safe) onCommit(next);
    };
    const step =
        'grid h-8 w-7 place-items-center text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40';
    return (
        <div className="inline-flex items-center overflow-hidden rounded-lg border border-input bg-background">
            <button
                type="button"
                disabled={disabled}
                onClick={() => bump(-0.25)}
                className={step}
                aria-label="Less time"
                title="−15 min"
            >
                −
            </button>
            <input
                type="number"
                inputMode="decimal"
                min={0.25}
                step={0.25}
                value={val}
                disabled={disabled}
                onChange={(e) => setVal(e.target.value)}
                onBlur={(e) => commit(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                }}
                className="w-10 border-x border-input bg-transparent py-1.5 text-center text-xs outline-none focus:bg-muted/40 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                title="The worker's per-phase wall-clock budget in hours. A from-scratch build+ship needs hours; the default is 1."
            />
            <button
                type="button"
                disabled={disabled}
                onClick={() => bump(0.25)}
                className={step}
                aria-label="More time"
                title="+15 min"
            >
                +
            </button>
            <span className="select-none px-2 text-[11px] text-muted-foreground">h</span>
        </div>
    );
};
