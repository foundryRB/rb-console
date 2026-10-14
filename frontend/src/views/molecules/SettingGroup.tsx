import { Card } from '@/components/ui/card';

export const SettingGroup: React.FC<{
    title: string;
    hint?: string;
    children: React.ReactNode;
}> = ({ title, hint, children }) => (
    <section>
        <h2 className="px-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
        </h2>
        {hint && <p className="mt-1 px-1 text-xs text-muted-foreground">{hint}</p>}
        <Card className="mt-2 divide-y divide-border overflow-hidden">{children}</Card>
    </section>
);
