import { useEffect, useState } from 'react';

import type { State } from '@/models';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useDeliveries } from '@/viewmodels/deliveries';
import { useSettings } from '@/viewmodels/settings';
import { callerOf } from '@/viewmodels/agents/agentChoices.model';
import { Field } from '@/views/molecules/Field';

export interface StartDeliveryFormProps {
    /** Called after a delivery is established, with the established delivery's derived
     *  State. The caller confirms the act from it (the repo, the derived phase) rather
     *  than closing blind onto an un-refreshed list - the establish response carries
     *  everything needed to land the operator on the thing they must now run. */
    onStarted?: (established: State) => void;
    /** Prefill the repo (the project cockpit opens a line on ITS repo). Still editable. */
    initialTarget?: string;
    /** Prefill the customer request. "Switch to Delivery" (issue #13) seeds this with the
     *  prepared brief on the over-scope ticket (the resolve worker's marked comment, or the
     *  ticket body itself). Still editable. Read once at mount; the caller remounts the form
     *  (a changing key) to re-seed it. */
    initialRequest?: string;
}

/** An existing app picked for the seed: its filename and its bytes as base64, the way
 *  the establish body carries it. */
interface PickedArchive {
    name: string;
    base64: string;
}

/** A File as base64, read once at pick time so submit stays synchronous. */
function readAsBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(reader.error);
        reader.onload = () => {
            const url = String(reader.result);
            resolve(url.slice(url.indexOf(',') + 1));
        };
        reader.readAsDataURL(file);
    });
}

/**
 * Establish a delivery: name one repo (created if new, adopted if it already exists) and
 * capture the customer's verbatim request, which is what the Scope phase works from. An
 * existing app, uploaded as a zip, seeds the new repo's default branch as it is, so Scope
 * reads the app itself and the line recasts it. This is the deterministic setup only - no
 * model, no credential. You run the phases afterward from the delivery itself (establish,
 * then run: two separate steps). With teams on, the line belongs to a team from the moment it
 * opens: a member of one team opens it for that team, a member of several chooses, and an admin
 * may name any team or none.
 */
