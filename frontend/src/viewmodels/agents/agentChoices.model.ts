import type { Agent, SessionInfo } from '@/models';

export const field =
    'rounded-lg border border-input bg-background px-3 py-2 text-xs outline-none focus:border-link';

export const picker =
    'rounded-lg border border-input bg-background px-2.5 py-1.5 text-[11px] outline-none focus:border-link';

export const CUSTOM = '__custom';

/** Who is choosing: whether the install serves several teams, whether the caller is an
 *  admin, and the teams it belongs to. An install with teams off reads as an admin. */
export interface Caller {
    teamsEnabled: boolean;
    admin: boolean;
    teams: string[];
}

export const callerOf = (session: SessionInfo | null): Caller => ({
    teamsEnabled: Boolean(session?.teams_enabled),
    admin: session?.admin ?? true,
    teams: session?.teams ?? [],
});

/** One level an agent can be saved at, as the picker offers it. */
export interface LevelChoice {
    value: string;
    label: string;
}

/** The levels a caller saves an agent at: the whole install (an admin), one of its teams,
 *  or itself alone. `team` keeps an edited agent's own team on offer. */
export const levelChoices = (caller: Caller, team = ''): LevelChoice[] => [
    ...(caller.admin ? [{ value: 'install', label: 'Everyone (install)' }] : []),
    ...Array.from(new Set([...caller.teams, team].filter(Boolean))).map((name) => ({
        value: `team:${name}`,
        label: `Team ${name}`,
    })),
    { value: 'user', label: 'Only me' },
];

export const defaultLevel = (caller: Caller): string => (caller.admin ? 'install' : 'user');

export const parseLevel = (value: string): { level: string; team: string } =>
    value.startsWith('team:')
        ? { level: 'team', team: value.slice('team:'.length) }
        : { level: value, team: '' };

export const levelValue = (agent: Agent): string =>
    agent.level === 'team' ? `team:${agent.owner ?? ''}` : (agent.level ?? 'install');

/** Who an agent serves, in words. */
export const levelLabel = (agent: Pick<Agent, 'level' | 'owner'>): string => {
    if (agent.level === 'team') return `team ${agent.owner ?? ''}`.trim();
    if (agent.level === 'user') return agent.owner ? `personal · ${agent.owner}` : 'personal';
    return 'install';
};
