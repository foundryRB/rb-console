import { create } from 'zustand';
import type { ErrorResponse, OperationReceiptResponse } from '@/models';
import type { RequestsState } from './requests.state';

export const useRequests = create<RequestsState>()(() => ({ operations: {}, revisions: {} }));

/**
 * The sign-in proxy's own route, which starts a fresh OIDC round trip and returns to
 * `rd` when it completes. The console is fronted by oauth2-proxy, whose prefix this is.
 */
const SIGN_IN = '/oauth2/start';

/**
 * Send the browser out of the SPA to re-authenticate, returning to where it was.
 * A full-page navigation, not a route change: the route belongs to the proxy sidecar,
 * the same reason the Settings Sign out control is an `<a href>` (INT-FC-R159).
 */
function reauthenticate(): void {
    const back = window.location.pathname + window.location.search;
    window.location.assign(`${SIGN_IN}?rd=${encodeURIComponent(back)}`);
}

/** Raise the backend's error detail when a response is not ok. */
async function unwrap<T>(res: Response): Promise<T> {
    if (res.status === 401) {
        // The session lapsed under a running page. Nothing in the app can recover it, so
        // hand the browser to the proxy rather than surface "401" as a widget error. This
        // is reachable only because every call below asks for JSON: without that header
        // the proxy answers a redirect to the identity provider instead, which a fetch
        // cannot act on - and in a Home Screen web app there is no address bar to escape
        // to (REF-PWA section 7).
        reauthenticate();
        throw new Error('Session expired; signing in again.');
    }
    if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
            const body = (await res.json()) as { detail?: unknown };
            const d = body.detail;
            // FastAPI request-validation errors put an ARRAY of {loc, msg, type} on `detail`;
            // a raised HTTPException puts a string. Flatten either to readable text so the UI
            // never renders a bare "[object Object]" (the reported timeout error).
            if (typeof d === 'string') detail = d;
            else if (Array.isArray(d))
                detail =
                    d
                        .map((e) =>
                            e && typeof e === 'object' && 'msg' in e
                                ? String((e as { msg: unknown }).msg)
                                : String(e),
                        )
                        .join('; ') || detail;
            else if (d != null) detail = JSON.stringify(d);
        } catch {
            // non-JSON error body; keep the status text
        }
        throw new Error(detail);
    }
    return res.json() as Promise<T>;
}

const unresolved = new Map<string, string>();

const subjectFor = (path: string, body?: unknown): string => {
    if (body && typeof body === 'object') {
        const value = body as Record<string, unknown>;
        for (const key of ['repo', 'target', 'handle']) {
            if (typeof value[key] === 'string') return value[key];
        }
    }
    const query = new URLSearchParams(path.split('?')[1] ?? '');
    return query.get('repo') ?? query.get('target') ?? query.get('handle') ?? path.split('?')[0];
};

