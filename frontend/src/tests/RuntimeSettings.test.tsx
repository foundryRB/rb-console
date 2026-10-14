import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

import { useSettings } from '@/viewmodels/settings';
import { RuntimeSettings } from '@/views/organisms/RuntimeSettings';

const DOORS = ['door-a', 'door-b', 'door-c', 'door-d'];
const SETTING = '/config/setting/';
// Room for every row to load a few times; past it a runaway loop stalls instead of hanging the run.
const BUDGET = 3 * (DOORS.length + 1);

const apiFetch = vi.hoisted(() => vi.fn<(path: string) => Promise<unknown>>());

vi.mock('@/viewmodels/requests', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/viewmodels/requests')>()),
    apiFetch,
}));

afterEach(cleanup);

const settingLoads = () =>
    apiFetch.mock.calls.map(([path]) => path).filter((path) => path.startsWith(SETTING));

// The Settings page subscribes to the whole store, so every settings write re-renders the rows.
const WholeStoreParent: React.FC = () => {
    useSettings();
    return <RuntimeSettings />;
};

test('each MCP door row loads its setting once, though every load writes the store', async () => {
    apiFetch.mockImplementation(async (path) => {
        if (path === '/config/mcp-doors') return { doors: DOORS };
        if (path.startsWith(SETTING)) {
            if (settingLoads().length > BUDGET) return new Promise(() => undefined);
            return { configured: false, fields: {} };
        }
        if (path === '/agents') return { agents: [] };
        if (path === '/config/driver') return { agent: '', model: '' };
        return {};
    });

    render(<WholeStoreParent />);
    for (const door of DOORS) await screen.findByRole('button', { name: new RegExp(door) });
    await act(() => new Promise((resolve) => setTimeout(resolve, 200)));

    const loads = settingLoads();
    expect(loads.filter((path) => path.startsWith(`${SETTING}mcp-`)).sort()).toEqual(
        DOORS.map((door) => `${SETTING}mcp-${door}`),
    );
    expect(loads.filter((path) => path === `${SETTING}run-retention`)).toHaveLength(1);
});
