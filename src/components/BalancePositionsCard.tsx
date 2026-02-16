import React, { useCallback, useState, useMemo, useRef, useEffect } from 'react';
import { Upload, FileSpreadsheet, Eye, RotateCcw, Download, CheckCircle2, XCircle, ChevronRight, ChevronDown, SlidersHorizontal, CalendarIcon, Pencil, Brain } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { Position } from '@/types/financial';
import type { BalanceSummaryTree } from '@/lib/api';
import { parsePositionsCSV, generateSamplePositionsCSV } from '@/lib/csvParser';
import { WhatIfBuilder } from '@/components/whatif/WhatIfBuilder';
import { useWhatIf } from '@/components/whatif/WhatIfContext';
import { BalanceDetailsModal } from '@/components/BalanceDetailsModal';
import { BehaviouralAssumptionsModal } from '@/components/behavioural/BehaviouralAssumptionsModal';
import { useBehavioural } from '@/components/behavioural/BehaviouralContext';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';
import { mapSummaryTreeToUiTree, type BalanceUiTree } from '@/lib/balanceUi';
import type { WhatIfModification } from '@/types/whatif';

interface BalancePositionsCardProps {
  positions: Position[];
  onPositionsChange: (positions: Position[]) => void;
  sessionId?: string | null;
  summaryTree?: BalanceSummaryTree | null;
}

type WhatIfDelta = {
  netAmount: number;
  netPositions: number;
  addedAmount: number;
  removedAmount: number;
  addedPositions: number;
  removedPositions: number;
  addedRateWeighted: number;
  removedRateWeighted: number;
  addedRateWeight: number;
  removedRateWeight: number;
  addedMaturityWeighted: number;
  removedMaturityWeighted: number;
  addedMaturityWeight: number;
  removedMaturityWeight: number;
  items: WhatIfModification[];
};

function emptyDelta(): WhatIfDelta {
  return {
    netAmount: 0,
    netPositions: 0,
    addedAmount: 0,
    removedAmount: 0,
    addedPositions: 0,
    removedPositions: 0,
    addedRateWeighted: 0,
    removedRateWeighted: 0,
    addedRateWeight: 0,
    removedRateWeight: 0,
    addedMaturityWeighted: 0,
    removedMaturityWeighted: 0,
    addedMaturityWeight: 0,
    removedMaturityWeight: 0,
    items: [],
  };
}

function weightedRateAccumulator(sumRate: number, sumAmount: number): number | null {
  if (sumAmount === 0) return null;
  return sumRate / sumAmount;
}

function weightedMaturityAccumulator(sumMaturity: number, sumAmount: number): number {
  if (sumAmount === 0) return 0;
  return sumMaturity / sumAmount;
}

function residualMaturityYearsFromDate(maturityDate: string): number {
  const parsed = new Date(maturityDate);
  if (Number.isNaN(parsed.getTime())) return 0;
  const now = Date.now();
  const years = (parsed.getTime() - now) / (365.25 * 24 * 60 * 60 * 1000);
  if (!Number.isFinite(years) || years < 0) return 0;
  return years;
}

