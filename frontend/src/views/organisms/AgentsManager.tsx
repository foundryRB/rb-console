import { useAgents } from '@/viewmodels/agents';
import { useEffect, useState } from 'react';

import type { Agent } from '@/models';
import { cn } from '@/utils';
import { useDeliveries } from '@/viewmodels/deliveries';
import { useSettings } from '@/viewmodels/settings';
import {
    callerOf,
    defaultLevel,
    levelChoices,
    levelLabel,
    levelValue,
    parseLevel,
} from '@/viewmodels/agents/agentChoices.model';
import { Button } from '@/components/ui/button';
import { AgentLevelSelect } from '@/views/molecules/AgentLevelSelect';

/** The provider registry: save a model config (name + base_url + model + credential) once,
 * then pick it where it works - a delivery's masthead (its co-pilot + workers), or the
 * Home co-pilot row above. The credential is stored server-side; the list never exposes
 * its value. A saved provider is editable in place - most often to refresh the models it
 * serves as new ones ship - and the credential is kept unless a new one is typed. With teams
 * on, each provider serves the whole install, one team, or only the person who saved it. */
export const AgentsManager: React.FC = () => {
    const { agents, agentsLoading, loadAgents, saveAgent, deleteAgent } = useAgents(),
        { actionLoading, actionError } = useDeliveries(),
        { session, loadSession } = useSettings();
    const caller = callerOf(session);
    const [editing, setEditing] = useState<Agent | null>(null);
    const [level, setLevel] = useState('');
    const [name, setName] = useState('');
    const [baseUrl, setBaseUrl] = useState('');
    const [model, setModel] = useState('');
    const [credential, setCredential] = useState('');
    const [models, setModels] = useState('');

    useEffect(() => {
        void loadAgents();
        void loadSession().catch(() => undefined);
    }, [loadAgents, loadSession]);

    const reset = () => {
        setEditing(null);
        setName('');
        setBaseUrl('');
        setModel('');
        setCredential('');
        setModels('');
        setLevel('');
    };

    // Load a saved provider into the form to edit it. Its name is its identity (the stored
    // slug), so it stays fixed while editing; the credential is left blank because the
    // stored one is kept unless a new value is typed (the backend keeps it on an empty send).
    const startEdit = (a: Agent) => {
        setEditing(a);
        setName(a.name);
        setBaseUrl(a.base_url);
        setModel(a.model);
        setModels((a.models ?? []).join('\n'));
        setCredential('');
        setLevel(levelValue(a));
    };

    const field =
        'rounded-lg border border-input bg-background px-3 py-2 text-xs outline-none focus:border-link';
    // Editing an already-credentialed provider needs no re-typed credential (the stored one is
    // kept); a fresh one still does - a provider with no credential cannot be applied.
    const keepsStoredCredential = Boolean(editing?.configured);
    const canSave = Boolean(name.trim()) && (Boolean(credential.trim()) || keepsStoredCredential);

    return (
        <div className="flex flex-col gap-3">
            <div>
                <h3 className="text-sm font-semibold tracking-tight">Saved providers</h3>
                <p className="text-xs text-muted-foreground">
                    Endpoint credentials. Save a credential once (a Claude sub or a compatible
                    base_url + key), list the models it serves, then pick the provider AND a model
                    on a project&apos;s masthead or for the Home co-pilot above - one credential,
                    many models, no retyping.{' '}
                    {actionError && <span className="text-destructive">{actionError}</span>}
                </p>
            </div>

            {agents.length > 0 && (
                <div className="flex flex-col gap-2">
                    {agents.map((a) => (
                        <div
                            key={a.name}
                            className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2"
                        >
                            <div className="min-w-0">
                                <div className="flex items-center gap-2 text-sm font-medium">
                                    {a.name}
                                    <span
                                        className={cn(
                                            'text-[10px]',
                                            a.configured
                                                ? 'text-[hsl(var(--success))]'
                                                : 'text-muted-foreground',
                                        )}
                                    >
                                        {a.configured ? '● credential set' : 'no credential'}
                                    </span>
                                    {caller.teamsEnabled && (
                                        <span className="text-[10px] text-muted-foreground">
                                            {levelLabel(a)}
                                        </span>
                                    )}
                                </div>
                                <div className="font-mono text-[11px] text-muted-foreground">
                                    {a.models?.length ? a.models.join(', ') : a.model || 'haiku'}
                                    {a.base_url ? ` · ${a.base_url}` : ' · Claude'}
                                </div>
                            </div>
                            <div className="flex shrink-0 gap-1">
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-7 px-2 text-xs"
                                    disabled={actionLoading || a.manageable === false}
                                    onClick={() => startEdit(a)}
                                >
                                    Edit
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="h-7 px-2 text-xs"
                                    disabled={actionLoading || a.manageable === false}
                                    onClick={() => void deleteAgent(a.name)}
                                >
                                    Delete
                                </Button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
            {agents.length === 0 && !agentsLoading && (
                <p className="text-xs text-muted-foreground">No saved providers yet.</p>
            )}

            <h3 className="text-sm font-semibold tracking-tight">
                {editing ? `Editing ${editing.name}` : 'Add provider'}
            </h3>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="name (e.g. My Claude sub)"
                    readOnly={Boolean(editing)}
                    className={cn(field, editing && 'cursor-not-allowed text-muted-foreground')}
                />
                <input
                    type="password"
                    value={credential}
                    onChange={(e) => setCredential(e.target.value)}
                    placeholder={
                        keepsStoredCredential
                            ? 'leave blank to keep the stored credential'
                            : 'setup-token or API key'
                    }
                    className={field}
                />
                <input
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    placeholder="base_url - blank for Claude"
                    className={field}
                />
                <input
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder="default model - blank for Haiku"
                    className={field}
                />
            </div>
            <textarea
                value={models}
                onChange={(e) => setModels(e.target.value)}
                placeholder="models this endpoint serves, one per line (optional) - picked separately per project"
                rows={3}
                className={cn(field, 'resize-y font-mono')}
            />
            {caller.teamsEnabled && (
                <AgentLevelSelect
                    choices={levelChoices(
                        caller,
                        editing?.level === 'team' ? (editing.owner ?? '') : '',
                    )}
                    value={level || defaultLevel(caller)}
                    onChange={setLevel}
                    disabled={actionLoading}
                    className="sm:max-w-xs"
                />
            )}
            <div className="flex gap-2">
                <Button
                    type="button"
                    disabled={actionLoading || !canSave}
                    className="h-8 px-3 text-xs"
                    onClick={() => {
                        const list = models
                            .split('\n')
                            .map((m) => m.trim())
                            .filter(Boolean);
                        const owner = parseLevel(level || defaultLevel(caller));
                        void saveAgent(
                            name.trim(),
                            'claude',
                            baseUrl.trim(),
                            model.trim(),
                            credential,
                            list,
                            owner.level,
                            owner.team,
                        );
                        reset();
                    }}
                >
                    {editing ? 'Save changes' : 'Save provider'}
                </Button>
                {editing && (
                    <Button
                        type="button"
                        variant="outline"
                        disabled={actionLoading}
                        className="h-8 px-3 text-xs"
                        onClick={reset}
                    >
                        Cancel
                    </Button>
                )}
            </div>
        </div>
    );
};
