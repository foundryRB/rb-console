import type { DeliveryConfig } from '@/models';
import { cn } from '@/utils';

/** The two delivery-level run shapes. Interactive gates every phase; one-shot compiles
 * the whole line with no suspend steps (the standing pre-authorization) - gates auto-sign
 * after a fresh-eyes review passes, and a gate whose stamp refuses ends the run on a
 * terminal stop, the line awaiting the operator's Sign (#181). There is no presence dial:
 * pod workers cannot pause for a human, so a stuck phase parks degraded and is answered
 * by re-drive with feedback. */
const OPTIONS = [
    {
        key: 'interactive',
        mode: 'interactive',
        label: 'Interactive',
        hint: 'Pauses at every gate for your sign-off.',
    },
    {
        key: 'one-shot',
        mode: 'one-shot',
        label: 'One-shot',
        hint: 'One prompt to a shipped app. Gates auto-sign after a fresh-eyes review passes; a stamp that refuses parks the line at its gate for your Sign, and a stuck phase parks degraded for your re-drive.',
    },
] as const;

/** Choose how a delivery's runs execute - a compact segmented control. The setting is
 * delivery-level and authoritative over every run the orchestrator compiles for it. */
export const DeliveryConfigStrip: React.FC<{
    config: DeliveryConfig;
    disabled?: boolean;
    onChange: (mode: string) => void;
}> = ({ config, disabled, onChange }) => {
    const active = config.mode === 'interactive' ? 'interactive' : 'one-shot';
    return (
        <div className="flex items-center gap-2">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-widest text-muted-foreground">
                Mode
            </span>
            <div className="flex gap-0.5 rounded-full border border-border bg-well/30 p-0.5">
                {OPTIONS.map((o) => {
                    const on = o.key === active;
                    return (
                        <button
                            key={o.key}
                            type="button"
                            disabled={disabled}
                            aria-pressed={on}
                            title={o.hint}
                            onClick={() => !on && onChange(o.mode)}
                            className={cn(
                                'rounded-full px-3 py-1.5 text-[11px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                                on
                                    ? 'bg-primary text-primary-foreground'
                                    : 'text-muted-foreground hover:text-foreground',
                            )}
                        >
                            {o.label}
                        </button>
                    );
                })}
            </div>
        </div>
    );
};
