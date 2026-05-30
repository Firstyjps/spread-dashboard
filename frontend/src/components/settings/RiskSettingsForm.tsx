"use client";

import { type FormEvent, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Field, Input, Select } from "@/components/chrome/Field";

export function RiskSettingsForm() {
  const [pauseBeforeFundingMin, setPauseBeforeFundingMin] = useState("5");
  const [emergencyStopOnLoss, setEmergencyStopOnLoss] = useState("50");
  const [maxConsecutiveErrors, setMaxConsecutiveErrors] = useState("5");
  const [orderPolicy, setOrderPolicy] = useState("post_only");
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);

  useEffect(() => {
    void fetch("/api/risk")
      .then((r) => r.json())
      .then((data: { riskSettings?: Record<string, string> }) => {
        if (data.riskSettings?.pauseBeforeFundingMin) setPauseBeforeFundingMin(data.riskSettings.pauseBeforeFundingMin);
        if (data.riskSettings?.emergencyStopOnLoss) setEmergencyStopOnLoss(data.riskSettings.emergencyStopOnLoss);
        if (data.riskSettings?.maxConsecutiveErrors) setMaxConsecutiveErrors(data.riskSettings.maxConsecutiveErrors);
        if (data.riskSettings?.orderPolicy) setOrderPolicy(data.riskSettings.orderPolicy);
      })
      .catch(() => void 0);
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    setMessage(null);

    try {
      const response = await fetch("/api/risk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pauseBeforeFundingMin: Number(pauseBeforeFundingMin),
          emergencyStopOnLoss: Number(emergencyStopOnLoss),
          maxConsecutiveErrors: Number(maxConsecutiveErrors),
          orderPolicy,
        }),
      });

      if (!response.ok) {
        const data = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(data?.error ?? "Failed to save risk controls.");
      }

      setMessage({ text: "Risk controls saved." });
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
    <form onSubmit={handleSubmit} className="p-4 grid grid-cols-1 md:grid-cols-4 gap-4">
      <Field label="Funding pause min">
        <Input
          name="pauseBeforeFundingMin"
          type="number"
          min={0}
          value={pauseBeforeFundingMin}
          onChange={(e) => setPauseBeforeFundingMin(e.target.value)}
        />
      </Field>
      <Field label="Emergency loss">
        <Input
          name="emergencyStopOnLoss"
          type="number"
          min={0}
          step="0.01"
          value={emergencyStopOnLoss}
          onChange={(e) => setEmergencyStopOnLoss(e.target.value)}
        />
      </Field>
      <Field label="Max errors">
        <Input
          name="maxConsecutiveErrors"
          type="number"
          min={1}
          value={maxConsecutiveErrors}
          onChange={(e) => setMaxConsecutiveErrors(e.target.value)}
        />
      </Field>
      <Field label="Order policy">
        <Select
          name="orderPolicy"
          value={orderPolicy}
          onChange={(e) => setOrderPolicy(e.target.value)}
          required
        >
          <option value="post_only">post_only</option>
          <option value="reduce_only_close">reduce_only_close</option>
        </Select>
      </Field>
      <div className="md:col-span-4 flex items-center justify-end gap-3 border-t border-bd1 pt-4">
        {message ? (
          <span className={`text-[11px] ${message.error ? "text-short" : "text-long"}`}>
            {message.text}
          </span>
        ) : null}
        <button
          type="submit"
          disabled={isSaving}
          className="h-9 px-3.5 rounded-md border border-bd1 ghost text-fg2 hover:text-fg1 text-[12.5px] focus-ring flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? <Loader2 size={12} className="animate-spin" /> : null}
          {isSaving ? "Saving..." : "Save risk controls"}
        </button>
      </div>
    </form>
  );
}
