import { useSettings } from '@/viewmodels/settings';
import { useFleet } from '@/viewmodels/fleet';
import { useCallback, useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';

const errorText = (e: unknown): string => (e instanceof Error ? e.message : 'Unknown error');

const field =
    'rounded-lg border border-input bg-background px-3 py-2 text-xs outline-none focus:border-link';

/**
 * Teams: each team is an identity-provider group, and each project belongs to at most one
 * team. A team's members see and act on its projects alone; a project assigned to no team is
 * visible to admins only. A line a member establishes joins their team as it opens.
 */
export const TeamsManager: React.FC = () => {
    const { teams, loadTeams, saveTeam, deleteTeam, assignProject } = useSettings();
    const { fleet, loadFleet } = useFleet();
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [name, setName] = useState('');
    const [group, setGroup] = useState('');
    const [project, setProject] = useState('');
    const [team, setTeam] = useState('');

    const load = useCallback(() => loadTeams().catch((e) => setError(errorText(e))), [loadTeams]);

    useEffect(() => {
        void load();
        void loadFleet();
    }, [load, loadFleet]);

    const act = async (effect: () => Promise<unknown>) => {
        setBusy(true);
        setError(null);
        try {
            await effect();
            await load();
        } catch (e) {
            setError(errorText(e));
        } finally {
            setBusy(false);
        }
    };

    const assigned = new Set(teams.flatMap((t) => t.repositories ?? []));
    const projects = fleet.map((p) => p.repo).sort((a, b) => a.localeCompare(b));
    const unassigned = projects.filter((repo) => !assigned.has(repo.toLowerCase()));

    return (
        <div className="flex flex-col gap-4">
            <div>
                <h3 className="text-sm font-semibold tracking-tight">Teams</h3>
                <p className="text-xs text-muted-foreground">
                    Each team is a group in the identity provider. Its members see and act on its
                    projects alone, and a line they open joins their team. Admins see every project.{' '}
                    {error && <span className="text-destructive">{error}</span>}
                </p>
            </div>

            {teams.length > 0 ? (
                <div className="flex flex-col gap-2">
                    {teams.map((t) => (
                        <div
                            key={t.name}
                            className="flex flex-col gap-1 rounded-lg border border-border bg-card px-3 py-2"
                        >
                            <div className="flex items-center justify-between gap-2">
                                <div className="min-w-0 text-sm font-medium">
                                    {t.name}
                                    <span className="ml-2 font-mono text-[11px] text-muted-foreground">
                                        group {t.group}
                                    </span>
                                </div>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-7 shrink-0 px-2 text-xs"
                                    disabled={busy}
                                    onClick={() => void act(() => deleteTeam(t.name))}
                                >
                                    Delete
                                </Button>
                            </div>
                            <div className="flex flex-wrap gap-1">
                                {(t.repositories ?? []).map((repo) => (
                                    <button
                                        key={repo}
                                        type="button"
                                        disabled={busy}
                                        title="Unassign"
                                        onClick={() => void act(() => assignProject(repo, ''))}
                                        className="rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground hover:text-foreground"
                                    >
                                        {repo} ×
                                    </button>
                                ))}
                                {(t.repositories ?? []).length === 0 && (
                                    <span className="text-[11px] text-muted-foreground">
                                        No projects yet.
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <p className="text-xs text-muted-foreground">
                    No teams yet. Until one is set up, every project is visible to admins only.
                </p>
            )}

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto]">
                <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="team name"
                    className={field}
                />
                <input
                    value={group}
                    onChange={(e) => setGroup(e.target.value)}
                    placeholder="identity-provider group"
                    className={field}
                />
                <Button
                    type="button"
                    className="h-8 px-3 text-xs"
                    disabled={busy || !name.trim() || !group.trim()}
                    onClick={() =>
                        void act(async () => {
                            await saveTeam(name.trim(), group.trim());
                            setName('');
                            setGroup('');
                        })
                    }
                >
                    Save team
                </Button>
            </div>

            {teams.length > 0 && (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto]">
                    <select
                        value={project}
                        onChange={(e) => setProject(e.target.value)}
                        className={field}
                    >
                        <option value="">Project…</option>
                        {projects.map((repo) => (
                            <option key={repo} value={repo}>
                                {repo}
                            </option>
                        ))}
                    </select>
                    <select
                        value={team}
                        onChange={(e) => setTeam(e.target.value)}
                        className={field}
                    >
                        <option value="">Team…</option>
                        {teams.map((t) => (
                            <option key={t.name} value={t.name}>
                                {t.name}
                            </option>
                        ))}
                    </select>
                    <Button
                        type="button"
                        className="h-8 px-3 text-xs"
                        disabled={busy || !project || !team}
                        onClick={() => void act(() => assignProject(project, team))}
                    >
                        Assign
                    </Button>
                </div>
            )}

            {unassigned.length > 0 && (
                <p className="text-[11px] text-muted-foreground">
                    Visible to admins only: {unassigned.join(', ')}
                </p>
            )}
        </div>
    );
};
