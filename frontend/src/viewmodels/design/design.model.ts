import type { Substance } from '@/models';

export const selectDesignPreview = (substance: Substance | null, screen: number) => {
    const screens = substance?.screens ?? [];
    const active = screens[Math.min(screen, Math.max(0, screens.length - 1))] ?? null;
    if (!active) return { screens, active, srcdoc: '' };
    const srcdoc = [
        '<!doctype html><html><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        `<style>${substance?.canvas_css ?? ''}</style>`,
        `<style>${substance?.theme_css ?? ''}\n${active.css ?? ''}</style>`,
        // The final style maps screen height to the iframe and keeps taller content scrollable.
        '<style>html,body{margin:0;height:100%}html{scrollbar-width:thin;scrollbar-color:rgba(0,0,0,0.3) transparent}.min-h-screen{min-height:100% !important}</style>',
        `<script>${substance?.canvas_js ?? ''}</script>`,
        '</head><body class="bg-background text-foreground">',
        active.html ?? '',
        '</body></html>',
    ].join('');
    return { screens, active, srcdoc };
};
