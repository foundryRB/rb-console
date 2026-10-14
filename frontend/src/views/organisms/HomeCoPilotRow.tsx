import { useAgents } from '@/viewmodels/agents';
import { useSettings } from '@/viewmodels/settings';
import { useCallback, useEffect, useState } from 'react';

import { useDeliveries } from '@/viewmodels/deliveries';
import { Button } from '@/components/ui/button';

import { SettingStatus } from '@/views/atoms/SettingStatus';

export const HomeCoPilotRow: React.FC = () => {
    const { driver, loadDriver } = useSettings();
    const { agents, loadAgents, applyAgentToDriver } = useAgents(),
        { actionLoading, actionError } = useDeliveries();
    const [pick, setPick] = useState('');
    const [pickModel, setPickModel] = useState('');

    const refresh = useCallback(
        () =>
            loadDriver()
                .then((d) => {
                    setPick((cur) => cur || d.agent);
                    setPickModel((cur) => cur || d.model);
                })
                .catch(() => undefined),
        [loadDriver],
    );

    useEffect(() => {
        void loadAgents();
        void refresh();
    }, [loadAgents, refresh]);

    // The home co-pilot answers everyone, so it takes an install agent alone.
    const usable = agents.filter((a) => a.configured && (a.level ?? 'install') === 'install');
    // The models the picked provider serves, plus whatever is currently in use, so it always shows.
    const pickedAgent = agents.find((a) => a.name === pick) ?? null;
    const modelOptions = Array.from(
        new Set([...(pickedAgent?.models ?? []), pickModel].filter(Boolean)),
    );
    const inUse =
        pick === driver?.agent && (pickModel || driver?.model || '') === (driver?.model || '');
    const apply = async () => {
        if (!pick) return;
        await applyAgentToDriver(pick, pickModel || undefined);
        await refresh();
    };

    return (
        <div className="flex flex-col gap-2 px-4 py-3">
            <span className="flex items-center gap-2.5">
                <span className="font-mono text-sm font-medium">Home co-pilot</span>
                <SettingStatus configured={Boolean(driver?.configured)} />
                {driver?.agent && (
                    <span className="text-[11px] text-muted-foreground">
                        answering as <span className="text-foreground">{driver.agent}</span>
                        {driver.model ? ` · ${driver.model}` : ''}
                    </span>
                )}
            </span>
            <span className="text-xs text-muted-foreground">
                The Fleet page assistant: it reads the whole floor and advises; it executes nothing.
                Pick which saved provider answers there, and which of its models. Each
                project&apos;s co-pilot and workers use the provider picked in that project&apos;s
                masthead, never this one.
            </span>
            <div className="flex flex-wrap items-center gap-2">
                <select
                    value={pick}
                    onChange={(e) => {
                        setPick(e.target.value);
                        setPickModel(''); // a new provider: back to its default model until one is chosen
                    }}
                    className="h-9 min-w-56 rounded-lg border border-input bg-background px-2.5 text-xs outline-none focus:border-link"
                >
                    <option value="">pick a saved provider…</option>
                    {usable.map((a) => (
                        <option key={a.name} value={a.name}>
                            {a.name}
                        </option>
                    ))}
                </select>
                {pick && modelOptions.length > 0 && (
                    <select
                        value={pickModel}
                        onChange={(e) => setPickModel(e.target.value)}
                        className="h-9 min-w-40 rounded-lg border border-input bg-background px-2.5 text-xs outline-none focus:border-link"
                        title="Which model this provider runs - one saved credential serves many"
                    >
                        <option value="">default model</option>
                        {modelOptions.map((m) => (
                            <option key={m} value={m}>
                                {m}
                            </option>
                        ))}
                    </select>
                )}
                <Button
                    type="button"
                    className="h-9 px-3 text-xs"
                    disabled={actionLoading || !pick || inUse}
                    onClick={() => void apply()}
                >
                    {pick && inUse ? 'In use' : 'Use this provider'}
                </Button>
                {usable.length === 0 && (
                    <span className="text-xs text-muted-foreground">
                        No saved providers with a credential yet - add one under Saved providers
                        below.
                    </span>
                )}
                {actionError && <span className="text-xs text-destructive">{actionError}</span>}
            </div>
        </div>
    );
};
