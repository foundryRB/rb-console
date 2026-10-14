import { useEffect } from 'react';
import { Link } from 'react-router-dom';

import { Cockpit } from '@/views/templates/Cockpit';
import { AgentsManager } from '@/views/organisms/AgentsManager';
import { GitIdentitiesManager } from '@/views/organisms/GitIdentitiesManager';
import { PairCredentialsManager } from '@/views/organisms/PairCredentialsManager';
import { RuntimeSettings } from '@/views/organisms/RuntimeSettings';
import { SessionCard } from '@/views/organisms/SessionCard';
import { Card } from '@/components/ui/card';
import { HiddenProjectsToggle } from '@/views/organisms/HiddenProjectsToggle';
import { HiddenIssuesToggle } from '@/views/organisms/HiddenIssuesToggle';
import { TeamsManager } from '@/views/organisms/TeamsManager';
import { useSettings } from '@/viewmodels/settings';

export const SettingsPage: React.FC = () => {
    const { session, loadSession } = useSettings();
    useEffect(() => {
        void loadSession().catch(() => undefined);
    }, [loadSession]);
    // The installation-wide settings serve every team at once, so with teams on they are an
    // admin's to set; a team member keeps its providers and its own view toggles.
    const installWide = !session?.teams_enabled || session.admin !== false;
    return (
        <Cockpit
            aside={
                <Link to="/" className="hover:text-link">
                    Back to the floor
                </Link>
            }
        >
            <div className="mb-4">
                <h1 className="text-lg font-semibold tracking-tight">Settings</h1>
                <p className="mt-1 text-xs text-muted-foreground">
                    Console-wide runtime configuration, applied live, persisted, never in git.
                </p>
            </div>
            <div className="flex flex-col gap-8">
                {session?.teams_enabled && session.admin && (
                    <Card className="p-6">
                        <TeamsManager />
                    </Card>
                )}
                {installWide ? (
                    <>
                        <RuntimeSettings />
                        <Card className="p-6">
                            <GitIdentitiesManager />
                        </Card>
                        <Card className="p-6">
                            <PairCredentialsManager />
                        </Card>
                    </>
                ) : (
                    <p className="text-xs text-muted-foreground">
                        The home co-pilot, git identities, pair credentials, MCP doors and run
                        retention serve every team, and an admin sets them.
                    </p>
                )}
                <Card className="p-6">
                    <AgentsManager />
                </Card>
                <Card className="p-6">
                    <h3 className="mb-3 text-sm font-semibold tracking-tight">Fleet</h3>
                    <HiddenProjectsToggle />
                </Card>
                <Card className="p-6">
                    <h3 className="mb-3 text-sm font-semibold tracking-tight">Inbox</h3>
                    <HiddenIssuesToggle />
                </Card>
                <SessionCard />
            </div>
        </Cockpit>
    );
};
export default SettingsPage;