export const StartDeliveryForm: React.FC<StartDeliveryFormProps> = ({
    onStarted,
    initialTarget,
    initialRequest,
}) => {
    const { establish, actionLoading, actionError } = useDeliveries();
    const { session, loadSession, teams, loadTeams } = useSettings();
    const caller = callerOf(session);
    const [team, setTeam] = useState('');
    const [target, setTarget] = useState(initialTarget ?? '');
    const [request, setRequest] = useState(initialRequest ?? '');
    const [appName, setAppName] = useState('');
    const [archive, setArchive] = useState<PickedArchive | null>(null);
    const [archiveError, setArchiveError] = useState<string | null>(null);
    // A file input holds its own value; remounting it (a new key) is how it is cleared.
    const [pickerKey, setPickerKey] = useState(0);

    useEffect(() => {
        void loadSession().catch(() => undefined);
    }, [loadSession]);
    useEffect(() => {
        if (caller.teamsEnabled && caller.admin) void loadTeams().catch(() => undefined);
    }, [caller.teamsEnabled, caller.admin, loadTeams]);

    // The teams this line can belong to: an admin's are every team, a member's its own.
    const teamOptions = caller.admin ? teams.map((t) => t.name) : caller.teams;
    const chosenTeam = team || (!caller.admin && caller.teams.length === 1 ? caller.teams[0] : '');
    const teamMissing = caller.teamsEnabled && !caller.admin && !chosenTeam;

    async function pick(event: React.ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        setArchiveError(null);
        if (!file) {
            setArchive(null);
            return;
        }
        try {
            setArchive({ name: file.name, base64: await readAsBase64(file) });
        } catch (err) {
            setArchive(null);
            setArchiveError(err instanceof Error ? err.message : 'could not read the archive');
        }
    }

    async function submit(event: React.FormEvent) {
        event.preventDefault();
        const state = await establish({
            target: target.trim(),
            request: request.trim(),
            ...(appName.trim() ? { app_name: appName.trim() } : {}),
            ...(chosenTeam ? { team: chosenTeam } : {}),
            ...(archive ? { source_archive: archive.base64, source_name: archive.name } : {}),
        });
        if (state) {
            setTarget('');
            setAppName('');
            setRequest('');
            setArchive(null);
            setPickerKey((k) => k + 1);
            onStarted?.(state);
        }
    }

    return (
        <Card className="p-5">
            <div className="mb-4">
                <h2 className="text-sm font-semibold tracking-tight">Establish a delivery</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                    Create a new org repo or adopt an existing one, and capture the request. This
                    only sets it up; you run the phases afterward from the delivery.
                </p>
            </div>

            <form onSubmit={submit} className="flex flex-col gap-4">
                <Field
                    label="Delivery repo"
                    hint="A repo in the org. Created if it does not exist, adopted if it does."
                >
                    <Input
                        required
                        value={target}
                        onChange={(e) => setTarget(e.target.value)}
                        placeholder="acme-store"
                    />
                </Field>

                <Field
                    label="App name"
                    hint="Optional. The app's fleet name - its namespace, hostname label, chart and packages. A fact of its own, and the same as the repo unless you say otherwise: name it when the organisation's repositories carry a prefix the app should not."
                >
                    <Input
                        value={appName}
                        onChange={(e) => setAppName(e.target.value)}
                        placeholder={target.trim() || 'acme-store'}
                    />
                </Field>

                {caller.teamsEnabled && (
                    <Field
                        label="Team"
                        hint={
                            caller.admin
                                ? 'Optional. The team whose members see and drive this line; with none, admins alone see it.'
                                : 'The team whose members see and drive this line.'
                        }
                    >
                        <select
                            value={chosenTeam}
                            onChange={(e) => setTeam(e.target.value)}
                            required={!caller.admin}
                            className="rounded-md border border-input bg-transparent px-3 py-2 text-sm"
                        >
                            <option value="" disabled={!caller.admin}>
                                {caller.admin ? 'No team' : 'Choose a team…'}
                            </option>
                            {teamOptions.map((name) => (
                                <option key={name} value={name}>
                                    {name}
                                </option>
                            ))}
                        </select>
                    </Field>
                )}

                <Field
                    label="Customer request"
                    hint="The verbatim ask - the ground truth the Scope phase works from."
                >
                    <textarea
                        value={request}
                        onChange={(e) => setRequest(e.target.value)}
                        placeholder="What the customer asked for, in their own words."
                        rows={4}
                        className="rounded-md border border-input bg-transparent px-3 py-2 text-sm"
                    />
                </Field>

                <Field
                    label="Existing app (optional)"
                    hint="A zip of the app as it is. It seeds a NEW repo's default branch, so Scope reads the app and the line recasts it. Vendored and built trees are skipped; env files and keys in the tree are refused by name."
                >
                    <input
                        key={pickerKey}
                        type="file"
                        accept=".zip,application/zip,application/x-zip-compressed"
                        onChange={pick}
                        className="text-sm"
                    />
                    {archive && (
                        <span className="text-[11px] text-muted-foreground">
                            {archive.name} will seed {target.trim() || 'the new repo'}
                        </span>
                    )}
                    {archiveError && (
                        <span className="text-[11px] text-destructive">{archiveError}</span>
                    )}
                </Field>

                <div className="flex items-center gap-3">
                    <Button
                        type="submit"
                        disabled={actionLoading || target.trim() === '' || teamMissing}
                    >
                        {actionLoading ? 'Establishing...' : 'Establish delivery'}
                    </Button>
                    {actionError && <span className="text-sm text-destructive">{actionError}</span>}
                </div>
            </form>
        </Card>
    );
};
