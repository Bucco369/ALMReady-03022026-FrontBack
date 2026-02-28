/**
 * FindLimitCompartment.tsx – Find the maximum amount of a product
 * to buy/sell while staying within an EVE/NII limit.
 *
 * ── LAYOUT ────────────────────────────────────────────────────────────
 *
 *   ┌──────────────────────┬──────────────────────┐
 *   │   Constraint Setup   │  Product Config      │
 *   ├──────────────────────┼──────────────────────┤
 *   │ • Metric (EVE/NII)   │ • Same form as       │
 *   │ • Scenario (base/    │   AddCatalog          │
 *   │   worst/specific)    │   (shared components  │
 *   │ • Limit value        │    from ProductConfig │
 *   │ • Solve for          │    Form.tsx)           │
 *   │   (notional/rate/    │ • Cascading dropdowns │
 *   │    maturity/spread)  │ • Structural config   │
 *   │ • [Find Limit]       │ • Template fields     │
 *   │ • Result display     │                       │
 *   │ • [Add to Mods]      │                       │
 *   └──────────────────────┴──────────────────────┘
 *
 * ── BACKEND ───────────────────────────────────────────────────────────
 *
 *   Calls POST /api/sessions/{id}/whatif/find-limit (V2 endpoint).
 *   The backend uses binary search (or linear scaling for notional) to
 *   find the maximum value of the solve_for variable such that the
 *   target metric stays within the limit.
 *
 *   Request payload uses LoanSpec format (same as V2 decomposer), so it
 *   fully supports: amortization, mixed rates, floor/cap, grace periods.
 *
 *   buildProductSpec() converts form state → LoanSpec API payload.
 *   This is a local function — TODO: move to shared/constants.ts and
 *   reuse in BuySellCompartment's Calculate Impact handler.
 *
 * ── RESULT FLOW ───────────────────────────────────────────────────────
 *
 *   1. User fills product form + constraint definition
 *   2. "Find Limit" button calls findLimit(sessionId, request)
 *   3. Response includes found_value + achieved_metric
 *   4. "Add to Modifications" creates a modification with the solved value
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  Target,
  Search as SearchIcon,
  Plus,
  Check,
  AlertTriangle,
  Loader2,
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
import { cn } from '@/lib/utils';
import { findLimit, type FindLimitResponseBody } from '@/lib/api';
import type { FindLimitMetric, FindLimitSolveFor, LoanSpec } from '@/types/whatif';
import { useWhatIf } from './WhatIfContext';
import {
  useProductFormState,
  CascadingDropdowns,
  StructuralConfigRow,
  TemplateFieldsForm,
  ComingSoonPlaceholder,
} from './shared/ProductConfigForm';
import {
  buildModificationFromForm,
  shouldShowTemplateFields,
  computeResidualMaturityYears,
  TEMPLATE_SUBCATEGORY_MAP,
} from './shared/constants';

// ── Constants ────────────────────────────────────────────────────────────

const METRIC_OPTIONS: { value: FindLimitMetric; label: string }[] = [
  { value: 'eve', label: 'EVE' },
  { value: 'nii', label: 'NII' },
];

const SCENARIO_OPTIONS = [
  { value: 'base', label: 'Base (No Shock)' },
  { value: 'worst', label: 'Worst Case' },
  { value: 'Parallel Up', label: 'Parallel Up (+200bp)' },
  { value: 'Parallel Down', label: 'Parallel Down (-200bp)' },
  { value: 'Steepener', label: 'Steepener' },
  { value: 'Flattener', label: 'Flattener' },
  { value: 'Short Up', label: 'Short Rate Up (+250bp)' },
  { value: 'Short Down', label: 'Short Rate Down (-250bp)' },
];

const SOLVE_FOR_OPTIONS: { value: FindLimitSolveFor; label: string; description: string }[] = [
  { value: 'notional', label: 'Notional', description: 'Find maximum notional amount' },
  { value: 'rate', label: 'Rate', description: 'Find the rate that hits the limit' },
  { value: 'maturity', label: 'Maturity', description: 'Find the maturity that hits the limit' },
  { value: 'spread', label: 'Spread', description: 'Find the spread (bps) that hits the limit' },
];

/** Map solve_for → template field IDs to exclude from the product form. */
const SOLVE_FOR_EXCLUDE_FIELDS: Record<string, string[]> = {
  notional: ['notional'],
  rate: ['coupon', 'depositRate', 'fixedRate', 'wac'],
  maturity: ['maturityDate'],
  spread: ['spread'],
};

