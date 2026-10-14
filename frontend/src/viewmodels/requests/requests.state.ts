import type { OperationReceiptResponse } from '@/models';
export interface RequestOperation {
    operation_id: string;
    path: string;
    status: 'pending' | 'complete' | 'conflict' | 'refused' | 'unknown';
    detail: string;
    operation_key?: string;
    receipt?: OperationReceiptResponse;
    receipt_error?: string;
}

export interface RequestsState {
    operations: Record<string, RequestOperation>;
    revisions: Record<string, string>;
}
