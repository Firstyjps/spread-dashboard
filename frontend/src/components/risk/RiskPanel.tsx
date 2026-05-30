import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Power, RotateCcw, Save, ShieldAlert, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/chrome/Button';
import { Field, Input } from '@/components/chrome/Field';
import { StatusDot } from '@/components/chrome/StatusDot';
import { formatNumber, formatUSD } from '@/lib/format';
import { cn } from '@/lib/cn';
import { riskApi } from '@/services/riskApi';
import type { RiskAuditItem, RiskConfig, RiskDecisionType, RiskRateStatus, RiskStatus } from '@/types/risk';

type RiskConfigForm = {
  dry_run_enabled: boolean;
  confirm_live: boolean;
  max_position_per_symbol: string;
  max_notional_exposure_usd: string;
  max_order_rate_per_minute: string;
  rate_limit_queue_timeout_s: string;
  price_sanity_band_pct: string;
  price_data_max_age_s: string;
  kill_switch_loss_threshold_usd: string;
  kill_switch_consecutive_failures: string;
  kill_switch_feed_stale_s: string;
  kill_switch_spread_inversion_pct: string;
  cooldown_minutes: string;
};

const EMPTY_FORM: RiskConfigForm = {
  dry_run_enabled: true,
  confirm_live: false,
  max_position_per_symbol: '0.1',
  max_notional_exposure_usd: '10000',
  max_order_rate_per_minute: '10',
  rate_limit_queue_timeout_s: '30',
  price_sanity_band_pct: '0.5',
  price_data_max_age_s: '2',
  kill_switch_loss_threshold_usd: '500',
  kill_switch_consecutive_failures: '3',
  kill_switch_feed_stale_s: '30',
  kill_switch_spread_inversion_pct: '2',
  cooldown_minutes: '5',
};

function configToForm(config: RiskConfig): RiskConfigForm {
  return {
    dry_run_enabled: config.dry_run_enabled,
    confirm_live: false,
    max_position_per_symbol: String(config.max_position_per_symbol),
    max_notional_exposure_usd: String(config.max_notional_exposure_usd),
    max_order_rate_per_minute: String(config.max_order_rate_per_minute),
    rate_limit_queue_timeout_s: String(config.rate_limit_queue_timeout_s),
    price_sanity_band_pct: String(config.price_sanity_band_pct),
    price_data_max_age_s: String(config.price_data_max_age_s),
    kill_switch_loss_threshold_usd: String(config.kill_switch_loss_threshold_usd),
    kill_switch_consecutive_failures: String(config.kill_switch_consecutive_failures),
    kill_switch_feed_stale_s: String(config.kill_switch_feed_stale_s),
    kill_switch_spread_inversion_pct: String(config.kill_switch_spread_inversion_pct),
    cooldown_minutes: String(config.cooldown_minutes),
  };
}

function formToPatch(form: RiskConfigForm) {
  return {
    dry_run_enabled: form.dry_run_enabled,
    confirm_live: form.confirm_live,
    max_position_per_symbol: Number(form.max_position_per_symbol),
    max_notional_exposure_usd: Number(form.max_notional_exposure_usd),
    max_order_rate_per_minute: Number(form.max_order_rate_per_minute),
    rate_limit_queue_timeout_s: Number(form.rate_limit_queue_timeout_s),
    price_sanity_band_pct: Number(form.price_sanity_band_pct),
    price_data_max_age_s: Number(form.price_data_max_age_s),
    kill_switch_loss_threshold_usd: Number(form.kill_switch_loss_threshold_usd),
    kill_switch_consecutive_failures: Number(form.kill_switch_consecutive_failures),
    kill_switch_feed_stale_s: Number(form.kill_switch_feed_stale_s),
    kill_switch_spread_inversion_pct: Number(form.kill_switch_spread_inversion_pct),
    cooldown_minutes: Number(form.cooldown_minutes),
  };
}

function riskTone(status?: RiskStatus): 'long' | 'warn' | 'short' | 'info' | 'muted' {
  if (!status) return 'muted';
  if (status.kill_switch_active || status.circuit_breaker_tripped) return 'short';
  if (status.cooldown_active) return 'warn';
  if (status.dry_run_mode) return 'info';
  return 'long';
}

function decisionClass(decision: RiskDecisionType) {
  if (decision === 'approve') return 'text-long';
  if (decision === 'reject') return 'text-short';
  return 'text-info';
}

function sumRateUsed(rates: Record<string, RiskRateStatus>) {
  return Object.values(rates).reduce((total, rate) => total + rate.used, 0);
}

