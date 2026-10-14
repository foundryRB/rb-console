import { useEffect, useRef, useState } from 'react';

import { triggerCls, panelCls } from '@/viewmodels/fleet/fleet.model';

export const FilterDropdown: React.FC<{
    ariaLabel: string;
    summary: string;
    /** Dismiss the panel the moment an option changes. Right for a single choice (picking a sort
     * is terminal); wrong for a set the operator assembles a click at a time (the filters). */
    closeOnPick?: boolean;
    children: React.ReactNode;
}> = ({ ariaLabel, summary, closeOnPick, children }) => {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement>(null);
    const triggerRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        if (!open) return;
        const onDoc = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener('mousedown', onDoc);
        return () => document.removeEventListener('mousedown', onDoc);
    }, [open]);

    const close = () => {
        setOpen(false);
        triggerRef.current?.focus();
    };

    const onKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Escape') {
            e.stopPropagation();
            close();
        }
    };

    return (
        <div ref={ref} className="relative" onKeyDown={onKeyDown}>
            <button
                ref={triggerRef}
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-label={ariaLabel}
                aria-expanded={open}
                className={triggerCls}
            >
                <span className="truncate">{summary}</span>
                <span aria-hidden="true" className="shrink-0 text-faint">
                    ▾
                </span>
            </button>
            {open && (
                // React's synthetic change event bubbles, so one handler here catches a pick from
                // any option the panel holds.
                <div className={panelCls} onChange={closeOnPick ? close : undefined}>
                    {children}
                </div>
            )}
        </div>
    );
};
