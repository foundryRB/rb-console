export const prefersReducedMotion = (): boolean =>
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export const REDRIVE = /```redrive\r?\n([\s\S]*?)```/;

export const splitRedrive = (
    text: string,
): { before: string; feedback: string; after: string } | null => {
    const m = REDRIVE.exec(text);
    if (!m) return null;
    const feedback = m[1].trim();
    if (!feedback) return null;
    return {
        before: text.slice(0, m.index).trim(),
        feedback,
        after: text.slice(m.index + m[0].length).trim(),
    };
};
