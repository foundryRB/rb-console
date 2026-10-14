import { cn } from '@/utils';

export const VerdictPill: React.FC<{ verdict: string }> = ({ verdict }) => (
    <span
        className={cn(
            'rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-widest',
            verdict === 'pass' &&
                'border-[hsl(var(--success))]/40 bg-[hsl(var(--success))]/10 text-[hsl(var(--success))]',
            verdict === 'fail' && 'border-destructive/50 bg-destructive/10 text-destructive',
            verdict !== 'pass' &&
                verdict !== 'fail' &&
                'border-amber-400/40 bg-amber-400/10 text-amber-400',
        )}
        title={
            verdict === 'pass'
                ? 'The last counted fresh-eyes review records VERDICT: PASS'
                : verdict === 'fail'
                  ? 'The last counted fresh-eyes review records VERDICT: FAIL - its findings are the work order'
                  : verdict === 'unrecorded'
                    ? "Reviewed, but by the PR's author or its merger, or ending VERDICT: UNRECORDED, so nothing is recorded. The PR awaits an independent reviewer"
                    : 'No fresh-eyes verdict yet - nothing merges unreviewed'
        }
    >
        {verdict === 'pass'
            ? 'PASS'
            : verdict === 'fail'
              ? 'FAIL'
              : verdict === 'unrecorded'
                ? 'unrecorded'
                : 'awaiting'}
    </span>
);
