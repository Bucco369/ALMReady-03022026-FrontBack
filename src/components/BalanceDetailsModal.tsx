import React, { useState, useMemo } from 'react';
import { FileSpreadsheet, Download, X, Filter } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';

interface BalanceDetailsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCategory?: string | null;
}

// Mock aggregated position data (baseline only, no What-If)
const MOCK_POSITIONS = [
  // Assets - Mortgages
  { id: 'MTG001', category: 'assets', subcategory: 'mortgages', group: 'Residential Fixed', currency: 'EUR', rateType: 'Fixed', counterparty: 'Retail', maturityBucket: '5-10Y', amount: 450_000_000, positions: 12, avgRate: 0.0345, avgMaturity: 7.2 },
  { id: 'MTG002', category: 'assets', subcategory: 'mortgages', group: 'Residential Variable', currency: 'EUR', rateType: 'Floating', counterparty: 'Retail', maturityBucket: '10-20Y', amount: 380_000_000, positions: 10, avgRate: 0.0285, avgMaturity: 12.5 },
  { id: 'MTG003', category: 'assets', subcategory: 'mortgages', group: 'Commercial', currency: 'EUR', rateType: 'Fixed', counterparty: 'Corporate', maturityBucket: '5-10Y', amount: 250_000_000, positions: 8, avgRate: 0.0420, avgMaturity: 6.8 },
  { id: 'MTG004', category: 'assets', subcategory: 'mortgages', group: 'Buy-to-Let', currency: 'GBP', rateType: 'Floating', counterparty: 'Retail', maturityBucket: '10-20Y', amount: 120_000_000, positions: 4, avgRate: 0.0395, avgMaturity: 15.3 },
  
  // Assets - Loans
  { id: 'LN001', category: 'assets', subcategory: 'loans', group: 'Corporate Term Loans', currency: 'EUR', rateType: 'Floating', counterparty: 'Corporate', maturityBucket: '1-5Y', amount: 180_000_000, positions: 6, avgRate: 0.0485, avgMaturity: 3.2 },
  { id: 'LN002', category: 'assets', subcategory: 'loans', group: 'SME Facilities', currency: 'EUR', rateType: 'Fixed', counterparty: 'SME', maturityBucket: '1-5Y', amount: 120_000_000, positions: 5, avgRate: 0.0525, avgMaturity: 2.8 },
  { id: 'LN003', category: 'assets', subcategory: 'loans', group: 'Consumer Loans', currency: 'EUR', rateType: 'Fixed', counterparty: 'Retail', maturityBucket: '<1Y', amount: 100_000_000, positions: 5, avgRate: 0.0650, avgMaturity: 0.8 },
  
  // Assets - Securities
  { id: 'SEC001', category: 'assets', subcategory: 'securities', group: 'Government Bonds', currency: 'EUR', rateType: 'Fixed', counterparty: 'Sovereign', maturityBucket: '5-10Y', amount: 280_000_000, positions: 6, avgRate: 0.0285, avgMaturity: 6.5 },
  { id: 'SEC002', category: 'assets', subcategory: 'securities', group: 'Corporate Bonds', currency: 'EUR', rateType: 'Fixed', counterparty: 'Corporate', maturityBucket: '1-5Y', amount: 170_000_000, positions: 4, avgRate: 0.0395, avgMaturity: 3.8 },
  { id: 'SEC003', category: 'assets', subcategory: 'securities', group: 'Covered Bonds', currency: 'USD', rateType: 'Fixed', counterparty: 'Financial', maturityBucket: '5-10Y', amount: 100_000_000, positions: 2, avgRate: 0.0420, avgMaturity: 5.2 },
  
  // Assets - Interbank
  { id: 'INT001', category: 'assets', subcategory: 'interbank', group: 'Central Bank Reserves', currency: 'EUR', rateType: 'Floating', counterparty: 'Central Bank', maturityBucket: '<1Y', amount: 150_000_000, positions: 4, avgRate: 0.0350, avgMaturity: 0.1 },
  { id: 'INT002', category: 'assets', subcategory: 'interbank', group: 'Interbank Placements', currency: 'EUR', rateType: 'Floating', counterparty: 'Financial', maturityBucket: '<1Y', amount: 50_000_000, positions: 2, avgRate: 0.0380, avgMaturity: 0.3 },
  
  // Assets - Other
  { id: 'OTH001', category: 'assets', subcategory: 'other-assets', group: 'Fixed Assets', currency: 'EUR', rateType: 'Fixed', counterparty: 'Other', maturityBucket: '>20Y', amount: 60_000_000, positions: 2, avgRate: 0.0000, avgMaturity: 30.0 },
  { id: 'OTH002', category: 'assets', subcategory: 'other-assets', group: 'Deferred Tax', currency: 'EUR', rateType: 'Fixed', counterparty: 'Other', maturityBucket: '5-10Y', amount: 40_000_000, positions: 2, avgRate: 0.0000, avgMaturity: 8.0 },
  
  // Liabilities - Deposits
  { id: 'DEP001', category: 'liabilities', subcategory: 'deposits', group: 'Retail Current Accounts', currency: 'EUR', rateType: 'Floating', counterparty: 'Retail', maturityBucket: '<1Y', amount: 320_000_000, positions: 8, avgRate: 0.0025, avgMaturity: 0.5 },
  { id: 'DEP002', category: 'liabilities', subcategory: 'deposits', group: 'Corporate Current Accounts', currency: 'EUR', rateType: 'Floating', counterparty: 'Corporate', maturityBucket: '<1Y', amount: 240_000_000, positions: 6, avgRate: 0.0080, avgMaturity: 0.3 },
  { id: 'DEP003', category: 'liabilities', subcategory: 'deposits', group: 'Savings Accounts', currency: 'EUR', rateType: 'Floating', counterparty: 'Retail', maturityBucket: '<1Y', amount: 120_000_000, positions: 4, avgRate: 0.0150, avgMaturity: 0.8 },
  
  // Liabilities - Term deposits
  { id: 'TD001', category: 'liabilities', subcategory: 'term-deposits', group: 'Retail Term 1Y', currency: 'EUR', rateType: 'Fixed', counterparty: 'Retail', maturityBucket: '<1Y', amount: 380_000_000, positions: 10, avgRate: 0.0280, avgMaturity: 0.7 },
  { id: 'TD002', category: 'liabilities', subcategory: 'term-deposits', group: 'Retail Term 2-3Y', currency: 'EUR', rateType: 'Fixed', counterparty: 'Retail', maturityBucket: '1-5Y', amount: 320_000_000, positions: 8, avgRate: 0.0350, avgMaturity: 2.1 },
  { id: 'TD003', category: 'liabilities', subcategory: 'term-deposits', group: 'Corporate Term', currency: 'EUR', rateType: 'Fixed', counterparty: 'Corporate', maturityBucket: '1-5Y', amount: 220_000_000, positions: 6, avgRate: 0.0380, avgMaturity: 1.8 },
  
  // Liabilities - Wholesale funding
  { id: 'WHL001', category: 'liabilities', subcategory: 'wholesale-funding', group: 'Senior Unsecured', currency: 'EUR', rateType: 'Fixed', counterparty: 'Financial', maturityBucket: '1-5Y', amount: 280_000_000, positions: 4, avgRate: 0.0420, avgMaturity: 2.5 },
  { id: 'WHL002', category: 'liabilities', subcategory: 'wholesale-funding', group: 'Repo Funding', currency: 'EUR', rateType: 'Floating', counterparty: 'Financial', maturityBucket: '<1Y', amount: 200_000_000, positions: 2, avgRate: 0.0380, avgMaturity: 0.2 },
  
  // Liabilities - Debt issued
  { id: 'DBT001', category: 'liabilities', subcategory: 'debt-issued', group: 'Covered Bonds Issued', currency: 'EUR', rateType: 'Fixed', counterparty: 'Financial', maturityBucket: '5-10Y', amount: 100_000_000, positions: 2, avgRate: 0.0450, avgMaturity: 6.2 },
  { id: 'DBT002', category: 'liabilities', subcategory: 'debt-issued', group: 'Subordinated Debt', currency: 'EUR', rateType: 'Fixed', counterparty: 'Financial', maturityBucket: '5-10Y', amount: 50_000_000, positions: 1, avgRate: 0.0580, avgMaturity: 7.5 },
  
  // Liabilities - Other
  { id: 'OTL001', category: 'liabilities', subcategory: 'other-liabilities', group: 'Provisions', currency: 'EUR', rateType: 'Fixed', counterparty: 'Other', maturityBucket: '1-5Y', amount: 50_000_000, positions: 1, avgRate: 0.0000, avgMaturity: 3.0 },
];

