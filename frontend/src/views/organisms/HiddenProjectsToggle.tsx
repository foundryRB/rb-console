import { useFleet } from '@/viewmodels/fleet';

export const HiddenProjectsToggle: React.FC = () => {
    const { showHidden, setShowHidden } = useFleet();
    return (
        <label className="flex cursor-pointer items-start gap-2.5">
            <input
                type="checkbox"
                checked={showHidden}
                onChange={(e) => setShowHidden(e.target.checked)}
                className="mt-1 shrink-0 accent-primary"
            />
            <span className="min-w-0">
                <span className="block text-sm font-medium">Show hidden projects</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                    Includes repos carrying the{' '}
                    <code className="rounded bg-muted px-1 text-foreground">foundry-hidden</code>{' '}
                    topic (CI, libraries, and the like), shown dimmed. They stay off the board by
                    default - and off the Inbox, which <em>Show hidden Inbox items</em> reveals. Add
                    or remove the topic on the repo in GitHub - click a project&apos;s name to open
                    it there.
                </span>
            </span>
        </label>
    );
};
