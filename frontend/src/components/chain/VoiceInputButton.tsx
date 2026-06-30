"use client";

import { useCallback, useRef, useState } from "react";
import { Loader2, Mic, MicOff } from "lucide-react";

import { Button } from "@/components/ui/button";

interface VoiceInputButtonProps {
  /** Called with transcribed text when recording completes. */
  onTranscript: (text: string) => void;
  disabled?: boolean;
}

type Status = "idle" | "recording" | "uploading";

/**
 * Whisper Flow voice input button — record microphone audio, transcribe locally
 * via POST /api/audio/transcribe, insert text into the caller's field.
 *
 * Separate from Piper TTS (text-to-speech). This is speech-to-text for prompts.
 * No credits charged. No DB record created.
 */
export function VoiceInputButton({ onTranscript, disabled }: VoiceInputButtonProps) {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size === 0) {
          setStatus("idle");
          setError("No audio was captured.");
          return;
        }
        setStatus("uploading");
        try {
          const fd = new FormData();
          fd.append("file", blob, "voice-input.webm");
          const res = await fetch("/api/audio/transcribe", {
            method: "POST",
            body: fd,
            credentials: "include",
          });
          const data = (await res.json()) as { text: string; error: string | null };
          if (data.error) {
            setError(data.error);
          } else if (data.text?.trim()) {
            onTranscript(data.text.trim());
          } else {
            setError("No speech detected. Try again.");
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : "Transcription failed.");
        }
        setStatus("idle");
      };

      recorder.start();
      recorderRef.current = recorder;
      setStatus("recording");
    } catch (e) {
      if (e instanceof DOMException && e.name === "NotAllowedError") {
        setError("Microphone permission denied. Allow microphone access in your browser.");
      } else {
        setError(e instanceof Error ? e.message : "Could not start recording.");
      }
      setStatus("idle");
    }
  }, [onTranscript]);

  const stopRecording = useCallback(() => {
    recorderRef.current?.stop();
    recorderRef.current = null;
  }, []);

  if (status === "recording") {
    return (
      <Button
        type="button"
        variant="destructive"
        size="sm"
        onClick={stopRecording}
        aria-label="Stop recording"
        title="Click to stop and transcribe"
        className="shrink-0 animate-pulse"
      >
        <MicOff className="h-4 w-4" />
      </Button>
    );
  }

  if (status === "uploading") {
    return (
      <Button type="button" variant="outline" size="sm" disabled className="shrink-0">
        <Loader2 className="h-4 w-4 animate-spin" />
      </Button>
    );
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={startRecording}
        aria-label="Record voice input"
        title="Speak your prompt"
        className="shrink-0"
      >
        <Mic className="h-4 w-4" />
      </Button>
      {error ? (
        <p className="text-xs text-destructive leading-tight max-w-[200px]">{error}</p>
      ) : null}
    </div>
  );
}