// Filter options
const CURRENCIES = ['EUR', 'USD', 'GBP', 'CHF'];
const RATE_TYPES = ['Fixed', 'Floating'];
const COUNTERPARTIES = ['Retail', 'Corporate', 'SME', 'Financial', 'Sovereign', 'Central Bank', 'Other'];
const MATURITY_BUCKETS = ['<1Y', '1-5Y', '5-10Y', '10-20Y', '>20Y'];

interface Filters {
  currencies: string[];
  rateTypes: string[];
  counterparties: string[];
  maturityBuckets: string[];
}

export function BalanceDetailsModal({ open, onOpenChange, selectedCategory }: BalanceDetailsModalProps) {
  const [filters, setFilters] = useState<Filters>({
    currencies: [],
    rateTypes: [],
    counterparties: [],
    maturityBuckets: [],
  });
  const [drillDownGroup, setDrillDownGroup] = useState<string | null>(null);

  // Determine context from selected category
  const getContextLabel = () => {
    if (!selectedCategory) return 'Full Balance';
    const labels: Record<string, string> = {
      'assets': 'Assets',
      'liabilities': 'Liabilities',
      'mortgages': 'Assets → Mortgages',
      'loans': 'Assets → Loans',
      'securities': 'Assets → Securities',
      'interbank': 'Assets → Interbank / Central Bank',
      'other-assets': 'Assets → Other assets',
      'deposits': 'Liabilities → Deposits',
      'term-deposits': 'Liabilities → Term deposits',
      'wholesale-funding': 'Liabilities → Wholesale funding',
      'debt-issued': 'Liabilities → Debt issued',
      'other-liabilities': 'Liabilities → Other liabilities',
    };
    return labels[selectedCategory] || 'Full Balance';
  };

  // Filter positions based on context and active filters
  const filteredPositions = useMemo(() => {
    let positions = [...MOCK_POSITIONS];

    // Filter by selected category context
    if (selectedCategory) {
      if (selectedCategory === 'assets') {
        positions = positions.filter(p => p.category === 'assets');
      } else if (selectedCategory === 'liabilities') {
        positions = positions.filter(p => p.category === 'liabilities');
      } else {
        positions = positions.filter(p => p.subcategory === selectedCategory);
      }
    }

    // Apply user filters
    if (filters.currencies.length > 0) {
      positions = positions.filter(p => filters.currencies.includes(p.currency));
    }
    if (filters.rateTypes.length > 0) {
      positions = positions.filter(p => filters.rateTypes.includes(p.rateType));
    }
    if (filters.counterparties.length > 0) {
      positions = positions.filter(p => filters.counterparties.includes(p.counterparty));
    }
    if (filters.maturityBuckets.length > 0) {
      positions = positions.filter(p => filters.maturityBuckets.includes(p.maturityBucket));
    }

    return positions;
  }, [selectedCategory, filters]);

  // Aggregate positions by group
  const aggregatedData = useMemo(() => {
    const grouped = filteredPositions.reduce((acc, pos) => {
      const key = drillDownGroup || pos.group;
      if (!acc[key]) {
        acc[key] = { 
          group: key, 
          amount: 0, 
          positions: 0, 
          rateSum: 0, 
          maturitySum: 0,
          items: [] 
        };
      }
      acc[key].amount += pos.amount;
      acc[key].positions += pos.positions;
      acc[key].rateSum += pos.avgRate * pos.amount;
      acc[key].maturitySum += pos.avgMaturity * pos.amount;
      acc[key].items.push(pos);
      return acc;
    }, {} as Record<string, { group: string; amount: number; positions: number; rateSum: number; maturitySum: number; items: typeof MOCK_POSITIONS }>);

    return Object.values(grouped).map(g => ({
      group: g.group,
      amount: g.amount,
      positions: g.positions,
      avgRate: g.amount > 0 ? g.rateSum / g.amount : 0,
      avgMaturity: g.amount > 0 ? g.maturitySum / g.amount : 0,
      canDrillDown: g.items.length > 1 && !drillDownGroup,
    })).sort((a, b) => b.amount - a.amount);
  }, [filteredPositions, drillDownGroup]);

  // Calculate totals
  const totals = useMemo(() => {
    const total = aggregatedData.reduce((acc, row) => {
      acc.amount += row.amount;
      acc.positions += row.positions;
      acc.rateSum += row.avgRate * row.amount;
      acc.maturitySum += row.avgMaturity * row.amount;
      return acc;
    }, { amount: 0, positions: 0, rateSum: 0, maturitySum: 0 });

    return {
      amount: total.amount,
      positions: total.positions,
      avgRate: total.amount > 0 ? total.rateSum / total.amount : 0,
      avgMaturity: total.amount > 0 ? total.maturitySum / total.amount : 0,
    };
  }, [aggregatedData]);

  const activeFilterCount = 
    filters.currencies.length + 
    filters.rateTypes.length + 
    filters.counterparties.length + 
    filters.maturityBuckets.length;

  const clearFilters = () => {
    setFilters({ currencies: [], rateTypes: [], counterparties: [], maturityBuckets: [] });
    setDrillDownGroup(null);
  };

  const handleExport = () => {
    // Generate Excel-compatible CSV with filtered data
    const headers = ['Group', 'Amount', 'Positions', 'Avg Rate (%)', 'Avg Maturity (years)'];
    const rows = aggregatedData.map(row => [
      row.group,
      row.amount.toString(),
      row.positions.toString(),
      (row.avgRate * 100).toFixed(2),
      row.avgMaturity.toFixed(1),
    ]);
    
    const csv = [
      headers.join(','),
      ...rows.map(r => r.join(',')),
      '',
      `Total,${totals.amount},${totals.positions},${(totals.avgRate * 100).toFixed(2)},${totals.avgMaturity.toFixed(1)}`,
    ].join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `balance_positions_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatAmount = (num: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'EUR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(num);
  };

  const formatPercent = (num: number) => (num * 100).toFixed(2) + '%';

  const toggleFilter = (category: keyof Filters, value: string) => {
    setFilters(prev => ({
      ...prev,
      [category]: prev[category].includes(value)
        ? prev[category].filter(v => v !== value)
        : [...prev[category], value],
    }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader className="pb-2 border-b border-border">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2 text-base">
              <FileSpreadsheet className="h-4 w-4 text-primary" />
              Balance Details — {getContextLabel()}
            </DialogTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              className="h-7 text-xs"
            >
              <Download className="mr-1.5 h-3 w-3" />
              Export to Excel
            </Button>
          </div>
        </DialogHeader>

        {/* Filter Bar */}
        <div className="flex items-center gap-2 py-3 border-b border-border/50 flex-wrap">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Filter className="h-3.5 w-3.5" />
            <span>Filters:</span>
          </div>

          {/* Currency Filter */}
          <FilterDropdown
            label="Currency"
            options={CURRENCIES}
            selected={filters.currencies}
            onToggle={(v) => toggleFilter('currencies', v)}
          />

          {/* Rate Type Filter */}
          <FilterDropdown
            label="Rate Type"
            options={RATE_TYPES}
            selected={filters.rateTypes}
            onToggle={(v) => toggleFilter('rateTypes', v)}
          />

          {/* Counterparty Filter */}
          <FilterDropdown
            label="Counterparty"
            options={COUNTERPARTIES}
            selected={filters.counterparties}
            onToggle={(v) => toggleFilter('counterparties', v)}
          />

          {/* Maturity Filter */}
          <FilterDropdown
            label="Maturity"
            options={MATURITY_BUCKETS}
            selected={filters.maturityBuckets}
            onToggle={(v) => toggleFilter('maturityBuckets', v)}
          />

          {activeFilterCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearFilters}
              className="h-6 text-xs px-2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3 mr-1" />
              Clear all
            </Button>
          )}

          {drillDownGroup && (
            <Badge variant="secondary" className="text-xs">
              Drill-down: {drillDownGroup}
              <button 
                onClick={() => setDrillDownGroup(null)} 
                className="ml-1.5 hover:text-destructive"
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          )}
        </div>

        {/* Active Filters Display */}
        {activeFilterCount > 0 && (
          <div className="flex items-center gap-1.5 py-2 flex-wrap">
            {filters.currencies.map(c => (
              <Badge key={c} variant="outline" className="text-[10px] h-5">
                {c}
                <button onClick={() => toggleFilter('currencies', c)} className="ml-1">
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            ))}
            {filters.rateTypes.map(r => (
              <Badge key={r} variant="outline" className="text-[10px] h-5">
                {r}
                <button onClick={() => toggleFilter('rateTypes', r)} className="ml-1">
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            ))}
            {filters.counterparties.map(c => (
              <Badge key={c} variant="outline" className="text-[10px] h-5">
                {c}
                <button onClick={() => toggleFilter('counterparties', c)} className="ml-1">
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            ))}
            {filters.maturityBuckets.map(m => (
              <Badge key={m} variant="outline" className="text-[10px] h-5">
                {m}
                <button onClick={() => toggleFilter('maturityBuckets', m)} className="ml-1">
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            ))}
          </div>
        )}

        {/* Aggregated Results Table */}
        <div className="flex-1 overflow-auto min-h-0">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-card z-10">
              <tr className="text-muted-foreground border-b border-border">
                <th className="text-left font-medium py-2.5 pl-3 bg-muted/50">Group</th>
                <th className="text-right font-medium py-2.5 bg-muted/50">Amount</th>
                <th className="text-right font-medium py-2.5 bg-muted/50">Positions</th>
                <th className="text-right font-medium py-2.5 bg-muted/50">Avg Rate</th>
                <th className="text-right font-medium py-2.5 pr-3 bg-muted/50">Avg Maturity</th>
              </tr>
            </thead>
            <tbody>
              {aggregatedData.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-muted-foreground">
                    No positions match the current filters
                  </td>
                </tr>
              ) : (
                <>
                  {aggregatedData.map((row) => (
                    <tr 
                      key={row.group}
                      className={cn(
                        "border-b border-border/50 transition-colors",
                        row.canDrillDown && "cursor-pointer hover:bg-muted/30"
                      )}
                      onClick={() => row.canDrillDown && setDrillDownGroup(row.group)}
                    >
                      <td className="py-2.5 pl-3">
                        <span className={cn(
                          "text-foreground",
                          row.canDrillDown && "underline decoration-dotted underline-offset-2"
                        )}>
                          {row.group}
                        </span>
                      </td>
                      <td className="text-right py-2.5 font-mono text-foreground">
                        {formatAmount(row.amount)}
                      </td>
                      <td className="text-right py-2.5 font-mono text-muted-foreground">
                        {row.positions}
                      </td>
                      <td className="text-right py-2.5 font-mono text-muted-foreground">
                        {formatPercent(row.avgRate)}
                      </td>
                      <td className="text-right py-2.5 pr-3 font-mono text-muted-foreground">
                        {row.avgMaturity.toFixed(1)}Y
                      </td>
                    </tr>
                  ))}
                  
                  {/* Totals Row */}
                  <tr className="border-t-2 border-border bg-muted/30 font-medium">
                    <td className="py-2.5 pl-3 text-foreground">
                      Total
                    </td>
                    <td className="text-right py-2.5 font-mono font-bold text-foreground">
                      {formatAmount(totals.amount)}
                    </td>
                    <td className="text-right py-2.5 font-mono text-muted-foreground">
                      {totals.positions}
                    </td>
                    <td className="text-right py-2.5 font-mono text-muted-foreground">
                      {formatPercent(totals.avgRate)}
                    </td>
                    <td className="text-right py-2.5 pr-3 font-mono text-muted-foreground">
                      {totals.avgMaturity.toFixed(1)}Y
                    </td>
                  </tr>
                </>
              )}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="pt-2 border-t border-border/30 flex items-center justify-between">
          <p className="text-[10px] text-muted-foreground">
            Showing {aggregatedData.length} aggregated group{aggregatedData.length !== 1 ? 's' : ''} • 
            {' '}{filteredPositions.length} underlying position{filteredPositions.length !== 1 ? 's' : ''}
            {activeFilterCount > 0 && ` • ${activeFilterCount} filter${activeFilterCount !== 1 ? 's' : ''} applied`}
          </p>
          <p className="text-[10px] text-muted-foreground italic">
            Read-only view • What-If positions excluded
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Filter Dropdown Component
interface FilterDropdownProps {
  label: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}

function FilterDropdown({ label, options, selected, onToggle }: FilterDropdownProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button 
          variant="outline" 
          size="sm" 
          className={cn(
            "h-6 text-xs px-2",
            selected.length > 0 && "border-primary text-primary"
          )}
        >
          {label}
          {selected.length > 0 && (
            <Badge variant="secondary" className="ml-1.5 h-4 min-w-4 text-[9px] px-1">
              {selected.length}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-48 p-2" align="start">
        <div className="space-y-1">
          {options.map((option) => (
            <label
              key={option}
              className="flex items-center gap-2 py-1 px-1 rounded hover:bg-muted/50 cursor-pointer text-sm"
            >
              <Checkbox
                checked={selected.includes(option)}
                onCheckedChange={() => onToggle(option)}
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
