import { lazy } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { AmbientField } from '@/views/atoms/AmbientField';

import { useStaleBundle } from '@/viewmodels/freshness';
import { RouterCockpit } from '@/views/templates/RouterCockpit';

const DeliveriesPage = lazy(() => import('@/views/pages/DeliveriesPage'));
const DeliveryDetailPage = lazy(() => import('@/views/pages/DeliveryDetailPage'));
const StudiosPage = lazy(() => import('@/views/pages/StudiosPage'));
const SettingsPage = lazy(() => import('@/views/pages/SettingsPage'));

export default function App() {
    const stale = useStaleBundle();
    return (
        <BrowserRouter>
            <AmbientField />
            {stale && (
                <div className="fixed inset-x-0 top-0 z-50 flex items-center justify-center gap-2 bg-primary px-4 py-1.5 text-sm text-primary-foreground shadow">
                    A new console version is live.
                    <button
                        type="button"
                        className="font-medium underline underline-offset-2"
                        onClick={() => window.location.reload()}
                    >
                        Reload
                    </button>
                </div>
            )}
            <Routes>
                <Route element={<RouterCockpit />}>
                    <Route index element={<DeliveriesPage />} />
                    <Route path="d" element={<DeliveryDetailPage />} />
                    <Route path="studios" element={<StudiosPage />} />
                    <Route path="settings" element={<SettingsPage />} />
                </Route>
            </Routes>
        </BrowserRouter>
    );
}
