interface FieldProps {
    label: string;
    hint?: string;
    children: React.ReactNode;
}

/** A labelled form row. Exported so the surrounding forms share one definition. */
export const Field: React.FC<FieldProps> = ({ label, hint, children }) => (
    <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {children}
        {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </label>
);
