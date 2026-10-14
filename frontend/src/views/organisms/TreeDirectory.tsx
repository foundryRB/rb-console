import { cn } from '@/utils';

import { type DirNode } from '@/viewmodels/worktree/worktree.model';

export const TreeDirectory: React.FC<{
    node: DirNode;
    depth: number;
    collapsed: Set<string>;
    onToggleDir: (path: string) => void;
    openPath: string | null;
    references: string[];
    onOpen: (path: string) => void;
    onRef: (path: string) => void;
}> = ({ node, depth, collapsed, onToggleDir, openPath, references, onOpen, onRef }) => (
    <>
        {node.dirs.map((d) => {
            const closed = collapsed.has(d.path);
            return (
                <div key={d.path}>
                    <button
                        type="button"
                        onClick={() => onToggleDir(d.path)}
                        className="flex w-full items-center gap-1.5 px-2 py-1 text-left font-mono text-[11px] text-muted-foreground hover:text-foreground"
                        style={{ paddingLeft: 8 + depth * 14 }}
                    >
                        <span className="w-3 text-[9px]">{closed ? '▸' : '▾'}</span>
                        <span className="font-semibold">{d.name}/</span>
                    </button>
                    {!closed && (
                        <TreeDirectory
                            node={d}
                            depth={depth + 1}
                            collapsed={collapsed}
                            onToggleDir={onToggleDir}
                            openPath={openPath}
                            references={references}
                            onOpen={onOpen}
                            onRef={onRef}
                        />
                    )}
                </div>
            );
        })}
        {node.files.map((f) => (
            <div
                key={f.path}
                className="flex items-center gap-1.5 pr-1"
                style={{ paddingLeft: 8 + depth * 14 + 14 }}
            >
                <input
                    type="checkbox"
                    checked={references.includes(f.path)}
                    onChange={() => onRef(f.path)}
                    title="reference this file in the co-pilot chat"
                    className="accent-primary"
                />
                <button
                    type="button"
                    onClick={() => onOpen(f.path)}
                    title={f.path}
                    className={cn(
                        'min-w-0 flex-1 truncate rounded px-1 py-1 text-left font-mono text-[11px] hover:text-link',
                        openPath === f.path ? 'text-link' : 'text-muted-foreground',
                    )}
                >
                    {f.path.split('/').pop()}
                </button>
            </div>
        ))}
    </>
);
