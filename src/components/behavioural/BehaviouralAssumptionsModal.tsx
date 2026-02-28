/**
 * BehaviouralAssumptionsModal.tsx – Tabbed modal for configuring behavioural
 * assumptions (NMDs, Loan Prepayments, Term Deposits).
 *
 * Single-step flow: open modal -> see all three tabs -> edit params -> Apply.
 * NMD tab uses a wider modal; Loan and Term tabs use a slimmer one.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Brain, Info } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  useBehavioural,
  NMD_BUCKETS,
  type NMDParameters,
  type LoanPrepaymentParameters,
  type TermDepositParameters,
} from './BehaviouralContext';

// Short bucket labels without the ">" prefix
const BUCKET_SHORT_LABELS: Record<string, string> = {};
for (const b of NMD_BUCKETS) {
  BUCKET_SHORT_LABELS[b.id] = b.label.replace(/^>/, '').trim();
}

/** Number input that shows placeholder "0" when value is 0, selects-all on focus */
function NumInput({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  suffix,
  className = '',
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  className?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const display = value === 0 ? '' : String(value);

  return (
    <div className="flex items-baseline gap-2">
      <input
        ref={ref}
        type="number"
        min={min} max={max} step={step}
        placeholder="0"
        value={display}
        onFocus={() => ref.current?.select()}
        onChange={(e) => {
          const num = parseFloat(e.target.value);
          if (e.target.value === '' || isNaN(num)) { onChange(0); return; }
          onChange(Math.max(min, Math.min(max, num)));
        }}
        className={`h-8 text-sm font-semibold w-24 rounded-md border border-input bg-background px-3 py-1 shadow-sm placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring ${className}`}
      />
      {suffix && <span className="text-xs text-muted-foreground">{suffix}</span>}
    </div>
  );
}

interface BehaviouralAssumptionsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function BehaviouralAssumptionsModal({
  open,
  onOpenChange,
}: BehaviouralAssumptionsModalProps) {
  const {
    nmdParams,
    setNmdParams,
    loanPrepaymentParams,
    setLoanPrepaymentParams,
    termDepositParams,
    setTermDepositParams,
    applyAssumptions,
  } = useBehavioural();

  const [activeTab, setActiveTab] = useState('nmd');

  // Local state for editing (cancel-safe)
  const [localNmd, setLocalNmd] = useState<NMDParameters>(nmdParams);
  const [localLoan, setLocalLoan] = useState<LoanPrepaymentParameters>(loanPrepaymentParams);
  const [localTerm, setLocalTerm] = useState<TermDepositParameters>(termDepositParams);

  // Sync local state when modal opens
  useEffect(() => {
    if (open) {
      setLocalNmd(nmdParams);
      setLocalLoan(loanPrepaymentParams);
      setLocalTerm(termDepositParams);
    }
  }, [open, nmdParams, loanPrepaymentParams, termDepositParams]);

  // ── NMD computed values ──────────────────────────────────────────────
  const coreProp = localNmd.coreProportion ?? 0;
  const nonCorePct = 100 - coreProp;

  // Core bucket weights must sum to coreProportion
  const distributionSum = useMemo(
    () => Object.values(localNmd.distribution).reduce((a, b) => a + b, 0),
    [localNmd.distribution],
  );
  const distributionValid = coreProp > 0
    ? Math.abs(distributionSum - coreProp) < 0.02
    : distributionSum === 0;

  // WAM computed from distribution (auto — replaces the manual input)
  const coreWam = useMemo(() => {
    if (distributionSum === 0) return 0;
    let wam = 0;
    for (const b of NMD_BUCKETS) {
      if (b.id === 'ON') continue;
      wam += (localNmd.distribution[b.id] ?? 0) * b.midpoint;
    }
    return wam / distributionSum;
  }, [localNmd.distribution, distributionSum]);

  // Total WAM (core proportion weighted)
  const totalWam = (coreProp / 100) * coreWam;

  // Auto-sync coreAverageMaturity from distribution WAM
  useEffect(() => {
    setLocalNmd(prev => ({ ...prev, coreAverageMaturity: coreWam }));
  }, [coreWam]);

  // Max value across all buckets (for visual bar scaling)
  const maxBucketValue = useMemo(() => {
    let max = nonCorePct;
    for (const b of NMD_BUCKETS) {
      if (b.id === 'ON') continue;
      max = Math.max(max, localNmd.distribution[b.id] ?? 0);
    }
    return Math.max(max, 1);
  }, [localNmd.distribution, nonCorePct]);

  // ── Loan computed values ─────────────────────────────────────────────
  const localCpr = useMemo(() => {
    const smm = localLoan.smm ?? 0;
    if (smm === 0) return 0;
    return (1 - Math.pow(1 - smm / 100, 12)) * 100;
  }, [localLoan.smm]);

  // ── Term computed values ─────────────────────────────────────────────
  const localAnnualTdrr = useMemo(() => {
    const tdrr = localTerm.tdrr ?? 0;
    if (tdrr === 0) return 0;
    return (1 - Math.pow(1 - tdrr / 100, 12)) * 100;
  }, [localTerm.tdrr]);

  // ── Handlers ─────────────────────────────────────────────────────────
  const handleNmdField = useCallback((field: 'coreProportion' | 'passThrough', value: number) => {
    setLocalNmd(prev => ({ ...prev, [field]: value }));
  }, []);

  const handleBucketChange = useCallback((bucketId: string, value: string) => {
    setLocalNmd(prev => {
      const dist = { ...prev.distribution };
      const num = parseFloat(value);
      if (value === '' || isNaN(num)) {
        delete dist[bucketId];
      } else if (num >= 0) {
        dist[bucketId] = num;
      }
      return { ...prev, distribution: dist };
    });
  }, []);

  const handleApply = () => {
    setNmdParams(localNmd);
    setLoanPrepaymentParams(localLoan);
    setTermDepositParams(localTerm);
    applyAssumptions();
    onOpenChange(false);
  };

  // ── Active indicators per tab ────────────────────────────────────────
  const nmdHasValues = coreProp > 0 || (localNmd.passThrough ?? 0) > 0 || Object.keys(localNmd.distribution).length > 0;
  const loanHasValues = (localLoan.smm ?? 0) > 0;
  const termHasValues = (localTerm.tdrr ?? 0) > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto max-w-4xl top-[12%] translate-y-0" style={{ position: 'fixed' }}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Brain className="h-4 w-4 text-primary" />
            Behavioural Assumptions
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            Affect repricing and timing of cash flows
          </p>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-1">
          <TabsList className="w-full grid grid-cols-3 h-9">
            <TabsTrigger value="nmd" className="text-xs gap-1.5">
              NMDs
              {nmdHasValues && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
            </TabsTrigger>
            <TabsTrigger value="loan" className="text-xs gap-1.5">
              Loan Prepayments
              {loanHasValues && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
            </TabsTrigger>
            <TabsTrigger value="term" className="text-xs gap-1.5">
              Term Deposits
              {termHasValues && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
            </TabsTrigger>
          </TabsList>

          {/* ── NMD Tab ──────────────────────────────────────────────── */}
          <TabsContent value="nmd" className="mt-3 space-y-4">
            {/* Parameters row */}
            <div className="grid grid-cols-3 gap-4">
              {/* Core Proportion */}
              <div className="rounded-lg border border-border/50 bg-muted/30 p-3 space-y-1.5">
                <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Core proportion</Label>
                <NumInput
                  value={coreProp} min={0} max={100} step={1} suffix="%"
                  onChange={(v) => handleNmdField('coreProportion', v)}
                />
                <p className="text-[10px] text-muted-foreground">
                  Non-core (auto): <span className="font-medium">{nonCorePct.toFixed(1)}%</span>
                </p>
              </div>

              {/* Core Avg Maturity — auto-calculated from distribution (read-only) */}
              <div className="rounded-lg border border-border/50 bg-muted/30 p-3 space-y-1.5">
                <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Core avg maturity</Label>
                <div className="h-8 flex items-center text-sm font-semibold">
                  {coreWam > 0 ? `${coreWam.toFixed(2)} years` : <span className="text-muted-foreground/40">-</span>}
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Computed from distribution. Total WAM: <span className="font-medium">{totalWam.toFixed(2)} yrs</span>
                </p>
              </div>

              {/* Pass-through Rate */}
              <div className="rounded-lg border border-border/50 bg-muted/30 p-3 space-y-1.5">
                <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Pass-through rate</Label>
                <NumInput
                  value={localNmd.passThrough ?? 0} min={0} max={100} step={1} suffix="%"
                  onChange={(v) => handleNmdField('passThrough', v)}
                />
                <p className="text-[10px] text-muted-foreground">
                  NII repricing pass-through (0% = none, 100% = full)
                </p>
              </div>
            </div>

            <div className="flex items-start gap-1.5 text-[10px] text-muted-foreground">
              <Info className="h-3 w-3 mt-0.5 shrink-0" />
              Applies to fixed NMDs only. Variable NMDs follow their repricing schedule automatically.
            </div>

            {/* Distribution — visual bars + inputs, single wide row */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium">Core Maturity Distribution</Label>
                <span className="text-[10px] text-muted-foreground">
                  Buckets must sum to {coreProp.toFixed(1)}% (core). O/N = {nonCorePct.toFixed(1)}% (non-core, auto).
                </span>
              </div>

              <div className="rounded-lg border border-border/50 bg-background p-2 overflow-x-auto">
                <div className="flex gap-0.5" style={{ minWidth: '720px' }}>
                  {NMD_BUCKETS.map((b) => {
                    const isON = b.id === 'ON';
                    const val = isON ? nonCorePct : (localNmd.distribution[b.id] ?? 0);
                    const barHeight = maxBucketValue > 0 ? Math.max(2, (val / maxBucketValue) * 48) : 2;

                    return (
                      <div key={b.id} className="flex-1 flex flex-col items-center gap-0.5 min-w-[36px]">
                        {/* Visual bar */}
                        <div className="w-full flex items-end justify-center" style={{ height: 52 }}>
                          <div
                            className={`w-full max-w-[28px] rounded-t-sm transition-all ${isON ? 'bg-muted-foreground/40' : 'bg-primary/70'}`}
                            style={{ height: barHeight }}
                          />
                        </div>
                        {/* Input */}
                        <input
                          type="number"
                          min={0} max={100} step={0.1}
                          placeholder="0"
                          value={isON ? val.toFixed(1) : (localNmd.distribution[b.id] != null ? localNmd.distribution[b.id] : '')}
                          disabled={isON}
                          onFocus={(e) => e.target.select()}
                          onChange={(e) => handleBucketChange(b.id, e.target.value)}
                          className={`w-full text-center text-[9px] border rounded px-0 py-0.5 outline-none focus:ring-1 focus:ring-primary/50 placeholder:text-muted-foreground/30 ${
                            isON ? 'bg-muted text-muted-foreground border-border/30' : 'bg-background border-border/50'
                          }`}
                        />
                        {/* Label */}
                        <span className="text-[7px] text-muted-foreground leading-tight text-center truncate w-full">
                          {BUCKET_SHORT_LABELS[b.id]}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Totals & WAM */}
              <div className="flex items-center gap-4 text-[10px] px-1">
                <span className={distributionValid ? 'text-green-700 font-medium' : 'text-destructive font-medium'}>
                  Core total: {distributionSum.toFixed(1)}% / {coreProp.toFixed(1)}%
                  {distributionValid ? ' \u2713' : ''}
                </span>
                {coreWam > 0 && (
                  <span className="text-muted-foreground">
                    Implied WAM (core): <span className="font-medium">{coreWam.toFixed(2)} years</span>
                  </span>
                )}
                <div className="flex-1" />
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-sm bg-muted-foreground/40" />
                    <span className="text-muted-foreground">Non-core</span>
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2 w-2 rounded-sm bg-primary/70" />
                    <span className="text-muted-foreground">Core</span>
                  </span>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* ── Loan Prepayments Tab ─────────────────────────────────── */}
          <TabsContent value="loan" className="mt-3">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-lg border border-border/50 bg-muted/30 p-4 space-y-1.5">
                <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">SMM - Single Monthly Mortality</Label>
                <NumInput
                  value={localLoan.smm ?? 0} min={0} max={50} step={0.01} suffix="% monthly"
                  onChange={(v) => setLocalLoan({ smm: v })}
                />
                <p className="text-[10px] text-muted-foreground">
                  Monthly prepayment rate applied to outstanding loan principal.
                </p>
              </div>
              <div className="rounded-lg border border-border/50 bg-muted/30 p-4 space-y-1.5">
                <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Equivalent CPR (annual)</Label>
                <div className="h-8 flex items-center text-sm font-semibold">
                  {localCpr > 0 ? `${localCpr.toFixed(2)}%` : <span className="text-muted-foreground/40">-</span>}
                </div>
                <p className="text-[10px] text-muted-foreground">
                  CPR = 1 - (1 - SMM)<sup>12</sup>
                </p>
              </div>
            </div>
          </TabsContent>

          {/* ── Term Deposits Tab ────────────────────────────────────── */}
          <TabsContent value="term" className="mt-3">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-lg border border-border/50 bg-muted/30 p-4 space-y-1.5">
                <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">TDRR - Monthly Early Redemption Rate</Label>
                <NumInput
                  value={localTerm.tdrr ?? 0} min={0} max={50} step={0.01} suffix="% monthly"
                  onChange={(v) => setLocalTerm({ tdrr: v })}
                />
                <p className="text-[10px] text-muted-foreground">
                  Monthly rate of early withdrawals from term deposit balances.
                </p>
              </div>
              <div className="rounded-lg border border-border/50 bg-muted/30 p-4 space-y-1.5">
                <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Equivalent annual TDRR</Label>
                <div className="h-8 flex items-center text-sm font-semibold">
                  {localAnnualTdrr > 0 ? `${localAnnualTdrr.toFixed(2)}%` : <span className="text-muted-foreground/40">-</span>}
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Annual = 1 - (1 - TDRR)<sup>12</sup>
                </p>
              </div>
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter className="gap-2 mt-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} className="text-xs">
            Cancel
          </Button>
          <Button size="sm" onClick={handleApply} className="text-xs">
            Apply & Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
