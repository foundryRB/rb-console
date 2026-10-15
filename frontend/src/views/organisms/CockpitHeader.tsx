import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Lockup } from '@/components/Lockup';
import { cn } from '@/utils';
import { useAppearance } from '@/viewmodels/appearance';
import { AppearanceControl } from '@/views/organisms/AppearanceControl';

export const CockpitHeader: React.FC<{ aside?: React.ReactNode; bar?: React.ReactNode }> = ({
    aside,
    bar,
}) => {
    const [barOpen, setBarOpen] = useState(false);
    const { resolved } = useAppearance();
    return (
        <header className="app-glass flex-none border-b border-border">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 sm:px-5">
                {/* The RB tile is the masthead's mark; the product name remains live text. The full
                        lockup (with its words) lives in the docs and the login, where there is room. */}
                <Link to="/" className="flex shrink-0 items-center gap-3" title="Back to the fleet">
                    <Lockup mode={resolved} height={36} compact />
                    <span className="flex flex-col leading-tight">
                        <span className="text-sm font-semibold tracking-tight">
                            Foundry Console
                        </span>
                        <span className="hidden text-[11px] text-muted-foreground sm:block">
                            Delivery command center
                        </span>
                    </span>
                </Link>
                {/* Desktop: the page's controls inline, flex-1 between brand and nav. Hidden
                        below lg, where they move into the disclosure panel instead. */}
                {bar && (
                    <div className="hidden min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-2 lg:flex">
                        {bar}
                    </div>
                )}
                <nav className="ml-auto flex shrink-0 items-center gap-3 text-sm text-muted-foreground sm:gap-4">
                    <AppearanceControl />
                    {aside}
                    {bar && (
                        <button
                            type="button"
                            onClick={() => setBarOpen((v) => !v)}
                            aria-expanded={barOpen}
                            className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground lg:hidden"
                        >
                            Controls
                            <span className={cn('transition-transform', barOpen && 'rotate-180')}>
                                ⌄
                            </span>
                        </button>
                    )}
                    <Link to="/settings" className="hover:text-link">
                        Settings
                    </Link>
                </nav>
                {/* Mobile/tablet: the same controls, stacked, revealed by the disclosure. It
                        spans the full row (basis-full) so it drops below the brand + nav, and
                        lg:hidden keeps it off the desktop masthead entirely. */}
                {bar && barOpen && (
                    <div className="flex basis-full flex-col gap-2 border-t border-border pt-2.5 lg:hidden">
                        {bar}
                    </div>
                )}
            </div>
        </header>
    );
};
