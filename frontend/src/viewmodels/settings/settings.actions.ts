import { create } from 'zustand';
import { apiFetch } from '@/viewmodels/requests';
import type {
    DriverInfo,
    McpDoorsResponse,
    SessionInfo,
    RolesResponse,
    SettingResponse,
    GitIdentitiesResponse,
    PairCredentialsResponse,
    TeamsResponse,
} from '@/models';
import type { SettingsState } from './settings.state';

interface SettingsActions {
    loadDriver: () => Promise<DriverInfo>;
    loadSession: () => Promise<SessionInfo>;
    loadDoors: () => Promise<McpDoorsResponse>;
    loadSetting: (name: string) => Promise<Record<string, unknown>>;
    saveSetting: (
        name: string,
        fields: Record<string, string>,
        secret: string | null,
    ) => Promise<Record<string, unknown>>;
    loadIdentities: () => Promise<GitIdentitiesResponse>;
    loadRoles: () => Promise<RolesResponse>;
    saveIdentity: (
        name: string,
        email: string,
        login: string,
        token: string | null,
    ) => Promise<void>;
    deleteIdentity: (name: string) => Promise<void>;
    assignRoles: (roles: Record<string, string>) => Promise<RolesResponse>;
    loadPairs: () => Promise<PairCredentialsResponse>;
    savePair: (name: string, host: string, login: string, token: string | null) => Promise<void>;
    deletePair: (name: string) => Promise<void>;
    loadTeams: () => Promise<TeamsResponse>;
    saveTeam: (name: string, group: string) => Promise<void>;
    deleteTeam: (name: string) => Promise<void>;
    assignProject: (repository: string, team: string) => Promise<void>;
}

export const useSettings = create<SettingsState & SettingsActions>()((set) => ({
    loading: false,
    error: null,
    driver: null,
    session: null,
    doors: null,
    identities: [],
    roles: {},
    catalog: [],
    credentials: [],
    settings: {},
    teams: [],
    loadTeams: async () => {
        const response = await apiFetch<TeamsResponse>('/config/teams');
        set({ teams: response.teams });
        return response;
    },
    saveTeam: (name, group) => apiFetch('/config/teams', { name, group }),
    deleteTeam: (name) =>
        apiFetch(`/config/teams/${encodeURIComponent(name)}`, undefined, 'DELETE'),
    assignProject: (repository, team) => apiFetch('/config/team-projects', { repository, team }),
    loadDriver: async () => {
        const response = await apiFetch<DriverInfo>('/config/driver');
        set({ driver: response });
        return response;
    },
    loadSession: async () => {
        try {
            const response = await apiFetch<SessionInfo>('/config/session');
            set({ session: response });
            return response;
        } catch (error) {
            set({ session: null });
            throw error;
        }
    },
    loadDoors: async () => {
        const response = await apiFetch<McpDoorsResponse>('/config/mcp-doors');
        set({ doors: response.doors });
        return response;
    },
    loadSetting: async (name) => {
        const response = await apiFetch<SettingResponse>(
            `/config/setting/${encodeURIComponent(name)}`,
        );
        set((state) => ({ settings: { ...state.settings, [name]: response } }));
        return { ...response.fields, configured: response.configured };
    },
    saveSetting: async (name, fields, secret) => {
        const response = await apiFetch<SettingResponse>(
            `/config/setting/${encodeURIComponent(name)}`,
            { fields, secret },
        );
        set((state) => ({ settings: { ...state.settings, [name]: response } }));
        return { ...response.fields, configured: response.configured };
    },
    loadIdentities: async () => {
        const response = await apiFetch<GitIdentitiesResponse>('/config/git-identities');
        set({ identities: response.identities });
        return response;
    },
    loadRoles: async () => {
        const response = await apiFetch<RolesResponse>('/config/git-roles');
        set({ roles: response.roles, catalog: response.catalog });
        return response;
    },
    saveIdentity: (name, email, login, token) =>
        apiFetch('/config/git-identities', { name, email, login, token }),
    deleteIdentity: (name) =>
        apiFetch(`/config/git-identities/${encodeURIComponent(name)}`, undefined, 'DELETE'),
    assignRoles: async (roles) => {
        const response = await apiFetch<RolesResponse>('/config/git-roles', { roles });
        set({ roles: response.roles, catalog: response.catalog });
        return response;
    },
    loadPairs: async () => {
        const response = await apiFetch<PairCredentialsResponse>('/config/pair-credentials');
        set({ credentials: response.credentials });
        return response;
    },
    savePair: (name, host, login, token) =>
        apiFetch('/config/pair-credentials', { name, host, login, token }),
    deletePair: (name) =>
        apiFetch(`/config/pair-credentials/${encodeURIComponent(name)}`, undefined, 'DELETE'),
}));
