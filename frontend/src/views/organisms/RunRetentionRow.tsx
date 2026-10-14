import { useSettings } from '@/viewmodels/settings';
import { useEffect, useState } from 'react';
import { cn } from '@/utils';

import { Button } from '@/components/ui/button';

import { Input } from '@/components/ui/input';

import { SettingChevron } from '@/views/atoms/SettingChevron';

import { errorText, RETENTION_FIELDS } from '@/viewmodels/settings/settings.model';

export const RunRetentionRow: React.FC = () => {
    const { loadSetting, saveSetting } = useSettings();
    const name = 'run-retention';
    const [vals, setVals] = useState<Record<string, string>>({});
    const [open, setOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const c = await loadSetting(name);
                if (cancelled) return;
                const next: Record<string, string> = {};
                for (const f of RETENTION_FIELDS)
                    next[f.key] = typeof c[f.key] === 'string' ? (c[f.key] as string) : '';
                setVals(next);
            } catch (e) {
                if (!cancelled) setError(errorText(e));
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [loadSetting, name]);

    const customized = RETENTION_FIELDS.some((f) => (vals[f.key] ?? '').trim() !== '');
    const save = async () => {
        setSaving(true);
        setError(null);
        try {
            await saveSetting(name, vals, null);
            setSaved(true);
            setOpen(false);
        } catch (e) {
            setError(errorText(e));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div>
            <button
                type="button"
                onClick={() => setOpen(!open)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40"
            >
                <span className="flex flex-col gap-0.5">
                    <span className="flex items-center gap-2.5">
                        <span className="font-mono text-sm font-medium">Run retention</span>
                        <span
                            className={cn(
                                'rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                                customized
                                    ? 'bg-primary/15 text-link'
                                    : 'bg-muted text-muted-foreground',
                            )}
                        >
                            {customized ? 'Custom' : 'Defaults'}
                        </span>
                        {saved && (
                            <span className="text-[11px] text-muted-foreground">
                                saved - applies from the next drive
                            </span>
                        )}
                    </span>
                    <span className="text-xs text-muted-foreground">
                        How long finished runs stay in the band and their logs stay readable. A
                        blank field runs the default.
                    </span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                    {open ? 'Close' : 'Edit'}
                    <SettingChevron open={open} />
                </span>
            </button>
            {open && (
                <div className="flex flex-col gap-2.5 px-4 pb-4">
                    {RETENTION_FIELDS.map((f) => (
                        <label key={f.key} className="flex flex-col gap-1">
                            <span className="text-xs font-medium">{f.label}</span>
                            <Input
                                type="number"
                                min={1}
                                placeholder={`${f.placeholder} (default)`}
                                value={vals[f.key] ?? ''}
                                onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })}
                            />
                            <span className="text-[11px] text-muted-foreground">{f.hint}</span>
                        </label>
                    ))}
                    {error && <span className="text-xs text-destructive">{error}</span>}
                    <Button type="button" onClick={() => void save()} disabled={saving}>
                        {saving ? 'Saving...' : 'Save'}
                    </Button>
                </div>
            )}
        </div>
    );
};
