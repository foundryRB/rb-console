import { FilterDropdown } from '@/views/molecules/FilterDropdown';

import { type InboxSort, SORT_OPTIONS, optionCls } from '@/viewmodels/fleet/fleet.model';

export const InboxSortMenu: React.FC<{ value: InboxSort; onChange: (next: InboxSort) => void }> = ({
    value,
    onChange,
}) => (
    <FilterDropdown ariaLabel="Sort the inbox" summary={`by ${value}`} closeOnPick>
        {SORT_OPTIONS.map((o) => (
            <label key={o} className={optionCls}>
                <input
                    type="radio"
                    name="inbox-sort"
                    checked={value === o}
                    onChange={() => onChange(o)}
                    className="accent-primary"
                />
                by {o}
            </label>
        ))}
    </FilterDropdown>
);
