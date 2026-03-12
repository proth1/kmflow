import { Badge } from "@/components/ui/badge";

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  pending_approval: {
    label: "Pending",
    className: "bg-yellow-100 text-yellow-800 border-yellow-200",
  },
  approved: {
    label: "Approved",
    className: "bg-green-100 text-green-800 border-green-200",
  },
  revoked: {
    label: "Revoked",
    className: "bg-red-100 text-red-800 border-red-200",
  },
  consent_revoked: {
    label: "Consent Revoked",
    className: "bg-orange-100 text-orange-800 border-orange-200",
  },
};

export function AgentStatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className: "",
  };
  return (
    <Badge variant="outline" className={config.className}>
      {config.label}
    </Badge>
  );
}