function mapPositionsToUiTree(positions: Position[]): BalanceUiTree {
  const seed = mapSummaryTreeToUiTree(null);
  if (positions.length === 0) return seed;

  type Bucket = {
    amount: number;
    positions: number;
    weightedRate: number;
    weight: number;
    weightedMaturity: number;
    maturityWeight: number;
  };

  const grouped = new Map<string, Bucket>();
  const categoryTotals: Record<'assets' | 'liabilities', Bucket> = {
    assets: { amount: 0, positions: 0, weightedRate: 0, weight: 0, weightedMaturity: 0, maturityWeight: 0 },
    liabilities: { amount: 0, positions: 0, weightedRate: 0, weight: 0, weightedMaturity: 0, maturityWeight: 0 },
  };

  positions.forEach((position) => {
    const category = position.instrumentType === 'Liability' ? 'liabilities' : 'assets';
    const amount = Number(position.notional) || 0;
    const rate = Number(position.couponRate) || 0;
    const weight = Math.abs(amount);
    const maturityYears = residualMaturityYearsFromDate(position.maturityDate);
    const subId = position.description
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'uploaded';
    const subName = position.description || 'Uploaded positions';
    const key = `${category}:${subId}:${subName}`;

    const existing = grouped.get(key) ?? {
      amount: 0,
      positions: 0,
      weightedRate: 0,
      weight: 0,
      weightedMaturity: 0,
      maturityWeight: 0,
    };
    existing.amount += amount;
    existing.positions += 1;
    existing.weightedRate += rate * weight;
    existing.weight += weight;
    existing.weightedMaturity += maturityYears * weight;
    existing.maturityWeight += weight;
    grouped.set(key, existing);

    categoryTotals[category].amount += amount;
    categoryTotals[category].positions += 1;
    categoryTotals[category].weightedRate += rate * weight;
    categoryTotals[category].weight += weight;
    categoryTotals[category].weightedMaturity += maturityYears * weight;
    categoryTotals[category].maturityWeight += weight;
  });

  const assetsSubcategories = Array.from(grouped.entries())
    .filter(([key]) => key.startsWith('assets:'))
    .map(([key, bucket]) => {
      const [, id, ...nameParts] = key.split(':');
      const name = nameParts.join(':');
      return {
        id,
        name,
        amount: bucket.amount,
        positions: bucket.positions,
        avgRate: weightedRateAccumulator(bucket.weightedRate, bucket.weight),
        avgMaturity: weightedMaturityAccumulator(bucket.weightedMaturity, bucket.maturityWeight),
      };
    });

  const liabilitiesSubcategories = Array.from(grouped.entries())
    .filter(([key]) => key.startsWith('liabilities:'))
    .map(([key, bucket]) => {
      const [, id, ...nameParts] = key.split(':');
      const name = nameParts.join(':');
      return {
        id,
        name,
        amount: bucket.amount,
        positions: bucket.positions,
        avgRate: weightedRateAccumulator(bucket.weightedRate, bucket.weight),
        avgMaturity: weightedMaturityAccumulator(bucket.weightedMaturity, bucket.maturityWeight),
      };
    });

  return {
    assets: {
      id: 'assets',
      name: 'Assets',
      amount: categoryTotals.assets.amount,
      positions: categoryTotals.assets.positions,
      avgRate: weightedRateAccumulator(categoryTotals.assets.weightedRate, categoryTotals.assets.weight),
      avgMaturity: weightedMaturityAccumulator(
        categoryTotals.assets.weightedMaturity,
        categoryTotals.assets.maturityWeight
      ),
      subcategories: assetsSubcategories.sort((a, b) => b.amount - a.amount),
    },
    liabilities: {
      id: 'liabilities',
      name: 'Liabilities',
      amount: categoryTotals.liabilities.amount,
      positions: categoryTotals.liabilities.positions,
      avgRate: weightedRateAccumulator(
        categoryTotals.liabilities.weightedRate,
        categoryTotals.liabilities.weight
      ),
      avgMaturity: weightedMaturityAccumulator(
        categoryTotals.liabilities.weightedMaturity,
        categoryTotals.liabilities.maturityWeight
      ),
      subcategories: liabilitiesSubcategories.sort((a, b) => b.amount - a.amount),
    },
  };
}

function computeWhatIfDeltas(modifications: WhatIfModification[], balanceTree: BalanceUiTree) {
  const deltas: Record<string, WhatIfDelta> = {};
  const ensure = (id: string) => {
    if (!deltas[id]) deltas[id] = emptyDelta();
  };

  ensure('assets');
  ensure('liabilities');
  balanceTree.assets.subcategories.forEach((sub) => ensure(sub.id));
  balanceTree.liabilities.subcategories.forEach((sub) => ensure(sub.id));

  modifications.forEach((mod) => {
    const notionalAbs = Math.abs(mod.notional ?? 0);
    const positionsAbs = Math.abs(mod.positionDelta ?? 1);
    const hasRate = typeof mod.rate === 'number' && !Number.isNaN(mod.rate);
    const rateValue = hasRate ? (mod.rate as number) : null;
    const maturityValue = typeof mod.maturity === 'number' && !Number.isNaN(mod.maturity) ? mod.maturity : 0;

    const category = mod.category === 'asset' ? 'assets' : mod.category === 'liability' ? 'liabilities' : null;
    if (category) {
      ensure(category);
      if (mod.type === 'add') {
        deltas[category].netAmount += notionalAbs;
        deltas[category].netPositions += positionsAbs;
        deltas[category].addedAmount += notionalAbs;
        deltas[category].addedPositions += positionsAbs;
        if (rateValue !== null) {
          deltas[category].addedRateWeighted += rateValue * notionalAbs;
          deltas[category].addedRateWeight += notionalAbs;
        }
        deltas[category].addedMaturityWeighted += maturityValue * notionalAbs;
        deltas[category].addedMaturityWeight += notionalAbs;
      } else {
        deltas[category].netAmount -= notionalAbs;
        deltas[category].netPositions -= positionsAbs;
        deltas[category].removedAmount += notionalAbs;
        deltas[category].removedPositions += positionsAbs;
        if (rateValue !== null) {
          deltas[category].removedRateWeighted += rateValue * notionalAbs;
          deltas[category].removedRateWeight += notionalAbs;
        }
        deltas[category].removedMaturityWeighted += maturityValue * notionalAbs;
        deltas[category].removedMaturityWeight += notionalAbs;
      }
      deltas[category].items.push(mod);
    }

    if (mod.subcategory) {
      ensure(mod.subcategory);
      if (mod.type === 'add') {
        deltas[mod.subcategory].netAmount += notionalAbs;
        deltas[mod.subcategory].netPositions += positionsAbs;
        deltas[mod.subcategory].addedAmount += notionalAbs;
        deltas[mod.subcategory].addedPositions += positionsAbs;
        if (rateValue !== null) {
          deltas[mod.subcategory].addedRateWeighted += rateValue * notionalAbs;
          deltas[mod.subcategory].addedRateWeight += notionalAbs;
        }
        deltas[mod.subcategory].addedMaturityWeighted += maturityValue * notionalAbs;
        deltas[mod.subcategory].addedMaturityWeight += notionalAbs;
      } else {
        deltas[mod.subcategory].netAmount -= notionalAbs;
        deltas[mod.subcategory].netPositions -= positionsAbs;
        deltas[mod.subcategory].removedAmount += notionalAbs;
        deltas[mod.subcategory].removedPositions += positionsAbs;
        if (rateValue !== null) {
          deltas[mod.subcategory].removedRateWeighted += rateValue * notionalAbs;
          deltas[mod.subcategory].removedRateWeight += notionalAbs;
        }
        deltas[mod.subcategory].removedMaturityWeighted += maturityValue * notionalAbs;
        deltas[mod.subcategory].removedMaturityWeight += notionalAbs;
      }
      deltas[mod.subcategory].items.push(mod);
    }
  });

  return deltas;
}

