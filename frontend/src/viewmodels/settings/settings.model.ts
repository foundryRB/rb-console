export const errorText = (e: unknown): string => (e instanceof Error ? e.message : 'Unknown error');

export interface FieldDef {
    key: string;
    placeholder: string;
}

export interface SettingDef {
    title: string;
    subtitle: string;
    name: string; // the setting name under /api/config/setting/<name>
    fields: FieldDef[];
    secretLabel: string;
}

export const RETENTION_FIELDS = [
    {
        key: 'pod_gc_delay_hours',
        label: 'Pod GC delay (hours)',
        placeholder: '1',
        hint: 'how long a finished run’s pods - and its live logs - linger before reclaim',
    },
    {
        key: 'ttl_success_days',
        label: 'Succeeded runs stay listed (days)',
        placeholder: '7',
        hint: 'how long a green run stays in the band’s history',
    },
    {
        key: 'ttl_failure_days',
        label: 'Failed runs stay listed (days)',
        placeholder: '30',
        hint: 'how long a failed run - and every log snapshot - is kept; never below the succeeded horizon',
    },
];

export const mcpDoorSetting = (door: string): SettingDef => ({
    title: door,
    subtitle: '',
    name: `mcp-${door}`,
    fields: [{ key: 'user', placeholder: 'user' }],
    secretLabel: 'password',
});
