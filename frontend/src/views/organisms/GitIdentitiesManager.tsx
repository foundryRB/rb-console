import { useSettings } from '@/viewmodels/settings';
import { useCallback, useEffect, useState } from 'react';

import { cn } from '@/utils';
import { Button } from '@/components/ui/button';


const errorText = (e: unknown): string => (e instanceof Error ? e.message : 'Unknown error');

const field =
    'rounded-lg border border-input bg-background px-3 py-2 text-xs outline-none focus:border-link';

const KIND_LABEL: Record<string, string> = {
    delivery: 'Delivery phases',
    maintenance: 'Maintenance acts',
    console: 'Console-side acts',
};

/**
 * Per-phase git identities. Each of the seven Job phases (the five delivery phases and the two
 * maintenance acts), plus the console's own acts, can run as a chosen machine-user identity -
 * or share one. The point is that the Review identity can be a DIFFERENT GitHub account than
 * the Delivery/Resolve identity, so it can actually approve the resolver's PR (GitHub refuses
 * to let an account approve its own). A role left unassigned has no identity: its worker gets
 * no git credentials, so an identity must be configured and assigned before that phase can run.
 */
export const GitIdentitiesManager: React.FC = () => {
    const {
        identities,
        roles,
        catalog,
        loadIdentities,
        loadRoles,
        saveIdentity,
        deleteIdentity,
        assignRoles,
    } = useSettings();
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const [name, setName] = useState('');
    const [login, setLogin] = useState('');
    const [email, setEmail] = useState('');
    const [token, setToken] = useState('');

    // .then-style (not an async body) so setState lands in a callback, the shape the
    // effect-hygiene lint expects - mirrors RuntimeSettings' own refresh().
    const load = useCallback(
        () => Promise.all([loadIdentities(), loadRoles()]).catch((e) => setError(errorText(e))),
        [loadIdentities, loadRoles],
    );

    useEffect(() => {
        void load();
    }, [load]);

    const canSave = Boolean(name.trim());

    const save = async () => {
        setBusy(true);
        setError(null);
        try {
            await saveIdentity(name.trim(), email.trim(), login.trim(), token || null);
            setName('');
            setLogin('');
            setEmail('');
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
            await deleteIdentity(n);
            await load();
        } catch (e) {
            setError(errorText(e));
        } finally {
            setBusy(false);
        }
    };

    const assign = async (roleKey: string, identityName: string) => {
        const next = { ...roles };
        if (identityName) next[roleKey] = identityName;
        else delete next[roleKey];
        setBusy(true);
        setError(null);
        try {
            await assignRoles(next);
        } catch (e) {
            setError(errorText(e));
        } finally {
            setBusy(false);
        }
    };

    // Group the assignable roles by kind so the grid reads at a glance.
    const kinds = Array.from(new Set(catalog.map((r) => r.kind)));

    return (
        <div className="flex flex-col gap-4">
            <div>
                <h3 className="text-sm font-semibold tracking-tight">Git identities</h3>
                <p className="text-xs text-muted-foreground">
                    Machine-user credentials the workers commit, push, and review as - assigned per
                    phase below. Give Review a different identity than Delivery/Resolve so it can
                    approve the resolver&apos;s PR (GitHub refuses to let an account approve its
                    own). The PAT is stored server-side and never listed.{' '}
                    {error && <span className="text-destructive">{error}</span>}
                </p>
            </div>

            {identities.length > 0 && (
                <div className="flex flex-col gap-2">
                    {identities.map((i) => (
                        <div
                            key={i.name}
                            className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2"
                        >
                            <div className="min-w-0">
                                <div className="flex items-center gap-2 text-sm font-medium">
                                    {i.name}
                                    <span
                                        className={cn(
                                            'text-[10px]',
                                            i.configured
                                                ? 'text-[hsl(var(--success))]'
                                                : 'text-muted-foreground',
                                        )}
                                    >
                                        {i.configured ? '● token set' : 'no token'}
                                    </span>
                                </div>
                                <div className="font-mono text-[11px] text-muted-foreground">
                                    {i.login ? `@${i.login}` : 'no login'}
                                    {i.email ? ` · ${i.email}` : ''}
                                </div>
                            </div>
                            <Button
                                type="button"
                                variant="outline"
                                className="h-7 shrink-0 px-2 text-xs"
                                disabled={busy}
                                onClick={() => void remove(i.name)}
                            >
                                Delete
                            </Button>
                        </div>
                    ))}
                </div>
            )}
            {identities.length === 0 && (
                <p className="text-xs text-muted-foreground">No git identities yet.</p>
            )}

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="name (e.g. Foundry Review)"
                    className={field}
                />
                <input
                    value={login}
                    onChange={(e) => setLogin(e.target.value)}
                    placeholder="GitHub login (e.g. foundry-review-bot)"
                    className={field}
                />
                <input
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="commit email (the GitHub no-reply)"
                    className={field}
                />
                <input
                    type="password"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="fine-grained PAT (blank to keep on edit)"
                    className={field}
                />
            </div>
            <div>
                <Button
                    type="button"
                    disabled={busy || !canSave}
                    className="h-8 px-3 text-xs"
                    onClick={() => void save()}
                >
                    Save identity
                </Button>
            </div>

            <div className="mt-1 border-t border-border pt-3">
                <h4 className="text-xs font-semibold tracking-tight">Assign identities to roles</h4>
                <p className="mt-0.5 text-xs text-muted-foreground">
                    Which identity each phase, and the console&apos;s own acts, run as. A row left
                    unassigned has no identity: that phase&apos;s worker gets no git credentials and
                    cannot push, so assign one before running it. Share one across many, or split
                    them all.
                </p>
                <div className="mt-2 flex flex-col gap-3">
                    {kinds.map((kind) => (
                        <div key={kind} className="flex flex-col gap-1.5">
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                                {KIND_LABEL[kind] ?? kind}
                            </span>
                            {catalog
                                .filter((r) => r.kind === kind)
                                .map((r) => (
                                    <label
                                        key={r.key}
                                        className="flex items-center justify-between gap-3"
                                    >
                                        <span className="font-mono text-xs">{r.label}</span>
                                        <select
                                            value={roles[r.key] ?? ''}
                                            disabled={busy}
                                            onChange={(e) => void assign(r.key, e.target.value)}
                                            className="h-8 min-w-56 rounded-lg border border-input bg-background px-2.5 text-xs outline-none focus:border-link"
                                        >
                                            <option value="">- unassigned (no identity) -</option>
                                            {identities.map((i) => (
                                                <option key={i.name} value={i.name}>
                                                    {i.name}
                                                </option>
                                            ))}
                                        </select>
                                    </label>
                                ))}
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};
