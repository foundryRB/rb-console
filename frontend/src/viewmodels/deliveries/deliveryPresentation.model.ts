import type { TreeEntry } from '@/models';

export const runEnded = (p?: string | null): boolean =>
    p === 'Succeeded' || p === 'Failed' || p === 'Error' || p === 'Stopped';

export type BuildTab = 'worktree' | 'live' | 'evidence';

export const EMPTY_TREE: TreeEntry[] = [];

export const EMPTY_REFS: string[] = [];
