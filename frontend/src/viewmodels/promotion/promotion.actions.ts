import type { PromotionDriveResponse, TargetDeclaredResponse } from '@/models';
import { create } from 'zustand';
import { apiFetch } from '@/viewmodels/requests';
import type { PromotionState, PromotionOptions, DeclareTargetIn } from '@/models';
import type { PromotionViewState } from './promotion.state';

interface PromotionActions {
    load: (repo: string) => Promise<void>;
    loadOptions: (repo: string) => Promise<void>;
    declare: (repo: string, target: Omit<DeclareTargetIn, 'repo'>) => Promise<boolean>;
    drive: (repo: string, target: string) => Promise<boolean>;
}

export const usePromotion = create<PromotionViewState & PromotionActions>((set) => ({
    state: null,
    loading: false,
    error: null,
    options: null,
    declaring: false,
    declareError: null,
    declared: null,
    driving: null,
    driveRepo: null,
    driveError: null,
    drove: null,
    droveRepo: null,
    async drive(repo: string, target: string) {
        set({ driving: target, driveRepo: repo, driveError: null, drove: null, droveRepo: null });
        try {
            const receipt = await apiFetch<PromotionDriveResponse>('/promotion/drive', {
                repo,
                target,
            });
            set({ drove: receipt, droveRepo: repo });
            // The door is performed by a worker, so where the target stands changes only once
            // that run lands: re-read rather than guess at a new state here.
            await usePromotion.getState().load(repo);
            return true;
        } catch (e) {
            set({ driveError: { repo, target, message: e instanceof Error ? e.message : String(e) } });
            return false;
        } finally {
            set({ driving: null });
        }
    },
    async loadOptions(repo: string) {
        try {
            const options = await apiFetch<PromotionOptions>(
                `/promotion/options?repo=${encodeURIComponent(repo)}`,
            );
            set({ options });
        } catch {
            // The form degrades to the pair kind, which needs no options.
            set({ options: { repo, readable: false, installs: [] } });
        }
    },
    async declare(repo: string, target: Omit<DeclareTargetIn, 'repo'>) {
        set({ declaring: true, declareError: null });
        try {
            const state = await apiFetch<TargetDeclaredResponse>('/promotion/target', {
                repo,
                ...target,
            });
            set({ state, declared: { target: state.target, commit: state.commit } });
            return true;
        } catch (e) {
            set({ declareError: e instanceof Error ? e.message : String(e) });
            return false;
        } finally {
            set({ declaring: false });
        }
    },
    async load(repo: string) {
        set({ loading: true, error: null });
        try {
            const state = await apiFetch<PromotionState>(
                `/promotion/state?repo=${encodeURIComponent(repo)}`,
            );
            set({ state });
        } catch (e) {
            set({ error: e instanceof Error ? e.message : String(e) });
        } finally {
            set({ loading: false });
        }
    },
}));
