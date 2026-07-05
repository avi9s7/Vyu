"use client";

import {
  BookOpen,
  CheckSquare,
  FileText,
  Folder,
  Home,
  Search,
  UploadCloud
} from "lucide-react";
import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import { demoSession, hasPermission } from "@/features/auth/permissions";
import { cn } from "@/lib/utils/cn";

type NavItem = {
  label: string;
  href: Route;
  icon: typeof Home;
  permission?: "canReview";
};

const navItems: NavItem[] = [
  { label: "Home", href: "/dashboard", icon: Home },
  { label: "New Search", href: "/search/new", icon: Search },
  { label: "My Workspace", href: "/workspace", icon: Folder },
  { label: "Reports", href: "/reports/generate", icon: FileText },
  { label: "Evidence Library", href: "/evidence-library", icon: BookOpen },
  { label: "Uploads", href: "/uploads", icon: UploadCloud },
  { label: "Reviews", href: "/reviews", icon: CheckSquare, permission: "canReview" as const }
];

export function Sidebar() {
  const pathname = usePathname();
  const visibleItems = navItems.filter(
    (item) => !item.permission || hasPermission(demoSession.user.role, item.permission)
  );

  return (
    <aside className="fixed inset-y-0 left-0 z-20 hidden w-[260px] border-r border-border bg-white lg:block">
      <div className="flex h-[72px] items-center border-b border-border px-6 py-5">
        <div>
          <div className="text-lg font-bold">Vyu</div>
          <div className="text-xs font-medium text-slate-500">
            Evidence Workspace
          </div>
        </div>
      </div>
      <nav className="space-y-1 px-3 py-5" aria-label="Primary navigation">
        {visibleItems.map((item) => {
          const active =
            pathname === item.href ||
            (item.href !== "/dashboard" && pathname.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              prefetch={false}
              className={cn(
                "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-semibold text-slate-600",
                active && "bg-[var(--color-primary-soft)] text-primary"
              )}
            >
              <Icon aria-hidden="true" size={18} strokeWidth={2} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
