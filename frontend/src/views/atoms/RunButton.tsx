import { cn } from '@/utils';

export const RunButton: React.FC<{
    onClick: () => void;
    disabled?: boolean;
    danger?: boolean;
    title?: string;
    className?: string;
    children: React.ReactNode;
}> = ({ onClick, disabled, danger, title, className, children }) => (
    <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        title={title}
        className={cn(
            'rounded-md border border-border px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 max-lg:px-3 max-lg:py-2',
            danger ? 'hover:border-destructive/60 hover:text-destructive' : 'hover:border-link/50',
            className,
        )}
    >
        {children}
    </button>
);
