import type {
    DriverInfo,
    SessionInfo,
    GitIdentity,
    RoleDef,
    PairCredential,
    SettingResponse,
    Team,
} from '@/models';

export interface SettingsState {
    loading: boolean;
    error: string | null;
    driver: DriverInfo | null;
    session: SessionInfo | null;
    doors: string[] | null;
    identities: GitIdentity[];
    roles: Record<string, string>;
    catalog: RoleDef[];
    credentials: PairCredential[];
    settings: Record<string, SettingResponse>;
    /** The teams and their projects: an admin's read alone. */
    teams: Team[];
}
