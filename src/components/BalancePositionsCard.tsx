import React, { useCallback, useState, useMemo, useRef, useEffect } from 'react';
import { Upload, FileSpreadsheet, Eye, RefreshCw, Download, CheckCircle2, XCircle, ChevronRight, ChevronDown, FlaskConical, CalendarIcon, Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Calendar } from '@/components/ui/calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import type { Position } from '@/types/financial';
import { parsePositionsCSV, generateSamplePositionsCSV } from '@/lib/csvParser';
import { WhatIfBuilder } from '@/components/whatif/WhatIfBuilder';
import { useWhatIf } from '@/components/whatif/WhatIfContext';
import { BalanceDetailsModal } from '@/components/BalanceDetailsModal';
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
      { id: 'loans', name: 'Loans', amount: 400_000_000, positions: 16, avgRate: 0.0510 },
      { id: 'securities', name: 'Securities', amount: 550_000_000, positions: 12, avgRate: 0.0465 },
      { id: 'interbank', name: 'Interbank / Central Bank', amount: 200_000_000, positions: 6, avgRate: 0.0380 },
      { id: 'other-assets', name: 'Other assets', amount: 100_000_000, positions: 4, avgRate: 0.0350 },
    ],
  },
  liabilities: {
    amount: 2_280_000_000,
    positions: 52,
    avgRate: 0.0285,
    subcategories: [
      { id: 'deposits', name: 'Deposits', amount: 680_000_000, positions: 18, avgRate: 0.0050 },
      { id: 'term-deposits', name: 'Term deposits', amount: 920_000_000, positions: 24, avgRate: 0.0320 },
      { id: 'wholesale-funding', name: 'Wholesale funding', amount: 480_000_000, positions: 6, avgRate: 0.0425 },
      { id: 'debt-issued', name: 'Debt issued', amount: 150_000_000, positions: 3, avgRate: 0.0480 },
      { id: 'other-liabilities', name: 'Other liabilities', amount: 50_000_000, positions: 1, avgRate: 0.0300 },
    ],
  },
};

// Helper to compute What-If deltas per category
function computeWhatIfDeltas(modifications: any[]) {
  const deltas: Record<string, { amount: number; positions: number; rate: number; items: any[] }> = {
    assets: { amount: 0, positions: 0, rate: 0, items: [] },
    liabilities: { amount: 0, positions: 0, rate: 0, items: [] },
    mortgages: { amount: 0, positions: 0, rate: 0, items: [] },
    loans: { amount: 0, positions: 0, rate: 0, items: [] },
    securities: { amount: 0, positions: 0, rate: 0, items: [] },
    interbank: { amount: 0, positions: 0, rate: 0, items: [] },
    'other-assets': { amount: 0, positions: 0, rate: 0, items: [] },
    deposits: { amount: 0, positions: 0, rate: 0, items: [] },
    'term-deposits': { amount: 0, positions: 0, rate: 0, items: [] },
    'wholesale-funding': { amount: 0, positions: 0, rate: 0, items: [] },
    'debt-issued': { amount: 0, positions: 0, rate: 0, items: [] },
    'other-liabilities': { amount: 0, positions: 0, rate: 0, items: [] },
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
  const [selectedCategoryForDetails, setSelectedCategoryForDetails] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set(['assets', 'liabilities']));
  const [showWhatIfBuilder, setShowWhatIfBuilder] = useState(false);
  const { modifications, isApplied, analysisDate, setAnalysisDate, cet1Capital, setCet1Capital, resetAll } = useWhatIf();
  
  // Compute What-If deltas
  const whatIfDeltas = useMemo(() => computeWhatIfDeltas(modifications), [modifications]);

  // Open View Details with optional category context
  const openDetails = (categoryId?: string) => {
    setSelectedCategoryForDetails(categoryId || null);
    setShowDetails(true);
  };

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
              {/* Analysis Date & CET1 Inputs - Consistent visual design */}
              <div className="flex gap-3 mb-2 pb-2 border-b border-border/30">
                {/* Analysis Date */}
                <AnalysisParameter
                  label="Analysis Date"
                  icon={<CalendarIcon className="h-3 w-3 text-muted-foreground" />}
                >
                  <Popover>
                    <PopoverTrigger asChild>
                      <button
                        className={cn(
                          "h-7 px-2 flex items-center gap-1.5 rounded border text-xs transition-colors",
                          "bg-background border-border hover:bg-muted/50",
                          !analysisDate && "text-muted-foreground"
                        )}
                      >
                        <CalendarIcon className="h-3 w-3" />
                        <span className={analysisDate ? "font-medium text-foreground" : ""}>
                          {analysisDate ? format(analysisDate, "dd MMM yyyy") : "Select date"}
                        </span>
                      </button>
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
                </AnalysisParameter>
                
                {/* CET1 Capital */}
                <CET1Input
                  value={cet1Capital}
                  onChange={setCet1Capital}
                />
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
                  onClick={() => openDetails()}
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

      {/* Balance Details Modal - Read-only aggregation explorer */}
      <BalanceDetailsModal 
        open={showDetails} 
        onOpenChange={setShowDetails}
        selectedCategory={selectedCategoryForDetails}
      />

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

// Analysis Parameter wrapper for consistent styling
interface AnalysisParameterProps {
  label: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

function AnalysisParameter({ label, children }: AnalysisParameterProps) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-medium text-muted-foreground whitespace-nowrap">
        {label}
      </span>
      {children}
    </div>
  );
}

