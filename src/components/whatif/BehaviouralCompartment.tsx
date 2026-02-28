/**
 * BehaviouralCompartment.tsx – Behavioural assumptions override for the What-If Workbench.
 *
 * ── WHAT ARE BEHAVIOURAL ASSUMPTIONS? ─────────────────────────────────
 *
 *   In IRRBB/ALM, certain products don't have contractual maturities or
 *   have optionality that depends on customer behaviour:
 *
 *   • NMD (Non-Maturing Deposits): No contractual maturity. The bank models
 *     a "core" proportion with an average maturity and a pass-through rate.
 *     - coreProportion: % of deposits considered stable (e.g. 70%)
 *     - coreAverageMaturity: Weighted avg maturity of core (e.g. 5 years)
 *     - passThrough: How much of rate changes pass to depositors (e.g. 30%)
 *
 *   • Loan Prepayments: Borrowers may repay early. Modelled via:
 *     - SMM (Single Monthly Mortality): Monthly prepayment rate (e.g. 2%)
 *
 *   • Term Deposits: Early redemption modelled via:
 *     - TDRR (Term Deposit Redemption Rate): Monthly early redemption (e.g. 1%)
 *
 * ── LAYOUT ────────────────────────────────────────────────────────────
 *
 *   LEFT panel: "Current Assumptions" — read-only summary showing what the engine
 *     currently uses as base case (from BehaviouralContext defaults).
 *     When overrides are pending, base values show a strike-through and the
 *     overridden value appears beside them in primary colour.
 *
 *   RIGHT panel: "Override" — form to create behavioural overrides as WhatIfModifications.
 *     The user selects a product family (NMD / Loan Prepayments / Term Deposits),
 *     adjusts parameters, and adds the override to the pending modifications list.
 *     If an override for that family already exists, the button updates it in place.
 *
 * ── MODIFICATION FORMAT ───────────────────────────────────────────────
 *
 *   Creates modifications with type='behavioural' and a behaviouralOverride
 *   object containing the adjusted parameters. One modification per family.
 */
import React, { useState, useMemo, useEffect } from 'react';
import {
  Brain,
  Eye,
  AlertTriangle,
  Plus,
  Check,
  Wallet,
  TrendingDown,
  Clock,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  useBehavioural,
  MAX_TOTAL_MATURITY,
} from '@/components/behavioural/BehaviouralContext';
import { NMDCashflowChart } from '@/components/behavioural/NMDCashflowChart';
import { useWhatIf } from './WhatIfContext';
import type { BehaviouralFamily, BehaviouralOverride } from '@/types/whatif';

// ── Helpers ─────────────────────────────────────────────────────────────

function computeCpr(smm: number): number {
  const d = smm / 100;
  return (1 - Math.pow(1 - d, 12)) * 100;
}

function computeAnnualTdrr(tdrr: number): number {
  const d = tdrr / 100;
  return (1 - Math.pow(1 - d, 12)) * 100;
}

// ═══════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════

