import { inspectReceipt } from '@/viewmodels/requests/requests.actions';
import { useRequests } from '@/viewmodels/requests';

export const OperationReceipts = () => {
    const operations = useRequests((state) => state.operations);
    const visible = Object.values(operations).filter(
        (operation) => operation.status === 'unknown' || operation.status === 'conflict',
    );
    if (!visible.length) return null;
    return (
        <aside
            aria-live="polite"
            className="flex flex-none flex-col gap-2 border-b border-amber-500/40 bg-amber-500/10 px-4 py-3"
        >
            {visible.map((operation) => (
                <div key={operation.operation_id} className="break-words text-xs">
                    <strong>
                        {operation.status === 'unknown' ? 'Outcome unknown' : 'Conflict'}
                    </strong>{' '}
                    {operation.detail} <code>{operation.operation_id}</code>
                    {operation.operation_key && (
                        <button
                            className="ml-2 underline"
                            onClick={() => void inspectReceipt(operation.operation_id)}
                        >
                            Inspect receipt
                        </button>
                    )}
                    {operation.receipt && (
                        <p>
                            Persisted receipt: {operation.receipt.state}. {operation.receipt.reason}{' '}
                            {Object.entries(operation.receipt.evidence)
                                .map(([key, value]) => (value ? `${key}: ${value}` : ''))
                                .join(' ')}
                        </p>
                    )}
                    {operation.receipt_error && <p>{operation.receipt_error}</p>}
                </div>
            ))}
        </aside>
    );
};
