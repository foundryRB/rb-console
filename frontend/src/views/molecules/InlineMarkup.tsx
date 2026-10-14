import { Fragment } from 'react';

import { SafeLink } from '@/views/atoms/SafeLink';

import { MD_LINK, safeHref } from '@/viewmodels/records/records.model';

export const InlineMarkup: React.FC<{ text: string }> = ({ text }) => {
    const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|https?:\/\/[^\s)]+)/g);
    return (
        <Fragment>
            {parts.map((p, i) => {
                if (p.startsWith('`') && p.endsWith('`')) {
                    return (
                        <code
                            key={i}
                            className="rounded bg-muted/70 px-1 py-0.5 font-mono text-[11px] text-foreground/90"
                        >
                            {p.slice(1, -1)}
                        </code>
                    );
                }
                if (p.startsWith('**') && p.endsWith('**')) {
                    return (
                        <b key={i} className="font-semibold text-foreground">
                            {p.slice(2, -2)}
                        </b>
                    );
                }
                const md = MD_LINK.exec(p);
                if (md) {
                    const href = safeHref(md[2]);
                    return href ? (
                        <SafeLink key={i} href={href}>
                            {md[1]}
                        </SafeLink>
                    ) : (
                        <Fragment key={i}>{p}</Fragment>
                    );
                }
                if (/^https?:\/\//.test(p)) {
                    // A bare URL - keep trailing punctuation (a sentence's period) out of the href.
                    const [, url, tail] = /^(.*?)([.,;:!?]*)$/.exec(p) as RegExpExecArray;
                    const href = safeHref(url);
                    return href ? (
                        <Fragment key={i}>
                            <SafeLink href={href}>{url}</SafeLink>
                            {tail}
                        </Fragment>
                    ) : (
                        <Fragment key={i}>{p}</Fragment>
                    );
                }
                return <Fragment key={i}>{p}</Fragment>;
            })}
        </Fragment>
    );
};