// ── Helpers ──────────────────────────────────────────────────────────────

function formatFoundValue(solveFor: string, value: number): string {
  switch (solveFor) {
    case 'notional': {
      const millions = value / 1e6;
      return `${millions.toLocaleString('en-US', { maximumFractionDigits: 1 })}M`;
    }
    case 'rate':
      return `${(value * 100).toFixed(3)}%`;
    case 'maturity':
      return `${value.toFixed(2)} years`;
    case 'spread':
      return `${value.toFixed(1)} bps`;
    default:
      return String(value);
  }
}

function formatMetricValue(value: number): string {
  const millions = value / 1e6;
  return `${millions >= 0 ? '+' : ''}${millions.toLocaleString('en-US', { maximumFractionDigits: 2 })}M`;
}

/** Build a LoanSpec-like object for the API from form state. */
function buildProductSpec(
  state: ReturnType<typeof useProductFormState>['state'],
  derived: ReturnType<typeof useProductFormState>['derived'],
  solveFor: FindLimitSolveFor,
): FindLimitResponseBody['product_spec'] | null {
  const { selectedTemplate } = derived;
  if (!selectedTemplate) return null;

  const fv = state.formValues;
  const termYears = computeResidualMaturityYears(fv);

  const rateType = derived.selectedVariant?.id.includes('floating') || derived.selectedVariant?.id.includes('frn')
    ? 'variable'
    : 'fixed';

  const rawRate = fv.coupon || fv.depositRate || fv.fixedRate || fv.wac;
  const fixedRate = rawRate ? parseFloat(rawRate) / 100 : null;

  const side = selectedTemplate.category === 'liability' ? 'L' : 'A';

  // For the solve_for field, use a reasonable reference value
  let notional = fv.notional ? parseFloat(fv.notional.replace(/,/g, '')) || 1_000_000 : 1_000_000;
  let specTermYears = termYears || 5.0;
  let specFixedRate = fixedRate;
  let spreadBps = fv.spread ? parseFloat(fv.spread) : 0.0;

  // When solving for a field, set a reference value for it
  if (solveFor === 'notional') notional = 1_000_000;
  if (solveFor === 'rate') specFixedRate = 0.03;
  if (solveFor === 'maturity') specTermYears = 5.0;
  if (solveFor === 'spread') spreadBps = 100.0;

  const freqMap: Record<string, string> = {
    'Monthly': '1M', 'Quarterly': '3M', 'Semi-Annual': '6M', 'Annual': '12M',
  };

  return {
    id: `findlimit_${Date.now()}`,
    notional,
    term_years: specTermYears,
    side,
    currency: fv.currency || 'EUR',
    rate_type: rateType,
    fixed_rate: specFixedRate,
    variable_index: fv.refIndex ? `EUR_${fv.refIndex.replace(/\s+/g, '_').toUpperCase()}` : null,
    spread_bps: spreadBps,
    amortization: state.selectedAmortization || 'bullet',
    grace_years: fv.graceYears ? parseFloat(fv.graceYears) : 0.0,
    daycount: fv.daycount || '30/360',
    payment_freq: freqMap[fv.paymentFreq || ''] || '12M',
    repricing_freq: fv.repricingFreq ? (freqMap[fv.repricingFreq] || null) : null,
    start_date: fv.startDate || null,
    floor_rate: fv.hasFloor === 'Yes' && fv.floorRate ? parseFloat(fv.floorRate) / 100 : null,
    cap_rate: fv.hasCap === 'Yes' && fv.capRate ? parseFloat(fv.capRate) / 100 : null,
    label: selectedTemplate.name,
  };
}

// ── Props ────────────────────────────────────────────────────────────────

interface FindLimitCompartmentProps {
  sessionId: string | null;
}

// ═════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═════════════════════════════════════════════════════════════════════════