function RiskStat({
  label,
  value,
  sub,
  tone = 'muted',
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: 'long' | 'warn' | 'short' | 'info' | 'muted';
}) {
  return (
    <div className="rounded-md border border-bd1 bg-bg2 px-4 py-3 min-h-[88px]">
      <div className="flex items-center gap-2">
        <StatusDot tone={tone} />
        <span className="label text-[9px]">{label}</span>
      </div>
      <div className="mt-3 num text-[20px] leading-none text-fg1 truncate">{value}</div>
      {sub ? <div className="mt-2 text-[11px] text-fg3 truncate">{sub}</div> : null}
    </div>
  );
}

function AuditRow({ item }: { item: RiskAuditItem }) {
  const time = new Date(item.timestamp_ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  return (
    <tr className="border-t border-bd1 row-hover">
      <td className="px-3 py-2 num text-[11px] text-fg3 whitespace-nowrap">{time}</td>
      <td className={cn('px-3 py-2 text-[12px] font-medium capitalize', decisionClass(item.decision_type))}>
        {item.decision_type}
      </td>
      <td className="px-3 py-2 text-[12px] text-fg1 whitespace-nowrap">{item.exchange}</td>
      <td className="px-3 py-2 text-[12px] text-fg2 whitespace-nowrap">{item.symbol}</td>
      <td className="px-3 py-2 num text-[12px] text-fg2 whitespace-nowrap">
        {item.side} {formatNumber(item.qty, { decimals: item.qty < 1 ? 4 : 2 })}
      </td>
      <td className="px-3 py-2 text-[12px] text-fg3 min-w-[220px]">{item.reason}</td>
    </tr>
  );
}

export function RiskPanel() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<RiskConfigForm>(EMPTY_FORM);
  const [killReason, setKillReason] = useState('manual risk stop');
  const [message, setMessage] = useState<{ text: string; tone: 'long' | 'short' | 'info' } | null>(null);

  const statusQuery = useQuery({
    queryKey: ['risk', 'status'],
    queryFn: riskApi.status,
    refetchInterval: 2000,
  });

  const configQuery = useQuery({
    queryKey: ['risk', 'config'],
    queryFn: riskApi.config,
  });

  const auditQuery = useQuery({
    queryKey: ['risk', 'audit'],
    queryFn: () => riskApi.audit({ page_size: 25 }),
    refetchInterval: 5000,
    enabled: riskApi.hasApiKey(),
  });

  const config = configQuery.data?.config ?? statusQuery.data?.config;

  useEffect(() => {
    if (config) setForm(configToForm(config));
  }, [config]);

  const invalidateRisk = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['risk', 'status'] }),
      queryClient.invalidateQueries({ queryKey: ['risk', 'config'] }),
      queryClient.invalidateQueries({ queryKey: ['risk', 'audit'] }),
    ]);
  };

  const updateConfig = useMutation({
    mutationFn: riskApi.updateConfig,
    onSuccess: async () => {
      setMessage({ text: 'Risk config saved.', tone: 'long' });
      await invalidateRisk();
    },
    onError: (error) => {
      setMessage({ text: error instanceof Error ? error.message : 'Failed to save risk config.', tone: 'short' });
    },
  });

  const activateKill = useMutation({
    mutationFn: riskApi.activateKillSwitch,
    onSuccess: async () => {
      setMessage({ text: 'Kill switch activated.', tone: 'short' });
      await invalidateRisk();
    },
    onError: (error) => {
      setMessage({ text: error instanceof Error ? error.message : 'Failed to activate kill switch.', tone: 'short' });
    },
  });

  const resetKill = useMutation({
    mutationFn: riskApi.resetKillSwitch,
    onSuccess: async () => {
      setMessage({ text: 'Kill switch reset.', tone: 'long' });
      await invalidateRisk();
    },
    onError: (error) => {
      setMessage({ text: error instanceof Error ? error.message : 'Failed to reset kill switch.', tone: 'short' });
    },
  });

  const status = statusQuery.data;
  const activeTone = riskTone(status);
  const rateUsed = status ? sumRateUsed(status.order_rates) : 0;
  const exposurePct = status && status.notional_cap_usd > 0
    ? Math.min(100, (status.notional_exposure_usd / status.notional_cap_usd) * 100)
    : 0;

  const positionRows = useMemo(() => Object.entries(status?.positions ?? {}), [status?.positions]);
  const rateRows = useMemo(() => Object.entries(status?.order_rates ?? {}), [status?.order_rates]);

  function updateField<K extends keyof RiskConfigForm>(key: K, value: RiskConfigForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    updateConfig.mutate(formToPatch(form));
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            {status?.kill_switch_active ? (
              <ShieldAlert size={18} strokeWidth={1.75} className="text-short" />
            ) : (
              <ShieldCheck size={18} strokeWidth={1.75} className="text-long" />
            )}
            <h1 className="text-[20px] font-semibold tracking-tight text-fg1">Risk</h1>
          </div>
          <div className="mt-1 text-[12px] text-fg3">
            {statusQuery.isLoading ? 'Loading status' : status?.last_decision?.reason ?? 'No decisions logged'}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {message ? <span className={cn('text-[12px]', message.tone === 'short' ? 'text-short' : message.tone === 'info' ? 'text-info' : 'text-long')}>{message.text}</span> : null}
          <div className="rounded-md border border-bd1 bg-bg2 h-8 px-3 flex items-center gap-2">
            <StatusDot tone={activeTone} />
            <span className="label text-[9px]">
              {status?.kill_switch_active ? 'Stopped' : status?.dry_run_mode ? 'Dry-run' : 'Live'}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
        <RiskStat
          label="Mode"
          value={status?.dry_run_mode ? 'Dry-run' : 'Live'}
          sub={status?.dry_run_mode ? 'Orders are simulated' : 'Exchange execution enabled'}
          tone={status?.dry_run_mode ? 'info' : 'long'}
        />
        <RiskStat
          label="Kill switch"
          value={status?.kill_switch_active ? 'Active' : 'Clear'}
          sub={status?.kill_switch_reason || 'No active stop'}
          tone={status?.kill_switch_active ? 'short' : 'long'}
        />
        <RiskStat
          label="Cooldown"
          value={status?.cooldown_active ? `${formatNumber(status.cooldown_remaining_s)}s` : 'Clear'}
          sub={status?.circuit_breaker_tripped ? 'Circuit breaker tripped' : 'No cooldown'}
          tone={status?.cooldown_active ? 'warn' : 'long'}
        />
        <RiskStat
          label="Notional"
          value={status ? formatUSD(status.notional_exposure_usd, { decimals: 0 }) : 'n/a'}
          sub={status ? `${formatNumber(exposurePct, { decimals: 1 })}% of ${formatUSD(status.notional_cap_usd, { decimals: 0 })}` : undefined}
          tone={exposurePct > 80 ? 'warn' : 'info'}
        />
        <RiskStat
          label="Rate used"
          value={`${rateUsed}/min`}
          sub={rateRows.length ? `${rateRows.length} exchanges tracked` : 'No live orders yet'}
          tone={rateUsed > 0 ? 'warn' : 'muted'}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.75fr)] gap-4">
        <form onSubmit={handleSubmit} className="rounded-md border border-bd1 bg-bg2 overflow-hidden">
          <div className="h-11 px-4 border-b border-bd1 flex items-center justify-between">
            <div className="text-[13px] font-medium text-fg1">Controls</div>
            <Button type="submit" size="sm" variant="ghost-primary" disabled={updateConfig.isPending}>
              {updateConfig.isPending ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              Save
            </Button>
          </div>
          <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <label className="sm:col-span-2 lg:col-span-1 rounded-md border border-bd1 bg-bg3/40 h-9 px-3 flex items-center gap-2 text-[12px] text-fg2">
              <input
                type="checkbox"
                checked={form.dry_run_enabled}
                onChange={(event) => updateField('dry_run_enabled', event.target.checked)}
                className="accent-long"
              />
              Dry-run enabled
            </label>
            <label className="sm:col-span-2 lg:col-span-1 rounded-md border border-bd1 bg-bg3/40 h-9 px-3 flex items-center gap-2 text-[12px] text-fg2">
              <input
                type="checkbox"
                checked={form.confirm_live}
                onChange={(event) => updateField('confirm_live', event.target.checked)}
                className="accent-long"
              />
              Confirm live
            </label>
            <Field label="Max position">
              <Input value={form.max_position_per_symbol} type="number" min={0.001} step="0.001" onChange={(event) => updateField('max_position_per_symbol', event.target.value)} />
            </Field>
            <Field label="Notional cap">
              <Input value={form.max_notional_exposure_usd} type="number" min={100} step="100" onChange={(event) => updateField('max_notional_exposure_usd', event.target.value)} />
            </Field>
            <Field label="Orders/min">
              <Input value={form.max_order_rate_per_minute} type="number" min={1} step="1" onChange={(event) => updateField('max_order_rate_per_minute', event.target.value)} />
            </Field>
            <Field label="Queue timeout s">
              <Input value={form.rate_limit_queue_timeout_s} type="number" min={1} step="1" onChange={(event) => updateField('rate_limit_queue_timeout_s', event.target.value)} />
            </Field>
            <Field label="Price band %">
              <Input value={form.price_sanity_band_pct} type="number" min={0.01} step="0.01" onChange={(event) => updateField('price_sanity_band_pct', event.target.value)} />
            </Field>
            <Field label="Tick max age s">
              <Input value={form.price_data_max_age_s} type="number" min={0.1} step="0.1" onChange={(event) => updateField('price_data_max_age_s', event.target.value)} />
            </Field>
            <Field label="Loss stop USD">
              <Input value={form.kill_switch_loss_threshold_usd} type="number" min={1} step="1" onChange={(event) => updateField('kill_switch_loss_threshold_usd', event.target.value)} />
            </Field>
            <Field label="Failure stop">
              <Input value={form.kill_switch_consecutive_failures} type="number" min={1} step="1" onChange={(event) => updateField('kill_switch_consecutive_failures', event.target.value)} />
            </Field>
            <Field label="Feed stale s">
              <Input value={form.kill_switch_feed_stale_s} type="number" min={1} step="1" onChange={(event) => updateField('kill_switch_feed_stale_s', event.target.value)} />
            </Field>
            <Field label="Inversion %">
              <Input value={form.kill_switch_spread_inversion_pct} type="number" min={0.01} step="0.01" onChange={(event) => updateField('kill_switch_spread_inversion_pct', event.target.value)} />
            </Field>
            <Field label="Cooldown min">
              <Input value={form.cooldown_minutes} type="number" min={1} step="1" onChange={(event) => updateField('cooldown_minutes', event.target.value)} />
            </Field>
          </div>
        </form>

        <div className="rounded-md border border-bd1 bg-bg2 overflow-hidden">
          <div className="h-11 px-4 border-b border-bd1 flex items-center justify-between">
            <div className="text-[13px] font-medium text-fg1">Kill Switch</div>
            <StatusDot tone={status?.kill_switch_active ? 'short' : 'long'} />
          </div>
          <div className="p-4 flex flex-col gap-3">
            <Field label="Reason">
              <Input value={killReason} onChange={(event) => setKillReason(event.target.value)} mono={false} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Button type="button" variant="ghost-danger" disabled={activateKill.isPending} onClick={() => activateKill.mutate(killReason)}>
                {activateKill.isPending ? <Loader2 size={13} className="animate-spin" /> : <Power size={13} />}
                Stop
              </Button>
              <Button type="button" variant="ghost" disabled={resetKill.isPending} onClick={() => resetKill.mutate()}>
                {resetKill.isPending ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />}
                Reset
              </Button>
            </div>
            <div className="border-t border-bd1 pt-3 space-y-2">
              {positionRows.length ? (
                positionRows.map(([symbol, qty]) => (
                  <div key={symbol} className="flex items-center justify-between text-[12px]">
                    <span className="text-fg3">{symbol}</span>
                    <span className="num text-fg1">{formatNumber(qty, { decimals: 4 })}</span>
                  </div>
                ))
              ) : (
                <div className="text-[12px] text-fg3">No tracked position</div>
              )}
              {rateRows.map(([exchange, rate]) => (
                <div key={exchange} className="flex items-center justify-between text-[12px]">
                  <span className="text-fg3">{exchange}</span>
                  <span className="num text-fg1">{rate.used}/{rate.limit}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-md border border-bd1 bg-bg2 overflow-hidden">
        <div className="h-11 px-4 border-b border-bd1 flex items-center justify-between">
          <div className="text-[13px] font-medium text-fg1">Audit</div>
          <span className="label text-[9px]">{auditQuery.data?.total ?? 0} records</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px]">
            <thead>
              <tr className="text-left label text-[9px]">
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Decision</th>
                <th className="px-3 py-2">Exchange</th>
                <th className="px-3 py-2">Symbol</th>
                <th className="px-3 py-2">Order</th>
                <th className="px-3 py-2">Reason</th>
              </tr>
            </thead>
            <tbody>
              {auditQuery.isLoading ? (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-[12px] text-fg3">
                    Loading audit
                  </td>
                </tr>
              ) : auditQuery.data?.items.length ? (
                auditQuery.data.items.map((item) => <AuditRow key={item.id} item={item} />)
              ) : (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-[12px] text-fg3">
                    {riskApi.hasApiKey() ? 'No audit records' : 'API key required for audit'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
