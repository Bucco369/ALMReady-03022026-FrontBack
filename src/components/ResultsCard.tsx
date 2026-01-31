import React, { useState } from 'react';
import { BarChart3, Eye, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import type { CalculationResults } from '@/types/financial';
import { EVEChart } from '@/components/results/EVEChart';
import { NIIChart } from '@/components/results/NIIChart';
import { useWhatIf } from '@/components/whatif/WhatIfContext';

interface ResultsCardProps {
  results: CalculationResults | null;
  isCalculating: boolean;
}

export function ResultsCard({ results, isCalculating }: ResultsCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [activeChart, setActiveChart] = useState<'eve' | 'nii'>('eve');
  const { modifications, isApplied } = useWhatIf();
  
  const hasModifications = modifications.length > 0 && isApplied;

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

  const formatPercentWithAbsolute = (percent: number, absolute: number) => {
    const sign = percent >= 0 ? '+' : '';
    const absSign = absolute >= 0 ? '+' : '';
    return `${sign}${percent.toFixed(1)}% (${absSign}${formatCompact(absolute)})`;
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

  // Calculate worst case values
  const worstEvePercent = (results.worstCaseDeltaEve / results.baseEve) * 100;
  const worstNiiResult = results.scenarioResults.find(s => s.scenarioName === results.worstCaseScenario);
  const worstNiiDelta = worstNiiResult?.deltaNii ?? 0;
  const worstNiiPercent = (worstNiiDelta / results.baseNii) * 100;

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
          {/* Four quarters layout: 1/4 summary, 3/4 single chart */}
          <div className="flex gap-3 h-full">
            {/* First quarter: Clean summary table only */}
            <div className="w-1/4 flex flex-col">
              <div className="rounded-lg border border-border overflow-hidden flex-1">
                <table className="w-full text-[10px]">
                  <thead>
                    <tr className="bg-muted/50 border-b border-border">
                      <th className="text-left font-semibold py-1.5 px-2 text-muted-foreground">Metric</th>
                      <th className="text-right font-semibold py-1.5 px-2 text-muted-foreground">Value</th>
                      <th className="text-right font-semibold py-1.5 px-2 text-muted-foreground">Δ What-If</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-border/50 hover:bg-accent/30">
                      <td className="py-2 px-2 font-medium text-foreground">Base EVE</td>
                      <td className="text-right py-2 px-2 font-mono font-semibold text-foreground">
                        {formatCompact(results.baseEve)}
                      </td>
                      <td className={`text-right py-2 px-2 font-mono ${hasModifications ? 'text-success' : 'text-muted-foreground'}`}>
                        {hasModifications ? '+12.5M' : '—'}
                      </td>
                    </tr>
                    <tr className="border-b border-border/50 hover:bg-accent/30">
                      <td className="py-2 px-2 font-medium text-foreground">Worst EVE vs C1</td>
                      <td className={`text-right py-2 px-2 font-mono font-semibold ${
                        worstEvePercent >= 0 ? 'text-success' : 'text-destructive'
                      }`}>
                        {formatPercentWithAbsolute(worstEvePercent, results.worstCaseDeltaEve)}
                      </td>
                      <td className={`text-right py-2 px-2 font-mono ${hasModifications ? 'text-success' : 'text-muted-foreground'}`}>
                        {hasModifications ? '+0.3%' : '—'}
                      </td>
                    </tr>
                    <tr className="border-b border-border/50 hover:bg-accent/30">
                      <td className="py-2 px-2 font-medium text-foreground">Base NII</td>
                      <td className="text-right py-2 px-2 font-mono font-semibold text-foreground">
                        {formatCompact(results.baseNii)}
                      </td>
                      <td className={`text-right py-2 px-2 font-mono ${hasModifications ? 'text-destructive' : 'text-muted-foreground'}`}>
                        {hasModifications ? '-2.1M' : '—'}
                      </td>
                    </tr>
                    <tr className="hover:bg-accent/30">
                      <td className="py-2 px-2 font-medium text-foreground">Worst NII vs C1</td>
                      <td className={`text-right py-2 px-2 font-mono font-semibold ${
                        worstNiiPercent >= 0 ? 'text-success' : 'text-destructive'
                      }`}>
                        {formatPercentWithAbsolute(worstNiiPercent, worstNiiDelta)}
                      </td>
                      <td className={`text-right py-2 px-2 font-mono ${hasModifications ? 'text-destructive' : 'text-muted-foreground'}`}>
                        {hasModifications ? '-0.2%' : '—'}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Remaining 3/4: Single tabbed chart */}
            <div className="w-3/4 flex flex-col">
              {/* Tab selector */}
              <Tabs value={activeChart} onValueChange={(v) => setActiveChart(v as 'eve' | 'nii')} className="flex flex-col h-full">
                <TabsList className="h-7 p-0.5 bg-muted/50 w-fit self-start mb-2">
                  <TabsTrigger 
                    value="eve" 
                    className="h-6 px-4 text-[10px] font-medium data-[state=active]:bg-background data-[state=active]:shadow-sm"
                  >
                    EVE
                  </TabsTrigger>
                  <TabsTrigger 
                    value="nii" 
                    className="h-6 px-4 text-[10px] font-medium data-[state=active]:bg-background data-[state=active]:shadow-sm"
                  >
                    NII
                  </TabsTrigger>
                </TabsList>
                
                <TabsContent value="eve" className="flex-1 mt-0">
                  <div className="rounded-lg border border-border overflow-hidden h-full">
                    <EVEChart fullWidth />
                  </div>
                </TabsContent>
                
                <TabsContent value="nii" className="flex-1 mt-0">
                  <div className="rounded-lg border border-border overflow-hidden h-full">
                    <NIIChart fullWidth />
                  </div>
                </TabsContent>
              </Tabs>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-auto p-6">
          <DialogHeader className="pb-4">
            <DialogTitle className="flex items-center gap-2.5 text-lg font-semibold">
              <BarChart3 className="h-5 w-5 text-primary" />
              Calculation Results – Full Details
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-6">
            {/* Summary Cards Row */}
            <div className="grid grid-cols-4 gap-4">
              <SummaryCard label="BASE EVE" value={formatCurrency(results.baseEve)} />
              <SummaryCard label="BASE NII" value={formatCurrency(results.baseNii)} />
              <SummaryCard label="WORST EVE" value={formatCurrency(results.worstCaseEve)} />
              <SummaryCard 
                label="ΔEVE (WORST)" 
                value={formatCompact(results.worstCaseDeltaEve)} 
                variant={results.worstCaseDeltaEve >= 0 ? 'success' : 'destructive'}
              />
            </div>

            {/* Scenario Results Table */}
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-muted/40 border-b border-border">
                    <th className="text-left py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Scenario</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wide">EVE</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wide">ΔEVE</th>
                  </tr>
                </thead>
                <tbody className="text-sm">
                  <tr className="border-b border-border/50 hover:bg-muted/20">
                    <td className="py-3 px-4 font-medium text-foreground">Base Case</td>
                    <td className="text-right py-3 px-4 font-mono text-foreground">{formatCurrency(results.baseEve)}</td>
                    <td className="text-right py-3 px-4 text-muted-foreground">—</td>
                  </tr>
                  {results.scenarioResults.map((result, index) => (
                    <tr 
                      key={result.scenarioId} 
                      className={`hover:bg-muted/20 ${index < results.scenarioResults.length - 1 ? 'border-b border-border/50' : ''}`}
                    >
                      <td className="py-3 px-4 font-medium text-foreground">{result.scenarioName}</td>
                      <td className="text-right py-3 px-4 font-mono text-foreground">{formatCurrency(result.eve)}</td>
                      <td
                        className={`text-right py-3 px-4 font-mono font-medium ${
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

function SummaryCard({ label, value, variant = 'default' }: { label: string; value: string; variant?: 'default' | 'success' | 'destructive' }) {
  const valueClass = variant === 'success' 
    ? 'text-success' 
    : variant === 'destructive' 
      ? 'text-destructive' 
      : 'text-foreground';
  
  return (
    <div className="rounded-xl bg-muted/40 p-4 text-center">
      <div className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-2">{label}</div>
      <div className={`text-xl font-bold ${valueClass}`}>{value}</div>
    </div>
  );
}
