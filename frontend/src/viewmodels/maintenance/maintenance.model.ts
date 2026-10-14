import type { MaintState, MaintPr, TicketCell } from '@/models';

export type { TicketCell } from '@/models';
export type TicketStep = TicketCell['step'];

export const selectTicketLine = (state: MaintState | null, ticket: number): TicketCell[] =>
    state?.ticket_lines?.[String(ticket)] ?? [];
export const selectLinkedPr = (state: MaintState | null, ticket: number): MaintPr | null =>
    state?.linked_pr?.[String(ticket)] ?? null;
export const selectClosedPr = (state: MaintState | null, ticket: number): MaintPr | null =>
    state?.closed_pr?.[String(ticket)] ?? null;
