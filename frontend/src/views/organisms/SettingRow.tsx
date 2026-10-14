import { useSettings } from '@/viewmodels/settings';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';

import { Input } from '@/components/ui/input';

import { SettingStatus } from '@/views/atoms/SettingStatus';
import { SettingChevron } from '@/views/atoms/SettingChevron';

import { errorText, type SettingDef } from '@/viewmodels/settings/settings.model';

export const SettingRow: React.FC<{ def: SettingDef }> = ({ def }) => {
    const { settings, loadSetting, saveSetting } = useSettings();
    const name = def.name;
    const configured = settings[name]?.configured ?? false;
    // One string, so a def rebuilt on every parent render leaves the load effect still.
    const fieldKeys = def.fields.map((f) => f.key).join(' ');
    const [vals, setVals] = useState<Record<string, string>>({});
    const [secret, setSecret] = useState('');
    const [open, setOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;
        void (async () => {
            try {
                const c = await loadSetting(name);
                if (cancelled) return;
                const next: Record<string, string> = {};
                for (const key of fieldKeys.split(' '))
                    next[key] = typeof c[key] === 'string' ? (c[key] as string) : '';
                setVals(next);
            } catch (e) {
                if (!cancelled) setError(errorText(e));
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [loadSetting, name, fieldKeys]);

    const save = async () => {
        setSaving(true);
        setError(null);
        try {
            await saveSetting(name, vals, secret || null);
            setSecret('');
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
                        <span className="font-mono text-sm font-medium">{def.title}</span>
                        <SettingStatus configured={configured} />
                    </span>
                    {def.subtitle && (
                        <span className="text-xs text-muted-foreground">{def.subtitle}</span>
                    )}
                </span>
                <span className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
                    {open ? 'Close' : 'Edit'}
                    <SettingChevron open={open} />
                </span>
            </button>
            {open && (
                <div className="flex flex-col gap-2 px-4 pb-4">
                    {def.fields.map((f) => (
                        <Input
                            key={f.key}
                            placeholder={f.placeholder}
                            value={vals[f.key] ?? ''}
                            onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })}
                        />
                    ))}
                    <Input
                        type="password"
                        placeholder={
                            configured
                                ? `${def.secretLabel} (leave blank to keep)`
                                : def.secretLabel
                        }
                        value={secret}
                        onChange={(e) => setSecret(e.target.value)}
                    />
                    {error && <span className="text-xs text-destructive">{error}</span>}
                    <Button type="button" onClick={() => void save()} disabled={saving}>
                        {saving ? 'Saving...' : 'Save'}
                    </Button>
                </div>
            )}
        </div>
    );
};
