import React from 'react';
import { BarChart3, TrendingDown, TrendingUp, AlertTriangle } from 'lucide-react';
import type { CalculationResults } from '@/types/financial';

interface ResultsDisplayProps {
  results: CalculationResults | null;
  isCalculating: boolean;
}

export function ResultsDisplay({ results, isCalculating }: ResultsDisplayProps) {
  const formatCurrency = (num: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  };

  const formatDelta = (num: number) => {
    const formatted = formatCurrency(Math.abs(num));
    return num >= 0 ? `+${formatted}` : `-${formatted.replace('$', '')}`;
  };

  if (isCalculating) {
    return (
      <div className="section-card animate-fade-in">
        <div className="section-header">
          <BarChart3 className="h-5 w-5 text-primary" />
          Results
        </div>
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <span className="ml-3 text-muted-foreground">Calculating...</span>
        </div>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="section-card animate-fade-in">
        <div className="section-header">
          <BarChart3 className="h-5 w-5 text-primary" />
          Results
        </div>
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <BarChart3 className="mb-3 h-12 w-12 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">
            Upload positions and curves, then click Calculate to see results
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="section-card animate-fade-in">
      <div className="section-header">
        <BarChart3 className="h-5 w-5 text-primary" />
        Results
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          Calculated at {new Date(results.calculatedAt).toLocaleTimeString()}
        </span>
      </div>

      {/* Summary Cards */}
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-lg border border-border bg-muted/30 p-4">
          <div className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Base EVE
          </div>
          <div className="text-2xl font-bold text-foreground">
            {formatCurrency(results.baseEve)}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-muted/30 p-4">
          <div className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Worst-Case EVE
          </div>
          <div className="text-2xl font-bold text-foreground">
            {formatCurrency(results.worstCaseEve)}
          </div>
          <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
            <AlertTriangle className="h-3 w-3" />
            {results.worstCaseScenario}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-muted/30 p-4">
          <div className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            ΔEVE (Worst Case)
          </div>
          <div
            className={`flex items-center gap-2 text-2xl font-bold ${
              results.worstCaseDeltaEve >= 0 ? 'value-positive' : 'value-negative'
            }`}
          >
            {results.worstCaseDeltaEve >= 0 ? (
              <TrendingUp className="h-5 w-5" />
            ) : (
              <TrendingDown className="h-5 w-5" />
            )}
            {formatDelta(results.worstCaseDeltaEve)}
          </div>
        </div>
      </div>

      {/* NII Summary */}
      <div className="mb-6 rounded-lg border border-border bg-muted/30 p-4">
        <div className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Base NII (12 months)
        </div>
        <div className="text-xl font-bold text-foreground">
          {formatCurrency(results.baseNii)}
        </div>
      </div>

      {/* Detailed Results Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="data-table">
          <thead>
            <tr>
              <th>Scenario</th>
              <th className="text-right">EVE</th>
              <th className="text-right">ΔEVE</th>
              <th className="text-right">NII</th>
              <th className="text-right">ΔNII</th>
            </tr>
          </thead>
          <tbody>
            <tr className="bg-muted/50">
              <td className="font-medium">Base Case</td>
              <td className="text-right font-mono">{formatCurrency(results.baseEve)}</td>
              <td className="text-right font-mono text-muted-foreground">—</td>
              <td className="text-right font-mono">{formatCurrency(results.baseNii)}</td>
              <td className="text-right font-mono text-muted-foreground">—</td>
            </tr>
            {results.scenarioResults.map((result) => (
              <tr key={result.scenarioId}>
                <td className="font-medium">{result.scenarioName}</td>
                <td className="text-right font-mono">{formatCurrency(result.eve)}</td>
                <td
                  className={`text-right font-mono ${
                    result.deltaEve >= 0 ? 'value-positive' : 'value-negative'
                  }`}
                >
                  {formatDelta(result.deltaEve)}
                </td>
                <td className="text-right font-mono">{formatCurrency(result.nii)}</td>
                <td
                  className={`text-right font-mono ${
                    result.deltaNii >= 0 ? 'value-positive' : 'value-negative'
                  }`}
                >
                  {formatDelta(result.deltaNii)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
