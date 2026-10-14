import { Fragment } from 'react';

import { InlineMarkup } from '@/views/molecules/InlineMarkup';

import { splitRow, isSeparatorRow } from '@/viewmodels/records/records.model';

export const RecordDocument: React.FC<{ text: string }> = ({ text }) => {
    const lines = text.split(/\r?\n/);
    const out: React.ReactNode[] = [];
    let code: string[] | null = null;
    let list: string[] | null = null;
    let table: string[][] | null = null;

    const flushList = (key: number) => {
        if (list && list.length) {
            out.push(
                <ul key={`l${key}`} className="my-1.5 flex flex-col gap-1 pl-4">
                    {list.map((it, j) => (
                        <li
                            key={j}
                            className="list-disc text-xs leading-relaxed text-foreground/90"
                        >
                            <InlineMarkup text={it} />
                        </li>
                    ))}
                </ul>,
            );
        }
        list = null;
    };

    const flushTable = (key: number) => {
        if (table && table.length) {
            const [head, ...rows] = table;
            out.push(
                <div
                    key={`t${key}`}
                    className="my-2 overflow-x-auto rounded-md border border-border"
                >
                    <table className="w-full border-collapse text-xs">
                        <thead>
                            <tr className="bg-muted/50">
                                {head.map((h, j) => (
                                    <th
                                        key={j}
                                        className="border-b border-border px-2.5 py-1.5 text-left font-mono text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
                                    >
                                        <InlineMarkup text={h} />
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r, ri) => (
                                <tr key={ri} className="border-b border-border/60 last:border-b-0">
                                    {r.map((c, ci) => (
                                        <td
                                            key={ci}
                                            className="px-2.5 py-1.5 align-top leading-relaxed text-foreground/90"
                                        >
                                            <InlineMarkup text={c} />
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>,
            );
        }
        table = null;
    };

    lines.forEach((raw, i) => {
        const line = raw.trimEnd();
        if (code !== null) {
            if (line.startsWith('```')) {
                out.push(
                    <pre
                        key={`c${i}`}
                        className="my-2 overflow-x-auto rounded-md border border-border bg-muted/70 p-2.5 font-mono text-[11px] leading-relaxed text-muted-foreground"
                    >
                        {code.join('\n')}
                    </pre>,
                );
                code = null;
            } else code.push(raw);
            return;
        }
        if (line.startsWith('```')) {
            flushList(i);
            flushTable(i);
            code = [];
            return;
        }
        if (/^\s*\|.*\|\s*$/.test(line)) {
            flushList(i);
            if (!isSeparatorRow(line)) (table ??= []).push(splitRow(line));
            return;
        }
        flushTable(i);
        if (/^\s*[-*]\s+/.test(line)) {
            (list ??= []).push(line.replace(/^\s*[-*]\s+/, ''));
            return;
        }
        flushList(i);
        if (/^#{1,3}\s/.test(line)) {
            out.push(
                <h4
                    key={i}
                    className="mb-1 mt-3 font-mono text-[10px] font-semibold uppercase tracking-widest text-muted-foreground first:mt-0"
                >
                    {line.replace(/^#+\s*/, '')}
                </h4>,
            );
        } else if (/^[A-Za-z_-]+:\s/.test(line) && line.length < 90) {
            const [k, ...rest] = line.split(':');
            out.push(
                <p key={i} className="font-mono text-[11px] leading-relaxed">
                    <span className="text-muted-foreground">{k}:</span>
                    <span className="text-foreground/90">{rest.join(':')}</span>
                </p>,
            );
        } else if (line.trim()) {
            out.push(
                <p key={i} className="my-1 text-xs leading-relaxed text-foreground/90">
                    <InlineMarkup text={line} />
                </p>,
            );
        }
    });
    flushList(lines.length);
    flushTable(lines.length + 1);

    return <Fragment>{out}</Fragment>;
};
