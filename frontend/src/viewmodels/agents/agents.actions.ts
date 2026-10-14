import { create } from 'zustand';
import type { AgentsResponse } from '@/models';
import { apiFetch } from '@/viewmodels/requests';

import { useDeliveries } from '@/viewmodels/deliveries';
import type { AgentsState } from './agents.state';
const errorText = (err: unknown): string => (err instanceof Error ? err.message : 'Unknown error');

interface AgentsActions {
    loadAgents: () => Promise<void>;
    saveAgent: (
        name: string,
        provider: string,
        base_url: string,
        model: string,
        credential: string,
        models?: string[],
        level?: string,
        team?: string,
    ) => Promise<boolean>;
    deleteAgent: (name: string) => Promise<void>;
    applyAgentToDriver: (name: string, model?: string) => Promise<void>;
    applyAgentToDelivery: (target: string, name: string, model?: string) => Promise<void>;
}
export const useAgents = create<AgentsState & AgentsActions>()((set, get) => ({
    agents: [],
    agentsLoading: false,
    loadAgents: async () => {
        set({ agentsLoading: true });
        try {
            const body = await apiFetch<AgentsResponse>('/agents');
            set({ agents: body.agents });
        } catch {
            // the registry degrades to empty
        } finally {
            set({ agentsLoading: false });
        }
    },
    saveAgent: async (name, provider, base_url, model, credential, models, level, team) => {
        useDeliveries.setState({ actionLoading: true, actionError: null });
        try {
            await apiFetch('/agents', {
                name,
                provider,
                base_url,
                model,
                credential,
                models: models ?? [],
                level: level ?? 'install',
                team: team ?? '',
            });
            await get().loadAgents();
            return true;
        } catch (err) {
            useDeliveries.setState({ actionError: errorText(err) });
            return false;
        } finally {
            useDeliveries.setState({ actionLoading: false });
        }
    },
    deleteAgent: async (name: string) => {
        useDeliveries.setState({ actionLoading: true, actionError: null });
        try {
            await apiFetch(`/agents/${encodeURIComponent(name)}`, undefined, 'DELETE');
            await get().loadAgents();
        } catch (err) {
            useDeliveries.setState({ actionError: errorText(err) });
        } finally {
            useDeliveries.setState({ actionLoading: false });
        }
    },
    applyAgentToDriver: async (name: string, model?: string) => {
        useDeliveries.setState({ actionLoading: true, actionError: null });
        try {
            await apiFetch(`/agents/${encodeURIComponent(name)}/apply-driver`, {
                model: model ?? '',
            });
        } catch (err) {
            useDeliveries.setState({ actionError: errorText(err) });
        } finally {
            useDeliveries.setState({ actionLoading: false });
        }
    },
    applyAgentToDelivery: async (target: string, name: string, model?: string) => {
        useDeliveries.setState({ actionLoading: true, actionError: null });
        try {
            await apiFetch(`/agents/${encodeURIComponent(name)}/apply-delivery`, {
                target,
                model: model ?? null,
            });
            await useDeliveries.getState().loadOverview(target); // reflect the applied agent + model on the target
        } catch (err) {
            useDeliveries.setState({ actionError: errorText(err) });
        } finally {
            useDeliveries.setState({ actionLoading: false });
        }
    },
}));
