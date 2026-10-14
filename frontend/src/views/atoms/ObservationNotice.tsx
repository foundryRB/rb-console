import type { Freshness } from '@/models';

interface ObservationNoticeProps {
    error?: string | null;
    freshness?: Freshness | null;
    hasData?: boolean;
}

/** A failed read, in one line: the request's, or the source read the observation reports.
 * Nothing while reads succeed. */
export const ObservationNotice = ({ error, freshness, hasData }: ObservationNoticeProps) => {
    const failure =
        error ??
        (freshness?.state === 'unavailable' || freshness?.reason_code === 'source_unavailable'
            ? 'source unreachable'
            : null);
    if (!failure) return null;
    const shown = hasData && freshness?.state !== 'unavailable';
    return (
        <p role="status" className="break-words text-xs text-muted-foreground">
            {shown ? `Showing the last read - ${failure}` : `Read unavailable - ${failure}`}
        </p>
    );
};
