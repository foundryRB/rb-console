import { cn } from '@/utils';

export interface PaneOption {
    key: string;
    label: string;
}

/** The mobile-only (below lg) tab bar that picks which pane of a two-pane cockpit shows.
 * At lg the two panes sit side by side and this bar is hidden (lg:hidden), so it never
 * touches the desktop cockpit - it only chooses the visible pane on phones and tablet
 * portrait, where a side-by-side split would starve both panes of width. */
export const PaneToggle: React.FC<{
    options: PaneOption[];
    active: string;
    onSelect: (key: string) => void;
}> = ({ options, active, onSelect }) => (
    <div className="flex flex-none gap-1 rounded-lg border border-border bg-well/20 p-1 lg:hidden">
        {options.map((o) => (
            <button
                key={o.key}
                type="button"
                aria-pressed={active === o.key}
                onClick={() => onSelect(o.key)}
                className={cn(
                    'min-h-[40px] flex-1 rounded-md px-3 text-xs font-semibold transition-colors',
                    active === o.key
                        ? 'bg-secondary text-secondary-foreground'
                        : 'text-muted-foreground hover:text-foreground',
                )}
            >
                {o.label}
            </button>
        ))}
    </div>
);
