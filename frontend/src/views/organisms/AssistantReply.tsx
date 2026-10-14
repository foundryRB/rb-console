import { Button } from '@/components/ui/button';
import { ChatMarkdown } from '@/views/organisms/ChatMarkdown';

import { splitRedrive } from '@/viewmodels/copilot/copilot.model';

export const AssistantReply: React.FC<{ text: string; onStage?: (feedback: string) => void }> = ({
    text,
    onStage,
}) => {
    const staged = onStage ? splitRedrive(text) : null;
    if (!staged) return <ChatMarkdown text={text} />;
    return (
        <>
            {staged.before && <ChatMarkdown text={staged.before} />}
            <div className="my-1.5 rounded-md border border-link/50 bg-primary/10 p-2">
                <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-widest text-link">
                    staged re-drive feedback
                </div>
                <p className="whitespace-pre-wrap text-xs leading-relaxed">{staged.feedback}</p>
                <Button
                    type="button"
                    className="mt-1.5 h-6 px-2 text-[11px]"
                    onClick={() => onStage?.(staged.feedback)}
                >
                    Stage into Re-drive →
                </Button>
            </div>
            {staged.after && <ChatMarkdown text={staged.after} />}
        </>
    );
};
