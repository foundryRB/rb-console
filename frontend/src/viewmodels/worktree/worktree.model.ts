import type { TreeEntry } from '@/models';

export const LANG: Record<string, string> = {
    md: 'markdown',
    json: 'json',
    yaml: 'yaml',
    yml: 'yaml',
    py: 'python',
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    html: 'html',
    css: 'css',
    sh: 'shell',
    toml: 'ini',
    txt: 'plaintext',
};

export const langOf = (path: string): string =>
    LANG[path.split('.').pop()?.toLowerCase() ?? ''] ?? 'plaintext';

export interface DirNode {
    name: string;
    path: string;
    dirs: DirNode[];
    files: TreeEntry[];
}

export function buildTree(files: TreeEntry[]): DirNode {
    const root: DirNode = { name: '', path: '', dirs: [], files: [] };
    const byPath = new Map<string, DirNode>([['', root]]);
    for (const f of [...files].sort((a, b) => a.path.localeCompare(b.path))) {
        const parts = f.path.split('/');
        let parent = root;
        for (let i = 0; i < parts.length - 1; i++) {
            const dirPath = parts.slice(0, i + 1).join('/');
            let node = byPath.get(dirPath);
            if (!node) {
                node = { name: parts[i], path: dirPath, dirs: [], files: [] };
                byPath.set(dirPath, node);
                parent.dirs.push(node);
            }
            parent = node;
        }
        parent.files.push(f);
    }
    return root;
}
