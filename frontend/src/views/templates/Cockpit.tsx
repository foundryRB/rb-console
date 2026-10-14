import { cn } from '@/utils';
import { CockpitHeader } from '@/views/organisms/CockpitHeader';
import { OperationReceipts } from '@/views/organisms/OperationReceipts';
import { PwaStatus } from '@/views/organisms/PwaStatus';

export interface CockpitProps {
    /** Optional right-aligned slot in the header, next to Settings. */
    aside?: React.ReactNode;
    /** The page's controls, hoisted into the masthead - the bar is otherwise just brand +
     * Settings, and a second controls row below it wastes a full line of height. */
    bar?: React.ReactNode;
    /** Instrument-panel mode: full-bleed width and a scrollable main column. The frame keeps
     * the masthead fixed; the page may scroll when the panes outgrow the viewport - clipping
     * substance to force "nothing scrolls" costs more than it buys. */
    frame?: boolean;
    children: React.ReactNode;
}

/** The foundry-floor shell. One home (Fleet, the brand link), one cockpit per project,
 * Settings - no tab rows, no breadcrumbs: the masthead carries the page's own controls. */
export const Cockpit: React.FC<CockpitProps> = ({ aside, bar, frame, children }) => {
    return (
        <div
            className={cn(
                'app-console',
                frame ? 'flex h-dvh min-h-[640px] flex-col' : 'min-h-screen',
            )}
        >
            <CockpitHeader aside={aside} bar={bar} />
            <OperationReceipts />
            <main
                className={cn(
                    'w-full',
                    frame
                        ? 'flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-3 sm:px-5'
                        : 'mx-auto max-w-[1900px] px-4 py-6 sm:px-5',
                )}
            >
                {children}
            </main>
            <PwaStatus />
        </div>
    );
};
