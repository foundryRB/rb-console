export const PhaseTag: React.FC<{ id: string }> = ({ id }) => (
    <span className="rounded border border-link/40 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-link">
        {id}
    </span>
);
