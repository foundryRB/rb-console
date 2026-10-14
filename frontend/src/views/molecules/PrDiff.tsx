import { lazy } from 'react';

import { Suspense } from 'react';
import type { MaintFile } from '@/models';

import { patchSides } from '@/viewmodels/maintenance/maintenancePresentation.model';

/** `dark` follows the install's appearance; the binding organism reads it. */
export const PrDiff: React.FC<{ files: MaintFile[]; dark?: boolean }> = ({
    files,
    dark = true,
}) => (
    <div className="flex flex-col gap-2">
        {files.map((f) => (
            <details key={f.filename} className="rounded-lg border border-border bg-well/20">
                <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2 font-mono text-[11px]">
                    <span className="font-semibold text-foreground">{f.filename}</span>
                    <span className="text-muted-foreground">{f.status}</span>
                    <span className="ml-auto text-[hsl(var(--success))]">+{f.additions}</span>
                    <span className="text-destructive">-{f.deletions}</span>
                </summary>
                {f.patch ? (
                    <div className="h-64 border-t border-border">
                        <Suspense
                            fallback={
                                <p className="p-3 text-xs text-muted-foreground">Loading diff…</p>
                            }
                        >
                            <MonacoDiff
                                theme={dark ? 'vs-dark' : 'light'}
                                original={patchSides(f.patch).original}
                                modified={patchSides(f.patch).modified}
                                options={{
                                    readOnly: true,
                                    renderSideBySide: false,
                                    minimap: { enabled: false },
                                    fontSize: 12,
                                    scrollBeyondLastLine: false,
                                }}
                            />
                        </Suspense>
                    </div>
                ) : (
                    <p className="border-t border-border px-3 py-2 text-[11px] text-muted-foreground">
                        No patch text (binary or too large) - open it on GitHub.
                    </p>
                )}
            </details>
        ))}
    </div>
);

const MonacoDiff = lazy(async () => {
    await import('@/monaco');
    return { default: (await import('@monaco-editor/react')).DiffEditor };
});
