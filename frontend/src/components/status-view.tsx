"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, RefreshCw, XCircle } from "lucide-react";

import { API_BASE, api } from "@/lib/api";
import type { AppStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type ConnState = "checking" | "connected" | "error";

export function StatusView() {
  const [conn, setConn] = useState<ConnState>("checking");
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  function loadStatus() {
    setRefreshing(true);
    setConn((current) => (current === "connected" ? current : "checking"));
    setErrorMsg(null);
    api
      .getStatus()
      .then((s) => {
        setStatus(s);
        setConn("connected");
      })
      .catch((err) => {
        setErrorMsg(err instanceof Error ? err.message : "Unreachable");
        setConn("error");
      })
      .finally(() => setRefreshing(false));
  }

  useEffect(() => {
    loadStatus();
  }, []);

  return (
    <div className="max-w-3xl space-y-6">
      <div className="flex justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={loadStatus}
          disabled={refreshing}
        >
          {refreshing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh
        </Button>
      </div>

      {/* Connection */}
      <Card role={conn === "error" ? "alert" : "status"} aria-live="polite">
        <CardContent className="flex items-center gap-4 p-5">
          {conn === "checking" ? (
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          ) : conn === "connected" ? (
            <CheckCircle2 className="h-6 w-6 text-emerald-400" />
          ) : (
            <XCircle className="h-6 w-6 text-destructive" />
          )}
          <div className="min-w-0">
            <p className="font-medium">
              {conn === "checking"
                ? "Checking API connection…"
                : conn === "connected"
                  ? "API connected"
                  : "API not reachable"}
            </p>
            <p className="break-words text-xs leading-relaxed text-muted-foreground">
              {API_BASE}
              {conn === "error" && errorMsg ? ` — ${errorMsg}` : ""}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Operating mode */}
      {status ? (
        (() => {
          const fullStack =
            status.generator_backend === "comfyui" &&
            status.product_scene_backend === "comfyui" &&
            status.video_backend === "comfyui";
          return (
            <Card>
              <CardContent className="flex items-center gap-4 p-5">
                <CheckCircle2
                  className={`h-6 w-6 ${fullStack ? "text-emerald-400" : "text-muted-foreground"}`}
                />
                <div>
                  <p className="font-medium">
                    {fullStack ? "Full Local Production Mode" : "Mock fallback mode"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {fullStack
                      ? "Real local stack: ComfyUI product scenes, local Qwen copy, ComfyUI/LTX video. Mock fallback available."
                      : "Running on the built-in mock fallback. Start ComfyUI / Ollama to enable the full local stack."}
                  </p>
                </div>
              </CardContent>
            </Card>
          );
        })()
      ) : null}

      {/* Configuration */}
      {status ? (
        <Card>
          <CardContent className="divide-y divide-border p-0">
            <Row
              label="Base text-to-image backend"
              value={status.generator_backend}
              mock={status.generator_backend === "mock"}
            />
            <Row
              label="Product scene backend"
              value={status.product_scene_backend}
              mock={status.product_scene_backend === "mock"}
            />
            <Row
              label="Product scene model"
              value={status.product_scene_model}
            />
            <Row
              label="Product scene mode"
              value={status.product_scene_mode}
            />
            <Row label="Copy provider" value={status.copy_backend} mock={status.copy_backend === "mock"} />
            <Row label="Video backend" value={status.video_backend} mock={status.video_backend === "mock"} />
            <Row label="Video engine" value={status.video_engine} />
            <Row
              label="Video to Text backend"
              value={status.transcription_backend}
              mock={status.transcription_backend === "mock"}
              ok={status.transcription_available}
              danger={!status.transcription_available}
            />
            <Row
              label="Transcription model"
              value={`${status.transcription_model_name} / ${status.transcription_device} / ${status.transcription_compute_type}`}
            />
            <Row
              label="ffmpeg"
              value={status.transcription_ffmpeg_available ? "Available" : "Missing"}
              ok={status.transcription_ffmpeg_available}
              danger={!status.transcription_ffmpeg_available && status.transcription_backend !== "mock"}
            />
            <Row
              label="faster-whisper"
              value={status.transcription_faster_whisper_available ? "Available" : "Missing"}
              ok={status.transcription_faster_whisper_available}
              danger={!status.transcription_faster_whisper_available && status.transcription_backend !== "mock"}
            />
            <Row
              label="ComfyUI"
              value={
                status.comfyui_configured
                  ? status.comfyui_reachable
                    ? status.comfyui_base_url
                    : "Offline"
                  : "Not configured"
              }
              ok={status.comfyui_configured && status.comfyui_reachable}
              danger={status.comfyui_configured && !status.comfyui_reachable}
            />
            <Row
              label="OpenAI key"
              value={status.openai_configured ? "Configured" : "Not set"}
              ok={status.openai_configured}
            />
            <Row
              label="Storage"
              value={status.storage_writable ? "Writable" : "Not writable"}
              ok={status.storage_writable}
              danger={!status.storage_writable}
            />
          </CardContent>
        </Card>
      ) : conn === "error" ? (
        <p className="text-sm text-muted-foreground">
          Start the backend, then reload this page. See the README quick start.
        </p>
      ) : null}
      {status?.comfyui_configured && !status.comfyui_reachable ? (
        <Card>
          <CardContent className="space-y-2 p-5">
            <div className="flex items-center gap-3">
              <XCircle className="h-5 w-5 text-destructive" />
              <p className="font-medium">ComfyUI offline</p>
            </div>
            <p className="text-sm text-muted-foreground">
              Expected URL:{" "}
              <span className="font-mono">{status.comfyui_base_url}</span>
            </p>
            <p className="text-sm text-muted-foreground">
              Start the app with{" "}
              <span className="font-mono">
                Start-Sovereign-Creative-Studio.bat
              </span>
              , then press Refresh.
            </p>
            {status.comfyui_error ? (
              <p className="break-words text-xs text-destructive">
                {status.comfyui_error}
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
      {status && !status.transcription_available ? (
        <Card>
          <CardContent className="space-y-2 p-5">
            <div className="flex items-center gap-3">
              <XCircle className="h-5 w-5 text-destructive" />
              <p className="font-medium">Real local transcription is not ready</p>
            </div>
            <p className="text-sm text-muted-foreground">
              {status.transcription_message ??
                "ffmpeg is required for real local transcription."}
            </p>
            <p className="text-sm text-muted-foreground">
              Install ffmpeg on PATH and install faster-whisper in the backend
              virtual environment, then press Refresh.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function Row({
  label,
  value,
  mock,
  ok,
  danger,
}: {
  label: string;
  value: string;
  mock?: boolean;
  ok?: boolean;
  danger?: boolean;
}) {
  const variant = danger
    ? "destructive"
    : mock
      ? "muted"
      : ok
        ? "success"
        : "default";
  return (
    <div className="flex flex-col items-start justify-between gap-2 p-4 sm:flex-row sm:items-center sm:gap-4">
      <span className="text-sm text-muted-foreground">{label}</span>
      <Badge variant={variant} className="max-w-full break-all text-left font-mono text-xs sm:max-w-[60%]">
        {value}
      </Badge>
    </div>
  );
}
