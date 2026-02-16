import React, { useEffect, useMemo, useState } from 'react';
import { FileSpreadsheet, Download, X, Filter } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { getBalanceDetails, type BalanceDetailsResponse } from '@/lib/api';

interface BalanceDetailsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCategory?: string | null;
  sessionId?: string | null;
}

interface Filters {
  currencies: string[];
  rateTypes: string[];
  counterparties: string[];
  maturityBuckets: string[];
}

function mapCategoryContext(selectedCategory?: string | null): {
  categoria_ui?: string;
  subcategory_id?: string;
} {
  if (!selectedCategory) return {};
  if (selectedCategory === 'assets') return { categoria_ui: 'Assets' };
  if (selectedCategory === 'liabilities') return { categoria_ui: 'Liabilities' };
  return { subcategory_id: selectedCategory };
}

function formatAmount(num: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(num);
}

function formatPercent(num: number | null | undefined) {
  if (num === null || num === undefined || Number.isNaN(num)) return '—';
  return (num * 100).toFixed(2) + '%';
}

function formatMaturity(num: number | null | undefined) {
  if (num === null || num === undefined || Number.isNaN(num)) return '—';
  return `${num.toFixed(1)}Y`;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

export function BalanceDetailsModal({
  open,
  onOpenChange,
  selectedCategory,
  sessionId,
}: BalanceDetailsModalProps) {
  const [filters, setFilters] = useState<Filters>({
    currencies: [],
    rateTypes: [],
    counterparties: [],
    maturityBuckets: [],
  });
  const [data, setData] = useState<BalanceDetailsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (!sessionId) {
      setData(null);
      setError('No active session');
      return;
    }
    let active = true;

    setLoading(true);
    setError(null);

    const context = mapCategoryContext(selectedCategory);
    getBalanceDetails(sessionId, {
      ...context,
      currency: filters.currencies,
      rate_type: filters.rateTypes,
      counterparty: filters.counterparties,
      maturity: filters.maturityBuckets,
    })
      .then((response) => {
        if (!active) return;
        setData(response);
      })
      .catch((err) => {
        if (!active) return;
        setData(null);
        setError(getErrorMessage(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [
    filters.counterparties,
    filters.currencies,
    filters.maturityBuckets,
    filters.rateTypes,
    open,
    selectedCategory,
    sessionId,
  ]);

  const getContextLabel = () => {
    if (!selectedCategory) return 'Full Balance';
    const labels: Record<string, string> = {
      assets: 'Assets',
      liabilities: 'Liabilities',
      mortgages: 'Assets → Mortgages',
      loans: 'Assets → Loans',
      securities: 'Assets → Securities',
      interbank: 'Assets → Interbank / Central Bank',
      'other-assets': 'Assets → Other assets',
      deposits: 'Liabilities → Deposits',
      'term-deposits': 'Liabilities → Term deposits',
      'wholesale-funding': 'Liabilities → Wholesale funding',
      'debt-issued': 'Liabilities → Debt issued',
      'other-liabilities': 'Liabilities → Other liabilities',
    };
    return labels[selectedCategory] || 'Full Balance';
  };

  const currencyOptions = useMemo(
    () => data?.facets.currencies.map((it) => it.value) ?? [],
    [data]
  );
  const rateTypeOptions = useMemo(
    () => data?.facets.rate_types.map((it) => it.value) ?? [],
    [data]
  );
  const counterpartyOptions = useMemo(
    () => data?.facets.counterparties.map((it) => it.value) ?? [],
    [data]
  );
  const maturityOptions = useMemo(
    () => data?.facets.maturities.map((it) => it.value) ?? [],
    [data]
  );

  const activeFilterCount =
    filters.currencies.length +
    filters.rateTypes.length +
    filters.counterparties.length +
    filters.maturityBuckets.length;

  const clearFilters = () => {
    setFilters({ currencies: [], rateTypes: [], counterparties: [], maturityBuckets: [] });
  };

  const handleExport = () => {
    if (!data) return;
    const headers = ['Group', 'Amount', 'Positions', 'Avg Rate (%)', 'Avg Maturity (years)'];
    const rows = data.groups.map((row) => [
      row.group,
      row.amount.toString(),
      row.positions.toString(),
      row.avg_rate === null ? '' : (row.avg_rate * 100).toFixed(2),
      row.avg_maturity === null ? '' : row.avg_maturity.toFixed(1),
    ]);
    const csv = [
      headers.join(','),
      ...rows.map((r) => r.join(',')),
      '',
      `Total,${data.totals.amount},${data.totals.positions},${
        data.totals.avg_rate === null ? '' : (data.totals.avg_rate * 100).toFixed(2)
      },${data.totals.avg_maturity === null ? '' : data.totals.avg_maturity.toFixed(1)}`,
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `balance_positions_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const toggleFilter = (category: keyof Filters, value: string) => {
    setFilters((prev) => ({
      ...prev,
      [category]: prev[category].includes(value)
        ? prev[category].filter((v) => v !== value)
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
              disabled={!data || data.groups.length === 0}
            >
              <Download className="mr-1.5 h-3 w-3" />
              Export to Excel
            </Button>
          </div>
        </DialogHeader>

        <div className="flex items-center gap-2 py-3 border-b border-border/50 flex-wrap">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Filter className="h-3.5 w-3.5" />
            <span>Filters:</span>
          </div>

          <FilterDropdown
            label="Currency"
            options={currencyOptions}
            selected={filters.currencies}
            onToggle={(v) => toggleFilter('currencies', v)}
          />

          <FilterDropdown
            label="Rate Type"
            options={rateTypeOptions}
            selected={filters.rateTypes}
            onToggle={(v) => toggleFilter('rateTypes', v)}
          />

          <FilterDropdown
            label="Counterparty"
            options={counterpartyOptions}
            selected={filters.counterparties}
            onToggle={(v) => toggleFilter('counterparties', v)}
          />

          <FilterDropdown
            label="Maturity"
            options={maturityOptions}
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
        </div>

        {activeFilterCount > 0 && (
          <div className="flex items-center gap-1.5 py-2 flex-wrap">
            {filters.currencies.map((c) => (
              <Badge key={c} variant="outline" className="text-[10px] h-5">
                {c}
                <button onClick={() => toggleFilter('currencies', c)} className="ml-1">
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            ))}
            {filters.rateTypes.map((r) => (
              <Badge key={r} variant="outline" className="text-[10px] h-5">
                {r}
                <button onClick={() => toggleFilter('rateTypes', r)} className="ml-1">
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            ))}
            {filters.counterparties.map((c) => (
              <Badge key={c} variant="outline" className="text-[10px] h-5">
                {c}
                <button onClick={() => toggleFilter('counterparties', c)} className="ml-1">
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            ))}
            {filters.maturityBuckets.map((m) => (
              <Badge key={m} variant="outline" className="text-[10px] h-5">
                {m}
                <button onClick={() => toggleFilter('maturityBuckets', m)} className="ml-1">
                  <X className="h-2.5 w-2.5" />
                </button>
              </Badge>
            ))}
          </div>
        )}

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
              {loading && (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-muted-foreground">
                    Loading details...
                  </td>
                </tr>
              )}
              {!loading && error && (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-destructive whitespace-pre-wrap">
                    {error}
                  </td>
                </tr>
              )}
              {!loading && !error && (data?.groups.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-muted-foreground">
                    No positions match the current filters
                  </td>
                </tr>
              )}
              {!loading &&
                !error &&
                data?.groups.map((row) => (
                  <tr key={row.group} className="border-b border-border/50 transition-colors hover:bg-muted/20">
                    <td className="py-2.5 pl-3">{row.group}</td>
                    <td className="text-right py-2.5 font-mono text-foreground">{formatAmount(row.amount)}</td>
                    <td className="text-right py-2.5 font-mono text-muted-foreground">{row.positions}</td>
                    <td className="text-right py-2.5 font-mono text-muted-foreground">{formatPercent(row.avg_rate)}</td>
                    <td className="text-right py-2.5 pr-3 font-mono text-muted-foreground">
                      {formatMaturity(row.avg_maturity)}
                    </td>
                  </tr>
                ))}

              {!loading && !error && data && data.groups.length > 0 && (
                <tr className="border-t-2 border-border bg-muted/30 font-medium">
                  <td className="py-2.5 pl-3 text-foreground">Total</td>
                  <td className="text-right py-2.5 font-mono font-bold text-foreground">
                    {formatAmount(data.totals.amount)}
                  </td>
                  <td className="text-right py-2.5 font-mono text-muted-foreground">{data.totals.positions}</td>
                  <td className="text-right py-2.5 font-mono text-muted-foreground">
                    {formatPercent(data.totals.avg_rate)}
                  </td>
                  <td className="text-right py-2.5 pr-3 font-mono text-muted-foreground">
                    {formatMaturity(data.totals.avg_maturity)}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="pt-2 border-t border-border/30 flex items-center justify-between">
          <p className="text-[10px] text-muted-foreground">
            Showing {data?.groups.length ?? 0} aggregated group{(data?.groups.length ?? 0) !== 1 ? 's' : ''} •{' '}
            {data?.totals.positions ?? 0} underlying position{(data?.totals.positions ?? 0) !== 1 ? 's' : ''}
            {activeFilterCount > 0 && ` • ${activeFilterCount} filter${activeFilterCount !== 1 ? 's' : ''} applied`}
          </p>
          <p className="text-[10px] text-muted-foreground italic">Read-only view • What-If positions excluded</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

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
            'h-6 text-xs px-2',
            selected.length > 0 && 'border-primary text-primary'
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
          {options.length === 0 && (
            <div className="text-xs text-muted-foreground px-1 py-1">No values</div>
          )}
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
