import HealthStatus from "@/components/HealthStatus";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import {
  Upload,
  Network,
  Target,
  CheckSquare,
  Activity,
  Bot,
} from "lucide-react";

const quickActions = [
  {
    icon: Upload,
    title: "Evidence Upload",
    description: "Ingest client evidence across 12 categories",
    href: "/evidence",
  },
  {
    icon: Network,
    title: "Knowledge Graph",
    description: "Explore semantic relationships in the evidence graph",
    href: "/graph/1db9aa11-c73b-5867-82a3-864dd695cf23",
  },
  {
    icon: Target,
    title: "TOM Analysis",
    description: "Automated Target Operating Model gap analysis",
    href: "/tom/1db9aa11-c73b-5867-82a3-864dd695cf23",
  },
  {
    icon: CheckSquare,
    title: "Conformance",
    description: "Process conformance checking against reference models",
    href: "/conformance",
  },
  {
    icon: Activity,
    title: "Monitoring",
    description: "Real-time platform and engagement monitoring",
    href: "/monitoring",
  },
  {
    icon: Bot,
    title: "Copilot",
    description: "AI-powered process intelligence assistant",
    href: "/copilot",
  },
];

export default function HomePage() {
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-1">
          Process Intelligence Dashboard
        </h1>
        <p className="text-[hsl(var(--muted-foreground))] text-base">
          AI-powered consulting engagement platform
        </p>
      </div>

      {/* Platform Health */}
      <Card className="mb-8">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">Platform Status</CardTitle>
          <CardDescription>Backend services and API health</CardDescription>
        </CardHeader>
        <CardContent>
          <HealthStatus />
        </CardContent>
      </Card>

      {/* Quick Actions Grid */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {quickActions.map((action) => {
            const Icon = action.icon;
            return (
              <Link key={action.href} href={action.href} className="group">
                <Card className="h-full transition-shadow hover:shadow-md cursor-pointer">
                  <CardHeader className="pb-2">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-md bg-[hsl(var(--primary))]/10">
                        <Icon className="h-5 w-5 text-[hsl(var(--primary))]" />
                      </div>
                      <CardTitle className="text-base group-hover:text-[hsl(var(--primary))] transition-colors">
                        {action.title}
                      </CardTitle>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <CardDescription>{action.description}</CardDescription>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      </div>

      {/* About */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">About KMFlow</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-[hsl(var(--muted-foreground))] leading-relaxed">
            KMFlow transforms consulting delivery by enabling data-driven process
            conversations from day one of client engagement. It ingests diverse
            client evidence, builds semantic relationships, synthesizes
            confidence-scored process views, and automates TOM gap analysis.
          </p>
          <ul className="text-sm text-[hsl(var(--muted-foreground))] space-y-1 list-disc list-inside">
            <li>Evidence-first approach across 12 evidence categories</li>
            <li>Semantic knowledge graph with Neo4j</li>
            <li>Confidence-scored process model generation (Consensus algorithm)</li>
            <li>Automated Target Operating Model gap analysis</li>
            <li>Regulatory, policy, and control overlay as connective tissue</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
