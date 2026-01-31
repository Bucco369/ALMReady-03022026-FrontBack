import React, { useCallback, useState } from 'react';
import { Upload, FileSpreadsheet, Eye, RefreshCw, Download, CheckCircle2, XCircle, ChevronRight, ChevronDown, FlaskConical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { Position } from '@/types/financial';
import { parsePositionsCSV, generateSamplePositionsCSV } from '@/lib/csvParser';
import { WhatIfBuilder } from '@/components/whatif/WhatIfBuilder';
import { useWhatIf } from '@/components/whatif/WhatIfContext';

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
      { name: 'Mortgages', amount: 1_200_000_000, positions: 34, avgRate: 0.0385 },
      { name: 'Bonds', amount: 850_000_000, positions: 22, avgRate: 0.0465 },
      { name: 'Loans', amount: 400_000_000, positions: 16, avgRate: 0.0510 },
    ],
  },
  liabilities: {
    amount: 2_280_000_000,
    positions: 52,
    avgRate: 0.0285,
    subcategories: [
      { name: 'Sight Deposits', amount: 680_000_000, positions: 18, avgRate: 0.0050 },
      { name: 'Term Deposits', amount: 920_000_000, positions: 24, avgRate: 0.0320 },
      { name: 'Wholesale Funding', amount: 680_000_000, positions: 10, avgRate: 0.0425 },
    ],
  },
};

export function BalancePositionsCard({ positions, onPositionsChange }: BalancePositionsCardProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set(['assets', 'liabilities']));
  const [showWhatIfBuilder, setShowWhatIfBuilder] = useState(false);
  const { modifications, isApplied } = useWhatIf();

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
                      <BalanceRow
                        id="assets"
                        label="Assets"
                        amount={PLACEHOLDER_DATA.assets.amount}
                        positions={PLACEHOLDER_DATA.assets.positions}
                        avgRate={PLACEHOLDER_DATA.assets.avgRate}
                        isExpanded={expandedRows.has('assets')}
                        onToggle={() => toggleRow('assets')}
                        formatAmount={formatAmount}
                        formatPercent={formatPercent}
                        variant="asset"
                      />
                      {expandedRows.has('assets') && PLACEHOLDER_DATA.assets.subcategories.map((sub, idx) => (
                        <SubcategoryRow
                          key={`asset-${idx}`}
                          label={sub.name}
                          amount={sub.amount}
                          positions={sub.positions}
                          avgRate={sub.avgRate}
                          formatAmount={formatAmount}
                          formatPercent={formatPercent}
                        />
                      ))}
                      
                      {/* Liabilities Row */}
                      <BalanceRow
                        id="liabilities"
                        label="Liabilities"
                        amount={PLACEHOLDER_DATA.liabilities.amount}
                        positions={PLACEHOLDER_DATA.liabilities.positions}
                        avgRate={PLACEHOLDER_DATA.liabilities.avgRate}
                        isExpanded={expandedRows.has('liabilities')}
                        onToggle={() => toggleRow('liabilities')}
                        formatAmount={formatAmount}
                        formatPercent={formatPercent}
                        variant="liability"
                      />
                      {expandedRows.has('liabilities') && PLACEHOLDER_DATA.liabilities.subcategories.map((sub, idx) => (
                        <SubcategoryRow
                          key={`liability-${idx}`}
                          label={sub.name}
                          amount={sub.amount}
                          positions={sub.positions}
                          avgRate={sub.avgRate}
                          formatAmount={formatAmount}
                          formatPercent={formatPercent}
                        />
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
                  onClick={handleReplace}
                  className="h-6 text-xs px-2"
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

// Balance Row Component (expandable parent row)
interface BalanceRowProps {
  id: string;
  label: string;
  amount: number;
  positions: number;
  avgRate: number;
  isExpanded: boolean;
  onToggle: () => void;
  formatAmount: (n: number) => string;
  formatPercent: (n: number) => string;
  variant: 'asset' | 'liability';
}

function BalanceRow({
  label,
  amount,
  positions,
  avgRate,
  isExpanded,
  onToggle,
  formatAmount,
  formatPercent,
  variant,
}: BalanceRowProps) {
  const ChevronIcon = isExpanded ? ChevronDown : ChevronRight;
  const labelColor = variant === 'asset' ? 'text-success' : 'text-destructive';
  
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
      </td>
      <td className="text-right py-1.5 font-mono text-muted-foreground">
        {positions}
      </td>
      <td className="text-right py-1.5 pr-2 font-mono text-muted-foreground">
        {formatPercent(avgRate)}
      </td>
    </tr>
  );
}

// Subcategory Row Component (indented child row)
interface SubcategoryRowProps {
  label: string;
  amount: number;
  positions: number;
  avgRate: number;
  formatAmount: (n: number) => string;
  formatPercent: (n: number) => string;
}

function SubcategoryRow({
  label,
  amount,
  positions,
  avgRate,
  formatAmount,
  formatPercent,
}: SubcategoryRowProps) {
  return (
    <tr className="bg-muted/20 text-muted-foreground">
      <td className="py-1 pl-7">
        <span className="text-[11px]">{label}</span>
      </td>
      <td className="text-right py-1 font-mono text-[11px]">
        {formatAmount(amount)}
      </td>
      <td className="text-right py-1 font-mono text-[11px]">
        {positions}
      </td>
      <td className="text-right py-1 pr-2 font-mono text-[11px]">
        {formatPercent(avgRate)}
      </td>
    </tr>
  );
}
