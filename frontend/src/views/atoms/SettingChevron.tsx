import { cn } from '@/utils';

export const SettingChevron: React.FC<{ open: boolean }> = ({ open }) => (
    <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-90')}
        aria-hidden
    >
        <path d="M9 6l6 6-6 6" />
    </svg>
);
