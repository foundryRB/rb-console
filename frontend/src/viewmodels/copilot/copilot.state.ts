import type { ChatMessage } from '@/models';
export interface CopilotState {
    fleetChat: ChatMessage[];
    fleetChatBusy: boolean;
    fleetChatConfigured: boolean | null;
    fleetChatModel: string | null;
    chats: Record<string, ChatMessage[]>;
    chatBusyKeys: Record<string, boolean>;
    chatConfigured: boolean | null;
    chatModel: string | null;
}
