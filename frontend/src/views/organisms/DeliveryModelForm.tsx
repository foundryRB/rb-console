import { useState } from 'react';
import type { Agent, DeliveryConfig } from '@/models';
import { cn } from '@/utils';
import { Button } from '@/components/ui/button';
import { TimeoutStepper } from '@/views/molecules/TimeoutStepper';
import { AgentLevelSelect } from '@/views/molecules/AgentLevelSelect';
import {
    field,
    picker,
    CUSTOM,
    defaultLevel,
    levelChoices,
    levelLabel,
    parseLevel,
    type Caller,
} from '@/viewmodels/agents/agentChoices.model';

export const DeliveryModelForm: React.FC<{
    config: DeliveryConfig;
    agents: Agent[];
    caller: Caller;
    disabled?: boolean;
    error?: string | null;
    onApplyAgent: (name: string, model?: string) => void;
    onSaveAgent: (
        name: string,
        baseUrl: string,
        model: string,
        credential: string,
        level: string,
        team: string,
    ) => void;
    onSetTimeout: (hours: number) => void;
}> = ({
    config,
    agents: listed,
    caller,
    disabled,
    error,
    onApplyAgent,
    onSaveAgent,
    onSetTimeout,
}) => {
    // The picker offers what the caller may apply: the install's agents, its teams' and its own.
    const agents = listed.filter((a) => a.usable !== false);
    const [adding, setAdding] = useState(false);
    const [name, setName] = useState('');
    const [baseUrl, setBaseUrl] = useState('');
    const [model, setModel] = useState('');
    const [credential, setCredential] = useState('');
    const [customOpen, setCustomOpen] = useState(false);
    const [customModel, setCustomModel] = useState('');
    const [level, setLevel] = useState('');

    // Show what actually backs this target. A target credentialed before providers carried names
    // (or via a direct model set) has no provider to select - say so rather than lying with a
    // "Select a provider…" placeholder over a live credential.
    const known = Boolean(config.agent) && agents.some((a) => a.name === config.agent);
    const selected = known ? config.agent : config.credentialed ? '__current' : '';
    // A line on someone else's agent shows whose it is, rather than an unnamed credential.
    const foreign = Boolean(config.agent) && !known;
    const activeAgent = agents.find((a) => a.name === config.agent) ?? null;
    // The models the selected agent serves, always including the one currently in use so it shows.
    const modelOptions = Array.from(
        new Set([...(activeAgent?.models ?? []), config.model].filter(Boolean)),
    );

    return (
        <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Provider
                </span>
                <select
                    disabled={disabled}
                    value={selected}
                    onChange={(e) => {
                        const v = e.target.value;
                        if (v === '__new') {
                            e.currentTarget.value = selected; // keep showing the current provider
                            setAdding(true);
                        } else if (v && v !== '__current') {
                            // Apply the picked provider; keep the current model if it serves it, else
                            // fall back to the provider's default (undefined lets the backend choose).
                            const a = agents.find((x) => x.name === v);
                            const keep = a?.models?.includes(config.model)
                                ? config.model
                                : undefined;
                            onApplyAgent(v, keep);
                        }
                    }}
                    // Capped: a native select is as wide as its longest option, so the longest
                    // saved provider name set the masthead's width. The open list still shows it.
                    className={cn(picker, 'max-w-[8rem]')}
                    title="Which saved provider (endpoint + credential) powers this project's worker and co-pilot"
                >
                    {!config.credentialed && (
                        <option value="" disabled>
                            Select a provider…
                        </option>
                    )}
                    {!known && config.credentialed && (
                        <option value="__current">
                            {foreign
                                ? `${config.agent} · ${levelLabel({ level: config.agent_level, owner: config.agent_owner })}`
                                : `${config.model || 'haiku'} · credential set (unnamed)`}
                        </option>
                    )}
                    {agents.map((a) => (
                        <option key={a.name} value={a.name} disabled={!a.configured}>
                            {a.name}
                            {a.configured ? '' : ' - no credential'}
                        </option>
                    ))}
                    <option value="__new">＋ Add a new provider…</option>
                </select>
                {/* The backend validates a credential against the provider before seating it
                    (issue #30), rejecting an explicit 401/403 rather than merely checking a
                    Secret exists - so this tick means the worker will actually authenticate, not
                    just that something is stored. A rejected save surfaces below via `error`
                    instead of ever reaching this true state. Valid, it is the tick alone beside
                    the provider it vouches for, its words kept for hover and screen readers;
                    unset, it keeps its sentence, since that one asks the operator to act. */}
                {config.credentialed ? (
                    <span
                        className="text-[11px] text-[hsl(var(--success))]"
                        title="credential valid"
                    >
                        <span aria-hidden="true">✓</span>
                        <span className="sr-only">credential valid</span>
                    </span>
                ) : (
                    <span className="text-[11px] text-muted-foreground">
                        no provider set - the worker + co-pilot need one
                    </span>
                )}

                {/* The model, chosen SEPARATELY from the credential: one saved sub, many models. */}
                {known && (
                    <>
                        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            Model
                        </span>
                        <select
                            disabled={disabled}
                            value={modelOptions.includes(config.model) ? config.model : CUSTOM}
                            onChange={(e) => {
                                const v = e.target.value;
                                if (v === CUSTOM) {
                                    setCustomModel(config.model);
                                    setCustomOpen(true);
                                } else if (config.agent) {
                                    onApplyAgent(config.agent, v);
                                }
                            }}
                            className={picker}
                            title="Which model this provider runs - one saved credential serves many"
                        >
                            {modelOptions.map((m) => (
                                <option key={m} value={m}>
                                    {m}
                                </option>
                            ))}
                            <option value={CUSTOM}>custom…</option>
                        </select>
                    </>
                )}
                {/* The per-phase worker budget commits on ±, blur, or Enter.
                    Its key reseeds the stepper after a save. */}
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Timeout
                </span>
                <TimeoutStepper
                    key={config.timeout_hours}
                    hours={config.timeout_hours}
                    disabled={disabled}
                    onCommit={onSetTimeout}
                />
            </div>

            {/* Applying a provider writes server-side (the per-target selection + credential); a
                failure there once left the picker looking like a no-op. Surface it next to the
                control so a rejected apply is never silent. */}
            {error && <p className="text-[11px] text-destructive">{error}</p>}
            {caller.teamsEnabled && config.agent_level === 'user' && (
                <p className="text-[11px] text-muted-foreground">
                    Runs on the personal seat of {config.agent_owner || 'its owner'}: only they
                    drive this line. Apply a team or install provider to share it.
                </p>
            )}

            {/* A custom model id, typed once and applied to the current provider (still one credential). */}
            {known && customOpen && (
                <div className="flex items-center gap-2">
                    <input
                        value={customModel}
                        onChange={(e) => setCustomModel(e.target.value)}
                        placeholder="model id"
                        className={field}
                        autoFocus
                    />
                    <Button
                        type="button"
                        className="h-7 px-2 text-xs"
                        disabled={disabled || !customModel.trim() || !config.agent}
                        onClick={() => {
                            onApplyAgent(config.agent, customModel.trim());
                            setCustomOpen(false);
                        }}
                    >
                        Use
                    </Button>
                    <Button
                        type="button"
                        variant="outline"
                        className="h-7 px-2 text-xs"
                        onClick={() => setCustomOpen(false)}
                    >
                        Cancel
                    </Button>
                </div>
            )}

            {adding && (
                <div className="flex flex-col gap-2 rounded-lg border border-border bg-well/10 p-3">
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="provider name (e.g. My Claude sub)"
                            className={field}
                        />
                        <input
                            type="password"
                            value={credential}
                            onChange={(e) => setCredential(e.target.value)}
                            placeholder="setup-token or API key"
                            className={field}
                        />
                        <input
                            value={model}
                            onChange={(e) => setModel(e.target.value)}
                            placeholder="model - blank for Haiku"
                            className={field}
                        />
                        <input
                            value={baseUrl}
                            onChange={(e) => setBaseUrl(e.target.value)}
                            placeholder="base_url - blank for Claude"
                            className={field}
                        />
                        {caller.teamsEnabled && (
                            <AgentLevelSelect
                                choices={levelChoices(caller)}
                                value={level || defaultLevel(caller)}
                                onChange={setLevel}
                                disabled={disabled}
                            />
                        )}
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            type="button"
                            className="h-7 px-2 text-xs"
                            disabled={disabled || !name.trim() || !credential.trim()}
                            onClick={() => {
                                const owner = parseLevel(level || defaultLevel(caller));
                                onSaveAgent(
                                    name.trim(),
                                    baseUrl.trim(),
                                    model.trim(),
                                    credential,
                                    owner.level,
                                    owner.team,
                                );
                                setAdding(false);
                                setName('');
                                setBaseUrl('');
                                setModel('');
                                setCredential('');
                            }}
                        >
                            Save &amp; use
                        </Button>
                        <Button
                            type="button"
                            variant="outline"
                            className="h-7 px-2 text-xs"
                            onClick={() => setAdding(false)}
                        >
                            Cancel
                        </Button>
                        <span className="text-[11px] text-muted-foreground">
                            Saves the endpoint credential to your providers, then applies it here.
                            Add more models to it under Settings · Saved providers.
                        </span>
                    </div>
                </div>
            )}
        </div>
    );
};
