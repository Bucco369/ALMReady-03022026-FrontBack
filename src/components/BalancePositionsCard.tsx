import React, { useCallback, useState, useMemo } from 'react';
import { Upload, FileSpreadsheet, Eye, RefreshCw, Download, CheckCircle2, XCircle, ChevronRight, ChevronDown, FlaskConical, CalendarIcon, DollarSign } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Calendar } from '@/components/ui/calendar';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import type { Position } from '@/types/financial';
import { parsePositionsCSV, generateSamplePositionsCSV } from '@/lib/csvParser';
import { WhatIfBuilder } from '@/components/whatif/WhatIfBuilder';
import { useWhatIf } from '@/components/whatif/WhatIfContext';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';

interface BalancePositionsCardProps {
  positions: Position[];
  onPositionsChange: (positions: Position[]) => void;
}

// Static placeholder data for the aggregated view
const PLACEHOLDER_DATA = {
  assets: {
    amount: 2_450_000_000,
    positions: 72,
    avgRate: 0.0425,
    subcategories: [
      { id: 'mortgages', name: 'Mortgages', amount: 1_200_000_000, positions: 34, avgRate: 0.0385 },
      { id: 'bonds', name: 'Bonds', amount: 850_000_000, positions: 22, avgRate: 0.0465 },
      { id: 'loans', name: 'Loans', amount: 400_000_000, positions: 16, avgRate: 0.0510 },
    ],
  },
  liabilities: {
    amount: 2_280_000_000,
    positions: 52,
    avgRate: 0.0285,
    subcategories: [
      { id: 'sight-deposits', name: 'Sight Deposits', amount: 680_000_000, positions: 18, avgRate: 0.0050 },
      { id: 'term-deposits', name: 'Term Deposits', amount: 920_000_000, positions: 24, avgRate: 0.0320 },
      { id: 'wholesale-funding', name: 'Wholesale Funding', amount: 680_000_000, positions: 10, avgRate: 0.0425 },
    ],
  },
};

// Helper to compute What-If deltas per category
function computeWhatIfDeltas(modifications: any[]) {
  const deltas: Record<string, { amount: number; positions: number; rate: number; items: any[] }> = {
    assets: { amount: 0, positions: 0, rate: 0, items: [] },
    liabilities: { amount: 0, positions: 0, rate: 0, items: [] },
    mortgages: { amount: 0, positions: 0, rate: 0, items: [] },
    bonds: { amount: 0, positions: 0, rate: 0, items: [] },
    loans: { amount: 0, positions: 0, rate: 0, items: [] },
    'sight-deposits': { amount: 0, positions: 0, rate: 0, items: [] },
    'term-deposits': { amount: 0, positions: 0, rate: 0, items: [] },
    'wholesale-funding': { amount: 0, positions: 0, rate: 0, items: [] },
  };

  modifications.forEach(mod => {
    const multiplier = mod.type === 'add' ? 1 : -1;
    const notional = (mod.notional || 0) * multiplier;
    const posCount = multiplier;
    const rate = (mod.rate || 0) * multiplier;

    // Determine parent category
    const category = mod.category === 'asset' ? 'assets' : mod.category === 'liability' ? 'liabilities' : null;
    
    if (category) {
      deltas[category].amount += notional;
      deltas[category].positions += posCount;
      deltas[category].rate += rate;
      deltas[category].items.push(mod);
    }

    // Subcategory
    if (mod.subcategory && deltas[mod.subcategory]) {
      deltas[mod.subcategory].amount += notional;
      deltas[mod.subcategory].positions += posCount;
      deltas[mod.subcategory].rate += rate;
      deltas[mod.subcategory].items.push(mod);
    }
  });

  return deltas;
}

