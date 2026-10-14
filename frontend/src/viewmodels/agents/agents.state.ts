import type { Agent } from '@/models';
export interface AgentsState {
    agents: Agent[];
    agentsLoading: boolean;
}
