import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';

import { Loading } from '@/views/organisms/Loading';

export const RouterCockpit: React.FC = () => (
    <Suspense fallback={<Loading />}>
        <Outlet />
    </Suspense>
);