export function BehaviouralCompartment() {
  return (
    <div className="flex h-full min-h-0">
      {/* Left: Current Assumptions */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex items-center gap-1.5 px-4 pb-2.5 pt-3 border-b border-border/40 shrink-0">
          <Eye className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold text-foreground">Current Assumptions</span>
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-4 py-3">
            <CurrentAssumptions />
          </div>
        </ScrollArea>
      </div>

      {/* Vertical divider */}
      <div className="w-px bg-border/60 shrink-0" />

      {/* Right: Override */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex items-center gap-1.5 px-4 pb-2.5 pt-3 border-b border-border/40 shrink-0">
          <Brain className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">Override</span>
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-4 py-3">
            <OverrideForm />
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// LEFT PANEL – Read-only summary of the three behavioural families
// ═══════════════════════════════════════════════════════════════════════

function CurrentAssumptions() {
  const {
    nmdParams,
    loanPrepaymentParams,
    termDepositParams,
    cprFromSmm,
    annualTdrr,
  } = useBehavioural();
  const { modifications } = useWhatIf();

  // Collect pending overrides keyed by family
  const pendingOverrides = useMemo(() => {
    const map = new Map<BehaviouralFamily, BehaviouralOverride>();
    for (const mod of modifications) {
      if (mod.type === 'behavioural' && mod.behaviouralOverride) {
        map.set(mod.behaviouralOverride.family, mod.behaviouralOverride);
      }
    }
    return map;
  }, [modifications]);

  const nmdOv = pendingOverrides.get('nmd');
  const loanOv = pendingOverrides.get('loan-prepayments');
  const tdOv = pendingOverrides.get('term-deposits');

  return (
    <div className="space-y-3">
      {/* ── NMD ────────────────────────────────────────────────── */}
      <AssumptionCard
        label="Non-Maturing Deposits"
        icon={Wallet}
        hasPendingOverride={!!nmdOv}
      >
        <ParamRow
          label="Core proportion"
          baseValue={`${nmdParams.coreProportion}%`}
          overrideValue={nmdOv?.coreProportion != null ? `${nmdOv.coreProportion}%` : undefined}
        />
        <ParamRow
          label="Core avg maturity"
          baseValue={`${nmdParams.coreAverageMaturity}y`}
          overrideValue={nmdOv?.coreAverageMaturity != null ? `${nmdOv.coreAverageMaturity}y` : undefined}
        />
        <ParamRow
          label="Pass-through rate"
          baseValue={`${nmdParams.passThrough}%`}
          overrideValue={nmdOv?.passThrough != null ? `${nmdOv.passThrough}%` : undefined}
        />
      </AssumptionCard>

      {/* ── Loan Prepayments ───────────────────────────────────── */}
      <AssumptionCard
        label="Loan Prepayments"
        icon={TrendingDown}
        hasPendingOverride={!!loanOv}
      >
        <ParamRow
          label="SMM (monthly)"
          baseValue={`${loanPrepaymentParams.smm}%`}
          overrideValue={loanOv?.smm != null ? `${loanOv.smm}%` : undefined}
        />
        <ParamRow
          label="CPR (annual)"
          baseValue={`${cprFromSmm.toFixed(2)}%`}
          overrideValue={loanOv?.smm != null ? `${computeCpr(loanOv.smm).toFixed(2)}%` : undefined}
          computed
        />
      </AssumptionCard>

      {/* ── Term Deposits ──────────────────────────────────────── */}
      <AssumptionCard
        label="Term Deposits"
        icon={Clock}
        hasPendingOverride={!!tdOv}
      >
        <ParamRow
          label="TDRR (monthly)"
          baseValue={`${termDepositParams.tdrr}%`}
          overrideValue={tdOv?.tdrr != null ? `${tdOv.tdrr}%` : undefined}
        />
        <ParamRow
          label="Annual TDRR"
          baseValue={`${annualTdrr.toFixed(2)}%`}
          overrideValue={tdOv?.tdrr != null ? `${computeAnnualTdrr(tdOv.tdrr).toFixed(2)}%` : undefined}
          computed
        />
      </AssumptionCard>
    </div>
  );
}

// ── Shared sub-components for the left panel ────────────────────────────

function AssumptionCard({
  label,
  icon: Icon,
  hasPendingOverride,
  children,
}: {
  label: string;
  icon: React.ElementType;
  hasPendingOverride: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border/40 bg-muted/20 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold">{label}</span>
        </div>
        {hasPendingOverride && (
          <Badge
            variant="outline"
            className="text-[9px] py-0 px-1.5 border-primary/50 bg-primary/5 text-primary"
          >
            Override pending
          </Badge>
        )}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function ParamRow({
  label,
  baseValue,
  overrideValue,
  computed,
}: {
  label: string;
  baseValue: string;
  overrideValue?: string;
  computed?: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className={cn('text-muted-foreground', computed && 'italic')}>
        {label}
      </span>
      <div className="flex items-center gap-1.5 font-mono">
        <span className={cn(overrideValue && 'line-through text-muted-foreground/50')}>
          {baseValue}
        </span>
        {overrideValue && (
          <>
            <span className="text-muted-foreground text-[9px]">&rarr;</span>
            <span className="text-primary font-medium">{overrideValue}</span>
          </>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// RIGHT PANEL – Override form
// ═══════════════════════════════════════════════════════════════════════

function OverrideForm() {
  const { nmdParams, loanPrepaymentParams, termDepositParams } = useBehavioural();
  const { modifications, addModification, updateModification } = useWhatIf();

  const [selectedFamily, setSelectedFamily] = useState<BehaviouralFamily | ''>('');

  // NMD form state
  const [coreProportion, setCoreProportion] = useState(75);
  const [coreAverageMaturity, setCoreAverageMaturity] = useState(6.25);
  const [passThrough, setPassThrough] = useState(10);

  // Anchor values for the PT ↔ Core coupling.
  // Captured once when the form loads (from context defaults or existing override).
  // Each +1% pass-through over the anchor reduces core by 1% and vice-versa.
  const [baseCoreProportion, setBaseCoreProportion] = useState(75);
  const [basePassThrough, setBasePassThrough] = useState(10);

  // Loan Prepayments form state
  const [smm, setSmm] = useState(0.5);

  // Term Deposits form state
  const [tdrr, setTdrr] = useState(0.1);

  // Find existing override for the selected family
  const existingOverrideMod = useMemo(() => {
    if (!selectedFamily) return null;
    return (
      modifications.find(
        (m) =>
          m.type === 'behavioural' &&
          m.behaviouralOverride?.family === selectedFamily,
      ) ?? null
    );
  }, [modifications, selectedFamily]);

  // Pre-fill form when family changes — from existing override or context defaults
  useEffect(() => {
    if (!selectedFamily) return;

    if (existingOverrideMod?.behaviouralOverride) {
      const ov = existingOverrideMod.behaviouralOverride;
      if (selectedFamily === 'nmd') {
        const core = ov.coreProportion ?? nmdParams.coreProportion;
        const pt = ov.passThrough ?? nmdParams.passThrough;
        setCoreProportion(core);
        setCoreAverageMaturity(ov.coreAverageMaturity ?? nmdParams.coreAverageMaturity);
        setPassThrough(pt);
        // Anchors = context defaults (the "base case" before any override)
        setBaseCoreProportion(nmdParams.coreProportion);
        setBasePassThrough(nmdParams.passThrough);
      } else if (selectedFamily === 'loan-prepayments') {
        setSmm(ov.smm ?? loanPrepaymentParams.smm);
      } else {
        setTdrr(ov.tdrr ?? termDepositParams.tdrr);
      }
    } else {
      if (selectedFamily === 'nmd') {
        setCoreProportion(nmdParams.coreProportion);
        setCoreAverageMaturity(nmdParams.coreAverageMaturity);
        setPassThrough(nmdParams.passThrough);
        setBaseCoreProportion(nmdParams.coreProportion);
        setBasePassThrough(nmdParams.passThrough);
      } else if (selectedFamily === 'loan-prepayments') {
        setSmm(loanPrepaymentParams.smm);
      } else {
        setTdrr(termDepositParams.tdrr);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFamily]);

  // Computed values
  const totalMaturity = (coreProportion / 100) * coreAverageMaturity;
  const isValidMaturity = totalMaturity <= MAX_TOTAL_MATURITY;
  const cpr = computeCpr(smm);
  const annualTdrrComputed = computeAnnualTdrr(tdrr);

  const canSubmit =
    selectedFamily !== '' &&
    (selectedFamily !== 'nmd' || isValidMaturity);

  // ── Submit handler ──────────────────────────────────────────────────

  const handleAddOverride = () => {
    if (!selectedFamily || !canSubmit) return;

    let override: BehaviouralOverride;
    let label: string;
    let details: string;

    if (selectedFamily === 'nmd') {
      override = { family: 'nmd', coreProportion, coreAverageMaturity, passThrough };
      label = 'NMD Assumptions';
      details = `Core: ${coreProportion}% \u2022 Mat: ${coreAverageMaturity}y \u2022 PT: ${passThrough}%`;
    } else if (selectedFamily === 'loan-prepayments') {
      override = { family: 'loan-prepayments', smm };
      label = 'Prepayment Override';
      details = `SMM: ${smm}% \u2192 CPR: ${cpr.toFixed(2)}%`;
    } else {
      override = { family: 'term-deposits', tdrr };
      label = 'Term Deposit Override';
      details = `TDRR: ${tdrr}% \u2192 Annual: ${annualTdrrComputed.toFixed(2)}%`;
    }

    if (existingOverrideMod) {
      updateModification(existingOverrideMod.id, {
        type: 'behavioural',
        label,
        details,
        behaviouralOverride: override,
      });
    } else {
      addModification({
        type: 'behavioural',
        label,
        details,
        behaviouralOverride: override,
      });
    }
  };

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Family selector */}
      <div className="space-y-1">
        <Label className="text-[10px] text-muted-foreground">Product Family</Label>
        <Select
          value={selectedFamily}
          onValueChange={(v) => setSelectedFamily(v as BehaviouralFamily)}
        >
          <SelectTrigger className="h-7 text-[11px]">
            <SelectValue placeholder="Select family to override..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="nmd" className="text-xs">
              Non-Maturing Deposits (NMD)
            </SelectItem>
            <SelectItem value="loan-prepayments" className="text-xs">
              Loan Prepayments
            </SelectItem>
            <SelectItem value="term-deposits" className="text-xs">
              Term Deposits
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* ── NMD form ──────────────────────────────────────────────── */}
      {selectedFamily === 'nmd' && (
        <>
          <div className="h-px bg-border/60" />
          <div className="space-y-3">
            <p className="text-[10px] text-muted-foreground italic">
              All parameters apply to the aggregate of all NMDs (no segmentation).
              Pass-through and core proportion are linked: &plusmn;1% PT &harr; &mp;1% core.
            </p>

            <div className="grid grid-cols-3 gap-2">
              {/* Core Proportion */}
              <div className="space-y-1">
                <Label className="text-[10px] text-muted-foreground">
                  Core proportion (%)
                </Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={coreProportion}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    if (!isNaN(n)) setCoreProportion(Math.max(0, Math.min(100, n)));
                  }}
                  className="h-7 text-[11px]"
                />
              </div>

              {/* Core Average Maturity */}
              <div className="space-y-1">
                <Label className="text-[10px] text-muted-foreground">
                  Core avg maturity (y)
                </Label>
                <Input
                  type="number"
                  min={2}
                  max={10}
                  step={0.25}
                  value={coreAverageMaturity}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    if (!isNaN(n)) setCoreAverageMaturity(Math.max(2, Math.min(10, n)));
                  }}
                  className="h-7 text-[11px]"
                />
              </div>

              {/* Pass-through — coupled: +1% PT → −1% Core */}
              <div className="space-y-1">
                <Label className="text-[10px] text-muted-foreground">
                  Pass-through (%)
                </Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={passThrough}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    if (!isNaN(n)) {
                      const clampedPT = Math.max(0, Math.min(100, n));
                      setPassThrough(clampedPT);
                      // Complementary: each +1% PT over anchor → −1% core
                      const delta = clampedPT - basePassThrough;
                      setCoreProportion(Math.max(0, Math.min(100, baseCoreProportion - delta)));
                    }
                  }}
                  className="h-7 text-[11px]"
                />
              </div>
            </div>

            {/* Total maturity validation */}
            <div
              className={cn(
                'rounded-md p-2 text-xs',
                isValidMaturity
                  ? 'bg-muted/50 border border-border/50'
                  : 'bg-destructive/10 border border-destructive/30',
              )}
            >
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Total avg maturity:</span>
                <span className={cn('font-semibold', !isValidMaturity && 'text-destructive')}>
                  {totalMaturity.toFixed(2)} years
                </span>
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">
                Max allowed: {MAX_TOTAL_MATURITY.toFixed(2)} years (EBA IRRBB)
              </div>
              {!isValidMaturity && (
                <div className="flex items-center gap-1 mt-1.5 text-destructive">
                  <AlertTriangle className="h-3 w-3" />
                  <span className="text-[10px] font-medium">
                    Exceeds supervisory limit
                  </span>
                </div>
              )}
            </div>

            {/* NMD Cashflow Chart */}
            <NMDCashflowChart
              coreProportion={coreProportion}
              coreAverageMaturity={coreAverageMaturity}
            />
          </div>
        </>
      )}

      {/* ── Loan Prepayments form ─────────────────────────────────── */}
      {selectedFamily === 'loan-prepayments' && (
        <>
          <div className="h-px bg-border/60" />
          <div className="space-y-3">
            <p className="text-[10px] text-muted-foreground italic">
              Applies to the aggregate loan portfolio (no segmentation).
            </p>

            <div className="space-y-1">
              <Label className="text-[10px] text-muted-foreground">
                SMM &ndash; Single Monthly Mortality (%)
              </Label>
              <Input
                type="number"
                min={0}
                max={50}
                step={0.01}
                value={smm}
                onChange={(e) => {
                  const n = parseFloat(e.target.value);
                  if (!isNaN(n)) setSmm(Math.max(0, Math.min(50, n)));
                }}
                className="h-7 text-[11px] w-32"
              />
            </div>

            {/* Computed CPR */}
            <div className="rounded-md p-2 text-xs bg-muted/50 border border-border/50">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Equivalent CPR (annual):</span>
                <span className="font-semibold">{cpr.toFixed(2)}%</span>
              </div>
              <div className="text-[10px] text-muted-foreground mt-1">
                CPR = 1 &minus; (1 &minus; SMM)<sup>12</sup>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── Term Deposits form ────────────────────────────────────── */}
      {selectedFamily === 'term-deposits' && (
        <>
          <div className="h-px bg-border/60" />
          <div className="space-y-3">
            <p className="text-[10px] text-muted-foreground italic">
              Applies to the aggregate term deposit portfolio.
            </p>

            <div className="space-y-1">
              <Label className="text-[10px] text-muted-foreground">
                TDRR &ndash; Term Deposit Redemption Rate (monthly %)
              </Label>
              <Input
                type="number"
                min={0}
                max={50}
                step={0.01}
                value={tdrr}
                onChange={(e) => {
                  const n = parseFloat(e.target.value);
                  if (!isNaN(n)) setTdrr(Math.max(0, Math.min(50, n)));
                }}
                className="h-7 text-[11px] w-32"
              />
            </div>

            {/* Computed annual TDRR */}
            <div className="rounded-md p-2 text-xs bg-muted/50 border border-border/50">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Equivalent annual TDRR:</span>
                <span className="font-semibold">{annualTdrrComputed.toFixed(2)}%</span>
              </div>
              <div className="text-[10px] text-muted-foreground mt-1">
                Annual = 1 &minus; (1 &minus; monthly)<sup>12</sup>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── Empty state ───────────────────────────────────────────── */}
      {selectedFamily === '' && (
        <div className="text-center py-8 text-muted-foreground">
          <Brain className="h-8 w-8 mx-auto mb-2 opacity-20" />
          <p className="text-xs">Select a product family to override its behavioural assumptions.</p>
          <p className="text-[10px] mt-1">
            Overrides will appear in the pending modifications bar and apply together with balance changes.
          </p>
        </div>
      )}

      {/* ── Submit button ─────────────────────────────────────────── */}
      {selectedFamily !== '' && (
        <Button
          size="sm"
          className="h-7 text-xs w-full"
          onClick={handleAddOverride}
          disabled={!canSubmit}
        >
          {existingOverrideMod ? (
            <>
              <Check className="h-3 w-3 mr-1" />
              Update Override
            </>
          ) : (
            <>
              <Plus className="h-3 w-3 mr-1" />
              Add Override
            </>
          )}
        </Button>
      )}
    </div>
  );
}
