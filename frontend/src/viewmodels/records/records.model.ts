export const MD_LINK = /^\[([^\]]+)\]\(([^)]+)\)$/;

export const safeHref = (url: string): string | null => {
    const u = url.trim();
    return /^(https?:\/\/|mailto:|\/)/i.test(u) ? u : null;
};

export const splitRow = (line: string): string[] =>
    line
        .replace(/^\s*\|/, '')
        .replace(/\|\s*$/, '')
        .split('|')
        .map((c) => c.trim());

export const isSeparatorRow = (line: string): boolean =>
    /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes('-');
