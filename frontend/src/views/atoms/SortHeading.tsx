import { cn } from '@/utils';

import { type SortKey } from '@/viewmodels/fleet/fleet.model';

export const SortHeading: React.FC<{
    label: string;
    sortKey: SortKey;
    active: SortKey | null;
    dir: 'asc' | 'desc';
    onSort: (k: SortKey) => void;
}> = ({ label, sortKey, active, dir, onSort }) => (
    <th className="px-4 py-2.5 text-left font-medium">
        <button
            type="button"
            onClick={() => onSort(sortKey)}
            className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-foreground"
        >
            {label}
            <span className={cn('text-[9px]', active === sortKey ? 'text-link' : 'text-faint')}>
                {active === sortKey ? (dir === 'asc' ? '▲' : '▼') : '↕'}
            </span>
        </button>
    </th>
);
