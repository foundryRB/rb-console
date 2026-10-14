import { usePromotion, type PromotionTargetView } from '@/viewmodels/promotion';
import { Button } from '@/components/ui/button';

export const PromoteButton: React.FC<{ repo: string; target: PromotionTargetView }> = ({
    repo,
    target,
}) => {
    const { drive, driving, driveError, drove, driveRepo, droveRepo } = usePromotion();
    const busy = driveRepo === repo && driving === target.name;
    const receipt = droveRepo === repo && drove?.target === target.name ? drove : null;
    const refusal = driveError?.repo === repo && driveError.target === target.name ? driveError.message : null;
    return (
        <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
                type="button"
                className="h-7 px-2.5 text-xs"
                disabled={Boolean(driving)}
                onClick={() => void drive(repo, target.name)}
            >
                {busy ? 'Driving…' : 'Promote'}
            </Button>
            {receipt && (
                <span className="font-mono text-[10.5px] text-[hsl(var(--success))]">
                    driving {receipt.release} · run {receipt.run_id}
                </span>
            )}
            {refusal && (
                <span className="max-w-md font-mono text-[10.5px] text-destructive">{refusal}</span>
            )}
        </div>
    );
};