export function FindLimitCompartment({ sessionId }: FindLimitCompartmentProps) {
  // ── Constraint state ─────────────────────────────────────────────────
  const [targetMetric, setTargetMetric] = useState<FindLimitMetric>('eve');
  const [targetScenario, setTargetScenario] = useState('worst');
  const [limitMode, setLimitMode] = useState<'pct' | 'abs'>('pct');
  const [limitValue, setLimitValue] = useState('');
  const [solveFor, setSolveFor] = useState<FindLimitSolveFor>('notional');

  // ── Result state ─────────────────────────────────────────────────────
  const [result, setResult] = useState<FindLimitResponseBody | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Product form (shared with AddCatalog) ────────────────────────────
  const { state, callbacks, derived } = useProductFormState();
  const { addModification, cet1Capital } = useWhatIf();

  // ── Exclude the solve_for field from the product form ────────────────
  const excludeFieldIds = useMemo(() => {
    const candidates = SOLVE_FOR_EXCLUDE_FIELDS[solveFor] || [];
    if (!derived.selectedTemplate) return new Set<string>();
    const templateFieldIds = new Set(derived.selectedTemplate.fields.map((f) => f.id));
    return new Set(candidates.filter((id) => templateFieldIds.has(id)));
  }, [solveFor, derived.selectedTemplate]);

  const showFields = shouldShowTemplateFields(
    state.selectedFamilyId,
    state.formValues,
    derived.selectedTemplate,
    derived.selectedVariant,
  );

  // Check if enough fields are filled (all required except excluded ones)
  const productReady = useMemo(() => {
    if (!derived.selectedTemplate) return false;
    if (!state.formValues.daycount) return false;
    if (!showFields) return false;

    // Check all required fields are filled, except excluded ones
    return derived.templateFormFields
      .filter((f) => {
        if (f.disabled || !f.required) return false;
        if (excludeFieldIds.has(f.id)) return false;
        if (f.showWhen && state.formValues[f.showWhen.field] !== f.showWhen.value) return false;
        return true;
      })
      .every((f) => !!state.formValues[f.id]);
  }, [derived.selectedTemplate, derived.templateFormFields, state.formValues, excludeFieldIds, showFields]);

  const hasCet1 = cet1Capital !== null && cet1Capital > 0;
  const canFind = !!sessionId && !!limitValue && productReady
    && (limitMode === 'abs' || hasCet1);

  // ── Find handler ─────────────────────────────────────────────────────

  const handleFind = useCallback(async () => {
    if (!sessionId || !limitValue) return;

    const productSpec = buildProductSpec(state, derived, solveFor);
    if (!productSpec) return;

    const parsed = parseFloat(limitValue);
    const absoluteLimit = limitMode === 'pct'
      ? (parsed / 100) * cet1Capital!
      : parsed;

    setIsSearching(true);
    setError(null);
    setResult(null);

    try {
      const resp = await findLimit(sessionId, {
        product_spec: productSpec,
        target_metric: targetMetric,
        target_scenario: targetScenario,
        limit_value: absoluteLimit,
        solve_for: solveFor,
      });
      setResult(resp);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSearching(false);
    }
  }, [sessionId, limitValue, limitMode, cet1Capital, state, derived, solveFor, targetMetric, targetScenario]);

  // ── Add to Modifications handler ─────────────────────────────────────

  const handleAddToModifications = useCallback(() => {
    if (!result || !derived.selectedTemplate) return;

    // Build a form values copy with the solved value injected
    const solvedFormValues = { ...state.formValues };

    // Inject the solved value into the appropriate form field
    if (result.solve_for === 'notional') {
      solvedFormValues.notional = String(Math.round(result.found_value));
    } else if (result.solve_for === 'rate') {
      const rateField = ['coupon', 'depositRate', 'fixedRate', 'wac'].find(
        (f) => derived.selectedTemplate!.fields.some((tf) => tf.id === f),
      );
      if (rateField) solvedFormValues[rateField] = String((result.found_value * 100).toFixed(4));
    } else if (result.solve_for === 'maturity') {
      // Convert years to a date
      const start = solvedFormValues.startDate ? new Date(solvedFormValues.startDate) : new Date();
      const matDate = new Date(start.getTime() + result.found_value * 365.25 * 24 * 60 * 60 * 1000);
      solvedFormValues.maturityDate = matDate.toISOString().slice(0, 10);
    } else if (result.solve_for === 'spread') {
      solvedFormValues.spread = String(result.found_value.toFixed(1));
    }

    const modData = buildModificationFromForm(
      derived.selectedTemplate,
      state.selectedAmortization,
      solvedFormValues,
    );

    addModification(modData);
    setResult(null);
  }, [result, derived.selectedTemplate, state, addModification]);

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full min-h-0">
      {/* ── Left Panel: Constraint & Result ──────────────────────────── */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex items-center gap-1.5 px-4 pb-2.5 pt-3 border-b border-border/40 shrink-0">
          <Target className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">Constraint & Result</span>
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-4 py-3 space-y-3">
            {/* ── Row 1: Metric | Scenario ──────────────────────────── */}
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-[10px] text-muted-foreground">Target Metric</Label>
                <Select value={targetMetric} onValueChange={(v) => { setTargetMetric(v as FindLimitMetric); setResult(null); }}>
                  <SelectTrigger className="h-7 text-[11px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {METRIC_OPTIONS.map((m) => (
                      <SelectItem key={m.value} value={m.value} className="text-xs">{m.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1">
                <Label className="text-[10px] text-muted-foreground">Scenario</Label>
                <Select value={targetScenario} onValueChange={(v) => { setTargetScenario(v); setResult(null); }}>
                  <SelectTrigger className="h-7 text-[11px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SCENARIO_OPTIONS.map((s) => (
                      <SelectItem key={s.value} value={s.value} className="text-xs">{s.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* ── Row 2: Limit Value (with mode toggle) | Solve For ── */}
            <div className="grid grid-cols-2 gap-2 items-start">
              <div className="space-y-1">
                <div className="flex items-center gap-1.5 h-[14px]">
                  <Label className="text-[10px] text-muted-foreground leading-none">
                    Δ{targetMetric.toUpperCase()} Limit
                  </Label>
                  {/* Segmented toggle: %CET1 / Absolute */}
                  <div className="flex rounded-md border border-border/60 overflow-hidden ml-auto">
                    <button
                      type="button"
                      onClick={() => { setLimitMode('pct'); setLimitValue(''); setResult(null); }}
                      className={cn(
                        'px-1.5 py-0 text-[9px] font-medium leading-[16px] transition-colors',
                        limitMode === 'pct'
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:bg-accent/60',
                      )}
                    >
                      %CET1
                    </button>
                    <button
                      type="button"
                      onClick={() => { setLimitMode('abs'); setLimitValue(''); setResult(null); }}
                      className={cn(
                        'px-1.5 py-0 text-[9px] font-medium leading-[16px] transition-colors',
                        limitMode === 'abs'
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:bg-accent/60',
                      )}
                    >
                      Abs
                    </button>
                  </div>
                </div>
                <div className="relative">
                  <Input
                    type="number"
                    step={limitMode === 'pct' ? '0.1' : '100000'}
                    placeholder={limitMode === 'pct' ? 'e.g. -15' : 'e.g. -50000000'}
                    value={limitValue}
                    onChange={(e) => { setLimitValue(e.target.value); setResult(null); }}
                    className={cn('h-7 text-[11px]', limitMode === 'pct' && 'pr-6')}
                  />
                  {limitMode === 'pct' && (
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground pointer-events-none">
                      %
                    </span>
                  )}
                </div>
                {/* Conversion hint */}
                {limitMode === 'pct' && hasCet1 && limitValue && (
                  <p className="text-[9px] text-muted-foreground/70">
                    = {((parseFloat(limitValue) / 100) * cet1Capital!).toLocaleString('en-US', { maximumFractionDigits: 0 })} EUR
                  </p>
                )}
                {limitMode === 'abs' && hasCet1 && limitValue && (
                  <p className="text-[9px] text-muted-foreground/70">
                    = {(parseFloat(limitValue) / cet1Capital! * 100).toFixed(2)}% CET1
                  </p>
                )}
                {limitMode === 'pct' && !hasCet1 && (
                  <p className="text-[9px] text-amber-500">
                    Set CET1 Capital first.
                  </p>
                )}
              </div>

              <div className="space-y-1">
                <div className="h-[14px] flex items-center">
                  <Label className="text-[10px] text-muted-foreground leading-none">Solve For</Label>
                </div>
                <Select value={solveFor} onValueChange={(v) => { setSolveFor(v as FindLimitSolveFor); setResult(null); }}>
                  <SelectTrigger className="h-7 text-[11px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOLVE_FOR_OPTIONS.map((s) => (
                      <SelectItem key={s.value} value={s.value} className="text-xs">
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[9px] text-muted-foreground/70">
                  {SOLVE_FOR_OPTIONS.find((s) => s.value === solveFor)?.description}
                </p>
              </div>
            </div>

            {/* ── Find button ──────────────────────────────────────────── */}
            <Button
              size="sm"
              className="h-8 text-xs w-full"
              onClick={handleFind}
              disabled={!canFind || isSearching}
            >
              {isSearching ? (
                <>
                  <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
                  Searching...
                </>
              ) : (
                <>
                  <SearchIcon className="h-3 w-3 mr-1.5" />
                  Find Limit
                </>
              )}
            </Button>

            {!sessionId && (
              <p className="text-[10px] text-muted-foreground text-center">
                Upload a balance and run a calculation first.
              </p>
            )}

            {/* ── Error ────────────────────────────────────────────────── */}
            {error && (
              <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-destructive/30 bg-destructive/5">
                <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
                <p className="text-[10px] text-destructive break-all">{error}</p>
              </div>
            )}

            {/* ── Result ───────────────────────────────────────────────── */}
            {result && (
              <div className="space-y-3">
                <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2.5 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                      Result
                    </span>
                    {result.converged ? (
                      <span className="flex items-center gap-1 text-[9px] text-success">
                        <Check className="h-2.5 w-2.5" /> Converged
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[9px] text-amber-500">
                        <AlertTriangle className="h-2.5 w-2.5" /> Approximate
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                    <div>
                      <span className="text-[9px] text-muted-foreground block">
                        Max {SOLVE_FOR_OPTIONS.find((s) => s.value === result.solve_for)?.label}
                      </span>
                      <span className="text-sm font-semibold text-primary font-mono">
                        {formatFoundValue(result.solve_for, result.found_value)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[9px] text-muted-foreground block">
                        Δ{result.target_metric.toUpperCase()} achieved
                      </span>
                      <span className="text-xs font-mono text-foreground">
                        {formatMetricValue(result.achieved_metric)}
                      </span>
                      {hasCet1 && (
                        <span className="text-[9px] text-muted-foreground ml-1">
                          ({(result.achieved_metric / cet1Capital! * 100).toFixed(2)}%)
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <Button
                  size="sm"
                  className="h-7 text-xs w-full"
                  onClick={handleAddToModifications}
                >
                  <Plus className="h-3 w-3 mr-1" />
                  Add {formatFoundValue(result.solve_for, result.found_value)} to Modifications
                </Button>
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* ── Vertical divider ──────────────────────────────────────────── */}
      <div className="w-px bg-border/60 shrink-0" />

      {/* ── Right Panel: Product Configuration ────────────────────────── */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex items-center gap-1.5 px-4 pb-2.5 pt-3 border-b border-border/40 shrink-0">
          <Plus className="h-3.5 w-3.5 text-success" />
          <span className="text-xs font-semibold text-foreground">Product Configuration</span>
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-4 py-3 space-y-4">
            <CascadingDropdowns state={state} callbacks={callbacks} derived={derived} />
            <StructuralConfigRow state={state} callbacks={callbacks} derived={derived} />

            {derived.selectedVariant?.comingSoon && (
              <ComingSoonPlaceholder name={derived.selectedVariant.name} />
            )}

            {showFields && (
              <>
                <div className="h-px bg-border/60" />

                <TemplateFieldsForm
                  state={state}
                  callbacks={callbacks}
                  derived={derived}
                  config={{ excludeFieldIds }}
                />
              </>
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
