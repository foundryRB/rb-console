import { Link } from 'react-router-dom';
import type { FleetItem } from '@/models';
import { projectLinks } from '@/utils';

import { ProjectChip } from '@/views/atoms/ProjectChip';

export const ProjectSignals: React.FC<{ p: FleetItem; attention?: number }> = ({
    p,
    attention,
}) => {
    const l = projectLinks(p.name.toLowerCase(), p.app_name, p.host);
    // A core repo is not a delivery and can never be onboarded, so the three phase chips have
    // nothing to report about it - shown unlit they read as a delivery that never started, which
    // is the misread the core role exists to end. Its inbox count still shows: the platform and
    // the playbook take maintenance tickets like any other repo, and that is the one signal here
    // that is true of them.
    const phases = p.role !== 'core';
    return (
        <span className="vf-project-signals inline-flex flex-wrap gap-1">
            {phases && (
                <>
                    <ProjectChip on={p.estimatekit} href={l.estimatekit}>
                        scope
                    </ProjectChip>
                    <ProjectChip on={p.protopane} href={l.protopane}>
                        design
                    </ProjectChip>
                    <ProjectChip
                        on={p.onboarded}
                        href={l.live}
                        tone="bg-[hsl(var(--success))]/15 text-[hsl(var(--success))]"
                    >
                        onboarded
                    </ProjectChip>
                </>
            )}
            {(attention ?? 0) > 0 && (
                <Link
                    to={`/d?repo=${encodeURIComponent(p.repo)}&mode=maintenance`}
                    onClick={(e) => e.stopPropagation()}
                    title={`${attention} item(s) in the Inbox - open the Maintenance tab`}
                    className="inline-flex items-center gap-1 rounded bg-amber-400/15 px-1.5 py-0.5 text-[10px] text-amber-400 hover:underline"
                >
                    <span className="h-1 w-1 rounded-full bg-current" />
                    {attention} to tend
                </Link>
            )}
        </span>
    );
};
