import { create } from 'zustand';

import type { PwaState } from './pwa.state';

const INSTALL_HINT_DISMISSED_KEY = 'pwa.installHintDismissed';

interface PwaActions {
    start: () => void;
    dismissInstallHint: () => void;
}

function isIos(): boolean {
    const touchMac = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    return /iPad|iPhone|iPod/.test(navigator.userAgent) || touchMac;
}

function isStandalone(): boolean {
    const legacy = (navigator as Navigator & { standalone?: boolean }).standalone === true;
    return window.matchMedia('(display-mode: standalone)').matches || legacy;
}

function hintDismissed(): boolean {
    try {
        return window.localStorage.getItem(INSTALL_HINT_DISMISSED_KEY) === '1';
    } catch {
        return false;
    }
}

/**
 * Manifest only, so this domain owns the install hint and nothing else. It is
 * still the single place the rest of the app asks about its installed state, so
 * taking a service worker later changes this file and no view (REF-PWA section 10).
 */
export const usePwa = create<PwaState & PwaActions>()((set, get) => ({
    started: false,
    installHintVisible: false,

    start: () => {
        if (get().started) {
            return;
        }
        set({ started: true, installHintVisible: isIos() && !isStandalone() && !hintDismissed() });
    },

    dismissInstallHint: () => {
        try {
            window.localStorage.setItem(INSTALL_HINT_DISMISSED_KEY, '1');
        } catch {
            // Storage unavailable; the hint comes back next launch.
        }
        set({ installHintVisible: false });
    },
}));
