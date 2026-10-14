import type { Action } from '@/models';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/utils';

export interface ActionPanelProps {
    action: Action;
    /** Whether a Sign releases a run: the line's run is parked on the gate or still heading
     *  there. False when that run has ended, where a Sign closes the gate and a drive follows. */
    signReleasesRun: boolean;
    className?: string;
}

const KIND_TITLE: Record<Action['kind'], string> = {
    launch: 'Planned launch',
    'await-gate': 'Awaiting gate',
    'needs-start': 'Needs start',
};

/**
 * Render the Action the orchestrator returned: the deterministic launch it would
 * spawn (skill, phase, MCP endpoints, credential), or the gate the line awaits and what
 * a Sign of it does, or a note that the target is not yet a delivery.
 */
export const ActionPanel: React.FC<ActionPanelProps> = ({ action, signReleasesRun, className }) => {
    const { kind, gate, launch } = action;
    return (
        <div className={cn('rounded-lg border border-link/40 bg-primary/5 p-4', className)}>
            <div className="mb-3 flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-primary" aria-hidden="true" />
                <span className="text-sm font-semibold">{KIND_TITLE[kind]}</span>
            </div>

            {kind === 'launch' && launch && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                    <dt className="text-muted-foreground">Skill</dt>
                    <dd className="font-mono">{launch.skill}</dd>

                    <dt className="text-muted-foreground">Phase</dt>
                    <dd className="font-mono">{launch.phase}</dd>

                    <dt className="text-muted-foreground">Credential</dt>
                    <dd>
                        <Badge variant={launch.has_credential ? 'success' : 'destructive'}>
                            {launch.has_credential ? 'present' : 'missing'}
                        </Badge>
                    </dd>

                    <dt className="text-muted-foreground">MCP endpoints</dt>
                    <dd className="flex flex-wrap gap-1.5">
                        {launch.mcp_endpoints.length > 0 ? (
                            launch.mcp_endpoints.map((endpoint) => (
                                <Badge key={endpoint} variant="secondary">
                                    {endpoint}
                                </Badge>
                            ))
                        ) : (
                            <span className="text-muted-foreground">none</span>
                        )}
                    </dd>

                    <dt className="self-start text-muted-foreground">Prompt</dt>
                    <dd className="whitespace-pre-wrap text-muted-foreground">{launch.prompt}</dd>
                </dl>
            )}

            {kind === 'await-gate' && (
                <p className="text-sm text-muted-foreground" data-testid="action-gate-hint">
                    {signReleasesRun ? 'Suspended on the' : 'Awaiting the'}{' '}
                    <span className="font-semibold capitalize text-foreground">{gate}</span> gate.
                    {signReleasesRun
                        ? ' Sign it to release the next phase.'
                        : ' Sign it to close the gate, then drive the line on.'}
                </p>
            )}

            {kind === 'needs-start' && (
                <p className="text-sm text-muted-foreground">
                    This target is not a delivery yet. Start it to lay down the scratch and plan the
                    first phase.
                </p>
            )}
        </div>
    );
};
