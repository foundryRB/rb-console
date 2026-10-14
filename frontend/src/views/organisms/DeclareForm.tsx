import { useEffect, useState } from 'react';
import { cn } from '@/utils';
import { usePromotion } from '@/viewmodels/promotion';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export const DeclareForm: React.FC<{ repo: string; onDone: () => void }> = ({ repo, onDone }) => {
    const { options, loadOptions, declare, declaring, declareError } = usePromotion();
    const [kind, setKind] = useState<'environment' | 'repository'>('environment');
    const [name, setName] = useState('');
    const [install, setInstall] = useState('');
    const [environment, setEnvironment] = useState('');
    const [pairRepo, setPairRepo] = useState('');
    const [branch, setBranch] = useState('main');
    const [credential, setCredential] = useState('');
    const [probeUrl, setProbeUrl] = useState('');

    useEffect(() => {
        void loadOptions(repo);
    }, [repo, loadOptions]);

    const installs = options?.installs ?? [];
    const chosen = installs.find((i) => i.install === install);
    const noManualEnvironment =
        kind === 'environment' &&
        installs.length > 0 &&
        installs.every((i) => !i.environments.length);

    const submit = async () => {
        const ok = await declare(repo, {
            name,
            kind,
            ...(kind === 'environment'
                ? { install, environment }
                : { pair_repo: pairRepo, branch, credential }),
            ...(probeUrl ? { probe_url: probeUrl } : {}),
        });
        if (ok) onDone();
    };

    const field = 'w-full rounded-md border border-input bg-well/20 px-2.5 py-1.5 text-xs';

    return (
        <Card className="flex-none space-y-3 p-4">
            <div className="text-sm font-semibold">Declare a target</div>

            <div className="flex gap-2">
                {(['environment', 'repository'] as const).map((k) => (
                    <button
                        key={k}
                        type="button"
                        onClick={() => setKind(k)}
                        className={cn(
                            'rounded-full px-3 py-1 text-[11px] font-semibold',
                            kind === k
                                ? 'bg-secondary text-secondary-foreground'
                                : 'text-muted-foreground hover:text-foreground',
                        )}
                    >
                        {k === 'environment'
                            ? 'An environment we run'
                            : "Another organization's repo"}
                    </button>
                ))}
            </div>

            <label className="block">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                    Name
                </span>
                <input
                    className={field}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="example-uat"
                />
            </label>

            {kind === 'environment' ? (
                <div className="grid grid-cols-2 gap-2">
                    <label className="block">
                        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                            Install
                        </span>
                        <select
                            className={field}
                            value={install}
                            onChange={(e) => {
                                setInstall(e.target.value);
                                setEnvironment('');
                            }}
                        >
                            <option value="">Select…</option>
                            {installs.map((i) => (
                                <option key={i.install} value={i.install}>
                                    {i.install}
                                </option>
                            ))}
                        </select>
                    </label>
                    <label className="block">
                        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                            Environment
                        </span>
                        <select
                            className={field}
                            value={environment}
                            onChange={(e) => setEnvironment(e.target.value)}
                            disabled={!chosen}
                        >
                            <option value="">Select…</option>
                            {(chosen?.environments ?? []).map((env) => (
                                <option key={env} value={env}>
                                    {env}
                                </option>
                            ))}
                        </select>
                    </label>
                </div>
            ) : (
                <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                        <label className="block">
                            <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                                Their repository
                            </span>
                            <input
                                className={field}
                                value={pairRepo}
                                onChange={(e) => setPairRepo(e.target.value)}
                                placeholder="their-org/their-repo"
                            />
                        </label>
                        <label className="block">
                            <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                                Base branch
                            </span>
                            <input
                                className={field}
                                value={branch}
                                onChange={(e) => setBranch(e.target.value)}
                            />
                        </label>
                    </div>
                    <label className="block">
                        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                            Credential name
                        </span>
                        <input
                            className={field}
                            value={credential}
                            onChange={(e) => setCredential(e.target.value)}
                            placeholder="partner-pair"
                        />
                        <span className="mt-1 block font-mono text-[10px] text-muted-foreground">
                            the name only: the platform holds the secret, and it never enters the
                            contract
                        </span>
                    </label>
                </div>
            )}

            <label className="block">
                <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                    Probe URL (optional)
                </span>
                <input
                    className={field}
                    value={probeUrl}
                    onChange={(e) => setProbeUrl(e.target.value)}
                    placeholder="https://…"
                />
                <span className="mt-1 block font-mono text-[10px] text-muted-foreground">
                    what proven-there means; leave it empty and the promotion closes at deployed
                </span>
            </label>

            {noManualEnvironment && (
                <p className="rounded-md border border-border bg-well/20 px-3 py-2 text-xs text-muted-foreground">
                    Every install this app runs on declares a single environment, and that one is
                    deployed automatically. Declare another environment on an install before a
                    promotion can target one.
                </p>
            )}

            {declareError && (
                <p className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                    {declareError}
                </p>
            )}

            <div className="flex items-center gap-2">
                <Button type="button" onClick={() => void submit()} disabled={declaring || !name}>
                    {declaring ? 'Declaring…' : 'Declare target'}
                </Button>
                <button
                    type="button"
                    onClick={onDone}
                    className="rounded-md border border-border px-3 py-2 text-xs text-muted-foreground hover:text-foreground"
                >
                    Cancel
                </button>
                <span className="font-mono text-[10px] text-muted-foreground">
                    commits devops/promotion.yaml to this app
                </span>
            </div>
        </Card>
    );
};
