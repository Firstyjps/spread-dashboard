"use client";

import { type FormEvent, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

const DEFAULT_LEVERAGE = 5;

export function SettingsDefaultsForm() {
  const [exchange, setExchange] = useState("okx");
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);

  useEffect(() => {
    void fetch("/api/settings")
      .then((r) => r.json())
      .then((data: { settings?: Record<string, string> }) => {
        if (data.settings?.defaultExchange) setExchange(data.settings.defaultExchange);
      })
      .catch(() => void 0);
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setMessage(null);

    try {
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          defaultExchange: exchange,
          defaultLeverage: DEFAULT_LEVERAGE,
        }),
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(data?.error ?? "Failed to save settings.");
      }

      setMessage({ text: "Settings saved." });
    } catch (error) {
      setMessage({
        text: error instanceof Error ? error.message : "Failed to save.",
        error: true,
      });
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="p-4 grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_auto] gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="label text-[9.5px]">Default exchange</span>
        <select
          name="defaultExchange"
          value={exchange}
          onChange={(e) => setExchange(e.target.value)}
          className="h-9 w-full rounded-md bg-bg3 border border-bd1 px-3 text-[13px] text-fg1 focus:outline-none focus:border-bd2"
        >
          <option value="okx">OKX</option>
          <option value="bybit">Bybit</option>
          <option value="binance">Binance</option>
        </select>
      </label>
      <div className="flex items-end gap-3">
        <button
          type="submit"
          disabled={isSaving}
          className="h-9 px-3.5 rounded-md border border-bd1 ghost text-fg2 hover:text-fg1 text-[12.5px] focus-ring disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
        >
          {isSaving ? <Loader2 size={12} className="animate-spin" /> : null}
          {isSaving ? "Saving..." : "Save settings"}
        </button>
        {message ? (
          <span
            className={`text-[11px] ${message.error ? "text-short" : "text-long"}`}
          >
            {message.text}
          </span>
        ) : null}
      </div>
    </form>
  );
}
