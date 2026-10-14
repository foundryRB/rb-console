export const ThinkingDots: React.FC = () => (
    <div className="fc-msg-in flex w-fit items-center gap-1 self-start rounded-lg bg-muted px-2.5 py-2">
        {[0, 160, 320].map((delay) => (
            <span
                key={delay}
                className="fc-thinking-dot h-1.5 w-1.5 rounded-full bg-muted-foreground"
                style={{ animationDelay: `${delay}ms` }}
            />
        ))}
    </div>
);
