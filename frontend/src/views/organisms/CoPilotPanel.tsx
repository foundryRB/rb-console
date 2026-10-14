import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { ChatMessage } from '@/models';
import { cn } from '@/utils';
import { Button } from '@/components/ui/button';

import { InlineMarkup } from '@/views/molecules/InlineMarkup';
import { AssistantReply } from '@/views/organisms/AssistantReply';
import { ThinkingDots } from '@/views/atoms/ThinkingDots';
import { prefersReducedMotion } from '@/viewmodels/copilot/copilot.model';

export const CoPilotPanel: React.FC<{
    messages: ChatMessage[];
    busy: boolean;
    configured: boolean | null;
    model: string | null;
    references: string[];
    onSend: (message: string) => void;
    onClear: () => void;
    onToggleReference: (path: string) => void;
    /** Override the two idle texts - the home co-pilot has different grounding. */
    notConfiguredHint?: React.ReactNode;
    emptyHint?: string;
    /** Present only while a gate awaits: a reply's ```redrive block renders as a staged
     * card, and its chip hands the feedback here (the gate card pre-fills its composer). */
    onStageRedrive?: (feedback: string) => void;
}> = ({
    messages,
    busy,
    configured,
    model,
    references,
    onSend,
    onClear,
    onToggleReference,
    notConfiguredHint,
    emptyHint,
    onStageRedrive,
}) => {
    const [draft, setDraft] = useState('');
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    // Whether the reader is pinned to the bottom. We only chase new content down while
    // they are - if they scrolled up to re-read, the typewriter must not yank them back.
    const atBottomRef = useRef(true);

    // Typewriter: reveal only the LAST assistant message, and only when it arrives while
    // the panel is already open. `shown` is how many characters of it are visible; a null
    // typing state means nothing is animating (history, user turns, reduced motion).
    const [typing, setTyping] = useState<{ index: number; shown: number } | null>(null);

    // Compare the transcript length across renders to tell a fresh turn from a re-render.
    // Deriving the trigger during render (not in an effect) is React's "reset state when a
    // prop changes" pattern: no flash, and no cascading-render lint. On mount seenLen ==
    // length, so pre-existing history is treated as already shown - it never re-types.
    const [seenLen, setSeenLen] = useState(messages.length);
    if (messages.length !== seenLen) {
        const grew = messages.length > seenLen;
        setSeenLen(messages.length);
        const last = messages[messages.length - 1];
        setTyping(
            grew && last?.role === 'assistant' && !prefersReducedMotion()
                ? { index: messages.length - 1, shown: 0 }
                : null, // the user's own turn, a clear, or reduced motion: show it whole
        );
    }

    const send = () => {
        const m = draft.trim();
        if (m && !busy) {
            onSend(m);
            setDraft('');
            inputRef.current?.focus(); // stay in the composer after firing (esp. after a Send click)
        }
    };

    const scrollToBottom = (smooth: boolean) => {
        const el = scrollRef.current;
        if (!el) return;
        el.scrollTo({
            top: el.scrollHeight,
            behavior: smooth && !prefersReducedMotion() ? 'smooth' : 'auto',
        });
        atBottomRef.current = true;
    };

    const onScroll = () => {
        const el = scrollRef.current;
        if (!el) return;
        atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    };

    // A new message landed, or the co-pilot started thinking: bring the tail into view.
    useEffect(() => {
        scrollToBottom(true);
    }, [messages.length, busy]);

    // Grow the composer with its content (up to a cap), and shrink back to one line when
    // it's cleared after a send. Runs on every draft change - it drives the DOM only.
    useEffect(() => {
        const el = inputRef.current;
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }, [draft]);

    // Advance the reveal one tick, then follow it down if the reader is still at the
    // bottom. The step scales with length so a long turn finishes in about the same beat
    // as a short one. All state changes happen inside the timeout (never synchronously in
    // the effect body), so the caret clears on the tick after the last character lands.
    useEffect(() => {
        if (!typing) return;
        const step = Math.max(1, Math.ceil((messages[typing.index]?.content.length ?? 0) / 80));
        const id = setTimeout(() => {
            setTyping((t) => {
                if (!t) return t;
                const full = messages[t.index]?.content ?? '';
                if (t.shown >= full.length) return null; // done: drop the caret
                return { ...t, shown: Math.min(full.length, t.shown + step) };
            });
            if (atBottomRef.current && scrollRef.current) {
                scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
            }
        }, 18);
        return () => clearTimeout(id);
    }, [typing, messages]);

    return (
        <div className="flex h-full min-h-0 flex-col gap-2">
            <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">
                    Co-pilot
                    {model && (
                        <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">
                            {model}
                        </span>
                    )}
                </span>
                {messages.length > 0 && (
                    <button
                        type="button"
                        onClick={onClear}
                        className="text-[11px] text-muted-foreground hover:text-link"
                    >
                        clear
                    </button>
                )}
            </div>

            {references.length > 0 && (
                <div className="flex flex-wrap gap-1">
                    {references.map((r) => (
                        <button
                            key={r}
                            type="button"
                            onClick={() => onToggleReference(r)}
                            title="click to drop this reference"
                            className="rounded bg-primary/15 px-1.5 py-0.5 font-mono text-[10px] text-link hover:line-through"
                        >
                            ⎘ {r} ✕
                        </button>
                    ))}
                </div>
            )}

            <div
                ref={scrollRef}
                onScroll={onScroll}
                className="vf-chat-transcript min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-background/80 p-3"
            >
                {configured === false && (
                    <p className="text-xs text-muted-foreground">
                        {notConfiguredHint ?? (
                            <>
                                Choose a provider for this delivery or add one in{' '}
                                <Link to="/settings" className="text-link hover:underline">
                                    Settings
                                </Link>
                                .
                            </>
                        )}
                    </p>
                )}
                {messages.length === 0 && configured !== false && (
                    <p className="text-xs text-muted-foreground">
                        {emptyHint ?? 'Ask about this phase or the referenced files.'}
                    </p>
                )}
                <div className="flex flex-col gap-2">
                    {messages.map((m, i) => {
                        const isTyping = typing?.index === i;
                        const text = isTyping ? m.content.slice(0, typing.shown) : m.content;
                        return (
                            <div
                                key={i}
                                className={cn(
                                    'fc-msg-in max-w-[85%] rounded-lg px-2.5 py-1.5 text-xs',
                                    m.role === 'user'
                                        ? 'self-end bg-primary/15'
                                        : 'self-start bg-muted',
                                )}
                            >
                                {m.role === 'assistant' && !isTyping ? (
                                    // Settled reply: full markdown (lists, links, code), with a staged
                                    // redrive block as a card. While it types, the inline path below
                                    // keeps the caret trailing the last character.
                                    <AssistantReply text={text} onStage={onStageRedrive} />
                                ) : (
                                    <span className="whitespace-pre-wrap">
                                        <InlineMarkup text={text} />
                                        {isTyping && (
                                            <span className="fc-caret ml-px text-link">▍</span>
                                        )}
                                    </span>
                                )}
                            </div>
                        );
                    })}
                    {busy && <ThinkingDots />}
                </div>
            </div>

            <div className="flex items-end gap-2">
                <textarea
                    ref={inputRef}
                    value={draft}
                    rows={1}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                        // Enter sends; Shift+Enter drops a newline (the textarea handles it).
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            send();
                        }
                    }}
                    placeholder="Ask the co-pilot…"
                    className="max-h-40 min-w-0 flex-1 resize-none overflow-y-auto rounded-lg border border-input bg-background px-3 py-2 text-sm leading-relaxed outline-none focus:border-link"
                />
                <Button type="button" onClick={send} disabled={busy || !draft.trim()}>
                    Send
                </Button>
            </div>
        </div>
    );
};
