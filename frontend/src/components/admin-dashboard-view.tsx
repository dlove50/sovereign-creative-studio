"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Coins,
  Loader2,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Users,
} from "lucide-react";

import { api, getActiveUserId } from "@/lib/api";
import type { AdminDashboard, AdminJobSummary, FamilyUser } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { confirmDialog } from "@/components/ui/confirm-host";

export function AdminDashboardView() {
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [savingUser, setSavingUser] = useState<string | null>(null);
  const [savingCredit, setSavingCredit] = useState<string | null>(null);
  const [activeUserId, setActiveUserId] = useState<string | null>(null);

  useEffect(() => {
    setActiveUserId(getActiveUserId());
  }, []);

  function load() {
    setLoading(true);
    setError(null);
    api
      .getAdminDashboard()
      .then(setDashboard)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load admin dashboard"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  async function resetSafeDefaults() {
    if (!await confirmDialog("Reset the image model to flux-kontext and switch video generation to the built-in test (mock) engine? Real video generation stays off until you turn it back on.")) return;
    setResetting(true);
    setError(null);
    try {
      await api.resetAdminSafeWorkflowDefaults();
      await api.getAdminDashboard().then(setDashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Safe reset failed");
    } finally {
      setResetting(false);
    }
  }

  async function createFamilyUser(input: {
    display_name: string;
    role: FamilyUser["role"];
    initial_credits: number;
    notes: string | null;
  }) {
    setSavingUser("create");
    setError(null);
    try {
      await api.createFamilyUser({ ...input, status: "active" });
      await api.getAdminDashboard().then(setDashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create family user");
    } finally {
      setSavingUser(null);
    }
  }

  async function updateFamilyUser(
    id: string,
    input: {
      display_name: string;
      role: FamilyUser["role"];
      status: FamilyUser["status"];
      notes: string | null;
    },
  ) {
    setSavingUser(id);
    setError(null);
    try {
      await api.updateFamilyUser(id, input);
      await api.getAdminDashboard().then(setDashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update family user");
    } finally {
      setSavingUser(null);
    }
  }

  async function setFamilyUserStatus(id: string, status: FamilyUser["status"]) {
    setSavingUser(id);
    setError(null);
    try {
      if (status === "active") {
        await api.reactivateFamilyUser(id);
      } else {
        await api.disableFamilyUser(id);
      }
      await api.getAdminDashboard().then(setDashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update family user status");
    } finally {
      setSavingUser(null);
    }
  }

  async function adjustCredits(input: {
    user_id: string;
    amount: number;
    note: string;
    direction: "add" | "remove";
  }) {
    if (input.direction === "remove" && !await confirmDialog("Remove these credits from the account?")) return;
    setSavingCredit(input.direction);
    setError(null);
    try {
      if (input.direction === "add") {
        await api.addCredits(input);
      } else {
        await api.removeCredits(input);
      }
      await api.getAdminDashboard().then(setDashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not adjust credits");
    } finally {
      setSavingCredit(null);
    }
  }

  async function refundTransaction(id: string) {
    if (!await confirmDialog("Refund this credit transaction? The credits go back to the account.")) return;
    setSavingCredit(id);
    setError(null);
    try {
      await api.refundCreditTransaction(id, "Manual local admin refund.");
      await api.getAdminDashboard().then(setDashboard);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refund transaction");
    } finally {
      setSavingCredit(null);
    }
  }

  if (loading && !dashboard) {
    return (
      <Card className="max-w-2xl">
        <CardContent className="flex items-center gap-3 p-5">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Loading private admin status...</p>
        </CardContent>
      </Card>
    );
  }

  if (error && !dashboard) {
    return (
      <Card className="max-w-2xl">
        <CardContent className="flex items-center gap-3 p-5">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!dashboard) return null;

  const health = dashboard.service_health;
  const config = dashboard.model_status.current_config;
  const totalCredits = dashboard.family_users.reduce(
    (sum, user) => sum + user.credit_balance,
    0,
  );
  const actingUser = activeUserId
    ? dashboard.family_users.find((user) => user.id === activeUserId)
    : null;
  const actingLabel = actingUser ? actingUser.display_name : "Owner / Admin (default)";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="gap-1">
            <ShieldCheck className="h-3.5 w-3.5" />
            Local private family studio
          </Badge>
          <Badge variant="muted" className="gap-1">
            <Users className="h-3.5 w-3.5" />
            Acting as: {actingLabel}
          </Badge>
          <Badge variant={health.comfyui_reachable ? "success" : "destructive"}>
            ComfyUI {health.comfyui_reachable ? "online" : "offline"}
          </Badge>
          <Badge variant={health.video_backend === "mock" ? "muted" : "outline"}>
            Video: {health.video_backend}
          </Badge>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={load}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={resetSafeDefaults}
            disabled={resetting}
          >
            {resetting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RotateCcw className="h-4 w-4" />
            )}
            Reset safe workflow config
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <section className="grid gap-4 md:grid-cols-3">
        <StatCard
          icon={CheckCircle2}
          label="Service health"
          value={health.comfyui_reachable ? "Ready" : "Check ComfyUI"}
        />
        <StatCard icon={Users} label="Family users" value={dashboard.family_users.length} />
        <StatCard icon={Coins} label="Total credits" value={totalCredits} />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Current Configuration</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <ConfigItem label="Base text-to-image backend" value={health.generator_backend} />
            <ConfigItem label="Base checkpoint" value={config.image_model} />
            <ConfigItem label="Product scene backend" value={health.product_scene_backend} />
            <ConfigItem label="Product scene model" value={health.product_scene_model} />
            <ConfigItem label="Product scene mode" value={health.product_scene_mode} />
            <ConfigItem label="Video backend" value={health.video_backend} />
            <ConfigItem label="Copy provider" value={health.copy_backend} />
            <ConfigItem label="ComfyUI URL" value={health.comfyui_base_url} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Workflow Safety</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Normal operation is Full Local Production Mode (ComfyUI/Flux Kontext scenes,
              local Qwen copy, ComfyUI/LTX video). The safe-reset button is a recovery
              fallback that restores a known-good config (mock video) if a workflow misbehaves.
            </p>
            <div className="grid gap-2">
              {Object.entries(dashboard.workflow_config).map(([key, value]) => (
                <ConfigItem key={key} label={key.replaceAll("_", " ")} value={value} />
              ))}
              {Object.keys(dashboard.workflow_config).length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No persisted workflow overrides found.
                </p>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2 pt-1">
              <Link href="/workflow-manager" className="text-sm text-primary hover:underline">
                Open Workflow Manager
              </Link>
              <Link href="/model-manager" className="text-sm text-primary hover:underline">
                Open Model Manager
              </Link>
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <UsersCard
          dashboard={dashboard}
          onCreate={createFamilyUser}
          onStatus={setFamilyUserStatus}
          onUpdate={updateFamilyUser}
          savingUser={savingUser}
        />
        <CreditLedgerCard
          dashboard={dashboard}
          onAdjust={adjustCredits}
          onRefund={refundTransaction}
          savingCredit={savingCredit}
        />
      </section>

      <section>
        <Link
          href="/admin/topups"
          className="flex items-center justify-between rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm transition-colors hover:bg-amber-500/15"
        >
          <span>
            <span className="font-semibold text-amber-300">
              Local Credit Top-Up
            </span>
            <span className="ml-2 text-muted-foreground">
              Grant local credits to a family member — local only, no real money or payment provider.
            </span>
          </span>
          <span className="text-muted-foreground">→</span>
        </Link>
      </section>

      <section>
        <Link
          href="/admin/backups"
          className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-4 py-3 text-sm transition-colors hover:bg-muted"
        >
          <span>
            <span className="font-semibold">Backup &amp; Recovery</span>
            <span className="ml-2 text-muted-foreground">
              Create a local snapshot ZIP of the database, storage, and config. Restore is manual.
            </span>
          </span>
          <span className="text-muted-foreground">→</span>
        </Link>
      </section>

      <section className="grid gap-3 xl:grid-cols-2">
        <Link
          href="/admin/jobs"
          className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-4 py-3 text-sm transition-colors hover:bg-muted"
        >
          <span>
            <span className="font-semibold">Job Monitor</span>
            <span className="ml-2 text-muted-foreground">
              Inspect queued, running, completed, and failed local generation jobs.
            </span>
          </span>
          <span className="text-muted-foreground">-&gt;</span>
        </Link>
        <Link
          href="/admin/storage"
          className="flex items-center justify-between rounded-lg border border-border bg-background/40 px-4 py-3 text-sm transition-colors hover:bg-muted"
        >
          <span>
            <span className="font-semibold">Storage Cleanup</span>
            <span className="ml-2 text-muted-foreground">
              Dry-run safe cleanup while protecting uploads and referenced assets.
            </span>
          </span>
          <span className="text-muted-foreground">-&gt;</span>
        </Link>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <JobsCard title="Recent Jobs" jobs={dashboard.recent_jobs} />
        <JobsCard title="Failed Jobs" jobs={dashboard.failed_jobs} empty="No failed jobs right now." />
      </section>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof CheckCircle2;
  label: string;
  value: string | number;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <span className="flex h-11 w-11 items-center justify-center rounded-md bg-primary/15 text-primary">
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <p className="text-xl font-semibold">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function ConfigItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-border bg-background/40 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 truncate font-mono text-xs">{value}</p>
    </div>
  );
}

function UsersCard({
  dashboard,
  onCreate,
  onStatus,
  onUpdate,
  savingUser,
}: {
  dashboard: AdminDashboard;
  onCreate: (input: {
    display_name: string;
    role: FamilyUser["role"];
    initial_credits: number;
    notes: string | null;
  }) => Promise<void>;
  onStatus: (id: string, status: FamilyUser["status"]) => Promise<void>;
  onUpdate: (
    id: string,
    input: {
      display_name: string;
      role: FamilyUser["role"];
      status: FamilyUser["status"];
      notes: string | null;
    },
  ) => Promise<void>;
  savingUser: string | null;
}) {
  const [draftName, setDraftName] = useState("");
  const [draftRole, setDraftRole] = useState<FamilyUser["role"]>("family_user");
  const [draftCredits, setDraftCredits] = useState(25);
  const [draftNotes, setDraftNotes] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);

  async function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draftName.trim()) return;
    await onCreate({
      display_name: draftName.trim(),
      role: draftRole,
      initial_credits: draftCredits,
      notes: draftNotes.trim() || null,
    });
    setDraftName("");
    setDraftRole("family_user");
    setDraftCredits(25);
    setDraftNotes("");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Family Users</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          onSubmit={submitCreate}
          className="space-y-3 rounded-md border border-border bg-background/40 p-3"
        >
          <div>
            <p className="text-sm font-medium">Add family member</p>
            <p className="text-xs text-muted-foreground">
              Local family users only. No public signup or passwords in this phase.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              onChange={(event) => setDraftName(event.target.value)}
              placeholder="Display name"
              value={draftName}
            />
            <select
              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              onChange={(event) => setDraftRole(event.target.value as FamilyUser["role"])}
              value={draftRole}
            >
              <option value="family_user">Family user</option>
              <option value="guest">Guest</option>
              <option value="owner_admin">Owner/admin</option>
            </select>
            <input
              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              min={0}
              onChange={(event) => setDraftCredits(Number(event.target.value) || 0)}
              type="number"
              value={draftCredits}
            />
            <input
              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              onChange={(event) => setDraftNotes(event.target.value)}
              placeholder="Optional notes"
              value={draftNotes}
            />
          </div>
          <Button
            type="submit"
            size="sm"
            disabled={savingUser === "create" || !draftName.trim()}
          >
            {savingUser === "create" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : null}
            Create family user
          </Button>
        </form>
        {dashboard.family_users.map((user) => (
          <FamilyUserRow
            editing={editingId === user.id}
            key={user.id}
            onCancel={() => setEditingId(null)}
            onEdit={() => setEditingId(user.id)}
            onStatus={onStatus}
            onUpdate={async (input) => {
              await onUpdate(user.id, input);
              setEditingId(null);
            }}
            saving={savingUser === user.id}
            user={user}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function FamilyUserRow({
  editing,
  onCancel,
  onEdit,
  onStatus,
  onUpdate,
  saving,
  user,
}: {
  editing: boolean;
  onCancel: () => void;
  onEdit: () => void;
  onStatus: (id: string, status: FamilyUser["status"]) => Promise<void>;
  onUpdate: (input: {
    display_name: string;
    role: FamilyUser["role"];
    status: FamilyUser["status"];
    notes: string | null;
  }) => Promise<void>;
  saving: boolean;
  user: FamilyUser;
}) {
  const [name, setName] = useState(user.display_name);
  const [role, setRole] = useState<FamilyUser["role"]>(user.role);
  const [status, setStatus] = useState<FamilyUser["status"]>(user.status);
  const [notes, setNotes] = useState(user.notes ?? "");

  useEffect(() => {
    setName(user.display_name);
    setRole(user.role);
    setStatus(user.status);
    setNotes(user.notes ?? "");
  }, [user]);

  if (editing) {
    return (
      <form
        className="space-y-3 rounded-md border border-border p-3"
        onSubmit={(event) => {
          event.preventDefault();
          onUpdate({
            display_name: name.trim(),
            role,
            status,
            notes: notes.trim() || null,
          });
        }}
      >
        <div className="grid gap-2 sm:grid-cols-2">
          <input
            className="rounded-md border border-border bg-background px-3 py-2 text-sm"
            onChange={(event) => setName(event.target.value)}
            value={name}
          />
          <select
            className="rounded-md border border-border bg-background px-3 py-2 text-sm"
            onChange={(event) => setRole(event.target.value as FamilyUser["role"])}
            value={role}
          >
            <option value="owner_admin">Owner/admin</option>
            <option value="family_user">Family user</option>
            <option value="guest">Guest</option>
          </select>
          <select
            className="rounded-md border border-border bg-background px-3 py-2 text-sm"
            onChange={(event) => setStatus(event.target.value as FamilyUser["status"])}
            value={status}
          >
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
          </select>
          <input
            className="rounded-md border border-border bg-background px-3 py-2 text-sm"
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Optional notes"
            value={notes}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="sm" disabled={saving || !name.trim()}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Save
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{user.display_name}</p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
        </div>
        <Badge variant="outline">{formatRole(user.role)}</Badge>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <Badge variant={user.status === "active" ? "success" : "muted"}>
          {user.status}
        </Badge>
        <Badge variant="muted">{user.credit_balance} credits</Badge>
        <Badge variant="muted">created {formatDate(user.created_at)}</Badge>
        {user.last_activity_at ? (
          <Badge variant="muted">active {formatDate(user.last_activity_at)}</Badge>
        ) : null}
      </div>
      {user.notes ? (
        <p className="mt-2 text-xs text-muted-foreground">{user.notes}</p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onEdit}>
          Edit
        </Button>
        {user.status === "active" ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onStatus(user.id, "disabled")}
            disabled={saving}
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Disable
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onStatus(user.id, "active")}
            disabled={saving}
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Reactivate
          </Button>
        )}
      </div>
    </div>
  );
}

function CreditLedgerCard({
  dashboard,
  onAdjust,
  onRefund,
  savingCredit,
}: {
  dashboard: AdminDashboard;
  onAdjust: (input: {
    user_id: string;
    amount: number;
    note: string;
    direction: "add" | "remove";
  }) => Promise<void>;
  onRefund: (id: string) => Promise<void>;
  savingCredit: string | null;
}) {
  const activeUsers = dashboard.family_users.filter((user) => user.status === "active");
  const [userId, setUserId] = useState(activeUsers[0]?.id ?? dashboard.family_users[0]?.id ?? "");
  const [amount, setAmount] = useState(10);
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!userId && dashboard.family_users[0]) {
      setUserId(dashboard.family_users[0].id);
    }
  }, [dashboard.family_users, userId]);

  async function submit(direction: "add" | "remove") {
    if (!userId || amount <= 0 || !note.trim()) return;
    await onAdjust({ user_id: userId, amount, note: note.trim(), direction });
    setNote("");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Credits and Usage</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded-md border border-border bg-background/40 p-3">
          <p className="text-sm font-medium">Manual local credit adjustment</p>
          <p className="text-xs text-muted-foreground">
            Private family ledger only. This is not payment processing or a paid top-up.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <select
              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              onChange={(event) => setUserId(event.target.value)}
              value={userId}
            >
              {dashboard.family_users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.display_name} ({user.credit_balance} credits)
                </option>
              ))}
            </select>
            <input
              className="rounded-md border border-border bg-background px-3 py-2 text-sm"
              min={1}
              onChange={(event) => setAmount(Number(event.target.value) || 0)}
              type="number"
              value={amount}
            />
            <input
              className="rounded-md border border-border bg-background px-3 py-2 text-sm sm:col-span-2"
              onChange={(event) => setNote(event.target.value)}
              placeholder="Required note/reason"
              value={note}
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => submit("add")}
              disabled={savingCredit === "add" || !note.trim() || amount <= 0}
            >
              {savingCredit === "add" ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Add credits
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => submit("remove")}
              disabled={savingCredit === "remove" || !note.trim() || amount <= 0}
            >
              {savingCredit === "remove" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : null}
              Remove credits
            </Button>
          </div>
        </div>

        <div className="grid gap-2">
          {dashboard.family_users.map((user) => (
            <div
              key={user.id}
              className="flex items-center justify-between rounded-md border border-border p-3"
            >
              <div>
                <p className="text-sm font-medium">{user.display_name}</p>
                <p className="text-xs text-muted-foreground">
                  {formatRole(user.role)} - {user.status}
                </p>
              </div>
              <Badge variant={user.status === "active" ? "success" : "muted"}>
                {user.credit_balance} credits
              </Badge>
            </div>
          ))}
        </div>

        <div>
          <p className="text-sm font-medium">Recent generation usage</p>
          <p className="text-xs text-muted-foreground">
            Failed jobs show as not charged unless a matching ledger charge exists.
          </p>
        </div>
        {dashboard.recent_usage.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent generation usage yet.</p>
        ) : (
          dashboard.recent_usage.slice(0, 8).map((item) => (
            <div key={`${item.feature}-${item.id}`} className="rounded-md border border-border p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">{item.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {item.user_name} - {item.feature} - {formatDate(item.created_at)}
                  </p>
                </div>
                <Badge
                  variant={
                    item.ledger_status === "charged"
                      ? "muted"
                      : item.ledger_status.includes("refunded")
                        ? "success"
                        : "outline"
                  }
                >
                  {item.ledger_status.replaceAll("_", " ")}
                </Badge>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Status: {item.status}. Credits charged: {item.credits_charged}.
              </p>
            </div>
          ))
        )}

        <div>
          <p className="text-sm font-medium">Recent credit transactions</p>
        </div>
        {dashboard.recent_credit_transactions.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No credit transactions yet. Failed jobs are not charged by the existing image ledger.
          </p>
        ) : (
          dashboard.recent_credit_transactions.map((tx) => (
            <div key={tx.id} className="rounded-md border border-border p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">{tx.reason}</p>
                  <p className="text-xs text-muted-foreground">
                    {tx.user_name} - {tx.related_feature} - {formatDate(tx.created_at)}
                  </p>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Badge variant={tx.amount >= 0 ? "success" : "muted"}>
                    {tx.amount >= 0 ? "+" : ""}
                    {tx.amount}
                  </Badge>
                  <Badge variant="outline">{tx.transaction_type.replaceAll("_", " ")}</Badge>
                  <Badge variant={tx.status === "refunded" ? "success" : "muted"}>
                    {tx.status}
                  </Badge>
                </div>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Balance after: {tx.balance_after}
              </p>
              {tx.note ? (
                <p className="mt-1 text-xs text-muted-foreground">{tx.note}</p>
              ) : null}
              {tx.amount < 0 && tx.status !== "refunded" ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => onRefund(tx.id)}
                  disabled={savingCredit === tx.id}
                >
                  {savingCredit === tx.id ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : null}
                  Refund
                </Button>
              ) : null}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function JobsCard({
  empty = "No jobs found.",
  jobs,
  title,
}: {
  empty?: string;
  jobs: AdminJobSummary[];
  title: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {jobs.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          jobs.map((job) => <JobRow key={`${job.type}-${job.id}`} job={job} />)
        )}
      </CardContent>
    </Card>
  );
}

function JobRow({ job }: { job: AdminJobSummary }) {
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{job.label}</p>
          <p className="text-xs text-muted-foreground">
            {job.type} - {formatDate(job.created_at)}
          </p>
        </div>
        <Badge variant={job.status === "failed" ? "destructive" : job.status === "completed" ? "success" : "muted"}>
          {job.status}
        </Badge>
      </div>
      {job.prompt ? (
        <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">{job.prompt}</p>
      ) : null}
      {job.error ? (
        <p className="mt-2 line-clamp-2 text-xs text-destructive">{job.error}</p>
      ) : null}
    </div>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatRole(role: FamilyUser["role"]) {
  if (role === "owner_admin") return "Owner/admin";
  if (role === "family_user") return "Family user";
  return "Guest";
}
