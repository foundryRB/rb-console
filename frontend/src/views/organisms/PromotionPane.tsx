import { useEffect, useState } from 'react';
import { cn } from '@/utils';
import { usePromotion } from '@/viewmodels/promotion';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { DeclareForm } from '@/views/organisms/DeclareForm';
import { PromoteButton } from '@/views/organisms/PromoteButton';
import { TONE, DOT, LABEL, nextAct } from '@/viewmodels/promotion/promotion.model';

export const PromotionPane: React.FC<{ repo: string }> = ({ repo }) => {
    const { state: observedState, loading, error, load } = usePromotion();
    const state = observedState?.repo === repo ? observedState : null;
    const [declaring, setDeclaring] = useState(false);

    useEffect(() => {
        void load(repo);
    }, [repo, load]);

    if (loading && !state) {
        return <p className="text-sm text-muted-foreground">Reading the promotion contract…</p>;
    }
    if (error) {
        return (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
            </div>
        );
    }
    if (state && !state.declared) {
        return declaring ? (
            <DeclareForm repo={repo} onDone={() => setDeclaring(false)} />
        ) : (
            <Card className="flex-none p-4">
                <p className="text-sm font-semibold">No promotion contract</p>
                <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
                    This app declares no promotion targets, so its releases go no further than the
                    entry environment it already deploys to. Declaring one is a commit to{' '}
                    <span className="font-mono">devops/promotion.yaml</span> in the app&apos;s own
                    repository, which the button below writes.
                </p>
                <Button type="button" className="mt-3" onClick={() => setDeclaring(true)}>
                    Declare a target
                </Button>
            </Card>
        );
    }

    // Not a promotion subject: say why, and draw no rows. Left to the derivation, both of
    // these read as PENDING (an empty proven compares unequal to anything), which put a
    // Promote act on a row where no promotion is possible.
    if (state?.subject === 'managed') {
        return (
            <Card className="flex-none p-4">
                <p className="text-sm font-semibold">Managed: not a promotion subject</p>
                <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
                    This app runs on no foundry, so there is no entry environment to prove a release
                    and nothing for a promotion to move. The repository target its contract declares
                    is its <span className="font-semibold">home</span> - the address its maintenance
                    and delivery lines land their pull requests through, at the
                    proven-in-CI-and-merged bar - not a door promotion drives.
                </p>
            </Card>
        );
    }
    if (state?.subject === 'nothing-proven') {
        return (
            <Card className="flex-none p-4">
                <p className="text-sm font-semibold">Nothing proven yet</p>
                <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
                    This app has published no release, so there is nothing to promote to the targets
                    its contract declares. The first release the entry environment serves becomes
                    the proven release, and the targets derive from there.
                </p>
            </Card>
        );
    }

    const targets = state?.targets ?? [];

    return (
        <>
            {state?.problem && (
                <div className="flex-none rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    The contract is malformed: {state.problem}
                </div>
            )}

            <Card className="flex flex-none flex-wrap items-center gap-x-6 gap-y-3 p-4">
                <div>
                    <div className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                        Proven release
                    </div>
                    <div className="text-2xl font-bold">{state?.proven || '-'}</div>
                </div>
                <div className="h-8 w-px bg-border" />
                <div className="font-mono text-[11px] text-muted-foreground">
                    the entry environment serves it; every target below is written only by promotion
                </div>
                {!declaring && (
                    <button
                        type="button"
                        onClick={() => setDeclaring(true)}
                        className="ml-auto rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:border-link/50 hover:text-link"
                    >
                        Declare a target
                    </button>
                )}
            </Card>

            {declaring && <DeclareForm repo={repo} onDone={() => setDeclaring(false)} />}

            <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto pr-1">
                {targets.length === 0 && (
                    <p className="text-xs text-muted-foreground">
                        The contract declares no targets yet.
                    </p>
                )}
                {targets.map((t) => (
                    <Card key={t.name} className={cn('flex-none border p-4', TONE[t.state])}>
                        <div className="flex flex-wrap items-center gap-3">
                            <span className={cn('h-2 w-2 flex-none rounded-full', DOT[t.state])} />
                            <div className="min-w-0">
                                <div className="text-sm font-semibold">{t.name}</div>
                                <div className="font-mono text-[10.5px] text-muted-foreground">
                                    {t.destination} · {t.kind}
                                </div>
                            </div>
                            <div className="flex flex-wrap gap-2 font-mono text-[10.5px] text-muted-foreground">
                                <span className="rounded border border-border px-2 py-0.5">
                                    door: {t.door}
                                </span>
                                <span className="rounded border border-border px-2 py-0.5">
                                    terms: {t.terms}
                                </span>
                                <span className="rounded border border-border px-2 py-0.5">
                                    acceptance: {t.acceptance}
                                </span>
                            </div>
                            <div className="ml-auto flex items-center gap-3">
                                <span className="font-mono text-sm">{t.accepted || '-'}</span>
                                <span
                                    className={cn(
                                        'rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase',
                                        t.door_shut
                                            ? 'border-destructive/60 text-destructive'
                                            : 'border-border',
                                    )}
                                >
                                    {t.door_shut ? 'door shut' : LABEL[t.state]}
                                </span>
                            </div>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                            <span className="font-mono text-[10.5px] text-muted-foreground">
                                {t.detail || nextAct(t, repo)}
                            </span>
                            {t.door_shut && (
                                <span className="font-mono text-[10.5px] text-destructive">
                                    · {nextAct(t, repo)}
                                </span>
                            )}
                            {/* Only a target that is actually behind offers the act. A shut
                                door offers registration instead (its detail says so), and a
                                current one has nothing to do. */}
                            {t.state === 'pending' && !t.door_shut && (
                                <div className="ml-auto">
                                    <PromoteButton repo={repo} target={t} />
                                </div>
                            )}
                        </div>
                    </Card>
                ))}
            </div>
        </>
    );
};
