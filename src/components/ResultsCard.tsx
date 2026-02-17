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
 * === CURRENT LIMITATIONS ===
 * - HARDCODED WHAT-IF IMPACT: The whatIfImpact object uses fixed values
 *   (+12.5M EVE, +8.2M worst EVE, -2.1M NII, -1.8M worst NII) that appear
 *   whenever What-If modifications are applied. Never computed from real data.
 * - %CET1 columns are blank until the user sets a CET1 capital value.
 * - Phase 1 will replace hardcoded impacts with delta values returned from
 *   the backend /calculate endpoint after applying What-If overlays.
 */
import React, { useState } from 'react';
import { BarChart3, Eye, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import type { CalculationResults } from '@/types/financial';
import { EVEChart } from '@/components/results/EVEChart';
import { NIIChart } from '@/components/results/NIIChart';
import { useWhatIf } from '@/components/whatif/WhatIfContext';
interface ResultsCardProps {
  results: CalculationResults | null;
  isCalculating: boolean;
  calcProgress?: number;
}
export function ResultsCard({
  results,
  isCalculating,
  calcProgress = 0,
}: ResultsCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [activeChart, setActiveChart] = useState<'eve' | 'nii'>('eve');
  const {
    modifications,
    isApplied,
    cet1Capital: contextCet1,
    analysisDate
  } = useWhatIf();
  const hasModifications = modifications.length > 0 && isApplied;

  // CET1 capital for percentage calculations – null when not set by the user.
  const cet1Capital = contextCet1;

  // What-If impact values – zeroed out until backend What-If overlay is implemented.
  // When Phase 2 lands, these will come from a separate /calculate call with
  // What-If modifications applied server-side.
  const whatIfImpact = {
    baseEve: 0,
    worstEve: 0,
    baseNii: 0,
    worstNii: 0
  };
  const formatCurrency = (num: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(num);
  };
  const formatCompact = (num: number) => {
    const abs = Math.abs(num);
    if (abs >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(num / 1e3).toFixed(0)}K`;
    return num.toString();
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
            <p className="text-[9px] text-muted-foreground mt-1">This typically takes 3–6 minutes — please wait</p>
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
  const worstNiiResult = results.scenarioResults.find(s => s.scenarioName === results.worstCaseScenario);
  const worstNiiDelta = worstNiiResult?.deltaNii ?? 0;
  const worstNiiPercent = cet1Capital !== null ? worstNiiDelta / cet1Capital * 100 : null;
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
                      <th className="text-center font-medium py-2 px-1.5 text-muted-foreground border-l border-border/40" colSpan={2}>What-If</th>
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
                    />
                    <ResultsSummaryRow
                      label="Worst scenario EVE"
                      baselineValue={results.worstCaseEve}
                      baselineCet1Pct={cet1Capital !== null ? results.worstCaseDeltaEve / cet1Capital * 100 : null}
                      impactValue={hasModifications ? whatIfImpact.worstEve : 0}
                      impactCet1Pct={hasModifications && cet1Capital !== null ? whatIfImpact.worstEve / cet1Capital * 100 : null}
                      postValue={results.worstCaseEve + (hasModifications ? whatIfImpact.worstEve : 0)}
                      postCet1Pct={cet1Capital !== null ? (results.worstCaseDeltaEve + (hasModifications ? whatIfImpact.worstEve : 0)) / cet1Capital * 100 : null}
                      hasModifications={hasModifications}
                      isWorst
                    />
                    <ResultsSummaryRow
                      label="Base NII"
                      baselineValue={results.baseNii}
                      baselineCet1Pct={cet1Capital !== null ? 0 : null}
                      impactValue={hasModifications ? whatIfImpact.baseNii : 0}
                      impactCet1Pct={hasModifications && cet1Capital !== null ? whatIfImpact.baseNii / cet1Capital * 100 : null}
                      postValue={results.baseNii + (hasModifications ? whatIfImpact.baseNii : 0)}
                      postCet1Pct={cet1Capital !== null ? (hasModifications ? whatIfImpact.baseNii : 0) / cet1Capital * 100 : null}
                      hasModifications={hasModifications}
                    />
                    <ResultsSummaryRow
                      label="Worst scenario NII"
                      baselineValue={results.baseNii + worstNiiDelta}
                      baselineCet1Pct={cet1Capital !== null ? worstNiiDelta / cet1Capital * 100 : null}
                      impactValue={hasModifications ? whatIfImpact.worstNii : 0}
                      impactCet1Pct={hasModifications && cet1Capital !== null ? whatIfImpact.worstNii / cet1Capital * 100 : null}
                      postValue={results.baseNii + worstNiiDelta + (hasModifications ? whatIfImpact.worstNii : 0)}
                      postCet1Pct={cet1Capital !== null ? (worstNiiDelta + (hasModifications ? whatIfImpact.worstNii : 0)) / cet1Capital * 100 : null}
                      hasModifications={hasModifications}
                      isWorst
                      isLast
                    />
                  </tbody>
                </table>
              </div>
            </div>

            {/* Right: Chart area - fills full height */}
            <div className="w-2/3 flex flex-col min-h-0">
              <div className="rounded-lg border border-border overflow-hidden flex-1 min-h-0">
                {activeChart === 'eve' ? <EVEChart fullWidth analysisDate={analysisDate} /> : <NIIChart fullWidth analysisDate={analysisDate} />}
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
              <SummaryCard label="BASE NII" value={formatCurrency(results.baseNii)} />
              <SummaryCard label="WORST EVE" value={formatCurrency(results.worstCaseEve)} delta={formatCompact(results.worstCaseDeltaEve)} deltaPercent={worstEvePercent !== null ? `${worstEvePercent >= 0 ? '+' : ''}${worstEvePercent.toFixed(1)}% CET1` : undefined} variant={results.worstCaseDeltaEve >= 0 ? 'success' : 'destructive'} />
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
  isWorst = false,
  isLast = false
}: ResultsSummaryRowProps) {
  const formatMillions = (num: number) => {
    const abs = Math.abs(num);
    if (abs >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(num / 1e3).toFixed(0)}K`;
    return num.toFixed(0);
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
      <td className={`text-right py-2 px-1.5 font-mono border-l border-border/40 ${getImpactClass(impactValue)}`}>
        {hasModifications ? formatImpact(impactValue) : '—'}
      </td>
      <td className={`text-right py-2 px-1.5 font-mono ${getImpactClass(impactCet1Pct)}`}>
        {hasModifications ? formatImpactPct(impactCet1Pct) : '—'}
      </td>
      {/* Post What-If */}
      <td className="text-right py-2 px-1.5 font-mono font-semibold text-foreground border-l border-border/40">{formatMillions(postValue)}</td>
      <td className="text-right py-2 px-1.5 font-mono text-foreground">{formatPct(postCet1Pct)}</td>
    </tr>;
}