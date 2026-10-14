import { useMaintenance } from '@/viewmodels/maintenance';

export const HiddenIssuesToggle: React.FC = () => {
    const { showHiddenIssues, setShowHiddenIssues } = useMaintenance();
    return (
        <label className="flex cursor-pointer items-start gap-2.5">
            <input
                type="checkbox"
                checked={showHiddenIssues}
                onChange={(e) => setShowHiddenIssues(e.target.checked)}
                className="mt-1 shrink-0 accent-primary"
            />
            <span className="min-w-0">
                <span className="block text-sm font-medium">Show hidden Inbox items</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">
                    Includes issues carrying the{' '}
                    <code className="rounded bg-muted px-1 text-foreground">foundry-hidden</code>{' '}
                    label, and every row - red CI, drift, unreleased, and the rest - of a repo
                    carrying the{' '}
                    <code className="rounded bg-muted px-1 text-foreground">foundry-hidden</code>{' '}
                    topic, shown dimmed in the Inbox. They stay off the queue by default; add or
                    remove the mark on the issue or the repo in GitHub.
                </span>
            </span>
        </label>
    );
};
