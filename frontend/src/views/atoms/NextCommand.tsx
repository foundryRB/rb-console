export interface NextCommandProps {
    command: string | null;
    label?: string;
}

/** The orchestrator's next command for a delivery, shown as a mono line. */
export const NextCommand: React.FC<NextCommandProps> = ({ command, label = 'Next command' }) => {
    if (!command) {
        return null;
    }
    return (
        <div className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                {label}
            </span>
            <code className="block overflow-x-auto whitespace-nowrap rounded-md border border-border bg-background/60 px-3 py-2 font-mono text-xs text-foreground">
                {command}
            </code>
        </div>
    );
};
