import { useMemo, useState } from 'react';

import type { MaintInboxItem } from '@/models';

import { InboxItem } from '@/views/molecules/InboxItem';

import { FilterChecks } from '@/views/organisms/FilterChecks';
import { InboxSortMenu } from '@/views/organisms/InboxSortMenu';

import {
    INBOX_COLLAPSED,
    rankOf,
    ageKeyOf,
    type InboxSort,
    SORT_NAME,
} from '@/viewmodels/fleet/fleet.model';

export const InboxStrip: React.FC<{
    items: MaintInboxItem[];
    appNames?: Record<string, string>;
}> = ({ items, appNames }) => {
    const [expanded, setExpanded] = useState(false);
    const [proj, setProj] = useState<Set<string>>(new Set());
    const [sig, setSig] = useState<Set<string>>(new Set());
    const [sort, setSort] = useState<InboxSort>('criticality');

    const projects = useMemo(
        () => Array.from(new Set(items.map((i) => i.repo))).sort((a, b) => a.localeCompare(b)),
        [items],
    );
    const signals = useMemo(
        () => Array.from(new Set(items.map((i) => i.signal))).sort((a, b) => a.localeCompare(b)),
        [items],
    );
    const filtered = useMemo(
        () =>
            items.filter(
                (i) =>
                    (proj.size === 0 || proj.has(i.repo)) && (sig.size === 0 || sig.has(i.signal)),
            ),
        [items, proj, sig],
    );
    // Sort a copy (never the incoming array); a stable sort keeps 'criticality' identical to the
    // backend's (urgency, repo, number) order, and the others fall back to it on a tie.
    const sorted = useMemo(() => {
        const arr = [...filtered];
        if (sort === 'project')
            arr.sort((a, b) => a.repo.localeCompare(b.repo) || rankOf(a) - rankOf(b));
        else if (sort === 'age')
            arr.sort((a, b) => ageKeyOf(a) - ageKeyOf(b) || rankOf(a) - rankOf(b));
        else arr.sort((a, b) => rankOf(a) - rankOf(b));
        return arr;
    }, [filtered, sort]);

    if (items.length === 0) return null;

    const filtering = proj.size > 0 || sig.size > 0;
    const shown = expanded ? sorted : sorted.slice(0, INBOX_COLLAPSED);
    const hidden = sorted.length - INBOX_COLLAPSED;
    const clear = () => {
        setProj(new Set());
        setSig(new Set());
    };

    return (
        // Rounded by its own corners, NOT by overflow-hidden. The filter panels open downward out
        // of the header, so a strip that clips its box cut the option list off at the strip's own
        // bottom edge: the shorter the queue, the fewer projects the operator could reach, and a
        // queue filtered down to nothing left barely one option standing. Rounding the ends
        // instead keeps the header's fill and the last row's hover inside the radius (the -1px is
        // the border they sit inside) while the panels overhang freely.
        <div className="app-glass rb-inbox mb-5 rounded-lg border border-border [&>*:last-child]:rounded-b-[calc(var(--radius)-1px)]">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1.5 rounded-t-[calc(var(--radius)-1px)] border-b border-border bg-secondary/40 px-4 py-2">
                <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Inbox
                </span>
                <span className="text-[11px] text-muted-foreground">
                    {filtering
                        ? `${filtered.length} of ${items.length}`
                        : `${items.length} item(s)`}
                </span>
                <div className="ml-auto flex items-center gap-1.5">
                    <InboxSortMenu
                        value={sort}
                        onChange={(next) => {
                            setSort(next);
                            setExpanded(false);
                        }}
                    />
                    <FilterChecks
                        ariaLabel="Filter the inbox by project"
                        allLabel="All projects"
                        options={projects}
                        selected={proj}
                        onChange={(next) => {
                            setProj(next);
                            setExpanded(false);
                        }}
                        renderOption={(r) => r.split('/').pop() ?? r}
                    />
                    <FilterChecks
                        ariaLabel="Filter the inbox by signal"
                        allLabel="All signals"
                        options={signals}
                        selected={sig}
                        onChange={(next) => {
                            setSig(next);
                            setExpanded(false);
                        }}
                    />
                    {filtering && (
                        <button
                            type="button"
                            onClick={clear}
                            className="font-mono text-[10px] text-link hover:underline"
                        >
                            clear
                        </button>
                    )}
                </div>
            </div>
            {filtered.length === 0 ? (
                <p className="px-4 py-2.5 text-[11px] text-muted-foreground">
                    No rows match this filter.{' '}
                    <button type="button" onClick={clear} className="text-link hover:underline">
                        Clear
                    </button>
                </p>
            ) : (
                shown.map((it, i) => (
                    <InboxItem
                        key={`${it.repo}-${it.signal}-${it.number ?? i}`}
                        it={it}
                        appName={appNames?.[it.repo]}
                    />
                ))
            )}
            {filtered.length > INBOX_COLLAPSED && (
                <button
                    type="button"
                    onClick={() => setExpanded((v) => !v)}
                    aria-expanded={expanded}
                    className="w-full px-4 py-1.5 text-left text-[10px] text-muted-foreground hover:bg-primary/5 hover:text-foreground"
                >
                    {expanded ? 'Show less' : `+${hidden} more, by ${SORT_NAME[sort]}`}
                </button>
            )}
        </div>
    );
};
