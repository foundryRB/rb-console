import { useMemo, useState } from 'react';
import type { Substance } from '@/models';
import { cn } from '@/utils';
import { RecordDocument } from '@/views/organisms/RecordDocument';
import { ScopeStat } from '@/views/atoms/ScopeStat';
import { PhaseTag } from '@/views/atoms/PhaseTag';
import { RefTag } from '@/views/atoms/RefTag';
import { ScopeLevel } from '@/views/atoms/ScopeLevel';
import { thCls, selectScopeContent, type TabId } from '@/viewmodels/scope/scope.model';

export const ScopePane: React.FC<{
    substance: Substance | null;
    record: string | null;
    slug?: string | null;
}> = ({ substance, record, slug }) => {
    const s = substance?.summary;
    const audit = substance?.audit;
    const requirements = substance?.requirements ?? [];
    const phases = substance?.phases ?? [];
    const assumptions = substance?.assumptions ?? [];
    const activities = substance?.activities ?? [];
    const estimate = substance?.estimate;
    const arch = substance?.architecture;
    const guidelines = arch?.guidelines ?? [];
    const diagrams = arch?.diagrams ?? [];

    const { componentsByPhase, tabs } = useMemo(
        () => selectScopeContent(substance, record),
        [substance, record],
    );

    const [tab, setTab] = useState<TabId>('overview');
    const active = tabs.some((t) => t.id === tab) ? tab : 'overview';

    if (!s || Object.keys(s).length === 0) {
        // The studio holds nothing for this slug (no project, or unreachable). Rendering the
        // committed proposal.md as if it were the substance would let an operator sign the
        // proposal gate believing they reviewed a live estimation - a record is not substance.
        // Name the slug: a mismatch here (repo `shatteredcatacombs` vs estimatekit
        // `shattered-catacombs`) is exactly what orphans a real estimation from its delivery.
        return record ? (
            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto pr-1 [&>*]:flex-none">
                <div className="flex items-start gap-2.5 rounded-lg border border-amber-400/40 bg-amber-400/10 px-3.5 py-2.5 text-xs">
                    <span className="translate-y-[1px] flex-none text-amber-400">△</span>
                    <p className="text-muted-foreground">
                        <span className="font-semibold text-foreground">
                            Not a live estimation.
                        </span>{' '}
                        No estimatekit project is linked to this delivery
                        {slug && (
                            <>
                                {' '}
                                (slug{' '}
                                <code className="rounded bg-well/40 px-1 py-0.5 font-mono text-[11px] text-foreground/90">
                                    {slug}
                                </code>
                                )
                            </>
                        )}{' '}
                        - estimatekit holds no project under that key, or it is unreachable. You are
                        seeing the committed <span className="font-mono">proposal.md</span> record
                        only. A record is not substance; sign the proposal gate on this basis with
                        care.
                    </p>
                </div>
                <div className="min-h-0 rounded-lg border border-border bg-well/10 p-4">
                    <RecordDocument text={record} />
                </div>
            </div>
        ) : (
            <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
                <span className="grid h-10 w-10 place-items-center rounded-xl border border-dashed border-border text-muted-foreground">
                    ◇
                </span>
                <p className="max-w-md text-xs text-muted-foreground">
                    No estimatekit project{slug ? ` for slug "${slug}"` : ' for this delivery'} yet
                    - it appears here, rendered natively, once scope runs.
                </p>
            </div>
        );
    }

    return (
        <div className="flex min-h-0 flex-1 flex-col gap-3">
            <div
                className="flex flex-wrap items-center gap-1 border-b border-border pb-2"
                role="tablist"
            >
                {tabs.map((t) => (
                    <button
                        key={t.id}
                        type="button"
                        role="tab"
                        aria-selected={active === t.id}
                        onClick={() => setTab(t.id)}
                        className={cn(
                            'rounded-md px-2.5 py-1 font-mono text-[11px] font-semibold',
                            active === t.id
                                ? 'bg-secondary text-secondary-foreground'
                                : 'text-muted-foreground hover:text-foreground',
                        )}
                    >
                        {t.label}
                        {t.count != null && (
                            <span className="ml-1.5 tabular-nums text-faint">{t.count}</span>
                        )}
                    </button>
                ))}
            </div>

            {/* [&>*]:flex-none: this column SCROLLS; without it, flexbox squeezes any
                overflow-hidden child (the diagram cards) to fit the bounded height,
                silently clipping content instead of scrolling. */}
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto pr-1 [&>*]:flex-none">
                {active === 'overview' && (
                    <>
                        <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
                            <ScopeStat k={s.requirement_count ?? '-'} l="Requirements" />
                            <ScopeStat
                                k={estimate ? `${estimate.total_md} MD` : (s.phase_count ?? '-')}
                                l={estimate ? 'Estimate' : 'Phases'}
                            />
                            <ScopeStat k={s.assumption_count ?? '-'} l="Assumptions" />
                            <ScopeStat
                                k={
                                    audit
                                        ? `${audit.passed_count}/${audit.passed_count + audit.failed_count}`
                                        : '-'
                                }
                                l="Audit checks"
                                ok={audit?.passed}
                            />
                        </div>

                        {s.description && (
                            <p className="border-l-2 border-link/50 pl-3 text-xs leading-relaxed text-muted-foreground">
                                <span className="font-semibold text-foreground">The ask</span> -{' '}
                                {s.description}
                            </p>
                        )}
                        {s.client && (
                            <p className="font-mono text-[11px] text-muted-foreground">
                                client · {s.client}
                            </p>
                        )}

                        {audit && (
                            <div
                                className={cn(
                                    'flex items-center gap-2.5 rounded-lg border px-3.5 py-2.5 text-xs',
                                    audit.passed
                                        ? 'border-[hsl(var(--success))]/40 bg-[hsl(var(--success))]/10'
                                        : 'border-destructive/50 bg-destructive/10',
                                )}
                            >
                                <b
                                    className={
                                        audit.passed
                                            ? 'text-[hsl(var(--success))]'
                                            : 'text-destructive'
                                    }
                                >
                                    {audit.passed ? 'Audit passed' : 'Audit failing'}
                                </b>
                                <span className="font-mono text-[11px] text-muted-foreground">
                                    {audit.passed_count} passed · {audit.failed_count} failed
                                </span>
                            </div>
                        )}

                        {audit && audit.suggestions.length > 0 && (
                            <details className="rounded-lg border border-border bg-well/20">
                                <summary className="flex cursor-pointer items-center gap-2 px-3.5 py-2.5 font-mono text-[11px] font-semibold text-muted-foreground">
                                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                                    {audit.suggestions.length} advisories - scheduling &amp;
                                    coverage
                                </summary>
                                {audit.suggestions.map((sg, i) => (
                                    <div
                                        key={i}
                                        className="flex items-baseline gap-2.5 border-t border-border px-3.5 py-2 text-xs"
                                    >
                                        <span className="h-1.5 w-1.5 flex-none translate-y-[-1px] rounded-full bg-amber-400" />
                                        <span className="flex-none font-semibold">{sg.title}</span>
                                        <span className="text-muted-foreground">{sg.detail}</span>
                                    </div>
                                ))}
                            </details>
                        )}
                    </>
                )}

                {active === 'estimate' && (
                    <>
                        {estimate && (
                            <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
                                {estimate.phases.map((p) => (
                                    <ScopeStat
                                        key={p.id}
                                        k={`${p.effort_md} MD`}
                                        l={`${p.id} effort`}
                                    />
                                ))}
                                <ScopeStat k={`${estimate.total_md} MD`} l="Total effort" ok />
                            </div>
                        )}
                        {activities.length > 0 && (
                            <div className="min-h-0 overflow-auto rounded-lg border border-border bg-well/20">
                                <table className="w-full border-collapse text-xs">
                                    <thead>
                                        <tr className="sticky top-0 z-10 bg-card">
                                            <th className={thCls}>Activity</th>
                                            <th className={thCls}>Phase</th>
                                            <th className={thCls}>Group</th>
                                            <th className={thCls}>Effort (MD)</th>
                                            <th className={thCls}>Requirements</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {activities.map((a) => (
                                            <tr
                                                key={a.id || a.activity}
                                                className="border-t border-border/60 align-top"
                                            >
                                                <td className="px-3 py-1.5">
                                                    <div className="font-medium text-foreground">
                                                        {a.activity}
                                                    </div>
                                                    {a.description && (
                                                        <div className="mt-0.5 text-[11px] text-muted-foreground">
                                                            {a.description}
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="whitespace-nowrap px-3 py-1.5">
                                                    {a.phase ? <PhaseTag id={a.phase} /> : null}
                                                </td>
                                                <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">
                                                    {a.group}
                                                </td>
                                                <td className="whitespace-nowrap px-3 py-1.5 font-mono tabular-nums text-foreground">
                                                    {a.effort_md}
                                                </td>
                                                <td className="px-3 py-1.5">
                                                    <div className="flex flex-wrap gap-1">
                                                        {a.req_ids.map((id) => (
                                                            <RefTag key={id} id={id} />
                                                        ))}
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </>
                )}

                {active === 'requirements' && (
                    <div className="min-h-0 overflow-auto rounded-lg border border-border bg-well/20">
                        <table className="w-full border-collapse text-xs">
                            <thead>
                                <tr className="sticky top-0 z-10 bg-card">
                                    <th className={thCls}>Req</th>
                                    <th className={thCls}>Category</th>
                                    <th className={thCls}>Description</th>
                                    <th className={thCls}>Phase</th>
                                </tr>
                            </thead>
                            <tbody>
                                {requirements.map((r) => (
                                    <tr key={r.id} className="border-t border-border/60 align-top">
                                        <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[11px] text-foreground">
                                            {r.id}
                                        </td>
                                        <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">
                                            {r.category}
                                        </td>
                                        <td className="px-3 py-1.5 text-foreground/90">
                                            {r.description}
                                        </td>
                                        <td className="whitespace-nowrap px-3 py-1.5">
                                            <div className="flex flex-wrap gap-1">
                                                {r.phases.length ? (
                                                    r.phases.map((p) => <PhaseTag key={p} id={p} />)
                                                ) : (
                                                    <span className="text-faint">-</span>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {active === 'phases' && (
                    <div className="flex flex-col gap-2">
                        {phases.map((p) => (
                            <div
                                key={p.id}
                                className="rounded-lg border border-border bg-well/20 px-3.5 py-2.5"
                            >
                                <div className="flex flex-wrap items-baseline gap-2">
                                    <PhaseTag id={p.id} />
                                    {p.name && (
                                        <span className="font-semibold text-foreground">
                                            {p.name}
                                        </span>
                                    )}
                                    {p.phase && (
                                        <span className="font-mono text-[10px] text-muted-foreground">
                                            {p.phase}
                                        </span>
                                    )}
                                    <span className="ml-auto font-mono text-[10px] tabular-nums text-muted-foreground">
                                        {p.requirement_ids.length} reqs
                                    </span>
                                </div>
                                {p.description && (
                                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                                        {p.description}
                                    </p>
                                )}
                                {p.requirement_ids.length > 0 && (
                                    <div className="mt-1.5 flex flex-wrap gap-1">
                                        {p.requirement_ids.map((id) => (
                                            <RefTag key={id} id={id} />
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {active === 'assumptions' && (
                    <div className="flex flex-col gap-1.5">
                        {assumptions.map((a) => (
                            <div
                                key={a.id || a.assumption}
                                className="rounded-lg border border-border bg-well/20 px-3.5 py-2.5"
                            >
                                <div className="flex flex-wrap items-baseline gap-2">
                                    {a.id && (
                                        <span className="font-mono text-[11px] text-foreground">
                                            {a.id}
                                        </span>
                                    )}
                                    {a.title && (
                                        <span className="font-semibold text-foreground">
                                            {a.title}
                                        </span>
                                    )}
                                    {a.confidence && (
                                        <ScopeLevel label="conf" value={a.confidence} />
                                    )}
                                    {a.impact && <ScopeLevel label="impact" value={a.impact} sev />}
                                    {a.group && (
                                        <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                                            {a.group}
                                        </span>
                                    )}
                                </div>
                                {a.assumption && (
                                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                                        {a.assumption}
                                    </p>
                                )}
                                {a.req_ids.length > 0 && (
                                    <div className="mt-1.5 flex flex-wrap gap-1">
                                        {a.req_ids.map((id) => (
                                            <RefTag key={id} id={id} />
                                        ))}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {active === 'architecture' && (
                    <>
                        {diagrams.map((d) => (
                            <div
                                key={d.name}
                                className="overflow-hidden rounded-lg border border-border bg-well/20"
                            >
                                <div className="flex items-center gap-2 px-3.5 py-2.5">
                                    {d.phase && <PhaseTag id={d.phase} />}
                                    <span className="font-mono text-[11px] font-semibold text-muted-foreground">
                                        {d.name}
                                    </span>
                                    {!d.svg && (
                                        <span className="ml-auto font-mono text-[10px] text-faint">
                                            source only - the studio serves no render yet
                                        </span>
                                    )}
                                    {d.svg && (
                                        <button
                                            type="button"
                                            className="ml-auto font-mono text-[10px] text-muted-foreground hover:text-foreground"
                                            title="Open this diagram alone in a new tab, at full size"
                                            onClick={() => {
                                                const url = URL.createObjectURL(
                                                    new Blob([d.svg as string], {
                                                        type: 'image/svg+xml',
                                                    }),
                                                );
                                                window.open(url, '_blank');
                                            }}
                                        >
                                            ⤢ full size
                                        </button>
                                    )}
                                </div>
                                {d.svg && (
                                    <div
                                        // Natural size, never scaled: PlantUML SVGs carry
                                        // preserveAspectRatio="none", so any max-width clamp squishes the
                                        // drawing instead of shrinking it. A wide diagram scrolls here.
                                        className="overflow-auto border-t border-border bg-white p-3"
                                        // estimatekit renders this SVG in-cluster from the project's own
                                        // .puml - first-party substance, embedded as the diagram itself.
                                        dangerouslySetInnerHTML={{ __html: d.svg }}
                                    />
                                )}
                                <details
                                    className={cn(!d.svg && 'open:bg-transparent')}
                                    open={!d.svg}
                                >
                                    <summary className="cursor-pointer border-t border-border px-3.5 py-2 font-mono text-[10px] text-muted-foreground">
                                        PlantUML source
                                    </summary>
                                    <pre className="overflow-auto border-t border-border p-3 font-mono text-[10.5px] leading-relaxed text-foreground/80">
                                        {d.puml}
                                    </pre>
                                </details>
                            </div>
                        ))}

                        {guidelines.length > 0 && (
                            <div className="flex flex-col gap-1.5">
                                {guidelines.map((g) => (
                                    <div
                                        key={g.id || g.name}
                                        className="rounded-lg border border-border bg-well/20 px-3.5 py-2"
                                    >
                                        <div className="flex flex-wrap items-baseline gap-2">
                                            {g.id && (
                                                <span className="font-mono text-[10px] text-muted-foreground">
                                                    {g.id}
                                                </span>
                                            )}
                                            <span className="font-semibold text-foreground">
                                                {g.name}
                                            </span>
                                            {g.group && (
                                                <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                                                    {g.group}
                                                </span>
                                            )}
                                        </div>
                                        {g.description && (
                                            <p className="mt-0.5 text-xs text-muted-foreground">
                                                {g.description}
                                            </p>
                                        )}
                                        {g.rationale && (
                                            <p className="mt-0.5 text-[11px] italic text-faint">
                                                {g.rationale}
                                            </p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}

                        {Object.entries(componentsByPhase).map(([phase, comps]) => (
                            <div
                                key={phase}
                                className="overflow-hidden rounded-lg border border-border bg-well/20"
                            >
                                <div className="flex items-center gap-2 px-3.5 py-2">
                                    <PhaseTag id={phase} />
                                    <span className="font-mono text-[9.5px] font-semibold uppercase tracking-widest text-muted-foreground">
                                        components
                                    </span>
                                </div>
                                <div className="overflow-auto border-t border-border">
                                    <table className="w-full border-collapse text-xs">
                                        <thead>
                                            <tr className="bg-card">
                                                <th className={thCls}>Layer</th>
                                                <th className={thCls}>Component</th>
                                                <th className={thCls}>Technology</th>
                                                <th className={thCls}>Description</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {comps.map((c, i) => (
                                                <tr
                                                    key={`${c.component}-${i}`}
                                                    className="border-t border-border/60 align-top"
                                                >
                                                    <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">
                                                        {c.layer}
                                                    </td>
                                                    <td className="whitespace-nowrap px-3 py-1.5 font-medium text-foreground">
                                                        {c.component}
                                                    </td>
                                                    <td className="whitespace-nowrap px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                                                        {c.technology}
                                                    </td>
                                                    <td className="px-3 py-1.5 text-foreground/90">
                                                        {c.description}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        ))}
                    </>
                )}

                {active === 'record' && record && (
                    <div className="min-h-0 rounded-lg border border-border bg-well/10 p-4">
                        <RecordDocument text={record} />
                    </div>
                )}
            </div>
        </div>
    );
};
