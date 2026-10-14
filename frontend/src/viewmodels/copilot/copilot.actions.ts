import { create } from 'zustand';
import type { ChatMessage, ChatTurn } from '@/models';
import { apiFetch } from '@/viewmodels/requests';

import { awaitTurn, chatResult } from '@/viewmodels/turns/turns.actions';

import { useDeliveries } from '@/viewmodels/deliveries';
import type { CopilotState } from './copilot.state';
const errorText = (err: unknown): string => (err instanceof Error ? err.message : 'Unknown error');
export const chatKey = (repo: string, mode: 'delivery' | 'maintenance'): string =>
    `${repo}::${mode}`;

/** A stable empty thread. A keyed selector miss must return THIS, not a fresh [], or
 * zustand's reference-equality check re-renders every tick. */
export const EMPTY_CHAT: ChatMessage[] = [];

interface CopilotActions {
    sendChat: (repo: string, phase: string, message: string) => Promise<void>;
    clearChat: (repo: string, phase: string) => void;
    sendFleetChat: (message: string) => Promise<void>;
    clearFleetChat: () => void;
}
export const useCopilot = create<CopilotState & CopilotActions>()((set, get) => ({
    chats: {},
    chatBusyKeys: {},
    chatConfigured: null,
    chatModel: null,
    fleetChat: [],
    fleetChatBusy: false,
    fleetChatConfigured: null,
    fleetChatModel: null,
    sendChat: async (repo: string, phase: string, message: string) => {
        // The thread is scoped to (repo, mode): a maintenance turn (phase 'maintenance')
        // and a delivery turn keep separate threads, and neither bleeds into another repo's
        // cockpit. The key is captured HERE, so a reply that lands after the operator has
        // navigated away still appends to the thread that asked.
        const key = chatKey(repo, phase === 'maintenance' ? 'maintenance' : 'delivery');
        const prior = get().chats[key] ?? [];
        const append = (msg: ChatMessage) =>
            set((s) => ({ chats: { ...s.chats, [key]: [...(s.chats[key] ?? []), msg] } }));
        set((s) => ({
            chats: { ...s.chats, [key]: [...prior, { role: 'user', content: message }] },
            chatBusyKeys: { ...s.chatBusyKeys, [key]: true },
        }));
        try {
            const { turn } = await apiFetch<ChatTurn>('/deliveries/chat', {
                target: repo,
                phase,
                message,
                history: prior, // the backend appends the new message itself
                references: useDeliveries.getState().references,
            });
            const res = await awaitTurn(turn, chatResult);
            set({ chatConfigured: res.configured, chatModel: res.model });
            if (res.configured && res.reply != null) {
                append({ role: 'assistant', content: res.reply });
            }
        } catch (err) {
            append({ role: 'assistant', content: `Error: ${errorText(err)}` });
        } finally {
            set((s) => ({ chatBusyKeys: { ...s.chatBusyKeys, [key]: false } }));
        }
    },
    clearChat: (repo: string, phase: string) =>
        set((s) => ({
            chats: {
                ...s.chats,
                [chatKey(repo, phase === 'maintenance' ? 'maintenance' : 'delivery')]: [],
            },
        })),
    sendFleetChat: async (message: string) => {
        const prior = get().fleetChat;
        set({ fleetChat: [...prior, { role: 'user', content: message }], fleetChatBusy: true });
        try {
            const { turn } = await apiFetch<ChatTurn>('/fleet/chat', { message, history: prior });
            const res = await awaitTurn(turn, chatResult);
            set({ fleetChatConfigured: res.configured, fleetChatModel: res.model });
            if (res.configured && res.reply != null) {
                set({ fleetChat: [...get().fleetChat, { role: 'assistant', content: res.reply }] });
            }
        } catch (err) {
            set({
                fleetChat: [
                    ...get().fleetChat,
                    { role: 'assistant', content: `Error: ${errorText(err)}` },
                ],
            });
        } finally {
            set({ fleetChatBusy: false });
        }
    },
    clearFleetChat: () => set({ fleetChat: [] }),
}));
