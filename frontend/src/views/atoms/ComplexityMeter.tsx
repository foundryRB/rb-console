import { cn } from '@/utils';

/** The three complexity levels the Console reads from a ticket's `Complexity:` marker, low -> high.
 * A value's index here is the meter's filled-bar count. */
const LEVELS = ['low', 'medium', 'high'] as const;
type Level = (typeof LEVELS)[number];

/** The fill colour per level: green (light) -> amber -> red (heavy), the codebase's own semantic
 * scale. All filled bars take the value's colour, so 'high' reads as three red bars at a glance. */
const FILL: Record<Level, string> = {
    low: 'bg-[hsl(var(--success))]',
    medium: 'bg-amber-400',
    high: 'bg-destructive',
};

/** Signal-bar heights, short -> tall, so the meter reads as a strength gauge. */
const BAR_H = ['h-1.5', 'h-2.5', 'h-3.5'];

/** A ticket's author-declared complexity as a 3-segment signal meter (low -> high) - a hint for
 * which model tier to point at the task. Renders nothing when the value is not one of the three
 * levels, so a ticket with no `Complexity:` marker (a clean repo) shows no badge. */
export const ComplexityMeter: React.FC<{ value: string; className?: string }> = ({
    value,
    className,
}) => {
    const level = LEVELS.indexOf(value as Level);
    if (level < 0) return null;
    return (
        <span
            className={cn('inline-flex items-end gap-0.5', className)}
            title={`Complexity: ${value} - the author's sizing (match your model tier)`}
            aria-label={`Complexity ${value}`}
        >
            {BAR_H.map((h, i) => (
                <span
                    key={h}
                    className={cn(
                        'w-1 rounded-[1px]',
                        h,
                        i <= level ? FILL[value as Level] : 'bg-muted-foreground/25',
                    )}
                />
            ))}
        </span>
    );
};
