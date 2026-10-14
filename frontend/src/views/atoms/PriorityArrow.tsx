import { cn } from '@/utils';

/** The five priority levels the Console reads from a ticket's `Priority:` marker (the usual Jira
 * scale), and the arrow glyph + colour each renders as: double-down / down (cool) through up /
 * double-up (hot). */
const ARROW: Record<string, { glyph: string; color: string; label: string }> = {
    lowest: { glyph: '⇊', color: 'text-sky-400', label: 'Lowest' }, // ⇊
    low: { glyph: '↓', color: 'text-sky-400', label: 'Low' }, // ↓
    medium: { glyph: '→', color: 'text-amber-400', label: 'Medium' }, // →
    high: { glyph: '↑', color: 'text-orange-400', label: 'High' }, // ↑
    highest: { glyph: '⇈', color: 'text-destructive', label: 'Highest' }, // ⇈
};

/** A ticket's author-declared priority as a single coloured arrow (the usual five-level scale).
 * Renders nothing when the value is not a known level, so a ticket with no `Priority:` marker
 * shows no arrow. */
export const PriorityArrow: React.FC<{ value: string; className?: string }> = ({
    value,
    className,
}) => {
    const a = ARROW[value];
    if (!a) return null;
    return (
        <span
            className={cn('inline-flex font-bold leading-none', a.color, className)}
            title={`Priority: ${a.label}`}
            aria-label={`Priority ${a.label}`}
        >
            {a.glyph}
        </span>
    );
};
