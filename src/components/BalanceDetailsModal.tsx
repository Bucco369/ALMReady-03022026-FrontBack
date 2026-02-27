import { useCallback, useEffect, useMemo, useState } from 'react';
import { FileSpreadsheet, Download, X, Filter, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import {
  getBalanceDetails,
  appendListParam,
  API_BASE,
  type BalanceDetailsResponse,
} from '@/lib/api';
import { DETAIL_CONTEXT_LABELS } from '@/config/balanceSchema';
import { FilterDropdown } from '@/components/shared/FilterDropdown';
import { HierarchicalFilterDropdown } from '@/components/shared/HierarchicalFilterDropdown';
import { useBalanceFilters, type BalanceFilters } from '@/hooks/useBalanceFilters';
import { formatAmount, formatPercent, formatMaturity, getErrorMessage } from '@/lib/formatters';

interface BalanceDetailsModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCategory?: string | null;
  sessionId?: string | null;
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

type SortField = 'group' | 'amount' | 'positions' | 'avg_rate' | 'avg_maturity';
type SortDir = 'asc' | 'desc';

export function BalanceDetailsModal({
  open,
  onOpenChange,
  selectedCategory,
  sessionId,
}: BalanceDetailsModalProps) {
  const { filters, debouncedFilters, toggleFilter, setFilterCategory, clearFilters, activeFilterCount } = useBalanceFilters();
  const [data, setData] = useState<BalanceDetailsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sorting
  const [sortField, setSortField] = useState<SortField>('amount');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Multi-dimensional groupby: when a filter dimension has >1 selected value,
  // that dimension becomes a grouping axis.  Produces cross-product rows.
  const groupByDims = useMemo(() => {
    const dims: string[] = [];
    if (debouncedFilters.currencies.length > 1) dims.push('currency');
    if (debouncedFilters.rateTypes.length > 1) dims.push('rate_type');
    if (debouncedFilters.segments.length > 1) dims.push('business_segment');
    if (debouncedFilters.maturityBuckets.length > 1) dims.push('maturity_bucket');
    if (debouncedFilters.remunerations.length > 1) dims.push('remuneration_bucket');
    if (debouncedFilters.bookValues.length > 1) dims.push('book_value_def');
    return dims;
  }, [debouncedFilters]);

  const groupByLabel = useMemo(() => {
    if (groupByDims.length === 0) return 'Group';
    const labels: Record<string, string> = {
      currency: 'Currency',
      rate_type: 'Rate Type',
      business_segment: 'Segment',
      maturity_bucket: 'Maturity',
      remuneration_bucket: 'Remuneration',
      book_value_def: 'Book Value',
    };
    return groupByDims.map((d) => labels[d] || d).join(' | ');
  }, [groupByDims]);

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
      currency: debouncedFilters.currencies,
      rate_type: debouncedFilters.rateTypes,
      segment: debouncedFilters.segments,
      strategic_segment: debouncedFilters.strategicSegments,
      maturity: debouncedFilters.maturityBuckets,
      remuneration: debouncedFilters.remunerations,
      book_value: debouncedFilters.bookValues,
      group_by: groupByDims.length > 0 ? groupByDims : undefined,
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
  }, [debouncedFilters, open, selectedCategory, sessionId]);

  const getContextLabel = () => {
    if (!selectedCategory) return 'Full Balance';
    return DETAIL_CONTEXT_LABELS[selectedCategory] || 'Full Balance';
  };

  const currencyFacets = useMemo(() => data?.facets.currencies ?? [], [data]);
  const rateTypeFacets = useMemo(() => data?.facets.rate_types ?? [], [data]);
  const segmentFacets = useMemo(() => data?.facets.segments ?? [], [data]);
  const segmentTree = useMemo(() => data?.facets.segment_tree ?? {}, [data]);
  const maturityFacets = useMemo(() => data?.facets.maturities ?? [], [data]);
  const remunerationFacets = useMemo(() => data?.facets.remunerations ?? [], [data]);
  const bookValueFacets = useMemo(() => data?.facets.book_values ?? [], [data]);

  // Sorting
  const handleSort = useCallback((field: SortField) => {
    setSortField((prev) => {
      if (prev === field) {
        setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
        return prev;
      }
      setSortDir(field === 'group' ? 'asc' : 'desc');
      return field;
    });
  }, []);

  const sortedGroups = useMemo(() => {
    if (!data?.groups) return [];
    return [...data.groups].sort((a, b) => {
      let va: string | number | null;
      let vb: string | number | null;
      if (sortField === 'group') {
        va = a.group.toLowerCase();
        vb = b.group.toLowerCase();
        return sortDir === 'asc'
          ? (va as string).localeCompare(vb as string)
          : (vb as string).localeCompare(va as string);
      }
      va = a[sortField] ?? 0;
      vb = b[sortField] ?? 0;
      return sortDir === 'asc' ? (va as number) - (vb as number) : (vb as number) - (va as number);
    });
  }, [data?.groups, sortField, sortDir]);

  // Max amount for data bars
  const maxAmount = useMemo(() => {
    if (!data?.groups.length) return 1;
    return Math.max(...data.groups.map((g) => Math.abs(g.amount)), 1);
  }, [data?.groups]);

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-30" />;
    return sortDir === 'asc'
      ? <ArrowUp className="h-3 w-3 ml-1 text-primary" />
      : <ArrowDown className="h-3 w-3 ml-1 text-primary" />;
  };

  const handleExport = () => {
    if (!sessionId) return;
    const qs = new URLSearchParams();
    const context = mapCategoryContext(selectedCategory);
    if (context.categoria_ui) qs.set('categoria_ui', context.categoria_ui);
    if (context.subcategory_id) qs.set('subcategory_id', context.subcategory_id);
    appendListParam(qs, 'currency', debouncedFilters.currencies);
    appendListParam(qs, 'rate_type', debouncedFilters.rateTypes);
    appendListParam(qs, 'segment', debouncedFilters.segments);
    appendListParam(qs, 'strategic_segment', debouncedFilters.strategicSegments);
    appendListParam(qs, 'maturity', debouncedFilters.maturityBuckets);
    appendListParam(qs, 'remuneration', debouncedFilters.remunerations);
    appendListParam(qs, 'book_value', debouncedFilters.bookValues);
    if (groupByDims.length > 0) qs.set('group_by', groupByDims.join(','));

    const query = qs.toString();
    const url = `${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/balance/export${query ? `?${query}` : ''}`;
    window.open(url, '_blank');
  };

  const allFilterBadges: { key: string; category: keyof BalanceFilters; value: string }[] = [
    ...filters.currencies.map((v) => ({ key: `cur-${v}`, category: 'currencies' as const, value: v })),
    ...filters.rateTypes.map((v) => ({ key: `rt-${v}`, category: 'rateTypes' as const, value: v })),
    ...filters.segments.map((v) => ({ key: `seg-${v}`, category: 'segments' as const, value: v })),
    ...filters.strategicSegments.map((v) => ({ key: `sseg-${v}`, category: 'strategicSegments' as const, value: v })),
    ...filters.maturityBuckets.map((v) => ({ key: `mat-${v}`, category: 'maturityBuckets' as const, value: v })),
    ...filters.remunerations.map((v) => ({ key: `rem-${v}`, category: 'remunerations' as const, value: v })),
    ...filters.bookValues.map((v) => ({ key: `bv-${v}`, category: 'bookValues' as const, value: v })),
  ];

  const handleClearSegments = useCallback(() => {
    setFilterCategory('segments', []);
    setFilterCategory('strategicSegments', []);
  }, [setFilterCategory]);

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
              disabled={!sessionId || !data || data.groups.length === 0}
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
            options={currencyFacets}
            selected={filters.currencies}
            onToggle={(v) => toggleFilter('currencies', v)}
            onSetAll={(vals) => setFilterCategory('currencies', vals)}
          />

          <FilterDropdown
            label="Rate Type"
            options={rateTypeFacets}
            selected={filters.rateTypes}
            onToggle={(v) => toggleFilter('rateTypes', v)}
            onSetAll={(vals) => setFilterCategory('rateTypes', vals)}
          />

          <HierarchicalFilterDropdown
            label="Segment"
            parentFacets={segmentFacets}
            segmentTree={segmentTree}
            selectedParents={filters.segments}
            selectedChildren={filters.strategicSegments}
            onToggleParent={(v) => toggleFilter('segments', v)}
            onToggleChild={(v) => toggleFilter('strategicSegments', v)}
            onClearAll={handleClearSegments}
          />

          <FilterDropdown
            label="Maturity"
            options={maturityFacets}
            selected={filters.maturityBuckets}
            onToggle={(v) => toggleFilter('maturityBuckets', v)}
            onSetAll={(vals) => setFilterCategory('maturityBuckets', vals)}
          />

          <FilterDropdown
            label="Remuneration"
            options={remunerationFacets}
            selected={filters.remunerations}
            onToggle={(v) => toggleFilter('remunerations', v)}
            onSetAll={(vals) => setFilterCategory('remunerations', vals)}
          />

          <FilterDropdown
            label="Book Value"
            options={bookValueFacets}
            selected={filters.bookValues}
            onToggle={(v) => toggleFilter('bookValues', v)}
            onSetAll={(vals) => setFilterCategory('bookValues', vals)}
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
            {allFilterBadges.map((b) => (
              <Badge key={b.key} variant="outline" className="text-[10px] h-5">
                {b.value}
                <button onClick={() => toggleFilter(b.category, b.value)} className="ml-1">
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
                <th
                  className="text-left font-medium py-2.5 pl-7 bg-muted/50 cursor-pointer select-none"
                  onClick={() => handleSort('group')}
                >
                  <span className="inline-flex items-center">{groupByLabel}<SortIcon field="group" /></span>
                </th>
                <th
                  className="text-right font-medium py-2.5 bg-muted/50 cursor-pointer select-none"
                  onClick={() => handleSort('amount')}
                >
                  <span className="inline-flex items-center justify-end">Amount (Mln)<SortIcon field="amount" /></span>
                </th>
                <th
                  className="text-right font-medium py-2.5 bg-muted/50 cursor-pointer select-none"
                  onClick={() => handleSort('positions')}
                >
                  <span className="inline-flex items-center justify-end">Positions<SortIcon field="positions" /></span>
                </th>
                <th
                  className="text-right font-medium py-2.5 bg-muted/50 cursor-pointer select-none"
                  onClick={() => handleSort('avg_rate')}
                >
                  <span className="inline-flex items-center justify-end">Avg Rate<SortIcon field="avg_rate" /></span>
                </th>
                <th
                  className="text-right font-medium py-2.5 pr-3 bg-muted/50 cursor-pointer select-none"
                  onClick={() => handleSort('avg_maturity')}
                >
                  <span className="inline-flex items-center justify-end">Avg Maturity<SortIcon field="avg_maturity" /></span>
                </th>
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
                sortedGroups.map((row) => {
                  const barWidth = Math.round((Math.abs(row.amount) / maxAmount) * 100);
                  return (
                      <tr
                        key={row.group}
                        className="border-b border-border/50 transition-colors hover:bg-muted/20"
                      >
                        <td className="py-2.5 pl-7">{row.group}</td>
                        <td className="text-right py-2.5 font-mono text-foreground relative">
                          <div
                            className="absolute inset-y-0.5 right-0 bg-primary/8 rounded-sm"
                            style={{ width: `${barWidth}%` }}
                          />
                          <span className="relative">{formatAmount(row.amount)}</span>
                        </td>
                        <td className="text-right py-2.5 font-mono text-muted-foreground">{row.positions}</td>
                        <td className="text-right py-2.5 font-mono text-muted-foreground">{formatPercent(row.avg_rate)}</td>
                        <td className="text-right py-2.5 pr-3 font-mono text-muted-foreground">
                          {formatMaturity(row.avg_maturity)}
                        </td>
                      </tr>
                  );
                })}

              {!loading && !error && data && data.groups.length > 1 && (
                <tr className="border-t-2 border-border bg-muted/30 font-medium">
                  <td className="py-2.5 pl-7 text-foreground">Total</td>
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
          <p className="text-[10px] text-muted-foreground italic">Read-only view • Export to Excel for full contract data</p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
