interface InstallHintProps {
    onDismiss: () => void;
}

/** iOS has no install prompt; this hint is the install experience there (REF-PWA section 4). */
export const InstallHint: React.FC<InstallHintProps> = ({ onDismiss }) => (
    <div
        role="note"
        data-testid="pwa-install-hint"
        className="flex items-start justify-between gap-3 rounded-md border bg-card px-4 py-3 text-sm shadow-lg"
    >
        <span>
            Install this app: tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>.
        </span>
        <button
            type="button"
            onClick={onDismiss}
            className="text-xs text-muted-foreground hover:text-foreground"
        >
            Dismiss
        </button>
    </div>
);
