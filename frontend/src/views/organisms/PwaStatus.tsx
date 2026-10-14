import { useEffect } from 'react';

import { usePwa } from '@/viewmodels/pwa';
import { InstallHint } from '@/views/molecules/InstallHint';

/** Mount once in the layout template: starts the PWA domain and shows the install hint. */
export const PwaStatus: React.FC = () => {
    const { start, installHintVisible, dismissInstallHint } = usePwa();

    useEffect(() => {
        start();
    }, [start]);

    if (!installHintVisible) {
        return null;
    }
    return (
        <div className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-md flex-col gap-2">
            <InstallHint onDismiss={dismissInstallHint} />
        </div>
    );
};
