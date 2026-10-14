import { useMemo, useState } from 'react';

import type { Substance } from '@/models';
import { cn } from '@/utils';
import { selectDesignPreview } from '@/viewmodels/design/design.model';
import { RecordDocument } from '@/views/organisms/RecordDocument';

/** Design, rendered natively: the protopane prototype's real screens, rebuilt from the
 * east-west export (theme CSS + screen bodies) in a sandboxed frame - no OIDC iframe, no
 * cookies. Falls back to the committed design record (the locked identity) when no
 * prototype exists yet. */
export const DesignPane: React.FC<{ substance: Substance | null; record: string | null }> = ({
    substance,
    record,
}) => {
    const [screen, setScreen] = useState(0);
    const { screens, active, srcdoc } = useMemo(
        () => selectDesignPreview(substance, screen),
        [substance, screen],
    );

    if (screens.length === 0) {
        return record ? (
            <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-well/10 p-4">
                <p className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                    design.md - the locked identity (no prototype in protopane yet)
                </p>
                <RecordDocument text={record} />
            </div>
        ) : (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
                <span className="grid h-10 w-10 place-items-center rounded-xl border border-dashed border-border text-muted-foreground">
                    ◇
                </span>
                <p className="max-w-md text-xs text-muted-foreground">
                    No prototype for this delivery yet - the real screens render here, natively,
                    once design runs.
                </p>
            </div>
        );
    }

    return (
        <div className="flex min-h-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
                {screens.map((s, i) => (
                    <button
                        key={s.slug || i}
                        type="button"
                        onClick={() => setScreen(i)}
                        className={cn(
                            'rounded-full border px-2.5 py-1 font-mono text-[11px] transition-colors',
                            i === screen
                                ? 'border-link/60 bg-primary/10 text-foreground'
                                : 'border-border text-muted-foreground hover:text-foreground',
                        )}
                    >
                        {s.name || s.slug}
                    </button>
                ))}
                <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                    the real prototype · rendered from the export
                </span>
            </div>
            <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-white">
                {/* allow-scripts: the Tailwind Play runtime IS the stylist; no same-origin,
                    so the frame stays isolated from the console. */}
                <iframe
                    title={`prototype · ${active?.name}`}
                    sandbox="allow-scripts"
                    srcDoc={srcdoc}
                    className="h-full w-full"
                />
            </div>
        </div>
    );
};
