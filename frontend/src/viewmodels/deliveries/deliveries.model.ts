import type { State, PhaseCell } from '@/models';
import type { DeliveriesState } from './deliveries.state';

export type { PhaseCell } from '@/models';
export type PhaseStep = PhaseCell['step'];

export const selectPhaseStrip = (state: State): PhaseCell[] => state.phase_cells ?? [];
export const selectPendingGate = (state: State): string | null => state.pending_gate ?? null;

export function repoName(repo: string): string {
    const parts = repo.split(/[\\/]/).filter(Boolean);
    return parts.length > 0 ? parts[parts.length - 1] : repo;
}

export const selectDeliveries = (state: DeliveriesState): State[] => state.deliveries;
export const selectDeliveryCount = (state: DeliveriesState): number => state.deliveries.length;
