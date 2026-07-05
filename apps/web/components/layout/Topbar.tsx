import { Bell, ShieldCheck } from "lucide-react";
import { demoSession } from "@/features/auth/permissions";

export function Topbar() {
  return (
    <header className="sticky top-0 z-10 flex h-[72px] items-center justify-between border-b border-border bg-white/95 px-4 backdrop-blur sm:px-6 lg:px-8">
      <div className="flex items-center gap-3">
        <ShieldCheck className="text-emerald-700" aria-hidden="true" size={20} />
        <div>
          <p className="text-sm font-semibold">Governed evidence mode</p>
          <p className="text-xs text-slate-500">
            Local deterministic foundation with API-ready boundaries
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4">
        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100"
          aria-label="Notifications"
        >
          <Bell size={18} aria-hidden="true" />
        </button>
        <div className="text-right">
          <p className="text-sm font-semibold">{demoSession.user.name}</p>
          <p className="text-xs capitalize text-slate-500">{demoSession.user.role}</p>
        </div>
      </div>
    </header>
  );
}
