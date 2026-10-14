import { Fragment } from 'react';

import { InlineMarkup } from '@/views/molecules/InlineMarkup';

export const ChatMarkdown: React.FC<{ text: string }> = ({ text }) => {
    const lines = text.split(/\r?\n/);
    const out: React.ReactNode[] = [];
    let list: { ordered: boolean; items: string[] } | null = null;
    let code: string[] | null = null;

    const flushCode = (key: string) => {
        if (code && code.length) {
            out.push(
                <pre
                    key={key}
                    className="my-1.5 overflow-x-auto rounded-md border border-border bg-muted/70 p-2 font-mono text-[11px] leading-relaxed"
                >
                    {code.join('\n')}
                </pre>,
            );
        }
        code = null;
    };

    const flushList = (key: number) => {
        if (list && list.items.length) {
            const items = list.items.map((it, j) => (
                <li key={j} className="leading-relaxed">
                    <InlineMarkup text={it} />
                </li>
            ));
            out.push(
                list.ordered ? (
                    <ol key={`o${key}`} className="my-1 flex list-decimal flex-col gap-0.5 pl-5">
                        {items}
                    </ol>
                ) : (
                    <ul key={`u${key}`} className="my-1 flex list-disc flex-col gap-0.5 pl-5">
                        {items}
                    </ul>
                ),
            );
        }
        list = null;
    };

    lines.forEach((raw, i) => {
        const line = raw.trimEnd();
        if (code !== null) {
            if (line.startsWith('```')) flushCode(`c${i}`);
            else code.push(raw);
            return;
        }
        if (line.startsWith('```')) {
            flushList(i);
            code = [];
            return;
        }
        const bullet = /^\s*[-*]\s+(.*)/.exec(line);
        const numbered = /^\s*\d+\.\s+(.*)/.exec(line);
        if (bullet) {
            if (!list || list.ordered) flushList(i);
            (list ??= { ordered: false, items: [] }).items.push(bullet[1]);
            return;
        }
        if (numbered) {
            if (!list || !list.ordered) flushList(i);
            (list ??= { ordered: true, items: [] }).items.push(numbered[1]);
            return;
        }
        flushList(i);
        if (line.trim()) {
            out.push(
                <p key={i} className="my-1 leading-relaxed first:mt-0 last:mb-0">
                    <InlineMarkup text={line} />
                </p>,
            );
        }
    });
    flushList(lines.length);
    flushCode('c-tail'); // an unclosed fence (e.g. mid-stream): show what streamed so far

    return <Fragment>{out}</Fragment>;
};