function computeFinalAvgRate(baseAmount: number, baseAvgRate: number | null, delta: WhatIfDelta): number | null {
  const baseWeight = baseAvgRate === null || Number.isNaN(baseAvgRate) ? 0 : Math.abs(baseAmount);
  const baseWeighted = baseWeight > 0 ? baseWeight * baseAvgRate : 0;

  const finalWeight = baseWeight + delta.addedRateWeight - delta.removedRateWeight;
  if (finalWeight <= 0) return null;

  const finalWeighted =
    baseWeighted +
    delta.addedRateWeighted -
    delta.removedRateWeighted;

  return finalWeighted / finalWeight;
}

function computeFinalAvgMaturity(baseAmount: number, baseAvgMaturity: number | null, delta: WhatIfDelta): number {
  const baseWeight = Math.abs(baseAmount);
  const baseMaturity = baseAvgMaturity ?? 0;
  const baseWeighted = baseWeight * baseMaturity;

  const finalWeight = baseWeight + delta.addedMaturityWeight - delta.removedMaturityWeight;
  if (finalWeight <= 0) return 0;

  const finalWeighted =
    baseWeighted +
    delta.addedMaturityWeighted -
    delta.removedMaturityWeighted;

  return finalWeighted / finalWeight;
}
export function BalancePositionsCard({
  positions,
  onPositionsChange,
  sessionId,
  summaryTree
}: BalancePositionsCardProps) {
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [selectedCategoryForDetails, setSelectedCategoryForDetails] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set(['assets', 'liabilities']));
  const [showWhatIfBuilder, setShowWhatIfBuilder] = useState(false);
  const [showBehaviouralModal, setShowBehaviouralModal] = useState(false);
  const {
    modifications,
    isApplied,
    analysisDate,
    setAnalysisDate,
    cet1Capital,
    setCet1Capital,
    resetAll
  } = useWhatIf();
  const { hasCustomAssumptions } = useBehavioural();

  const balanceTree = useMemo(() => {
    if (summaryTree) return mapSummaryTreeToUiTree(summaryTree);
    return mapPositionsToUiTree(positions);
  }, [positions, summaryTree]);

  // Compute What-If deltas on top of loaded base balance
  const whatIfDeltas = useMemo(
    () => computeWhatIfDeltas(modifications, balanceTree),
    [balanceTree, modifications]
  );

  // Open View Details with optional category context
  const openDetails = (categoryId?: string) => {
    setSelectedCategoryForDetails(categoryId || null);
    setShowDetails(true);
  };
  const handleFileUpload = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = e => {
      const content = e.target?.result as string;
      const parsed = parsePositionsCSV(content);
      onPositionsChange(parsed);
    };
    reader.readAsText(file);
  }, [onPositionsChange]);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith('.csv')) {
      handleFileUpload(file);
    }
  }, [handleFileUpload]);
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);
  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  }, [handleFileUpload]);
  const handleBrowseClick = useCallback(() => {
    uploadInputRef.current?.click();
  }, []);
  const handleDownloadSample = useCallback(() => {
    const content = generateSamplePositionsCSV();
    const blob = new Blob([content], {
      type: 'text/csv'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sample_positions.csv';
    a.click();
    URL.revokeObjectURL(url);
  }, []);
  const handleReplace = useCallback(() => {
    onPositionsChange([]);
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
  const formatPercent = (num: number | null | undefined) => {
    if (num === null || num === undefined || Number.isNaN(num)) return '—';
    return (num * 100).toFixed(2) + '%';
  };
  const formatYears = (num: number | null | undefined) => {
    if (num === null || num === undefined || Number.isNaN(num)) return '0.0Y';
    return `${num.toFixed(1)}Y`;
  };
  const isLoaded =
    balanceTree.assets.positions > 0 ||
    balanceTree.liabilities.positions > 0 ||
    positions.length > 0;
  return <>
      <div className="dashboard-card">
        <div className="dashboard-card-header justify-between">
          {/* Left: Title + Analysis Date & CET1 */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <FileSpreadsheet className="h-3.5 w-3.5 text-primary" />
              <span className="text-xs font-semibold text-foreground">Balance Positions</span>
            </div>
            
            {isLoaded && (
              <div className="flex items-center gap-3">
                {/* Analysis Date - Compact */}
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-medium text-muted-foreground">Analysis Date</span>
                  <Popover>
                    <PopoverTrigger asChild>
                      <button className={cn(
                        "h-6 px-2 flex items-center gap-1 rounded border text-[11px] transition-colors",
                        "bg-background border-border hover:bg-muted/50",
                        !analysisDate && "text-muted-foreground"
                      )}>
                        <CalendarIcon className="h-2.5 w-2.5" />
                        <span className={analysisDate ? "font-medium text-foreground" : ""}>
                          {analysisDate ? format(analysisDate, "dd MMM yy") : "Select"}
                        </span>
                      </button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0" align="start">
                      <Calendar 
                        mode="single" 
                        selected={analysisDate || undefined} 
                        onSelect={date => setAnalysisDate(date || null)} 
                        initialFocus 
                        className="p-3 pointer-events-auto" 
                      />
                    </PopoverContent>
                  </Popover>
                </div>
                
                {/* CET1 Capital - Compact */}
                <CompactCET1Input value={cet1Capital} onChange={setCet1Capital} />
              </div>
            )}
          </div>
          
          {/* Right: Status indicator */}
          <StatusIndicator loaded={isLoaded} />
        </div>

        <div className="dashboard-card-content">
          {!isLoaded ? <div className={`compact-upload-zone ${isDragging ? 'active' : ''}`} onDrop={handleDrop} onDragOver={handleDragOver} onDragLeave={handleDragLeave}>
              <Upload className="h-5 w-5 text-muted-foreground mb-1" />
              <p className="text-xs text-muted-foreground mb-2">Drop CSV or click to upload</p>
              <Input ref={uploadInputRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleInputChange} />
              <div className="flex gap-1.5">
                <Button variant="outline" size="sm" onClick={handleBrowseClick} className="h-6 text-xs px-2">
                  Browse
                </Button>
                <Button variant="ghost" size="sm" onClick={handleDownloadSample} className="h-6 text-xs px-2">
                  <Download className="mr-1 h-3 w-3" />
                  Sample
                </Button>
              </div>
            </div> : <div className="flex flex-col flex-1 min-h-0">
              {/* Scrollable Balance Table with Sticky Header - Apple Style */}
              <div className="flex-1 min-h-0 overflow-hidden rounded-xl border border-border/40">
                <div className="h-full overflow-auto balance-scroll-container">
                  <table className="w-full min-w-[980px] text-xs table-fixed">
                    <colgroup>
                      <col className="w-[46%]" />
                      <col className="w-[13.5%]" />
                      <col className="w-[13.5%]" />
                      <col className="w-[13.5%]" />
                      <col className="w-[13.5%]" />
                    </colgroup>
                    <thead className="sticky top-0 z-10">
                      <tr className="text-muted-foreground">
                        <th className="text-left text-[10px] font-medium uppercase tracking-wide py-2 pl-3 pr-2 bg-card border-b border-border/40">Category</th>
                        <th className="text-right text-[10px] font-medium uppercase tracking-wide py-2 px-2 bg-card border-b border-border/40">Amount</th>
                        <th className="text-right text-[10px] font-medium uppercase tracking-wide py-2 px-2 bg-card border-b border-border/40">Pos.</th>
                        <th className="text-right text-[10px] font-medium uppercase tracking-wide py-2 px-2 bg-card border-b border-border/40">Avg Rate</th>
                        <th className="text-right text-[10px] font-medium uppercase tracking-wide py-2 px-2 bg-card border-b border-border/40">Avg Res Mat</th>
                      </tr>
                    </thead>
                    <tbody>
                      {/* Assets Row */}
                      <BalanceRowWithDelta id="assets" label={balanceTree.assets.name} amount={balanceTree.assets.amount} positions={balanceTree.assets.positions} avgRate={balanceTree.assets.avgRate} avgMaturity={balanceTree.assets.avgMaturity} delta={whatIfDeltas.assets ?? emptyDelta()} isExpanded={expandedRows.has('assets')} onToggle={() => toggleRow('assets')} formatAmount={formatAmount} formatPercent={formatPercent} formatYears={formatYears} variant="asset" />
                      {expandedRows.has('assets') && balanceTree.assets.subcategories.map(sub => <React.Fragment key={`asset-${sub.id}`}>
                          <SubcategoryRowWithDelta 
                            id={sub.id} 
                            label={sub.name} 
                            amount={sub.amount} 
                            positions={sub.positions} 
                            avgRate={sub.avgRate} 
                            avgMaturity={sub.avgMaturity}
                            delta={whatIfDeltas[sub.id]} 
                            formatAmount={formatAmount} 
                            formatPercent={formatPercent}
                            formatYears={formatYears}
                            onViewDetails={() => openDetails(sub.id)}
                          />
                          {/* Render What-If items under this subcategory */}
                          {whatIfDeltas[sub.id]?.items.map((mod: WhatIfModification) => <WhatIfItemRow key={mod.id} label={mod.label} amount={mod.notional || 0} positionDelta={mod.positionDelta ?? 1} type={mod.type} formatAmount={formatAmount} />)}
                        </React.Fragment>)}
                      
                      {/* Liabilities Row */}
                      <BalanceRowWithDelta id="liabilities" label={balanceTree.liabilities.name} amount={balanceTree.liabilities.amount} positions={balanceTree.liabilities.positions} avgRate={balanceTree.liabilities.avgRate} avgMaturity={balanceTree.liabilities.avgMaturity} delta={whatIfDeltas.liabilities ?? emptyDelta()} isExpanded={expandedRows.has('liabilities')} onToggle={() => toggleRow('liabilities')} formatAmount={formatAmount} formatPercent={formatPercent} formatYears={formatYears} variant="liability" />
                      {expandedRows.has('liabilities') && balanceTree.liabilities.subcategories.map(sub => <React.Fragment key={`liability-${sub.id}`}>
                          <SubcategoryRowWithDelta 
                            id={sub.id} 
                            label={sub.name} 
                            amount={sub.amount} 
                            positions={sub.positions} 
                            avgRate={sub.avgRate} 
                            avgMaturity={sub.avgMaturity}
                            delta={whatIfDeltas[sub.id]} 
                            formatAmount={formatAmount} 
                            formatPercent={formatPercent}
                            formatYears={formatYears}
                            onViewDetails={() => openDetails(sub.id)}
                          />
                          {/* Render What-If items under this subcategory */}
                          {whatIfDeltas[sub.id]?.items.map((mod: WhatIfModification) => <WhatIfItemRow key={mod.id} label={mod.label} amount={mod.notional || 0} positionDelta={mod.positionDelta ?? 1} type={mod.type} formatAmount={formatAmount} />)}
                        </React.Fragment>)}
                    </tbody>
                  </table>
                </div>
              </div>
              
              {/* Action Buttons - What-If, Behavioural and Reset */}
              <div className="flex gap-2 pt-2 border-t border-border/30 mt-2">
                <Button size="sm" onClick={() => setShowWhatIfBuilder(true)} className="flex-1 h-6 text-xs relative">
                  <SlidersHorizontal className="mr-1 h-3 w-3" />
                  What-If
                  {modifications.length > 0 && <span className={`absolute -top-1 -right-1 h-3.5 min-w-[14px] rounded-full text-[9px] font-bold flex items-center justify-center px-1 ${isApplied ? 'bg-success text-success-foreground' : 'bg-warning text-warning-foreground'}`}>
                      {modifications.length}
                    </span>}
                </Button>
                <Button
                  size="sm"
                  onClick={() => setShowBehaviouralModal(true)}
                  className="flex-1 h-6 text-xs gap-1 relative"
                >
                  <Brain className="h-3 w-3" />
                  Behavioural
                  {hasCustomAssumptions && (
                    <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-background border border-primary-foreground" />
                  )}
                </Button>
                <Button variant="outline" size="sm" onClick={() => {
              resetAll();
              handleReplace();
            }} className="h-6 w-6 p-0 shrink-0 rounded-full" title="Reset all">
                  <RotateCcw className="h-3 w-3" />
                </Button>
              </div>
            </div>}
        </div>
      </div>

      {/* Balance Details Modal - Read-only aggregation explorer */}
      <BalanceDetailsModal
        open={showDetails}
        onOpenChange={setShowDetails}
        selectedCategory={selectedCategoryForDetails}
        sessionId={sessionId ?? null}
      />

      {/* What-If Builder Side Panel */}
      <WhatIfBuilder
        open={showWhatIfBuilder}
        onOpenChange={setShowWhatIfBuilder}
        sessionId={sessionId ?? null}
        balanceTree={balanceTree}
      />

      {/* Behavioural Assumptions Modal */}
      <BehaviouralAssumptionsModal open={showBehaviouralModal} onOpenChange={setShowBehaviouralModal} />
    </>;
}

// Status Indicator Component
function StatusIndicator({
  loaded
}: {
  loaded: boolean;
}) {
  return loaded ? <div className="flex items-center gap-1 text-success">
      <CheckCircle2 className="h-3 w-3" />
      <span className="text-[9px] font-medium">Balance loaded</span>
    </div> : <div className="flex items-center gap-1 text-muted-foreground">
      <XCircle className="h-3 w-3" />
      <span className="text-[10px] font-medium">Not loaded</span>
    </div>;
}

// Balance Row Component with What-If delta display
interface BalanceRowWithDeltaProps {
  id: string;
  label: string;
  amount: number;
  positions: number;
  avgRate: number | null;
  avgMaturity: number | null;
  delta: WhatIfDelta;
  isExpanded: boolean;
  onToggle: () => void;
  formatAmount: (n: number) => string;
  formatPercent: (n: number | null | undefined) => string;
  formatYears: (n: number | null | undefined) => string;
  variant: 'asset' | 'liability';
}
function BalanceRowWithDelta({
  label,
  amount,
  positions,
  avgRate,
  avgMaturity,
  delta,
  isExpanded,
  onToggle,
  formatAmount,
  formatPercent,
  formatYears,
  variant
}: BalanceRowWithDeltaProps) {
  const ChevronIcon = isExpanded ? ChevronDown : ChevronRight;
  const labelColor = variant === 'asset' ? 'text-success' : 'text-destructive';
  const hasAmountDelta = delta.addedAmount > 0 || delta.removedAmount > 0;
  const hasPositionsDelta = delta.addedPositions > 0 || delta.removedPositions > 0;
  const displayedAvgRate = computeFinalAvgRate(amount, avgRate, delta);
  const displayedAvgMaturity = computeFinalAvgMaturity(amount, avgMaturity, delta);
  const rateDelta =
    avgRate !== null &&
    displayedAvgRate !== null &&
    !Number.isNaN(avgRate) &&
    !Number.isNaN(displayedAvgRate)
      ? displayedAvgRate - avgRate
      : null;
  const baseMaturityForDelta = avgMaturity ?? 0;
  const maturityDelta = displayedAvgMaturity - baseMaturityForDelta;
  const formatDeltaAmount = (n: number) => {
    if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return `${Math.round(n)}`;
  };
  return <tr className="group cursor-pointer hover:bg-accent/50 transition-colors duration-150 border-b border-border/30" onClick={onToggle}>
      <td className="py-2 pl-3 pr-2">
        <div className="flex items-center gap-1.5">
          <ChevronIcon className="h-3 w-3 text-muted-foreground group-hover:text-foreground transition-colors" />
          <span className={`font-semibold ${labelColor}`}>{label}</span>
        </div>
      </td>
      <td className="text-right py-2 px-2 font-mono font-medium text-foreground whitespace-nowrap">
        {formatAmount(amount)}
        {hasAmountDelta && (
          <span className="ml-1 text-[9px]">
            (
            {delta.addedAmount > 0 && <span className="text-success">+{formatDeltaAmount(delta.addedAmount)}</span>}
            {delta.addedAmount > 0 && delta.removedAmount > 0 && <span className="text-muted-foreground px-0.5">/</span>}
            {delta.removedAmount > 0 && <span className="text-destructive">-{formatDeltaAmount(delta.removedAmount)}</span>}
            )
          </span>
        )}
      </td>
      <td className="text-right py-2 px-2 font-mono text-muted-foreground whitespace-nowrap">
        {positions}
        {hasPositionsDelta && (
          <span className="ml-1 text-[9px]">
            (
            {delta.addedPositions > 0 && <span className="text-success">+{delta.addedPositions}</span>}
            {delta.addedPositions > 0 && delta.removedPositions > 0 && <span className="text-muted-foreground px-0.5">/</span>}
            {delta.removedPositions > 0 && <span className="text-destructive">-{delta.removedPositions}</span>}
            )
          </span>
        )}
      </td>
      <td className="text-right py-2 px-2 font-mono text-muted-foreground whitespace-nowrap">
        {formatPercent(displayedAvgRate)}
        {rateDelta !== null && Math.abs(rateDelta) > 1e-8 && (
          <span className="ml-1 text-[9px]">
            (
            <span className={rateDelta > 0 ? 'text-success' : 'text-destructive'}>
              {rateDelta > 0 ? '+' : ''}{formatPercent(rateDelta)}
            </span>
            )
          </span>
        )}
      </td>
      <td className="text-right py-2 px-2 font-mono text-muted-foreground whitespace-nowrap">
        {formatYears(displayedAvgMaturity)}
        {Math.abs(maturityDelta) > 1e-8 && (
          <span className="ml-1 text-[9px]">
            (
            <span className={maturityDelta > 0 ? 'text-success' : 'text-destructive'}>
              {maturityDelta > 0 ? '+' : ''}{formatYears(maturityDelta)}
            </span>
            )
          </span>
        )}
      </td>
    </tr>;
}

// Subcategory Row Component with What-If delta display and View Details icon
interface SubcategoryRowWithDeltaProps {
  id: string;
  label: string;
  amount: number;
  positions: number;
  avgRate: number | null;
  avgMaturity: number | null;
  delta?: WhatIfDelta;
  formatAmount: (n: number) => string;
  formatPercent: (n: number | null | undefined) => string;
  formatYears: (n: number | null | undefined) => string;
  onViewDetails: () => void;
}
function SubcategoryRowWithDelta({
  label,
  amount,
  positions,
  avgRate,
  avgMaturity,
  delta,
  formatAmount,
  formatPercent,
  formatYears,
  onViewDetails
}: SubcategoryRowWithDeltaProps) {
  const safeDelta = delta ?? emptyDelta();
  const hasAmountDelta = safeDelta.addedAmount > 0 || safeDelta.removedAmount > 0;
  const hasPositionsDelta = safeDelta.addedPositions > 0 || safeDelta.removedPositions > 0;
  const displayedAvgRate = computeFinalAvgRate(amount, avgRate, safeDelta);
  const displayedAvgMaturity = computeFinalAvgMaturity(amount, avgMaturity, safeDelta);
  const rateDelta =
    avgRate !== null &&
    displayedAvgRate !== null &&
    !Number.isNaN(avgRate) &&
    !Number.isNaN(displayedAvgRate)
      ? displayedAvgRate - avgRate
      : null;
  const baseMaturityForDelta = avgMaturity ?? 0;
  const maturityDelta = displayedAvgMaturity - baseMaturityForDelta;
  const formatDeltaAmount = (n: number) => {
    if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(0)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return `${Math.round(n)}`;
  };
  return <tr className="text-muted-foreground group hover:bg-accent/40 transition-colors duration-150 border-b border-border/20">
      <td className="py-1.5 pl-8 pr-2">
        <div className="flex items-center gap-1.5">
          <span className="text-[11px]">{label}</span>
          <button 
            onClick={(e) => {
              e.stopPropagation();
              onViewDetails();
            }}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded-md hover:bg-muted/60"
            title={`View ${label} details`}
          >
            <Eye className="h-3 w-3 text-muted-foreground hover:text-foreground transition-colors" />
          </button>
        </div>
      </td>
      <td className="text-right py-1.5 px-2 font-mono text-[11px] whitespace-nowrap">
        {formatAmount(amount)}
        {hasAmountDelta && (
          <span className="ml-1 text-[9px]">
            (
            {safeDelta.addedAmount > 0 && <span className="text-success">+{formatDeltaAmount(safeDelta.addedAmount)}</span>}
            {safeDelta.addedAmount > 0 && safeDelta.removedAmount > 0 && <span className="text-muted-foreground px-0.5">/</span>}
            {safeDelta.removedAmount > 0 && <span className="text-destructive">-{formatDeltaAmount(safeDelta.removedAmount)}</span>}
            )
          </span>
        )}
      </td>
      <td className="text-right py-1.5 px-2 font-mono text-[11px] whitespace-nowrap">
        {positions}
        {hasPositionsDelta && (
          <span className="ml-1 text-[9px]">
            (
            {safeDelta.addedPositions > 0 && <span className="text-success">+{safeDelta.addedPositions}</span>}
            {safeDelta.addedPositions > 0 && safeDelta.removedPositions > 0 && <span className="text-muted-foreground px-0.5">/</span>}
            {safeDelta.removedPositions > 0 && <span className="text-destructive">-{safeDelta.removedPositions}</span>}
            )
          </span>
        )}
      </td>
      <td className="text-right py-1.5 px-2 font-mono text-[11px] whitespace-nowrap">
        {formatPercent(displayedAvgRate)}
        {rateDelta !== null && Math.abs(rateDelta) > 1e-8 && (
          <span className="ml-1 text-[9px]">
            (
            <span className={rateDelta > 0 ? 'text-success' : 'text-destructive'}>
              {rateDelta > 0 ? '+' : ''}{formatPercent(rateDelta)}
            </span>
            )
          </span>
        )}
      </td>
      <td className="text-right py-1.5 px-2 font-mono text-[11px] whitespace-nowrap">
        {formatYears(displayedAvgMaturity)}
        {Math.abs(maturityDelta) > 1e-8 && (
          <span className="ml-1 text-[9px]">
            (
            <span className={maturityDelta > 0 ? 'text-success' : 'text-destructive'}>
              {maturityDelta > 0 ? '+' : ''}{formatYears(maturityDelta)}
            </span>
            )
          </span>
        )}
      </td>
    </tr>;
}

// What-If Item Row (shows individual What-If positions)
interface WhatIfItemRowProps {
  label: string;
  amount: number;
  positionDelta: number;
  type: 'add' | 'remove';
  formatAmount: (n: number) => string;
}
function WhatIfItemRow({
  label,
  amount,
  positionDelta,
  type,
  formatAmount
}: WhatIfItemRowProps) {
  const isAdd = type === 'add';
  const signedPositions = isAdd ? Math.abs(positionDelta) : -Math.abs(positionDelta);
  return <tr className={`${isAdd ? 'bg-success/5' : 'bg-destructive/5'} border-b border-border/10`}>
      <td className="py-1 pl-11 pr-2">
        <span className={`text-[10px] font-medium ${isAdd ? 'text-success' : 'text-destructive'}`}>
          {isAdd ? '+ ' : '− '}{label}
          <span className="ml-1 text-[8px] opacity-60">(What-If)</span>
        </span>
      </td>
      <td className={`text-right py-1 px-2 font-mono text-[10px] whitespace-nowrap ${isAdd ? 'text-success' : 'text-destructive'}`}>
        {isAdd ? '+' : '−'}{formatAmount(Math.abs(amount))}
      </td>
      <td className={`text-right py-1 px-2 font-mono text-[10px] whitespace-nowrap ${isAdd ? 'text-success' : 'text-destructive'}`}>
        {signedPositions > 0 ? '+' : ''}{signedPositions}
      </td>
      <td className="text-right py-1 px-2 font-mono text-[10px] text-muted-foreground whitespace-nowrap">
        —
      </td>
      <td className="text-right py-1 px-2 font-mono text-[10px] text-muted-foreground whitespace-nowrap">
        —
      </td>
    </tr>;
}

// Compact CET1 Input for header row
interface CompactCET1InputProps {
  value: number | null;
  onChange: (value: number | null) => void;
}
function CompactCET1Input({ value, onChange }: CompactCET1InputProps) {
  const [isEditing, setIsEditing] = useState(value === null);
  const [inputValue, setInputValue] = useState(value?.toString() || '');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (value === null) {
      setIsEditing(true);
      setInputValue('');
    } else {
      setInputValue(value.toString());
    }
  }, [value]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isEditing]);

  const formatCET1Display = (num: number) => {
    if (num >= 1e9) return `${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `${(num / 1e6).toFixed(0)}M`;
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

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] font-medium text-muted-foreground">CET1</span>
      {isEditing ? (
        <input
          ref={inputRef}
          type="text"
          inputMode="numeric"
          placeholder="Value"
          value={inputValue}
          onChange={e => setInputValue(e.target.value.replace(/[^0-9.]/g, ''))}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            if (inputValue && value !== null && inputValue === value.toString()) {
              setIsEditing(false);
            } else if (inputValue) {
              handleConfirm();
            }
          }}
          className={cn(
            "h-6 px-2 w-20 rounded border text-[11px] font-mono",
            "bg-background border-border focus:outline-none focus:ring-1 focus:ring-primary",
            "placeholder:text-muted-foreground"
          )}
        />
      ) : (
        <button
          onClick={() => setIsEditing(true)}
          className={cn(
            "h-6 px-2 flex items-center gap-1 rounded border text-[11px] transition-colors group",
            "bg-muted/30 border-border/70 hover:bg-muted/50"
          )}
          title="Click to edit"
        >
          <span className="font-mono font-medium text-foreground">{formatCET1Display(value!)}</span>
          <Pencil className="h-2 w-2 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
      )}
    </div>
  );
}
