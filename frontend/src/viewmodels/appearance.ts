import { useSyncExternalStore } from 'react';

export type Appearance = 'light' | 'dark' | 'system';
declare global {
    interface Window {
        vodafoneAppearance: {
            get(): { preference: Appearance; resolved: 'dark' | 'light'; motion: boolean; reduced: boolean };
            set(value: Appearance): void;
            setMotion(enabled: boolean): void;
        };
    }
}
const subscribe = (notify: () => void) => {
    document.addEventListener('vodafone-appearance', notify);
    return () => document.removeEventListener('vodafone-appearance', notify);
};
// Primitive snapshots stay referentially stable between appearance events.
export const useAppearance = () => {
    const preference = useSyncExternalStore(subscribe, () => window.vodafoneAppearance.get().preference);
    const resolved = useSyncExternalStore(subscribe, () => window.vodafoneAppearance.get().resolved);
    const motion = useSyncExternalStore(subscribe, () => window.vodafoneAppearance.get().motion);
    const reduced = useSyncExternalStore(subscribe, () => window.vodafoneAppearance.get().reduced);
    return { preference, resolved, motion, reduced, set: window.vodafoneAppearance.set, setMotion: window.vodafoneAppearance.setMotion };
};
