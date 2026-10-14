import { execFileSync } from 'node:child_process';
import path from 'node:path';

const cache = new Map<string, unknown>();

/** Browser fixtures carry the same pure backend projection as the real API. */
export const contractFixture = (data: unknown, runs: unknown[] = [], graphs: Record<string, unknown> = {}): unknown => {
    if (!data || typeof data !== 'object' || (!('phases' in data) && !('positions' in data))) return data;
    const input = JSON.stringify({ data, runs, graphs });
    if (!cache.has(input)) {
        const output = execFileSync(process.env.PYTHON ?? 'python', [path.resolve('e2e/project_fixture.py')], {
            input, encoding: 'utf8',
        });
        cache.set(input, JSON.parse(output));
    }
    return cache.get(input);
};
