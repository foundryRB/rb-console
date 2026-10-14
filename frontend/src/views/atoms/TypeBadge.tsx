import { cn } from '@/utils';

/** The colour per known org Issue Type, keyed by the lowercased name. Bug reads as a problem
 * (red), Feature as new work (violet), Task as plain work (slate). An org type outside this set
 * still renders, in a neutral tint, so a custom type is shown rather than dropped. */
const TONE: Record<string, string> = {
    bug: 'border-destructive/40 bg-destructive/10 text-destructive',
    feature: 'border-violet-400/40 bg-violet-400/10 text-violet-400',
    task: 'border-slate-400/40 bg-slate-400/10 text-slate-300',
};

const NEUTRAL = 'border-border bg-muted/40 text-muted-foreground';

/** A ticket's native GitHub Issue Type as a small pill (Bug / Feature / Task, or whatever the
 * org named it). Renders nothing when the ticket has no type, so an untyped ticket shows no
 * badge - the same invisible-until-set discipline as the complexity meter and priority arrow. */
export const TypeBadge: React.FC<{ value: string; className?: string }> = ({
    value,
    className,
}) => {
    if (!value) return null;
    return (
        <span
            className={cn(
                'rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wide',
                TONE[value.toLowerCase()] ?? NEUTRAL,
                className,
            )}
            title={`Type: ${value} (GitHub issue type)`}
        >
            {value}
        </span>
    );
};
