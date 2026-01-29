import React, { useState } from 'react';
import { BarChart3, TrendingDown, TrendingUp, AlertTriangle, Eye, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { CalculationResults } from '@/types/financial';
import { EVEChart } from '@/components/results/EVEChart';
import { NIIChart } from '@/components/results/NIIChart';

interface ResultsCardProps {
  results: CalculationResults | null;
  isCalculating: boolean;
}

export function ResultsCard({ results, isCalculating }: ResultsCardProps) {
  const [showDetails, setShowDetails] = useState(false);

  const formatCurrency = (num: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  };

  const formatCompact = (num: number) => {
    const abs = Math.abs(num);
    if (abs >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(num / 1e3).toFixed(0)}K`;
    return num.toString();
  };

  const formatDelta = (num: number) => {
    const formatted = formatCompact(Math.abs(num));
    return num >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  if (isCalculating) {
    return (
      <div className="dashboard-card h-full">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Results</span>
          </div>
        </div>
        <div className="dashboard-card-content flex items-center justify-center">
          <div className="flex flex-col items-center gap-2">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span className="text-sm text-muted-foreground">Running IRRBB calculation...</span>
          </div>
        </div>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="dashboard-card h-full">
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
      </div>
    );
  }

  return (
    <>
      <div className="dashboard-card h-full">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Results</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground">
              {new Date(results.calculatedAt).toLocaleTimeString()}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowDetails(true)}
              className="h-5 px-2 text-[10px]"
            >
              <Eye className="mr-1 h-3 w-3" />
              Details
            </Button>
          </div>
        </div>

        <div className="dashboard-card-content">
          {/* Four quarters layout: 1/4 summary, 3/4 charts */}
          <div className="flex gap-3 h-full">
            {/* First quarter: Numeric summary */}
            <div className="w-1/4 flex flex-col gap-2">
              {/* Key Metrics */}
              <div className="space-y-1.5">
                <ResultMetricCompact label="Base EVE" value={formatCompact(results.baseEve)} />
                <ResultMetricCompact label="Base NII" value={formatCompact(results.baseNii)} />
              </div>
              
              {/* Worst Case Box */}
              <div className="rounded-lg border border-warning/30 bg-warning/5 p-2 flex-1">
                <div className="flex items-center gap-1 mb-1.5">
                  <AlertTriangle className="h-3 w-3 text-warning" />
                  <span className="text-[10px] font-semibold text-foreground">Worst Case</span>
                </div>
                <div className="text-[9px] text-muted-foreground mb-1">{results.worstCaseScenario}</div>
                <div
                  className={`flex items-center gap-1 text-sm font-bold ${
                    results.worstCaseDeltaEve >= 0 ? 'text-success' : 'text-destructive'
                  }`}
                >
                  {results.worstCaseDeltaEve >= 0 ? (
                    <TrendingUp className="h-3.5 w-3.5" />
                  ) : (
                    <TrendingDown className="h-3.5 w-3.5" />
                  )}
                  <span>ΔEVE {formatDelta(results.worstCaseDeltaEve)}</span>
                </div>
              </div>

              {/* Mini scenario table */}
              <div className="rounded-lg border border-border overflow-hidden flex-1">
                <div className="bg-muted/30 px-2 py-1 border-b border-border">
                  <span className="text-[9px] font-medium text-muted-foreground uppercase tracking-wide">Scenarios</span>
                </div>
                <div className="max-h-20 overflow-auto custom-scrollbar">
                  <table className="w-full text-[10px]">
                    <tbody>
                      {results.scenarioResults.slice(0, 4).map((result) => (
                        <tr key={result.scenarioId} className="border-b border-border/30">
                          <td className="py-0.5 px-2 text-foreground truncate max-w-[80px]">{result.scenarioName}</td>
                          <td className={`text-right py-0.5 px-2 font-mono ${
                            result.deltaEve >= 0 ? 'text-success' : 'text-destructive'
                          }`}>
                            {result.deltaEve >= 0 ? '+' : ''}{formatCompact(result.deltaEve)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Remaining 3/4: Charts side by side */}
            <div className="w-3/4 flex gap-3">
              {/* EVE Chart */}
              <div className="flex-1 rounded-lg border border-border overflow-hidden">
                <EVEChart />
              </div>
              
              {/* NII Chart */}
              <div className="flex-1 rounded-lg border border-border overflow-hidden">
                <NIIChart />
              </div>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-primary" />
              Calculation Results – Full Details
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4">
            <div className="grid grid-cols-4 gap-3">
              <SummaryCard label="Base EVE" value={formatCurrency(results.baseEve)} />
              <SummaryCard label="Base NII" value={formatCurrency(results.baseNii)} />
              <SummaryCard label="Worst EVE" value={formatCurrency(results.worstCaseEve)} />
              <SummaryCard 
                label="ΔEVE (Worst)" 
                value={formatDelta(results.worstCaseDeltaEve)} 
                variant={results.worstCaseDeltaEve >= 0 ? 'success' : 'destructive'}
              />
            </div>

            <div className="rounded-lg border border-border overflow-hidden">
              <table className="data-table text-xs">
                <thead>
                  <tr>
                    <th>Scenario</th>
                    <th className="text-right">EVE</th>
                    <th className="text-right">ΔEVE</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="bg-muted/30">
                    <td className="font-medium">Base Case</td>
                    <td className="text-right font-mono">{formatCurrency(results.baseEve)}</td>
                    <td className="text-right text-muted-foreground">—</td>
                  </tr>
                  {results.scenarioResults.map((result) => (
                    <tr key={result.scenarioId}>
                      <td className="font-medium">{result.scenarioName}</td>
                      <td className="text-right font-mono">{formatCurrency(result.eve)}</td>
                      <td
                        className={`text-right font-mono ${
                          result.deltaEve >= 0 ? 'text-success' : 'text-destructive'
                        }`}
                      >
                        {result.deltaEve >= 0 ? '+' : ''}{formatCurrency(result.deltaEve).replace('$', '')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function ResultMetricCompact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/50 px-2.5 py-1.5">
      <div className="text-[9px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className="text-base font-bold text-foreground">{value}</div>
    </div>
  );
}

function SummaryCard({ label, value, variant = 'default' }: { label: string; value: string; variant?: 'default' | 'success' | 'destructive' }) {
  const valueClass = variant === 'success' 
    ? 'text-success' 
    : variant === 'destructive' 
      ? 'text-destructive' 
      : 'text-foreground';
  
  return (
    <div className="rounded-lg bg-muted/50 p-3 text-center">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide mb-1">{label}</div>
      <div className={`text-sm font-bold ${valueClass}`}>{value}</div>
    </div>
  );
}
