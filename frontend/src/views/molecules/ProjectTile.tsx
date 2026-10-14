import { cn } from '@/utils';

export const ProjectTile: React.FC<{
    n: number;
    label: string;
    accent?: string;
    active?: boolean;
    onClick?: () => void;
}> = ({ n, label, accent, active, onClick }) => (
    <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        title={`Filter to ${label.toLowerCase()}`}
        className={cn(
            'app-glass cursor-pointer rounded-lg border px-4 py-3 text-left transition-colors',
            active ? 'border-link ring-1 ring-link/40' : 'border-border hover:border-link/50',
        )}
    >
        <div
            className={cn('font-mono text-2xl font-bold tabular-nums', accent ?? 'text-foreground')}
        >
            {n}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
            {label}
            {active && ' · filtering'}
        </div>
    </button>
);
