import { useSettings } from '@/viewmodels/settings';
import { useEffect } from 'react';

import { cn } from '@/utils';
import { buttonVariants } from '@/components/ui/button-variants';
import { Card } from '@/components/ui/card';

/** Ends the session the console is served behind - the way out of an installed console,
 * which opens full-screen from a phone's Home Screen with no address bar to type the
 * proxy's route into.
 *
 * Two properties are load-bearing. The control is a plain `<a href>` full-page navigation,
 * never a react-router `Link` and never a `fetch`: the route belongs to the oauth2-proxy
 * sidecar in front of the app, so the browser has to LEAVE the SPA for it - a client-side
 * route would resolve inside the app shell and a fetch would clear the cookie without moving
 * the tab. And the card renders only where the gate is on; an install serving open has no
 * session to end, and a control that 404s is worse than none. */
export const SessionCard: React.FC = () => {
    const { session, loadSession } = useSettings();
    useEffect(() => {
        void loadSession().catch(() => undefined);
    }, [loadSession]);
    if (!session?.oidc_enabled || !session.sign_out_url) return null;
    return (
        <Card className="p-6">
            <h3 className="mb-3 text-sm font-semibold tracking-tight">Session</h3>
            <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="min-w-0 text-xs text-muted-foreground">
                    Ends this browser&apos;s console session at the sign-in proxy. The next visit
                    goes through the identity provider again - which, while it still holds a session
                    of its own, signs you straight back in without asking.
                </p>
                <a
                    href={session.sign_out_url}
                    className={cn(buttonVariants({ variant: 'outline' }), 'shrink-0')}
                >
                    Sign out
                </a>
            </div>
        </Card>
    );
};