export function BalancePositionsCard({ positions, onPositionsChange }: BalancePositionsCardProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set(['assets', 'liabilities']));
  const [showWhatIfBuilder, setShowWhatIfBuilder] = useState(false);
  const { modifications, isApplied, analysisDate, setAnalysisDate, cet1Capital, setCet1Capital, resetAll } = useWhatIf();
  
  // Compute What-If deltas
  const whatIfDeltas = useMemo(() => computeWhatIfDeltas(modifications), [modifications]);

  const handleFileUpload = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        const parsed = parsePositionsCSV(content);
        onPositionsChange(parsed);
        setFileName(file.name);
      };
      reader.readAsText(file);
    },
    [onPositionsChange]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith('.csv')) {
        handleFileUpload(file);
      }
    },
    [handleFileUpload]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFileUpload(file);
      }
    },
    [handleFileUpload]
  );

  const handleDownloadSample = useCallback(() => {
    const content = generateSamplePositionsCSV();
    const blob = new Blob([content], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sample_positions.csv';
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const handleReplace = useCallback(() => {
    onPositionsChange([]);
    setFileName(null);
    setExpandedRows(new Set());
  }, [onPositionsChange]);

  const toggleRow = (rowId: string) => {
    setExpandedRows(prev => {
      const next = new Set(prev);
      if (next.has(rowId)) {
        next.delete(rowId);
      } else {
        next.add(rowId);
      }
      return next;
    });
  };

  const formatAmount = (num: number) => {
    if (num >= 1e9) return `${(num / 1e9).toFixed(2)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(0)}M`;
    if (num >= 1e3) return `${(num / 1e3).toFixed(0)}K`;
    return num.toString();
  };

  const formatPercent = (num: number) => (num * 100).toFixed(2) + '%';

  const formatCurrency = (num: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  };

  const isLoaded = positions.length > 0;

  return (
    <>
      <div className="dashboard-card">
        <div className="dashboard-card-header">
          <div className="flex items-center gap-1.5">
            <FileSpreadsheet className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">Balance Positions</span>
          </div>
          <StatusIndicator loaded={isLoaded} />
        </div>

        <div className="dashboard-card-content">
          {!isLoaded ? (
            <div
              className={`compact-upload-zone ${isDragging ? 'active' : ''}`}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
            >
              <Upload className="h-5 w-5 text-muted-foreground mb-1" />
              <p className="text-xs text-muted-foreground mb-2">Drop CSV or click to upload</p>
              <div className="flex gap-1.5">
                <label>
                  <Input
                    type="file"
                    accept=".csv"
                    className="hidden"
                    onChange={handleInputChange}
                  />
                  <Button variant="outline" size="sm" asChild className="h-6 text-xs px-2">
                    <span>Browse</span>
                  </Button>
                </label>
                <Button variant="ghost" size="sm" onClick={handleDownloadSample} className="h-6 text-xs px-2">
                  <Download className="mr-1 h-3 w-3" />
                  Sample
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col flex-1 min-h-0">
              {/* Analysis Date & CET1 Inputs */}
              <div className="flex gap-2 mb-2 pb-2 border-b border-border/30">
                {/* Analysis Date Picker */}
                <div className="flex-1">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        size="sm"
                        className={cn(
                          "h-7 w-full justify-start text-left text-xs font-normal",
                          !analysisDate && "text-muted-foreground"
                        )}
                      >
                        <CalendarIcon className="mr-1.5 h-3 w-3" />
                        {analysisDate ? format(analysisDate, "dd MMM yyyy") : "Analysis Date"}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar
                        mode="single"
                        selected={analysisDate || undefined}
                        onSelect={(date) => setAnalysisDate(date || null)}
                        initialFocus
                        className="p-3 pointer-events-auto"
                      />
                    </PopoverContent>
                  </Popover>
                </div>
                
                {/* CET1 Capital Input */}
                <div className="flex-1">
                  <div className="relative">
                    <DollarSign className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
                    <Input
                      type="number"
                      placeholder="CET1 Capital"
                      value={cet1Capital ?? ''}
                      onChange={(e) => setCet1Capital(e.target.value ? parseFloat(e.target.value) : null)}
                      className="h-7 text-xs pl-6 pr-2"
                    />
                  </div>
                </div>
              </div>

              {/* Scrollable Balance Table with Sticky Header */}
              <div className="flex-1 min-h-0 overflow-hidden rounded-md border border-border/50">
                <div className="h-full overflow-auto balance-scroll-container">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 z-10 bg-card">
                      <tr className="text-muted-foreground border-b border-border">
                        <th className="text-left font-medium py-1.5 pl-2 bg-muted/50">Category</th>
                        <th className="text-right font-medium py-1.5 bg-muted/50">Amount</th>
                        <th className="text-right font-medium py-1.5 bg-muted/50">Pos.</th>
                        <th className="text-right font-medium py-1.5 pr-2 bg-muted/50">Avg Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Assets Row */}
                      <BalanceRowWithDelta
                        id="assets"
                        label="Assets"
                        amount={PLACEHOLDER_DATA.assets.amount}
                        positions={PLACEHOLDER_DATA.assets.positions}
                        avgRate={PLACEHOLDER_DATA.assets.avgRate}
                        delta={whatIfDeltas.assets}
                        isExpanded={expandedRows.has('assets')}
                        onToggle={() => toggleRow('assets')}
                        formatAmount={formatAmount}
                        formatPercent={formatPercent}
                        variant="asset"
                      />
                      {expandedRows.has('assets') && PLACEHOLDER_DATA.assets.subcategories.map((sub) => (
                        <React.Fragment key={`asset-${sub.id}`}>
                          <SubcategoryRowWithDelta
                            id={sub.id}
                            label={sub.name}
                            amount={sub.amount}
                            positions={sub.positions}
                            avgRate={sub.avgRate}
                            delta={whatIfDeltas[sub.id]}
                            formatAmount={formatAmount}
                            formatPercent={formatPercent}
                          />
                          {/* Render What-If items under this subcategory */}
                          {whatIfDeltas[sub.id]?.items.map((mod: any) => (
                            <WhatIfItemRow
                              key={mod.id}
                              label={mod.label}
                              amount={mod.notional || 0}
                              type={mod.type}
                              formatAmount={formatAmount}
                            />
                          ))}
                        </React.Fragment>
                      ))}
                      
                      {/* Liabilities Row */}
                      <BalanceRowWithDelta
                        id="liabilities"
                        label="Liabilities"
                        amount={PLACEHOLDER_DATA.liabilities.amount}
                        positions={PLACEHOLDER_DATA.liabilities.positions}
                        avgRate={PLACEHOLDER_DATA.liabilities.avgRate}
                        delta={whatIfDeltas.liabilities}
                        isExpanded={expandedRows.has('liabilities')}
                        onToggle={() => toggleRow('liabilities')}
                        formatAmount={formatAmount}
                        formatPercent={formatPercent}
                        variant="liability"
                      />
                      {expandedRows.has('liabilities') && PLACEHOLDER_DATA.liabilities.subcategories.map((sub) => (
                        <React.Fragment key={`liability-${sub.id}`}>
                          <SubcategoryRowWithDelta
                            id={sub.id}
                            label={sub.name}
                            amount={sub.amount}
                            positions={sub.positions}
                            avgRate={sub.avgRate}
                            delta={whatIfDeltas[sub.id]}
                            formatAmount={formatAmount}
                            formatPercent={formatPercent}
                          />
                          {/* Render What-If items under this subcategory */}
                          {whatIfDeltas[sub.id]?.items.map((mod: any) => (
                            <WhatIfItemRow
                              key={mod.id}
                              label={mod.label}
                              amount={mod.notional || 0}
                              type={mod.type}
                              formatAmount={formatAmount}
                            />
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              
              {/* Action Buttons */}
              <div className="flex gap-1.5 pt-2 border-t border-border/30 mt-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowDetails(true)}
                  className="flex-1 h-6 text-xs"
                >
                  <Eye className="mr-1 h-3 w-3" />
                  View details
                </Button>
                <Button
                  size="sm"
                  onClick={() => setShowWhatIfBuilder(true)}
                  className="flex-1 h-6 text-xs relative"
                >
                  <FlaskConical className="mr-1 h-3 w-3" />
                  What-If
                  {modifications.length > 0 && (
                    <span className={`absolute -top-1 -right-1 h-3.5 min-w-[14px] rounded-full text-[9px] font-bold flex items-center justify-center px-1 ${
                      isApplied ? 'bg-success text-success-foreground' : 'bg-warning text-warning-foreground'
                    }`}>
                      {modifications.length}
                    </span>
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    resetAll();
                    handleReplace();
                  }}
                  className="h-6 text-xs px-2"
                  title="Reset all"
                >
                  <RefreshCw className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Details Modal - Now shows expanded aggregated view */}
      <Dialog open={showDetails} onOpenChange={setShowDetails}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <FileSpreadsheet className="h-4 w-4 text-primary" />
              Balance Positions - Aggregated View
            </DialogTitle>
          </DialogHeader>
          <div className="overflow-auto flex-1">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-card z-10">
                <tr className="text-muted-foreground border-b border-border">
                  <th className="text-left font-medium py-2 pl-3 bg-muted/50">Category</th>
                  <th className="text-right font-medium py-2 bg-muted/50">Amount</th>
                  <th className="text-right font-medium py-2 bg-muted/50">Positions</th>
                  <th className="text-right font-medium py-2 pr-3 bg-muted/50">Avg Rate</th>
                </tr>
              </thead>
              <tbody>
                {/* Assets - Always expanded in details */}
                <tr className="border-b border-border bg-success/5">
                  <td className="py-2 pl-3">
                    <span className="font-semibold text-success">Assets</span>
                  </td>
                  <td className="text-right py-2 font-mono font-semibold text-foreground">
                    {formatCurrency(PLACEHOLDER_DATA.assets.amount)}
                  </td>
                  <td className="text-right py-2 font-mono text-muted-foreground">
                    {PLACEHOLDER_DATA.assets.positions}
                  </td>
                  <td className="text-right py-2 pr-3 font-mono text-muted-foreground">
                    {formatPercent(PLACEHOLDER_DATA.assets.avgRate)}
                  </td>
                </tr>
                {PLACEHOLDER_DATA.assets.subcategories.map((sub, idx) => (
                  <tr key={`modal-asset-${idx}`} className="border-b border-border/50">
                    <td className="py-1.5 pl-8">
                      <span className="text-muted-foreground">{sub.name}</span>
                    </td>
                    <td className="text-right py-1.5 font-mono text-sm">
                      {formatCurrency(sub.amount)}
                    </td>
                    <td className="text-right py-1.5 font-mono text-muted-foreground">
                      {sub.positions}
                    </td>
                    <td className="text-right py-1.5 pr-3 font-mono text-muted-foreground">
                      {formatPercent(sub.avgRate)}
                    </td>
                  </tr>
                ))}
                
                {/* Liabilities - Always expanded in details */}
                <tr className="border-b border-border bg-destructive/5 mt-2">
                  <td className="py-2 pl-3">
                    <span className="font-semibold text-destructive">Liabilities</span>
                  </td>
                  <td className="text-right py-2 font-mono font-semibold text-foreground">
                    {formatCurrency(PLACEHOLDER_DATA.liabilities.amount)}
                  </td>
                  <td className="text-right py-2 font-mono text-muted-foreground">
                    {PLACEHOLDER_DATA.liabilities.positions}
                  </td>
                  <td className="text-right py-2 pr-3 font-mono text-muted-foreground">
                    {formatPercent(PLACEHOLDER_DATA.liabilities.avgRate)}
                  </td>
                </tr>
                {PLACEHOLDER_DATA.liabilities.subcategories.map((sub, idx) => (
                  <tr key={`modal-liability-${idx}`} className="border-b border-border/50">
                    <td className="py-1.5 pl-8">
                      <span className="text-muted-foreground">{sub.name}</span>
                    </td>
                    <td className="text-right py-1.5 font-mono text-sm">
                      {formatCurrency(sub.amount)}
                    </td>
                    <td className="text-right py-1.5 font-mono text-muted-foreground">
                      {sub.positions}
                    </td>
                    <td className="text-right py-1.5 pr-3 font-mono text-muted-foreground">
                      {formatPercent(sub.avgRate)}
                    </td>
                  </tr>
                ))}

                {/* Net Position Summary */}
                <tr className="border-t-2 border-border bg-muted/30">
                  <td className="py-2 pl-3">
                    <span className="font-semibold text-foreground">Net Position</span>
                  </td>
                  <td className="text-right py-2 font-mono font-bold text-foreground">
                    {formatCurrency(PLACEHOLDER_DATA.assets.amount - PLACEHOLDER_DATA.liabilities.amount)}
                  </td>
                  <td className="text-right py-2 font-mono text-muted-foreground">
                    {PLACEHOLDER_DATA.assets.positions + PLACEHOLDER_DATA.liabilities.positions}
                  </td>
                  <td className="text-right py-2 pr-3 font-mono text-muted-foreground">
                    —
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-muted-foreground text-center pt-2 border-t border-border/30">
            This aggregated view summarizes underlying position-level data
          </p>
        </DialogContent>
      </Dialog>

      {/* What-If Builder Side Panel */}
      <WhatIfBuilder open={showWhatIfBuilder} onOpenChange={setShowWhatIfBuilder} />
    </>
  );
}

// Status Indicator Component
function StatusIndicator({ loaded }: { loaded: boolean }) {
  return loaded ? (
    <div className="flex items-center gap-1 text-success">
      <CheckCircle2 className="h-3 w-3" />
      <span className="text-[10px] font-medium">Loaded</span>
    </div>
  ) : (
    <div className="flex items-center gap-1 text-muted-foreground">
      <XCircle className="h-3 w-3" />
      <span className="text-[10px] font-medium">Not loaded</span>
    </div>
  );
}

// Balance Row Component with What-If delta display
interface BalanceRowWithDeltaProps {
  id: string;
  label: string;
  amount: number;
  positions: number;
  avgRate: number;
  delta: { amount: number; positions: number; rate: number; items: any[] };
  isExpanded: boolean;
  onToggle: () => void;
  formatAmount: (n: number) => string;
  formatPercent: (n: number) => string;
  variant: 'asset' | 'liability';
}

function BalanceRowWithDelta({
  label,
  amount,
  positions,
  avgRate,
  delta,
  isExpanded,
  onToggle,
  formatAmount,
  formatPercent,
  variant,
}: BalanceRowWithDeltaProps) {
  const ChevronIcon = isExpanded ? ChevronDown : ChevronRight;
  const labelColor = variant === 'asset' ? 'text-success' : 'text-destructive';
  const hasDelta = delta.amount !== 0 || delta.positions !== 0;
  
  const formatDelta = (n: number) => {
    if (n === 0) return '';
    const sign = n > 0 ? '+' : '';
    if (Math.abs(n) >= 1e9) return `${sign}${(n / 1e9).toFixed(1)}B`;
    if (Math.abs(n) >= 1e6) return `${sign}${(n / 1e6).toFixed(0)}M`;
    if (Math.abs(n) >= 1e3) return `${sign}${(n / 1e3).toFixed(0)}K`;
    return `${sign}${n}`;
  };
  
  return (
    <tr 
      className="group cursor-pointer hover:bg-muted/30 transition-colors border-b border-border/30"
      onClick={onToggle}
    >
      <td className="py-1.5 pl-2">
        <div className="flex items-center gap-1">
          <ChevronIcon className="h-3 w-3 text-muted-foreground group-hover:text-foreground transition-colors" />
          <span className={`font-semibold ${labelColor}`}>{label}</span>
        </div>
      </td>
      <td className="text-right py-1.5 font-mono font-medium text-foreground">
        {formatAmount(amount)}
        {hasDelta && delta.amount !== 0 && (
          <span className={`ml-1 text-[9px] ${delta.amount > 0 ? 'text-success' : 'text-destructive'}`}>
            ({formatDelta(delta.amount)})
          </span>
        )}
      </td>
      <td className="text-right py-1.5 font-mono text-muted-foreground">
        {positions}
        {hasDelta && delta.positions !== 0 && (
          <span className={`ml-1 text-[9px] ${delta.positions > 0 ? 'text-success' : 'text-destructive'}`}>
            ({delta.positions > 0 ? '+' : ''}{delta.positions})
          </span>
        )}
      </td>
      <td className="text-right py-1.5 pr-2 font-mono text-muted-foreground">
        {formatPercent(avgRate)}
        {hasDelta && delta.rate !== 0 && (
          <span className={`ml-1 text-[9px] ${delta.rate > 0 ? 'text-success' : 'text-destructive'}`}>
            ({delta.rate > 0 ? '+' : ''}{(delta.rate * 100).toFixed(2)}%)
          </span>
        )}
      </td>
    </tr>
  );
}

// Subcategory Row Component with What-If delta display
interface SubcategoryRowWithDeltaProps {
  id: string;
  label: string;
  amount: number;
  positions: number;
  avgRate: number;
  delta?: { amount: number; positions: number; rate: number; items: any[] };
  formatAmount: (n: number) => string;
  formatPercent: (n: number) => string;
}

function SubcategoryRowWithDelta({
  label,
  amount,
  positions,
  avgRate,
  delta,
  formatAmount,
  formatPercent,
}: SubcategoryRowWithDeltaProps) {
  const hasDelta = delta && (delta.amount !== 0 || delta.positions !== 0);
  
  const formatDelta = (n: number) => {
    if (n === 0) return '';
    const sign = n > 0 ? '+' : '';
    if (Math.abs(n) >= 1e9) return `${sign}${(n / 1e9).toFixed(1)}B`;
    if (Math.abs(n) >= 1e6) return `${sign}${(n / 1e6).toFixed(0)}M`;
    if (Math.abs(n) >= 1e3) return `${sign}${(n / 1e3).toFixed(0)}K`;
    return `${sign}${n}`;
  };

  return (
    <tr className="bg-muted/20 text-muted-foreground">
      <td className="py-1 pl-7">
        <span className="text-[11px]">{label}</span>
      </td>
      <td className="text-right py-1 font-mono text-[11px]">
        {formatAmount(amount)}
        {hasDelta && delta.amount !== 0 && (
          <span className={`ml-1 text-[9px] ${delta.amount > 0 ? 'text-success' : 'text-destructive'}`}>
            ({formatDelta(delta.amount)})
          </span>
        )}
      </td>
      <td className="text-right py-1 font-mono text-[11px]">
        {positions}
        {hasDelta && delta.positions !== 0 && (
          <span className={`ml-1 text-[9px] ${delta.positions > 0 ? 'text-success' : 'text-destructive'}`}>
            ({delta.positions > 0 ? '+' : ''}{delta.positions})
          </span>
        )}
      </td>
      <td className="text-right py-1 pr-2 font-mono text-[11px]">
        {formatPercent(avgRate)}
        {hasDelta && delta.rate !== 0 && (
          <span className={`ml-1 text-[9px] ${delta.rate > 0 ? 'text-success' : 'text-destructive'}`}>
            ({delta.rate > 0 ? '+' : ''}{(delta.rate * 100).toFixed(2)}%)
          </span>
        )}
      </td>
    </tr>
  );
}

// What-If Item Row (shows individual What-If positions)
interface WhatIfItemRowProps {
  label: string;
  amount: number;
  type: 'add' | 'remove';
  formatAmount: (n: number) => string;
}

function WhatIfItemRow({ label, amount, type, formatAmount }: WhatIfItemRowProps) {
  const isAdd = type === 'add';
  return (
    <tr className={`${isAdd ? 'bg-success/10' : 'bg-destructive/10'}`}>
      <td className="py-0.5 pl-10">
        <span className={`text-[10px] font-medium ${isAdd ? 'text-success' : 'text-destructive'}`}>
          {isAdd ? '+ ' : '− '}{label}
          <span className="ml-1 text-[8px] opacity-70">(What-If)</span>
        </span>
      </td>
      <td className={`text-right py-0.5 font-mono text-[10px] ${isAdd ? 'text-success' : 'text-destructive'}`}>
        {isAdd ? '+' : '−'}{formatAmount(Math.abs(amount))}
      </td>
      <td className={`text-right py-0.5 font-mono text-[10px] ${isAdd ? 'text-success' : 'text-destructive'}`}>
        {isAdd ? '+1' : '−1'}
      </td>
      <td className="text-right py-0.5 pr-2 font-mono text-[10px] text-muted-foreground">
        —
      </td>
    </tr>
  );
}
