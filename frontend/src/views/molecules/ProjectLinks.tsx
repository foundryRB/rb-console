import type { FleetItem } from '@/models';
import { projectLinks } from '@/utils';

import { QuickLink } from '@/views/atoms/QuickLink';

export const ProjectLinks: React.FC<{ p: FleetItem }> = ({ p }) => {
    if (!p.onboarded) return null;
    const l = projectLinks(p.name.toLowerCase(), p.app_name, p.host);
    return (
        <span className="vf-project-links inline-flex flex-wrap gap-2">
            <QuickLink href={l.docs}>docs↗</QuickLink>
            <QuickLink href={l.argocd}>argo↗</QuickLink>
            <QuickLink href={l.grafana}>graf↗</QuickLink>
        </span>
    );
};
