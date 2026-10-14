import { useSettings } from '@/viewmodels/settings';
import { useCallback, useEffect, useState } from 'react';

import { cn } from '@/utils';
import { Button } from '@/components/ui/button';


const errorText = (e: unknown): string => (e instanceof Error ? e.message : 'Unknown error');

const field =
    'rounded-lg border border-input bg-background px-3 py-2 text-xs outline-none focus:border-link';

/**
 * Pair credentials: what a promotion target's `credential:` name resolves to.
 *
 * Every other credential the platform deals in is minted by it. A token for another
 * organization's repository is not ours to create - it is granted to us - so this panel
 * REGISTERS a supplied secret rather than issuing one, and the name must be the one the app's
 * own `devops/promotion.yaml` writes down. Until a pair is registered here, its target's door
 * cannot be opened, and the Promotion pane says exactly that instead of drawing a row that
 * looks like every working one.
 */
export const PairCredentialsManager: React.FC = () => {
    const { credentials, loadPairs, savePair, deletePair } = useSettings();
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const [name, setName] = useState('');
    const [host, setHost] = useState('');
    const [login, setLogin] = useState('');
    const [token, setToken] = useState('');

    const load = useCallback(() => loadPairs().catch((e) => setError(errorText(e))), [loadPairs]);

    useEffect(() => {
        void load();
    }, [load]);

    const save = async () => {
        setBusy(true);
        setError(null);
        try {
            await savePair(name.trim(), host.trim(), login.trim(), token || null);
            setName('');
            setHost('');
            setLogin('');
            setToken('');
            await load();
        } catch (e) {
            setError(errorText(e));
        } finally {
            setBusy(false);
        }
    };

    const remove = async (n: string) => {
        setBusy(true);
        setError(null);
        try {
            await deletePair(n);
            await load();
        } catch (e) {
            setError(errorText(e));
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="flex flex-col gap-4">
            <div>
                <h3 className="text-sm font-semibold tracking-tight">Pair credentials</h3>
                <p className="text-xs text-muted-foreground">
                    What a promotion target&apos;s{' '}
                    <code className="rounded bg-muted px-1 text-foreground">credential:</code> name
                    resolves to - the repo-host token another organization granted us for their
                    repository, so a{' '}
                    <code className="rounded bg-muted px-1 text-foreground">kind: repository</code>{' '}
                    target&apos;s door can actually be opened. The platform mints no credential for
                    a repository it does not own, so this registers one they supplied. Use the exact
                    name the app&apos;s <span className="font-mono">devops/promotion.yaml</span>{' '}
                    declares. The secret is stored server-side and never listed.{' '}
                    {error && <span className="text-destructive">{error}</span>}
                </p>
            </div>

            {credentials.length > 0 ? (
                <div className="flex flex-col gap-2">
                    {credentials.map((c) => (
                        <div
                            key={c.name}
                            className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2"
                        >
                            <div className="min-w-0">
                                <div className="flex items-center gap-2 text-sm font-medium">
                                    <span className="font-mono">{c.name}</span>
                                    <span
                                        className={cn(
                                            'text-[10px]',
                                            c.configured
                                                ? 'text-[hsl(var(--success))]'
                                                : 'text-destructive',
                                        )}
                                    >
                                        {c.configured
                                            ? '● secret held'
                                            : 'no secret - the door is shut'}
                                    </span>
                                </div>
                                <div className="font-mono text-[11px] text-muted-foreground">
                                    {c.host || 'github.com'}
                                    {c.login ? ` · as @${c.login}` : ''}
                                </div>
                            </div>
                            <Button
                                type="button"
                                variant="outline"
                                className="h-7 shrink-0 px-2 text-xs"
                                disabled={busy}
                                onClick={() => void remove(c.name)}
                            >
                                Delete
                            </Button>
                        </div>
                    ))}
                </div>
            ) : (
                <p className="text-xs text-muted-foreground">
                    No pair credentials registered. Any repository target declared today has a door
                    nothing can open.
                </p>
            )}

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="credential name (as the contract declares it)"
                    className={field}
                />
                <input
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                    placeholder="host (github.com)"
                    className={field}
                />
                <input
                    value={login}
                    onChange={(e) => setLogin(e.target.value)}
                    placeholder="login we act as over there (optional)"
                    className={field}
                />
                <input
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="the token they granted us (blank to keep on edit)"
                    className={field}
                />
            </div>
            <div className="flex items-center gap-3">
                <Button
                    type="button"
                    disabled={busy || !name.trim()}
                    className="h-8 px-3 text-xs"
                    onClick={() => void save()}
                >
                    Register credential
                </Button>
                <span className="font-mono text-[10px] text-muted-foreground">
                    needs branch-push and pull-request-open on their repository
                </span>
            </div>
        </div>
    );
};
