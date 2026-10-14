import type { ScopeComponent, Substance } from '@/models';

export const sevClass = (v: string): string =>
    /critical/i.test(v)
        ? 'text-destructive'
        : /high/i.test(v)
          ? 'text-amber-400'
          : 'text-muted-foreground';

export const thCls =
    'px-3 py-1.5 text-left font-mono text-[9.5px] font-semibold uppercase tracking-widest text-muted-foreground';

export type TabId =
    'overview' | 'estimate' | 'requirements' | 'phases' | 'assumptions' | 'architecture' | 'record';

export const selectScopeContent = (substance: Substance | null, record: string | null) => {
    const requirements = substance?.requirements ?? [];
    const phases = substance?.phases ?? [];
    const assumptions = substance?.assumptions ?? [];
    const activities = substance?.activities ?? [];
    const estimate = substance?.estimate;
    const arch = substance?.architecture;
    const guidelines = arch?.guidelines ?? [];
    const diagrams = arch?.diagrams ?? [];
    const componentsByPhase = (arch?.components ?? []).reduce<Record<string, ScopeComponent[]>>(
        (acc, c) => {
            (acc[c.phase] ??= []).push(c);
            return acc;
        },
        {},
    );

    const tabs: { id: TabId; label: string; count?: number }[] = [
        { id: 'overview', label: 'Overview' },
    ];
    if (estimate || activities.length)
        tabs.push({ id: 'estimate', label: 'Estimate', count: activities.length });
    if (requirements.length)
        tabs.push({ id: 'requirements', label: 'Requirements', count: requirements.length });
    if (phases.length) tabs.push({ id: 'phases', label: 'Phases', count: phases.length });
    if (assumptions.length)
        tabs.push({ id: 'assumptions', label: 'Assumptions', count: assumptions.length });
    if (guidelines.length || diagrams.length || Object.keys(componentsByPhase).length)
        tabs.push({
            id: 'architecture',
            label: 'Architecture',
            count: diagrams.length || undefined,
        });
    if (record) tabs.push({ id: 'record', label: 'Record' });
    return { componentsByPhase, tabs };
};
