import type { FleetItem } from '@/models';
import { githubUrl } from '@/utils';

export const ProjectName: React.FC<{ p: FleetItem }> = ({ p }) => (
    <div className="vf-project-name min-w-0">
        <div className="flex items-center gap-1.5">
            <a
                href={githubUrl(p.repo)}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="font-medium hover:text-link"
                title={`${p.repo} - open on GitHub`}
            >
                {p.name}
            </a>
            {p.hidden && (
                <span className="rounded bg-muted px-1 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">
                    hidden
                </span>
            )}
            {/* Marks a repo the Foundry is built out of, so its empty Live and Delivery cells
                read as "never deployed, by nature" rather than as an app that failed to come
                up. Neutral like the hidden badge - the board's only colour stays paused-amber. */}
            {p.role === 'core' && (
                <span
                    title="The Foundry is built out of this repo - it is declared in foundry.yaml, never onboarded as an app, and has nothing to deploy"
                    className="rounded bg-muted px-1 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground"
                >
                    core
                </span>
            )}
        </div>
        <div className="vf-repo-slug font-mono text-[11px] text-muted-foreground" title={p.repo}>
            {p.repo}
        </div>
    </div>
);
