import type { DeliveryStatus } from '@/models';
import { Badge, type BadgeProps } from '@/components/ui/badge';

export interface StatusBadgeProps {
    status: DeliveryStatus;
    label?: string;
}

const VARIANT: Record<DeliveryStatus, BadgeProps['variant']> = {
    'not-a-delivery': 'outline',
    loading: 'outline',
    unavailable: 'destructive',
    'run-phase': 'default',
    'awaiting-gate': 'secondary',
    delivered: 'success',
    learned: 'success',
    degraded: 'destructive',
};

/** A coloured pill naming a delivery's derived status. */
export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label }) => (
    <Badge variant={VARIANT[status]}>{label ?? status}</Badge>
);
