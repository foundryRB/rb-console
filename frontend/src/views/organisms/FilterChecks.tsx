import { FilterDropdown } from '@/views/molecules/FilterDropdown';

import { optionCls } from '@/viewmodels/fleet/fleet.model';

export const FilterChecks: React.FC<{
    ariaLabel: string;
    allLabel: string;
    options: string[];
    selected: Set<string>;
    onChange: (next: Set<string>) => void;
    renderOption?: (o: string) => string;
}> = ({ ariaLabel, allLabel, options, selected, onChange, renderOption }) => {
    const label = renderOption ?? ((o: string) => o);

    const toggle = (o: string) => {
        const next = new Set(selected);
        if (next.has(o)) next.delete(o);
        else next.add(o);
        onChange(next);
    };

    const summary =
        selected.size === 0
            ? allLabel
            : selected.size === 1
              ? label([...selected][0])
              : `${selected.size} selected`;

    return (
        <FilterDropdown ariaLabel={ariaLabel} summary={summary}>
            {options.map((o) => (
                <label key={o} className={optionCls}>
                    <input
                        type="checkbox"
                        checked={selected.has(o)}
                        onChange={() => toggle(o)}
                        className="accent-primary"
                    />
                    {label(o)}
                </label>
            ))}
        </FilterDropdown>
    );
};
