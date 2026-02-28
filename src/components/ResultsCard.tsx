/**
 * ResultsCard.tsx – Displays IRRBB calculation results (EVE + NII).
 *
 * === ROLE IN THE SYSTEM ===
 * The bottom-right quadrant of the dashboard. Shows:
 * 1. A summary table (left 1/3) with 4 rows × 3 column groups:
 *    - Baseline: Base EVE, Worst EVE, Base NII, Worst NII (from CalculationResults)
 *    - What-If: Impact delta values (currently HARDCODED)
 *    - Post What-If: Baseline + impact
 *    Each column group shows both absolute value and %CET1.
 * 2. A chart area (right 2/3) toggling between EVEChart and NIIChart.
 * 3. A "Details" dialog with full scenario comparison table.
 *
 * === WHAT-IF INTEGRATION ===
 * When the user clicks "Apply to Analysis" in the WhatIfBuilder, this component
 * calls POST /api/sessions/{id}/calculate/whatif with the modifications. The
 * backend runs EVE/NII only on the delta positions (adds with positive sign,
 * removes with negative sign) using the same curves & scenarios as the base
 * calculation. The 4 impact values replace the previously hardcoded zeros.
 * - %CET1 columns are blank until the user sets a CET1 capital value.
 */
import React, { useState, useEffect, useRef } from 'react';
import { BarChart3, Eye, Clock, Loader2, ChevronDown, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { CalculationResults, Scenario } from '@/types/financial';
import { EVEChart } from '@/components/results/EVEChart';
import { NIIChart } from '@/components/results/NIIChart';
import { useWhatIf } from '@/components/whatif/WhatIfContext';
import { calculateWhatIf, getChartData } from '@/lib/api';
import type { WhatIfModificationRequest, ChartBucketRow, ChartNiiMonthRow } from '@/lib/api';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
interface ResultsCardProps {
  results: CalculationResults | null;
  isCalculating: boolean;
  calcProgress?: number;
  calcPhase?: string;
  calcEta?: string;
  sessionId: string | null;
  scenarios?: Scenario[];
}
export function ResultsCard({
  results,
  isCalculating,
  calcProgress = 0,
  calcPhase = '',
  calcEta = '',
  sessionId,
  scenarios = [],
}: ResultsCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [activeChart, setActiveChart] = useState<'eve' | 'nii'>('eve');
  const {
    modifications,
    isApplied,
    applyCounter,
    cet1Capital: contextCet1,
    analysisDate
  } = useWhatIf();
  const hasModifications = modifications.length > 0 && isApplied;

  // CET1 capital for percentage calculations – null when not set by the user.
  const cet1Capital = contextCet1;

  // What-If impact from backend calculation.
  const [whatIfImpact, setWhatIfImpact] = useState({
    baseEve: 0,
    worstEve: 0,
    baseNii: 0,
    worstNii: 0,
    scenarioEveDeltas: {} as Record<string, number>,
    scenarioNiiDeltas: {} as Record<string, number>,
    eveBucketDeltas: undefined as import('@/lib/api').WhatIfBucketDelta[] | undefined,
    niiMonthDeltas: undefined as import('@/lib/api').WhatIfMonthDelta[] | undefined,
  });
  const whatIfRequestIdRef = useRef(0);
  const [whatIfLoading, setWhatIfLoading] = useState(false);
  const [selectedScenario, setSelectedScenario] = useState('parallel-up');

  // Refs to always read the latest values inside the What-If useEffect without
  // adding them to its dependency array (which would re-trigger the call).
  const modificationsRef = useRef(modifications);
  modificationsRef.current = modifications;
  const resultsRef = useRef(results);
  resultsRef.current = results;

  // Chart data from backend (per-bucket EVE + per-month NII).
  const [eveBuckets, setEveBuckets] = useState<ChartBucketRow[]>([]);
  const [niiMonthly, setNiiMonthly] = useState<ChartNiiMonthRow[]>([]);
  const [chartDataLoading, setChartDataLoading] = useState(false);

  // Fetch chart data when calculation results are available.
  useEffect(() => {
    if (!results || !sessionId) {
      setEveBuckets([]);
      setNiiMonthly([]);
      return;
    }
    let cancelled = false;
    setChartDataLoading(true);
    getChartData(sessionId)
      .then((resp) => {
        if (cancelled) return;
        setEveBuckets(resp.eve_buckets);
        setNiiMonthly(resp.nii_monthly);
      })
      .catch((err) => {
        console.error('Failed to fetch chart data:', err);
        if (!cancelled) {
          setEveBuckets([]);
          setNiiMonthly([]);
        }
      })
      .finally(() => {
        if (!cancelled) setChartDataLoading(false);
      });
    return () => { cancelled = true; };
  }, [results, sessionId]);

  // Default to the worst scenario when calculation results arrive.
  useEffect(() => {
    if (results && results.scenarioResults.length > 0) {
      const worstResult = results.scenarioResults.find(
        s => s.scenarioName === results.worstCaseScenario
      );
      setSelectedScenario(worstResult?.scenarioId ?? results.scenarioResults[0].scenarioId);
    }
  }, [results]);

  // Trigger What-If calculation ONLY when the user explicitly clicks "Apply to
  // Analysis" (applyCounter increments). We guard on isApplied so that clearing /
  // removing modifications (which sets isApplied=false) resets the impact.
  // We read modifications & results from refs to avoid re-triggering when those
  // change (e.g. after a base recalculation or modification list edits).
  useEffect(() => {
    const currentMods = modificationsRef.current;
    const currentResults = resultsRef.current;

    if (!isApplied || currentMods.length === 0 || !currentResults || !sessionId) {
      setWhatIfImpact({ baseEve: 0, worstEve: 0, baseNii: 0, worstNii: 0, scenarioEveDeltas: {}, scenarioNiiDeltas: {}, eveBucketDeltas: undefined, niiMonthDeltas: undefined });
      setWhatIfLoading(false);
      return;
    }

    const requestId = ++whatIfRequestIdRef.current;
    setWhatIfLoading(true);
    setWhatIfImpact({ baseEve: 0, worstEve: 0, baseNii: 0, worstNii: 0, scenarioEveDeltas: {}, scenarioNiiDeltas: {}, eveBucketDeltas: undefined, niiMonthDeltas: undefined });

    const startTime = Date.now();
    const MIN_SPINNER_MS = 400;
    let cancelled = false;
    let tid: ReturnType<typeof setTimeout>;

    // V1 backend only handles 'add' and 'remove' types
    const v1Mods = currentMods.filter((m) => m.type === 'add' || m.type === 'remove');
    const modsPayload: WhatIfModificationRequest[] = v1Mods.map((m) => ({
      id: m.id,
      type: m.type,
      label: m.label,
      notional: m.notional,
      currency: m.currency,
      category: m.category,
      subcategory: m.subcategory,
      rate: m.rate,
      maturity: m.maturity,
      removeMode: m.removeMode,
      contractIds: m.contractIds,
      productTemplateId: m.productTemplateId,
      startDate: m.startDate,
      maturityDate: m.maturityDate,
      paymentFreq: m.paymentFreq,
      repricingFreq: m.repricingFreq,
      refIndex: m.refIndex,
      spread: m.spread,
      // V2 enrichment fields
      amortization: m.amortization,
      floorRate: m.floorRate,
      capRate: m.capRate,
    }));

    calculateWhatIf(sessionId, { modifications: modsPayload })
      .then((resp) => {
        if (cancelled || requestId !== whatIfRequestIdRef.current) return;
        const elapsed = Date.now() - startTime;
        const delay = Math.max(0, MIN_SPINNER_MS - elapsed);
        tid = setTimeout(() => {
          if (cancelled || requestId !== whatIfRequestIdRef.current) return;
          setWhatIfImpact({
            baseEve: resp.base_eve_delta,
            worstEve: resp.worst_eve_delta,
            baseNii: resp.base_nii_delta,
            worstNii: resp.worst_nii_delta,
            scenarioEveDeltas: resp.scenario_eve_deltas ?? {},
            scenarioNiiDeltas: resp.scenario_nii_deltas ?? {},
            eveBucketDeltas: resp.eve_bucket_deltas,
            niiMonthDeltas: resp.nii_month_deltas,
          });
          setWhatIfLoading(false);
        }, delay);
      })
      .catch((err) => {
        console.error("What-If calculation failed:", err);
        if (!cancelled && requestId === whatIfRequestIdRef.current) {
          setWhatIfImpact({ baseEve: 0, worstEve: 0, baseNii: 0, worstNii: 0, scenarioEveDeltas: {}, scenarioNiiDeltas: {}, eveBucketDeltas: undefined, niiMonthDeltas: undefined });
          setWhatIfLoading(false);
        }
      });

    return () => {
      cancelled = true;
      clearTimeout(tid);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyCounter, isApplied, sessionId]);
  // Build a lookup from scenario id → display label matching the Curves & Scenarios card
  // format: "Parallel Up +200bp", "Short Down -250bp", etc.
  const scenarioDisplayMap = new Map<string, string>();
  for (const sc of scenarios) {
    scenarioDisplayMap.set(sc.id, sc.name);
  }
  const getScenarioLabel = (scenarioId: string, fallbackName: string) =>
    scenarioDisplayMap.get(scenarioId) ?? fallbackName;

  const formatCurrency = (num: number) => {
    const millions = num / 1e6;
    return millions.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + '€';
  };
  const formatCompact = (num: number) => {
    const millions = num / 1e6;
    return millions.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + '€';
  };
  const formatPercentWithAbsolute = (percent: number, absolute: number) => {
    const sign = percent >= 0 ? '+' : '';
    const absSign = absolute >= 0 ? '+' : '';
    return `${sign}${percent.toFixed(1)}% (${absSign}${formatCompact(absolute)})`;
  };
  if (isCalculating) {
    return <div className="dashboard-card h-full">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Results</span>
          </div>
        </div>
        <div className="dashboard-card-content flex items-center justify-center">
          <div className="w-full max-w-xs">
            <p className="text-sm text-muted-foreground mb-3">Running IRRBB calculation...</p>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-300"
                  style={{ width: `${Math.round(calcProgress)}%` }}
                />
              </div>
              <span className="text-[10px] font-medium text-muted-foreground tabular-nums w-7 text-right">
                {Math.round(calcProgress)}%
              </span>
            </div>
            <p className="text-[9px] text-muted-foreground mt-1">
              {calcEta || 'Estimating…'}
            </p>
          </div>
        </div>
      </div>;
  }
  if (!results) {
    return <div className="dashboard-card h-full">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Results</span>
          </div>
        </div>
        <div className="dashboard-card-content flex flex-col items-center justify-center text-center">
          <Clock className="h-8 w-8 text-muted-foreground/50 mb-2" />
          <p className="text-sm text-muted-foreground font-medium">Not calculated yet</p>
          <p className="text-xs text-muted-foreground/70">Upload data and click Calculate to run IRRBB analysis</p>
        </div>
      </div>;
  }

  // Calculate worst case values – percentages expressed as delta / CET1 (IRRBB standard)
  const worstEvePercent = cet1Capital !== null ? results.worstCaseDeltaEve / cet1Capital * 100 : null;
  // NII worst may differ from EVE worst – find the actual NII-worst scenario
  const worstNiiResult = results.scenarioResults.reduce(
    (worst, sr) => (sr.deltaNii < worst.deltaNii ? sr : worst),
    results.scenarioResults[0]
  );
  const worstNiiDelta = worstNiiResult?.deltaNii ?? 0;
  const worstNiiPercent = cet1Capital !== null ? worstNiiDelta / cet1Capital * 100 : null;

  // Selected scenario (from dropdown) – drives both summary table and chart.
  const selectedResult = results.scenarioResults.find(s => s.scenarioId === selectedScenario);
  const selectedScenarioDisplayName = selectedResult
    ? getScenarioLabel(selectedResult.scenarioId, selectedResult.scenarioName)
    : '';
  const isWorstSelected = selectedResult?.scenarioName === results.worstCaseScenario;
  const scenarioDropdownLabel = isWorstSelected
    ? `${selectedScenarioDisplayName} (Worst)`
    : selectedScenarioDisplayName;

  return <>
      <div className="dashboard-card h-full flex flex-col">
        <div className="dashboard-card-header flex-shrink-0">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <BarChart3 className="h-3.5 w-3.5 text-primary" />
              <span className="text-xs font-semibold text-foreground">Results</span>
            </div>
            <Button size="sm" onClick={() => setShowDetails(true)} className="h-5 px-2 text-[10px]">
              <Eye className="mr-1 h-3 w-3" />
              Details
            </Button>
            {/* Scenario selector – drives table + chart */}
            <Popover>
              <PopoverTrigger asChild>
                <Button size="sm" variant="outline" className="h-5 px-2 text-[10px] font-medium">
                  {scenarioDropdownLabel || 'Scenario'}
                  <ChevronDown className="ml-1 h-2.5 w-2.5" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-56" align="start">
                <div className="space-y-3">
                  <div className="text-xs font-medium text-foreground">Select Scenario</div>
                  <RadioGroup value={selectedScenario} onValueChange={setSelectedScenario}>
                    {results.scenarioResults.map((sr) => {
                      const isWorst = sr.scenarioName === results.worstCaseScenario;
                      const displayName = getScenarioLabel(sr.scenarioId, sr.scenarioName);
                      return (
                        <div key={sr.scenarioId} className="flex items-center space-x-2">
                          <RadioGroupItem value={sr.scenarioId} id={`rc-${sr.scenarioId}`} />
                          <Label htmlFor={`rc-${sr.scenarioId}`} className="text-xs cursor-pointer">
                            {displayName}{isWorst ? ' (Worst)' : ''}
                          </Label>
                        </div>
                      );
                    })}
                  </RadioGroup>
                </div>
              </PopoverContent>
            </Popover>
          </div>
          <div className="flex items-center gap-2">
            {/* EVE/NII Toggle - Primary style */}
            <div className="flex items-center h-6 p-0.5 bg-primary rounded-md">
              <button onClick={() => setActiveChart('eve')} className={`h-5 px-3 text-[10px] font-medium rounded-sm transition-all ${activeChart === 'eve' ? 'bg-background text-foreground shadow-sm' : 'text-primary-foreground/70 hover:text-primary-foreground'}`}>
                EVE
              </button>
              <button onClick={() => setActiveChart('nii')} className={`h-5 px-3 text-[10px] font-medium rounded-sm transition-all ${activeChart === 'nii' ? 'bg-background text-foreground shadow-sm' : 'text-primary-foreground/70 hover:text-primary-foreground'}`}>
                NII
              </button>
            </div>
          </div>
        </div>

        {/* Warnings banner — non-blocking info about excluded instruments */}
        {results.warnings.length > 0 && (
          <div className="mx-3 mb-1.5 flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50/60 px-3 py-1.5 text-[11px] text-blue-800">
            <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-blue-500" />
            <div className="space-y-0.5">
              {results.warnings.map((w, i) => (
                <p key={i}>{w}</p>
              ))}
            </div>
          </div>
        )}

        <div className="dashboard-card-content flex-1 min-h-0">
          {/* Layout: 1/3 table, 2/3 chart - both fill available height */}
          <div className="flex gap-3 h-full">
            {/* Left: Grouped summary table - fills full height */}
            <div className="w-1/3 flex flex-col min-h-0">
              <div className="rounded-xl border border-border/40 flex-1 min-h-0 overflow-auto">
                <table className="w-full text-[11px] h-full">
                  <thead className="sticky top-0 z-10">
                    {/* Group headers */}
                    <tr className="bg-card border-b border-border/40">
                      <th className="text-center align-middle font-medium py-2 px-2 text-muted-foreground" rowSpan={2}>Metric</th>
                      <th className="text-center font-medium py-2 px-1.5 text-muted-foreground border-l border-border/40" colSpan={2}>Baseline</th>
                      <th className="text-center font-medium py-2 px-1.5 text-muted-foreground border-l border-border/40" colSpan={2}>
                        <span className="inline-flex items-center gap-1 justify-center">
                          What-If
                          {whatIfLoading && <Loader2 className="h-3 w-3 animate-spin" />}
                        </span>
                      </th>
                      <th className="text-center font-medium py-2 px-1.5 text-muted-foreground border-l border-border/40" colSpan={2}>Post W-I</th>
                    </tr>
                    {/* Subcolumn headers */}
                    <tr className="bg-card border-b border-border/40">
                      <th className="text-right font-medium py-1.5 px-1.5 text-muted-foreground/80 border-l border-border/40">Value</th>
                      <th className="text-right font-medium py-1.5 px-1.5 text-muted-foreground/80">%CET1</th>
                      <th className="text-right font-medium py-1.5 px-1.5 text-muted-foreground/80 border-l border-border/40">Value</th>
                      <th className="text-right font-medium py-1.5 px-1.5 text-muted-foreground/80">%CET1</th>
                      <th className="text-right font-medium py-1.5 px-1.5 text-muted-foreground/80 border-l border-border/40">Value</th>
                      <th className="text-right font-medium py-1.5 px-1.5 text-muted-foreground/80">%CET1</th>
                    </tr>
                  </thead>
                  <tbody>
                    <ResultsSummaryRow
                      label="Base EVE"
                      baselineValue={results.baseEve}
                      baselineCet1Pct={cet1Capital !== null ? 0 : null}
                      impactValue={hasModifications ? whatIfImpact.baseEve : 0}
                      impactCet1Pct={hasModifications && cet1Capital !== null ? whatIfImpact.baseEve / cet1Capital * 100 : null}
                      postValue={results.baseEve + (hasModifications ? whatIfImpact.baseEve : 0)}
                      postCet1Pct={cet1Capital !== null ? (hasModifications ? whatIfImpact.baseEve : 0) / cet1Capital * 100 : null}
                      hasModifications={hasModifications}
                      isLoading={whatIfLoading}
                    />
                    {(() => {
                      const scenarioEveDelta = hasModifications
                        ? (whatIfImpact.scenarioEveDeltas[selectedScenario] ?? whatIfImpact.worstEve)
                        : 0;
                      return <ResultsSummaryRow
                        label={`${scenarioDropdownLabel} EVE`}
                        baselineValue={selectedResult?.eve ?? results.baseEve}
                        baselineCet1Pct={cet1Capital !== null ? (selectedResult?.deltaEve ?? 0) / cet1Capital * 100 : null}
                        impactValue={scenarioEveDelta}
                        impactCet1Pct={hasModifications && cet1Capital !== null ? scenarioEveDelta / cet1Capital * 100 : null}
                        postValue={(selectedResult?.eve ?? results.baseEve) + scenarioEveDelta}
                        postCet1Pct={cet1Capital !== null ? ((selectedResult?.deltaEve ?? 0) + scenarioEveDelta) / cet1Capital * 100 : null}
                        hasModifications={hasModifications}
                        isLoading={whatIfLoading}
                        isWorst={isWorstSelected}
                      />;
                    })()}
                    <ResultsSummaryRow
                      label="Base NII"
                      baselineValue={results.baseNii}
                      baselineCet1Pct={cet1Capital !== null ? 0 : null}
                      impactValue={hasModifications ? whatIfImpact.baseNii : 0}
                      impactCet1Pct={hasModifications && cet1Capital !== null ? whatIfImpact.baseNii / cet1Capital * 100 : null}
                      postValue={results.baseNii + (hasModifications ? whatIfImpact.baseNii : 0)}
                      postCet1Pct={cet1Capital !== null ? (hasModifications ? whatIfImpact.baseNii : 0) / cet1Capital * 100 : null}
                      hasModifications={hasModifications}
                      isLoading={whatIfLoading}
                    />
                    {(() => {
                      const scenarioNiiDelta = hasModifications
                        ? (whatIfImpact.scenarioNiiDeltas[selectedScenario] ?? whatIfImpact.worstNii)
                        : 0;
                      return <ResultsSummaryRow
                        label={`${scenarioDropdownLabel} NII`}
                        baselineValue={results.baseNii + (selectedResult?.deltaNii ?? 0)}
                        baselineCet1Pct={cet1Capital !== null ? (selectedResult?.deltaNii ?? 0) / cet1Capital * 100 : null}
                        impactValue={scenarioNiiDelta}
                        impactCet1Pct={hasModifications && cet1Capital !== null ? scenarioNiiDelta / cet1Capital * 100 : null}
                        postValue={results.baseNii + (selectedResult?.deltaNii ?? 0) + scenarioNiiDelta}
                        postCet1Pct={cet1Capital !== null ? ((selectedResult?.deltaNii ?? 0) + scenarioNiiDelta) / cet1Capital * 100 : null}
                        hasModifications={hasModifications}
                        isLoading={whatIfLoading}
                        isWorst={isWorstSelected}
                        isLast
                      />;
                    })()}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Right: Chart area - fills full height */}
            <div className="w-2/3 flex flex-col min-h-0">
              <div className="rounded-lg border border-border overflow-hidden flex-1 min-h-0">
                {activeChart === 'eve'
                  ? <EVEChart fullWidth analysisDate={analysisDate} selectedScenario={selectedScenario} scenarioLabel={scenarioDropdownLabel} eveBuckets={eveBuckets} chartDataLoading={chartDataLoading} whatIfBucketDeltas={whatIfImpact.eveBucketDeltas} />
                  : <NIIChart fullWidth analysisDate={analysisDate} selectedScenario={selectedScenario} scenarioLabel={scenarioDropdownLabel} niiMonthly={niiMonthly} chartDataLoading={chartDataLoading} whatIfMonthDeltas={whatIfImpact.niiMonthDeltas} />}
              </div>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-5xl max-h-[85vh] overflow-auto p-6">
          <DialogHeader className="pb-4">
            <DialogTitle className="flex items-center gap-2.5 text-lg font-semibold">
              <BarChart3 className="h-5 w-5 text-primary" />
              Calculation Results – Full Details
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-6">
            {/* Summary Cards Row - 4 uniform rectangular cards */}
            <div className="grid grid-cols-4 gap-4">
              <SummaryCard label="BASE EVE" value={formatCurrency(results.baseEve)} />
              <SummaryCard label="WORST EVE" value={formatCurrency(results.worstCaseEve)} delta={formatCompact(results.worstCaseDeltaEve)} deltaPercent={worstEvePercent !== null ? `${worstEvePercent >= 0 ? '+' : ''}${worstEvePercent.toFixed(1)}% CET1` : undefined} variant={results.worstCaseDeltaEve >= 0 ? 'success' : 'destructive'} />
              <SummaryCard label="BASE NII" value={formatCurrency(results.baseNii)} />
              <SummaryCard label="WORST NII" value={formatCurrency(results.baseNii + worstNiiDelta)} delta={formatCompact(worstNiiDelta)} deltaPercent={worstNiiPercent !== null ? `${worstNiiPercent >= 0 ? '+' : ''}${worstNiiPercent.toFixed(1)}% CET1` : undefined} variant={worstNiiDelta >= 0 ? 'success' : 'destructive'} />
            </div>

            {/* Scenario Comparison Table - EVE and NII side by side */}
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-muted/40 border-b border-border">
                    <th className="text-left py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Scenario</th>
                    <th className="text-right py-3 px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">EVE</th>
                    <th className="text-right py-3 px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">ΔEVE</th>
                    <th className="text-right py-3 px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">ΔEVE %CET1</th>
                    <th className="text-right py-3 px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">NII</th>
                    <th className="text-right py-3 px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wide">ΔNII</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wide">ΔNII %CET1</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  {/* Base Case Row */}
                  <tr className="border-b border-border/50 hover:bg-muted/20 bg-muted/10">
                    <td className="py-3 px-4 font-semibold text-foreground">Base Case</td>
                    <td className="text-right py-3 px-3 font-mono text-foreground">{formatCurrency(results.baseEve)}</td>
                    <td className="text-right py-3 px-3 text-muted-foreground">—</td>
                    <td className="text-right py-3 px-3 text-muted-foreground">—</td>
                    <td className="text-right py-3 px-3 font-mono text-foreground">{formatCurrency(results.baseNii)}</td>
                    <td className="text-right py-3 px-3 text-muted-foreground">—</td>
                    <td className="text-right py-3 px-4 text-muted-foreground">—</td>
                  </tr>
                  {/* Scenario Rows */}
                  {results.scenarioResults.map((result, index) => {
                  const evePercent = cet1Capital !== null ? result.deltaEve / cet1Capital * 100 : null;
                  const niiPercent = cet1Capital !== null ? result.deltaNii / cet1Capital * 100 : null;
                  return <tr key={result.scenarioId} className={`hover:bg-muted/20 ${index < results.scenarioResults.length - 1 ? 'border-b border-border/50' : ''}`}>
                        <td className="py-3 px-4 font-medium text-foreground">{result.scenarioName}</td>
                        <td className="text-right py-3 px-3 font-mono text-foreground">{formatCurrency(result.eve)}</td>
                        <td className={`text-right py-3 px-3 font-mono font-medium ${result.deltaEve >= 0 ? 'text-success' : 'text-destructive'}`}>
                          {result.deltaEve >= 0 ? '+' : ''}{formatCompact(result.deltaEve)}
                        </td>
                        <td className={`text-right py-3 px-3 font-mono text-xs ${result.deltaEve >= 0 ? 'text-success' : 'text-destructive'}`}>
                          {evePercent !== null ? `${evePercent >= 0 ? '+' : ''}${evePercent.toFixed(1)}%` : '—'}
                        </td>
                        <td className="text-right py-3 px-3 font-mono text-foreground">{formatCurrency(result.nii)}</td>
                        <td className={`text-right py-3 px-3 font-mono font-medium ${result.deltaNii >= 0 ? 'text-success' : 'text-destructive'}`}>
                          {result.deltaNii >= 0 ? '+' : ''}{formatCompact(result.deltaNii)}
                        </td>
                        <td className={`text-right py-3 px-4 font-mono text-xs ${result.deltaNii >= 0 ? 'text-success' : 'text-destructive'}`}>
                          {niiPercent !== null ? `${niiPercent >= 0 ? '+' : ''}${niiPercent.toFixed(1)}%` : '—'}
                        </td>
                      </tr>;
                })}
                </tbody>
              </table>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>;
}
interface SummaryCardProps {
  label: string;
  value: string;
  delta?: string;
  deltaPercent?: string;
  variant?: 'default' | 'success' | 'destructive';
}
function SummaryCard({
  label,
  value,
  delta,
  deltaPercent,
  variant = 'default'
}: SummaryCardProps) {
  const deltaClass = variant === 'success' ? 'text-success' : variant === 'destructive' ? 'text-destructive' : 'text-muted-foreground';
  return <div className="rounded-xl bg-muted/40 p-4">
      <div className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-2">{label}</div>
      <div className="text-xl font-bold text-foreground">{value}</div>
      {(delta || deltaPercent) && <div className={`text-xs font-medium mt-1 ${deltaClass}`}>
          {delta && <span>{delta}</span>}
          {delta && deltaPercent && <span className="mx-1">•</span>}
          {deltaPercent && <span>{deltaPercent}</span>}
        </div>}
    </div>;
}

// Helper component for summary table rows
interface ResultsSummaryRowProps {
  label: string;
  baselineValue: number;
  baselineCet1Pct: number | null;
  impactValue: number;
  impactCet1Pct: number | null;
  postValue: number;
  postCet1Pct: number | null;
  hasModifications: boolean;
  isLoading?: boolean;
  isWorst?: boolean;
  isLast?: boolean;
}
function ResultsSummaryRow({
  label,
  baselineValue,
  baselineCet1Pct,
  impactValue,
  impactCet1Pct,
  postValue,
  postCet1Pct,
  hasModifications,
  isLoading = false,
  isWorst = false,
  isLast = false
}: ResultsSummaryRowProps) {
  const formatMillions = (num: number) => {
    const millions = num / 1e6;
    return millions.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + '€';
  };
  const formatImpact = (num: number) => {
    if (num === 0) return '—';
    const sign = num >= 0 ? '+' : '';
    return `${sign}${formatMillions(num)}`;
  };
  const formatPct = (pct: number | null) => pct !== null ? `${pct.toFixed(1)}%` : '—';
  const formatImpactPct = (pct: number | null) => {
    if (pct === null || pct === 0) return '—';
    const sign = pct >= 0 ? '+' : '';
    return `${sign}${pct.toFixed(1)}%`;
  };
  const getImpactClass = (val: number) => {
    if (val === 0) return 'text-muted-foreground';
    return val >= 0 ? 'text-success' : 'text-destructive';
  };
  return <tr className={`hover:bg-accent/40 transition-colors duration-150 ${!isLast ? 'border-b border-border/30' : ''}`}>
      <td className="py-2 px-2 font-medium text-foreground whitespace-nowrap">{label}</td>
      {/* Baseline */}
      <td className="text-right py-2 px-1.5 font-mono text-foreground border-l border-border/40">{formatMillions(baselineValue)}</td>
      <td className="text-right py-2 px-1.5 font-mono text-muted-foreground">{formatPct(baselineCet1Pct)}</td>
      {/* What-If Impact */}
      <td className={`text-right py-2 px-1.5 font-mono border-l border-border/40 ${isLoading ? 'text-muted-foreground' : getImpactClass(impactValue)}`}>
        {isLoading ? (
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground inline-block" />
        ) : hasModifications ? formatImpact(impactValue) : '—'}
      </td>
      <td className={`text-right py-2 px-1.5 font-mono ${isLoading ? 'text-muted-foreground' : getImpactClass(impactCet1Pct)}`}>
        {isLoading ? '' : hasModifications ? formatImpactPct(impactCet1Pct) : '—'}
      </td>
      {/* Post What-If */}
      <td className={`text-right py-2 px-1.5 font-mono font-semibold border-l border-border/40 ${isLoading ? 'text-muted-foreground' : 'text-foreground'}`}>
        {isLoading ? '...' : formatMillions(postValue)}
      </td>
      <td className={`text-right py-2 px-1.5 font-mono ${isLoading ? 'text-muted-foreground' : 'text-foreground'}`}>
        {isLoading ? '' : formatPct(postCet1Pct)}
      </td>
    </tr>;
}