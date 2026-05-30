"use client";

import { FormEvent, useState } from "react";
import { Loader2, Send } from "lucide-react";
import { Button } from "@/components/chrome/Button";
import { Field, Input } from "@/components/chrome/Field";

type TelegramSettingsFormProps = {
  botTokenConfigured: boolean;
  chatIdConfigured: boolean;
  chatIdPreview: string;
};

type TestResponse = {
  ok?: boolean;
  message?: string;
  error?: string;
};

export function TelegramSettingsForm({
  botTokenConfigured,
  chatIdConfigured,
  chatIdPreview,
}: TelegramSettingsFormProps) {
  const [isTesting, setIsTesting] = useState(false);
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleTestConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsTesting(true);
    setStatus("idle");
    setMessage(null);

    try {
      const response = await fetch("/api/alerts/test", {
        method: "POST",
        cache: "no-store",
      });
      const data = (await response.json().catch(() => ({}))) as TestResponse;

      if (!response.ok || !data.ok) {
        throw new Error(data.error ?? "Telegram test failed.");
      }

      setStatus("success");
      setMessage(data.message ?? "Telegram test alert sent.");
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Telegram test failed.");
    } finally {
      setIsTesting(false);
    }
  }

  return (
    <form onSubmit={handleTestConnection} className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
      <Field label="Bot Token" hint="Read from TELEGRAM_BOT_TOKEN on the server.">
        <Input
          readOnly
          type="password"
          value={botTokenConfigured ? "configured" : ""}
          placeholder="Not configured"
          mono={false}
        />
      </Field>

      <Field label="Chat ID" hint="Read from TELEGRAM_CHAT_ID on the server.">
        <Input readOnly value={chatIdPreview} placeholder="Not configured" />
      </Field>

      <div className="md:col-span-2 flex flex-col sm:flex-row sm:items-center gap-3">
        <Button type="submit" variant="ghost-primary" size="lg" disabled={isTesting}>
          {isTesting ? (
            <Loader2 size={13} strokeWidth={1.75} className="animate-spin" />
          ) : (
            <Send size={13} strokeWidth={1.75} />
          )}
          Test Connection
        </Button>
        <div
          className={
            status === "error"
              ? "text-[12px] text-short"
              : status === "success"
                ? "text-[12px] text-long"
                : "text-[12px] text-fg3"
          }
        >
          {message ??
            (botTokenConfigured && chatIdConfigured
              ? "Ready to test the configured Telegram channel."
              : "Set both env vars before alerts can be sent.")}
        </div>
      </div>
    </form>
  );
}
