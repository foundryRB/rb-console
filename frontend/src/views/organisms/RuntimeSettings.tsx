import { useSettings } from '@/viewmodels/settings';
import { useEffect, useState } from 'react';

import { HomeCoPilotRow } from '@/views/organisms/HomeCoPilotRow';
import { RunRetentionRow } from '@/views/organisms/RunRetentionRow';

import { SettingRow } from '@/views/organisms/SettingRow';
import { SettingGroup } from '@/views/molecules/SettingGroup';
import { errorText, mcpDoorSetting } from '@/viewmodels/settings/settings.model';

export const RuntimeSettings: React.FC = () => {
    const { doors, loadDoors } = useSettings();
    const [doorsError, setDoorsError] = useState<string | null>(null);

    useEffect(() => {
        loadDoors().catch((e) => setDoorsError(errorText(e)));
    }, [loadDoors]);

    return (
        <div className="flex flex-col gap-8">
            <SettingGroup title="Home co-pilot">
                <HomeCoPilotRow />
            </SettingGroup>

            <SettingGroup
                title="Run retention"
                hint="The executor's garbage collection: pods (live logs), run rows (the band's history), and log snapshots expire on these horizons. Applies from the next drive."
            >
                <RunRetentionRow />
            </SettingGroup>

            <SettingGroup
                title="MCP doors"
                hint="The studios the worker connects to over MCP, each with its own Basic-auth credential. CSD (the intent+plan methodology) runs locally and has no door."
            >
                {doorsError ? (
                    <p className="px-4 py-3 text-xs text-destructive">{doorsError}</p>
                ) : doors === null ? (
                    <p className="px-4 py-3 text-xs text-muted-foreground">Loading doors...</p>
                ) : (
                    doors.map((door) => <SettingRow key={door} def={mcpDoorSetting(door)} />)
                )}
            </SettingGroup>
        </div>
    );
};
