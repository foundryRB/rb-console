import type { Seed } from '@/models';
import { Badge, type BadgeProps } from '@/components/ui/badge';

export interface SeedBadgeProps {
    seed: Seed;
    /** The source a demo rehearses (its owner/name); named in the pill's title when set. */
    demoOf?: string;
}

const LABEL: Record<Exclude<Seed, ''>, string> = {
    new: 'new',
    'follow-on': 'follow-on',
    recast: 'recast',
    demo: 'demo',
};

const VARIANT: Record<Exclude<Seed, ''>, BadgeProps['variant']> = {
    new: 'outline',
    'follow-on': 'secondary',
    recast: 'secondary',
    demo: 'default',
};

/** A pill naming what the line grows from, read off the repo's tags: an ask (new), a shipped
 *  phase (follow-on), an existing app seeded into the repo (recast), or a shipped line the org
 *  holds, rehearsed under a demo- name (demo, its source named in the title). Nothing renders
 *  when the source could not read the tags: an unseen fact is shown as unseen, never as new. */
export const SeedBadge: React.FC<SeedBadgeProps> = ({ seed, demoOf }) =>
    seed === '' ? null : (
        <Badge
            variant={VARIANT[seed]}
            title={
                seed === 'demo' && demoOf
                    ? `A rehearsal of ${demoOf}: every phase copies that line's deliverable and attests the copy`
                    : "What the line grows from, read off the repo's tags"
            }
        >
            {LABEL[seed]}
        </Badge>
    );
