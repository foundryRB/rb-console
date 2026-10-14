import type { LevelChoice } from '@/viewmodels/agents/agentChoices.model';
import { cn } from '@/utils';

/** Who a saved agent serves: everyone, one team, or only the person saving it. */
export const AgentLevelSelect: React.FC<{
    choices: LevelChoice[];
    value: string;
    onChange: (value: string) => void;
    disabled?: boolean;
    className?: string;
}> = ({ choices, value, onChange, disabled, className }) => (
    <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        title="Who may apply this agent to a line"
        className={cn(
            'rounded-lg border border-input bg-background px-3 py-2 text-xs outline-none focus:border-link',
            className,
        )}
    >
        {choices.map((choice) => (
            <option key={choice.value} value={choice.value}>
                {choice.label}
            </option>
        ))}
    </select>
);
