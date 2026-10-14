import { cn } from '@/utils';

export const SettingStatus: React.FC<{ configured: boolean }> = ({ configured }) => (
    <span
        className={cn(
            'rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
            configured ? 'bg-primary/15 text-link' : 'bg-muted text-muted-foreground',
        )}
    >
        {configured ? 'Configured' : 'Not set'}
    </span>
);