// CET1 Capital Input - Two-state component (editable → locked)
interface CET1InputProps {
  value: number | null;
  onChange: (value: number | null) => void;
}

function CET1Input({ value, onChange }: CET1InputProps) {
  const [isEditing, setIsEditing] = useState(value === null);
  const [inputValue, setInputValue] = useState(value?.toString() || '');
  const inputRef = useRef<HTMLInputElement>(null);
  
  // Sync internal state when external value changes (e.g., reset)
  useEffect(() => {
    if (value === null) {
      setIsEditing(true);
      setInputValue('');
    } else {
      setInputValue(value.toString());
    }
  }, [value]);
  
  // Focus input when entering edit mode
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isEditing]);

  const formatCET1Display = (num: number) => {
    // Just format with commas, no suffix
    return num.toLocaleString('en-US');
  };

  const handleConfirm = () => {
    const parsed = parseFloat(inputValue);
    if (!isNaN(parsed) && parsed > 0) {
      onChange(parsed);
      setIsEditing(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleConfirm();
    } else if (e.key === 'Escape') {
      if (value !== null) {
        setInputValue(value.toString());
        setIsEditing(false);
      }
    }
  };

  const handleEditClick = () => {
    setIsEditing(true);
  };

  // Consistent wrapper with label
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-medium text-muted-foreground whitespace-nowrap">
        CET1
      </span>
      {isEditing ? (
        <div className="flex flex-col">
          <input
            ref={inputRef}
            type="text"
            inputMode="numeric"
            placeholder="Enter value"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value.replace(/[^0-9.]/g, ''))}
            onKeyDown={handleKeyDown}
            onBlur={() => {
              if (inputValue && value !== null && inputValue === value.toString()) {
                setIsEditing(false);
              } else if (inputValue) {
                handleConfirm();
              }
            }}
            className={cn(
              "h-7 px-2 w-28 rounded border text-xs font-mono",
              "bg-background border-border focus:outline-none focus:ring-1 focus:ring-primary",
              "placeholder:text-muted-foreground"
            )}
          />
          <span className="text-[8px] text-muted-foreground mt-0.5">Enter to confirm</span>
        </div>
      ) : (
        <button
          onClick={handleEditClick}
          className={cn(
            "h-7 px-2 flex items-center gap-1.5 rounded border text-xs transition-colors group",
            "bg-muted/30 border-border/70 hover:bg-muted/50"
          )}
          title="Click to edit"
        >
          <span className="font-mono font-medium text-foreground">{formatCET1Display(value!)}</span>
          <Pencil className="h-2.5 w-2.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
      )}
    </div>
  );
}
