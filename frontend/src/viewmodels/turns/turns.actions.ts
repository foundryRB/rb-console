import type { ChatTurnPoll, FleetResponse } from '@/models';
import { apiFetch } from '@/viewmodels/requests';
export class TurnStillRunning extends Error {}

/** The client's own give-up, not a bound on the work. It clears the 180s model bound a chat
 * turn is held to server-side; the fleet rescan (routed through the same turn since issue
 * #36) has no server-side bound at all, so for that one this is a wait limit and nothing
 * more. The e2e harness shortens it through `window.__turnDeadlineMs` so the give-up path is
 * testable without a 200s test; nothing sets it in production. Issue #39. */
const TURN_DEADLINE_MS = 200_000;
const turnDeadlineMs = (): number =>
    (globalThis as { __turnDeadlineMs?: number }).__turnDeadlineMs ?? TURN_DEADLINE_MS;

/** Redeem a started turn, whatever work it runs. The work behind a turn outlasts the proxy
 * chain in front of the pod (the old synchronous POSTs were severed at oauth2-proxy's 30s
 * upstream default - a bare "Error: 502" mid-chat, INT-FC-R55, and the same on the
 * masthead's refresh, INT-FC-R107), so the backend runs it in a thread and we poll until
 * the result (or the turn's error) lands. `redeem` shapes the done poll and `what` names
 * the work in a failure; the schedule, the deadline and the error contract live here once,
 * for every kind of turn. */
export const awaitTurn = async <T>(
    turn: string,
    redeem: (poll: ChatTurnPoll) => T,
    what = 'turn',
    deadlineMs = turnDeadlineMs(),
): Promise<T> => {
    const deadline = Date.now() + deadlineMs;
    let wait = 400; // quick first polls (a not-configured turn lands near-instantly)
    for (;;) {
        await new Promise((r) => setTimeout(r, wait));
        wait = Math.min(wait * 2, 2000);
        const poll = await apiFetch<ChatTurnPoll>(`/chat/turns/${turn}`);
        if (poll.status === 'done') return redeem(poll);
        if (poll.status === 'error') throw new Error(poll.error || `the ${what} failed`);
        if (Date.now() > deadline) throw new TurnStillRunning(`the ${what} is still running`);
    }
};

/** The co-pilot's reply out of a done poll (INT-FC-R55): a turn that ran but was not
 * configured legitimately carries no reply, so the degrade is a shape, not a failure. */
export const chatResult = (
    poll: ChatTurnPoll,
): Required<Pick<ChatTurnPoll, 'reply' | 'configured' | 'model'>> => ({
    reply: poll.reply ?? null,
    configured: poll.configured ?? false,
    model: poll.model ?? null,
});

/** The rescanned fleet out of a done poll (INT-FC-R107). Unlike a chat reply, an absent
 * payload here has no honest degrade: defaulting to [] would blank the board, stamp the
 * refreshed-at and flash the ✓ - a failed refresh wearing a successful one's face, which
 * is the one thing the forced refresh must never do.
 *
 * `!poll.projects` alone did not hold that line: [] is truthy in JS, so an empty fleet
 * sailed through the guard written to stop exactly this and wore the ✓ anyway. The server
 * now says whether the board it answered is current or held (INT-FC-R144), which is the
 * fact the guard was reaching for - a scan that could not be made is a failed refresh
 * however many projects it managed to return. */
export const fleetResult = (poll: ChatTurnPoll): FleetResponse => {
    if (!poll.projects) throw new Error('the refresh answered no fleet');
    if (poll.stale_since) throw new Error(poll.stale_reason || 'the rescan could not read the org');
    return {
        projects: poll.projects,
        stale_since: poll.stale_since,
        stale_reason: poll.stale_reason,
        freshness: poll.freshness,
    };
};
