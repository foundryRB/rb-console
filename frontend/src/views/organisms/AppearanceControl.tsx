import { useAppearance, type Appearance } from '@/viewmodels/appearance';

export const AppearanceControl = () => {
    const appearance = useAppearance();
    return (
        <div className="rb-appearance">
            <label>
                <span className="sr-only">Appearance</span>
                <select
                    aria-label="Appearance"
                    value={appearance.preference}
                    onChange={(e) => appearance.set(e.target.value as Appearance)}
                >
                    <option value="light">Light</option>
                    <option value="dark">Dark</option>
                    <option value="system">System</option>
                </select>
            </label>
        </div>
    );
};
