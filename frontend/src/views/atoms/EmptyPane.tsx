export const EmptyPane: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
        <span className="grid h-10 w-10 place-items-center rounded-xl border border-dashed border-border text-muted-foreground">
            ◇
        </span>
        <p className="max-w-md text-xs text-muted-foreground">{children}</p>
    </div>
);