export async function apiFetch<T>(path: string, body?: unknown, method?: string): Promise<T> {
    const verb = method ?? (body === undefined ? 'GET' : 'POST');
    const command = !['GET', 'HEAD', 'OPTIONS'].includes(verb);
    const subject = subjectFor(path, body);
    const fingerprint = `${verb}:${path}:${JSON.stringify(body)}`;
    const operation_id = command ? (unresolved.get(fingerprint) ?? crypto.randomUUID()) : null;
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (operation_id) {
        headers['Idempotency-Key'] = operation_id;
        const revision = useRequests.getState().revisions[subject];
        if (revision) headers['If-Match'] = revision.startsWith('"') ? revision : `"${revision}"`;
        useRequests.setState((state) => ({
            operations: {
                ...state.operations,
                [operation_id]: {
                    operation_id,
                    path,
                    status: 'pending',
                    detail: 'Awaiting receipt',
                },
            },
        }));
    }
    let res: Response;
    try {
        res = await fetch(`/api${path}`, {
            method: verb,
            headers,
            body: body === undefined ? undefined : JSON.stringify(body),
        });
    } catch (error) {
        if (operation_id) {
            unresolved.set(fingerprint, operation_id);
            const detail = `Outcome unknown. Operation ${operation_id}: check its receipt before repeating the action.`;
            useRequests.setState((state) => ({
                operations: {
                    ...state.operations,
                    [operation_id]: { operation_id, path, status: 'unknown', detail },
                },
            }));
            throw new Error(detail, { cause: error });
        }
        throw error;
    }
    const revision = res.headers.get('ETag') ?? res.headers.get('X-Source-Revision');
    if (revision)
        useRequests.setState((state) => ({
            revisions: { ...state.revisions, [subject]: revision },
        }));
    let failure: Partial<ErrorResponse> = {};
    if (!res.ok) {
        try {
            failure = (await res.clone().json()) as Partial<ErrorResponse>;
        } catch {
            /* HTTP status remains available. */
        }
    }
    try {
        const result = await unwrap<T>(res);
        if (
            result &&
            typeof result === 'object' &&
            'revision' in result &&
            typeof result.revision === 'string'
        ) {
            const sourceRevision = result.revision;
            useRequests.setState((state) => ({
                revisions: { ...state.revisions, [subject]: sourceRevision },
            }));
        }
        if (operation_id) {
            unresolved.delete(fingerprint);
            useRequests.setState((state) => ({
                operations: {
                    ...state.operations,
                    [operation_id]: {
                        operation_id,
                        path,
                        status: 'complete',
                        detail: 'Receipt received',
                    },
                },
            }));
        }
        return result;
    } catch (error) {
        if (operation_id) {
            // The server answers `source_unavailable` for a command only before dispatch, when
            // nothing was done; from dispatch on, every failure answers `operation_unknown`. So
            // that refusal's outcome is known, and a retry is a new operation. Every other
            // server error, a truncated success, and an explicit unknown stay unknown.
            const notDispatched = failure.code === 'source_unavailable';
            const unknown =
                res.ok ||
                (res.status >= 500 && !notDispatched) ||
                failure.code === 'operation_unknown';
            if (unknown) unresolved.set(fingerprint, operation_id);
            const detail = error instanceof Error ? error.message : String(error);
            useRequests.setState((state) => ({
                operations: {
                    ...state.operations,
                    [operation_id]: {
                        operation_id,
                        path,
                        status: unknown ? 'unknown' : res.status === 409 ? 'conflict' : 'refused',
                        operation_key: failure.operation_key ?? undefined,
                        detail,
                    },
                },
            }));
            // The receipt is looked up by its operation key, so the key is what the message
            // names when the server returned one; the request's own id otherwise.
            const named = failure.operation_key ?? operation_id;
            if (res.status === 409 && !unknown)
                throw new Error(
                    `Conflict: ${detail}. Refresh current state before submitting again. Operation ${named}`,
                    { cause: error },
                );
            if (unknown)
                throw new Error(`Outcome unknown. Operation ${named}: ${detail}`, {
                    cause: error,
                });
        }
        throw error;
    }
}

export async function inspectReceipt(operation_id: string): Promise<void> {
    const operation = useRequests.getState().operations[operation_id];
    if (!operation?.operation_key) return;
    try {
        const receipt = await apiFetch<OperationReceiptResponse>(
            `/operations/${encodeURIComponent(operation.operation_key)}`,
        );
        useRequests.setState((state) => ({
            operations: {
                ...state.operations,
                [operation_id]: {
                    ...state.operations[operation_id],
                    receipt,
                    receipt_error: undefined,
                },
            },
        }));
    } catch (error) {
        useRequests.setState((state) => ({
            operations: {
                ...state.operations,
                [operation_id]: {
                    ...state.operations[operation_id],
                    receipt_error: error instanceof Error ? error.message : String(error),
                },
            },
        }));
    }
}
