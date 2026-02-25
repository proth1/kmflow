"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import {
  BarChart3,
  Upload,
  Network,
  Target,
  CheckSquare,
  Eye,
  Activity,
  Map,
  Bot,
  Users,
  Workflow,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Menu,
  Sun,
  Moon,
  Shield,
  FileText,
  Plug,
  Search,
  ClipboardList,
  FlaskConical,
  TrendingUp,
  Settings,
  GitBranch,
  Monitor,
  Sliders,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const navSections: NavSection[] = [
  {
    title: "Analytics",
    items: [
      { label: "Dashboard", href: "/", icon: BarChart3 },
    ],
  },
  {
    title: "Evidence",
    items: [
      { label: "Evidence Upload", href: "/evidence", icon: Upload },
      { label: "Knowledge Graph", href: "/graph/demo-1", icon: Network },
      { label: "Data Lineage", href: "/lineage", icon: GitBranch },
    ],
  },
  {
    title: "Analysis",
    items: [
      { label: "TOM Alignment", href: "/tom/demo-1", icon: Target },
      { label: "Conformance", href: "/conformance", icon: CheckSquare },
      { label: "Visualize", href: "/visualize/demo-1", icon: Eye },
    ],
  },
  {
    title: "Operations",
    items: [
      { label: "Monitoring", href: "/monitoring", icon: Activity },
      { label: "Roadmap", href: "/roadmap/demo-1", icon: Map },
      { label: "Processes", href: "/processes", icon: Workflow },
      { label: "Simulations", href: "/simulations", icon: FlaskConical },
    ],
  },
  {
    title: "Governance",
    items: [
      { label: "Governance", href: "/governance", icon: Shield },
      { label: "Reports", href: "/reports", icon: FileText },
      { label: "Analytics", href: "/analytics", icon: TrendingUp },
    ],
  },
  {
    title: "Integrations",
    items: [
      { label: "Connectors", href: "/integrations", icon: Plug },
      { label: "Shelf Requests", href: "/shelf-requests", icon: ClipboardList },
      { label: "Patterns", href: "/patterns", icon: Search },
    ],
  },
  {
    title: "AI",
    items: [
      { label: "Copilot", href: "/copilot", icon: Bot },
    ],
  },
  {
    title: "Client",
    items: [
      { label: "Portal", href: "/portal", icon: Users },
    ],
  },
  {
    title: "Admin",
    items: [
      { label: "Admin", href: "/admin", icon: Settings },
      { label: "TM Agents", href: "/admin/task-mining/agents", icon: Monitor },
      { label: "TM Policy", href: "/admin/task-mining/policy", icon: Sliders },
      { label: "TM Dashboard", href: "/admin/task-mining/dashboard", icon: Activity },
      { label: "TM Quarantine", href: "/admin/task-mining/quarantine", icon: ShieldAlert },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

interface SidebarContentProps {
  collapsed?: boolean;
  pathname: string;
  collapsedSections: Set<string>;
  onToggleSection: (title: string) => void;
}

function SidebarContent({
  collapsed = false,
  pathname,
  collapsedSections,
  onToggleSection,
}: SidebarContentProps) {
  return (
    <nav className="flex flex-col gap-1 p-2">
      {navSections.map((section) => {
        const isSectionCollapsed = collapsedSections.has(section.title);
        return (
          <div key={section.title} className="mb-1">
            {!collapsed && (
              <button
                onClick={() => onToggleSection(section.title)}
                aria-label={`${isSectionCollapsed ? "Expand" : "Collapse"} ${section.title} section`}
                aria-expanded={!isSectionCollapsed}
                className="flex w-full items-center justify-between px-2 py-1 mb-0.5"
              >
                <span className="text-xs font-semibold uppercase tracking-wider text-[hsl(var(--primary))] opacity-70">
                  {section.title}
                </span>
                <ChevronDown
                  className={cn(
                    "h-3 w-3 text-[hsl(var(--sidebar-foreground))] opacity-50 transition-transform duration-200",
                    isSectionCollapsed && "-rotate-90"
                  )}
                />
              </button>
            )}
            {(!isSectionCollapsed || collapsed) && (
              <div className="flex flex-col gap-0.5">
                {section.items.map((item) => {
                  const active = isActive(pathname, item.href);
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-2 py-2 text-sm font-medium transition-colors",
                        "text-[hsl(var(--sidebar-foreground))] hover:bg-white/10",
                        active && "bg-[hsl(var(--primary))]/20 text-[hsl(var(--primary-foreground))]",
                        collapsed && "justify-center px-2"
                      )}
                      title={collapsed ? item.label : undefined}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      {!collapsed && <span>{item.label}</span>}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="h-9 w-9 text-[hsl(var(--foreground))]"
      aria-label="Toggle theme"
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const [collapsedSections, setCollapsedSections] = React.useState<Set<string>>(
    new Set()
  );

  function toggleSection(title: string) {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(title)) {
        next.delete(title);
      } else {
        next.add(title);
      }
      return next;
    });
  }

  return (
    <div className="flex h-screen overflow-hidden bg-[hsl(var(--background))]">
      {/* Desktop Sidebar */}
      <aside
        className={cn(
          "hidden md:flex flex-col bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] transition-all duration-300 shrink-0",
          sidebarCollapsed ? "w-[72px]" : "w-[260px]"
        )}
      >
        {/* Sidebar header */}
        <div
          className={cn(
            "flex items-center border-b border-white/10 h-14 shrink-0",
            sidebarCollapsed ? "justify-center px-2" : "px-4 justify-between"
          )}
        >
          {!sidebarCollapsed && (
            <span className="font-bold text-lg tracking-tight text-[hsl(var(--primary))]">
              KMFlow
            </span>
          )}
          <button
            onClick={() => setSidebarCollapsed((v) => !v)}
            className="rounded-md p-1.5 hover:bg-white/10 transition-colors"
            aria-label="Toggle sidebar"
          >
            {sidebarCollapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Sidebar nav */}
        <div className="flex-1 overflow-y-auto">
          <SidebarContent
            collapsed={sidebarCollapsed}
            pathname={pathname}
            collapsedSections={collapsedSections}
            onToggleSection={toggleSection}
          />
        </div>
      </aside>

      {/* Mobile Sidebar Sheet */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-[260px] p-0 bg-[hsl(var(--sidebar))] text-[hsl(var(--sidebar-foreground))] border-r border-white/10">
          <SheetHeader className="h-14 px-4 border-b border-white/10 flex-row items-center space-y-0">
            <SheetTitle className="font-bold text-lg text-[hsl(var(--primary))]">
              KMFlow
            </SheetTitle>
          </SheetHeader>
          <div className="overflow-y-auto">
            <SidebarContent
              collapsed={false}
              pathname={pathname}
              collapsedSections={collapsedSections}
              onToggleSection={toggleSection}
            />
          </div>
        </SheetContent>
      </Sheet>

      {/* Main area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top header */}
        <header className="flex h-14 items-center border-b border-[hsl(var(--border))] bg-[hsl(var(--background))] px-4 shrink-0">
          {/* Mobile menu button */}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden mr-2"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </Button>

          {/* Mobile brand */}
          <span className="md:hidden font-bold text-[hsl(var(--primary))]">
            KMFlow
          </span>

          <div className="flex-1" />

          <ThemeToggle />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-[hsl(var(--background))]">
          {children}
        </main>
      </div>
    </div>
  );
}
