import { lazy } from 'react';
import { Suspense, useMemo, useRef, useState } from 'react';
import type { FileContent, TreeEntry } from '@/models';

import { TreeDirectory } from '@/views/organisms/TreeDirectory';
import { useAppearance } from '@/viewmodels/appearance';
import { langOf, buildTree } from '@/viewmodels/worktree/worktree.model';

export const WorktreePanel: React.FC<{
    repo: string;
    tree: TreeEntry[];
    treeLoading: boolean;
    onLoadTree: (repo: string) => void;
    openFile: FileContent | null;
    fileLoading: boolean;
    error?: string | null;
    onOpenFile: (repo: string, path: string) => void;
    references: string[];
    onToggleReference: (path: string) => void;
}> = ({
    repo,
    tree,
    treeLoading,
    onLoadTree,
    openFile,
    fileLoading,
    error,
    onOpenFile,
    references,
    onToggleReference,
}) => {
    const { resolved } = useAppearance();
    const [requestedRepo, setRequestedRepo] = useState<string | null>(null);
    const requestTree = () => {
        setRequestedRepo(repo);
        onLoadTree(repo);
    };

    const files = useMemo(() => tree.filter((e) => e.type === 'blob'), [tree]);
    const root = useMemo(() => buildTree(files), [files]);
    const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
    const toggleDir = (p: string) =>
        setCollapsed((s) => {
            const n = new Set(s);
            if (n.has(p)) n.delete(p);
            else n.add(p);
            return n;
        });

    // Point the co-pilot at EXACT lines: select in Monaco, click, and the reference rides
    // as "path#L10-L20" - the backend slices just those lines into the chat context.
    const editorRef = useRef<{
        getSelection: () => {
            startLineNumber: number;
            endLineNumber: number;
            isEmpty: () => boolean;
        } | null;
    } | null>(null);
    const referenceSelection = () => {
        if (!openFile) return;
        const sel = editorRef.current?.getSelection?.();
        if (sel && !sel.isEmpty()) {
            const a = Math.min(sel.startLineNumber, sel.endLineNumber);
            const b = Math.max(sel.startLineNumber, sel.endLineNumber);
            onToggleReference(`${openFile.path}#L${a}-L${b}`);
        } else {
            onToggleReference(openFile.path);
        }
    };

    return (
        <div className="flex h-full min-h-[420px] flex-col gap-3 lg:flex-row">
            <div className="max-h-52 w-full shrink-0 overflow-auto rounded-lg border border-border bg-well/20 py-1 lg:max-h-none lg:w-64">
                <button
                    type="button"
                    onClick={requestTree}
                    disabled={treeLoading}
                    className="px-2 py-1 text-xs text-link"
                >
                    {requestedRepo === repo ? 'Refresh file tree' : 'Load file tree'}
                </button>
                {error && (
                    <p role="status" className="p-2 text-xs text-destructive">
                        Read unavailable: {error}
                    </p>
                )}
                {treeLoading && <p className="p-2 text-xs text-muted-foreground">Loading…</p>}
                {!treeLoading && requestedRepo === repo && files.length === 0 && (
                    <p className="p-2 text-xs text-muted-foreground">Nothing committed yet.</p>
                )}
                <TreeDirectory
                    node={root}
                    depth={0}
                    collapsed={collapsed}
                    onToggleDir={toggleDir}
                    openPath={openFile?.path ?? null}
                    references={references}
                    onOpen={(p) => onOpenFile(repo, p)}
                    onRef={onToggleReference}
                />
            </div>
            <div className="min-h-[280px] min-w-0 flex-1 overflow-hidden rounded-lg border border-border bg-editor lg:min-h-0">
                {fileLoading ? (
                    <p className="p-3 text-xs text-muted-foreground">Loading…</p>
                ) : openFile ? (
                    <div className="relative h-full">
                        <button
                            type="button"
                            onClick={referenceSelection}
                            title="Reference the selected lines (or the whole file) in the co-pilot chat"
                            className="absolute right-3 top-2 z-10 rounded-md border border-border bg-card/90 px-2 py-1 font-mono text-[10px] font-semibold text-muted-foreground hover:border-link/50 hover:text-link"
                        >
                            ⎘ selection → co-pilot
                        </button>
                        <Suspense
                            fallback={
                                <p className="p-3 text-xs text-muted-foreground">
                                    Loading the editor…
                                </p>
                            }
                        >
                            <MonacoEditor
                                height="100%"
                                language={langOf(openFile.path)}
                                value={openFile.content}
                                theme={resolved === 'dark' ? 'vs-dark' : 'light'}
                                onMount={(editor) => {
                                    editorRef.current =
                                        editor as unknown as typeof editorRef.current;
                                }}
                                options={{
                                    readOnly: true,
                                    minimap: { enabled: false },
                                    fontSize: 12.5,
                                    lineNumbers: 'on',
                                    scrollBeyondLastLine: false,
                                    wordWrap: 'on',
                                    automaticLayout: true,
                                    padding: { top: 10 },
                                }}
                            />
                        </Suspense>
                    </div>
                ) : (
                    <p className="p-3 text-xs text-muted-foreground">
                        Select a file to view it. Check a box to send it to the co-pilot as a
                        reference.
                    </p>
                )}
            </div>
        </div>
    );
};

const MonacoEditor = lazy(async () => {
    await import('@/monaco');
    return import('@monaco-editor/react');
});
