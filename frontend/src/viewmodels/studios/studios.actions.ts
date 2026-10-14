import { create } from 'zustand';
import type { StudiosResponse } from '@/models';
import { apiFetch } from '@/viewmodels/requests';

import type { StudiosState } from './studios.state';

interface StudiosActions {
    loadStudios: () => Promise<void>;
}
export const useStudios = create<StudiosState & StudiosActions>()((set) => ({
    studios: [],
    studiosLoading: false,
    loadStudios: async () => {
        set({ studiosLoading: true });
        try {
            const body = await apiFetch<StudiosResponse>('/studios');
            set({ studios: body.studios });
        } catch {
            // the studios strip degrades silently; a studio just reads as unreachable
        } finally {
            set({ studiosLoading: false });
        }
    },
}));
