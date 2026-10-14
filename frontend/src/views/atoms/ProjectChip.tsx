import { cn } from '@/utils';

export const ProjectChip: React.FC<{
    on: boolean;
    href?: string;
    children: React.ReactNode;
    tone?: string;
}> = ({ on, href, children, tone }) => {
    const cls = cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]',
        on ? (tone ?? 'bg-primary/15 text-link') : 'bg-muted text-faint',
    );
    const inner = (
        <>
            <span
                className={cn('h-1 w-1 rounded-full', on ? 'bg-current' : 'bg-muted-foreground/40')}
            />
            {children}
        </>
    );
    return on && href ? (
        <a
            href={href}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className={cn(cls, 'hover:underline')}
        >
            {inner}
        </a>
    ) : (
        <span className={cls}>{inner}</span>
    );
};
