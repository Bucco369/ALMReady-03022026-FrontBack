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
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Results</span>
          </div>
        </div>
        <div className="dashboard-card-content flex items-center justify-center">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span className="text-xs text-muted-foreground">Calculating...</span>
          </div>
        </div>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Results</span>
          </div>
        </div>
        <div className="dashboard-card-content flex flex-col items-center justify-center text-center">
          <Clock className="h-6 w-6 text-muted-foreground/50 mb-2" />
          <p className="text-xs text-muted-foreground">Not calculated yet</p>
          <p className="text-[10px] text-muted-foreground/70">Upload data and click Calculate</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Results</span>
          </div>
          <span className="text-[10px] text-muted-foreground">
            {new Date(results.calculatedAt).toLocaleTimeString()}
          </span>
        </div>

        <div className="dashboard-card-content">
          <div className="grid grid-cols-2 gap-2 mb-2">
            <ResultMetric label="Base EVE" value={formatCompact(results.baseEve)} />
            <ResultMetric label="Base NII" value={formatCompact(results.baseNii)} />
          </div>

          <div className="rounded-md border border-border p-2 mb-2">
            <div className="flex items-center gap-1.5 mb-1">
              <AlertTriangle className="h-3 w-3 text-warning" />
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Worst Case</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{results.worstCaseScenario}</span>
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
                ΔEVE {formatDelta(results.worstCaseDeltaEve)}
              </div>
            </div>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowDetails(true)}
            className="w-full h-6 text-xs"
          >
            <Eye className="mr-1 h-3 w-3" />
            View results
          </Button>
        </div>
      </div>

      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-primary" />
              Calculation Results
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

function ResultMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-muted/50 px-2 py-1.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</div>
      <div className="text-sm font-semibold text-foreground">{value}</div>
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
