export const RefTag: React.FC<{ id: string }> = ({ id }) => (
    <span className="rounded bg-well/30 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
        {id}
    </span>
);
