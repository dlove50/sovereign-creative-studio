"use client";

import { useEffect, useState } from "react";
import { UserCircle } from "lucide-react";

import { api, getActiveUserId, setActiveUserId } from "@/lib/api";
import type { FamilyUser } from "@/lib/types";

/**
 * Local "acting as" family user selector (attribution only — no authentication).
 * The chosen id is stored in localStorage and sent on every API request via the
 * X-SCS-Family-User-Id header. Empty selection => seeded owner/admin default.
 */
export function ActiveUserSelector() {
  const [users, setUsers] = useState<FamilyUser[]>([]);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    api
      .listFamilyUsers()
      .then((all) => setUsers(all.filter((u) => u.status === "active")))
      .catch(() => setUsers([]));
    setSelected(getActiveUserId() ?? "");
  }, []);

  function onChange(id: string) {
    setSelected(id);
    setActiveUserId(id || null);
    // Re-fetch every view under the new acting user.
    if (typeof window !== "undefined") window.location.reload();
  }

  const current = users.find((u) => u.id === selected);
  const actingName = current ? current.display_name : "Owner / Admin";

  return (
    <div className="space-y-1.5 rounded-md border border-border bg-background/40 p-3">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <UserCircle className="h-3.5 w-3.5" /> Acting as: <span className="text-foreground">{actingName}</span>
      </div>
      <select
        aria-label="Active family user"
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        className="flex h-9 w-full rounded-md border border-input bg-background/60 px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <option value="">Owner / Admin (default)</option>
        {users.map((u) => (
          <option key={u.id} value={u.id}>
            {u.display_name}
            {u.role === "owner_admin" ? " (owner)" : ""}
          </option>
        ))}
      </select>
      <p className="text-[11px] text-muted-foreground">Private local family mode</p>
    </div>
  );
}
