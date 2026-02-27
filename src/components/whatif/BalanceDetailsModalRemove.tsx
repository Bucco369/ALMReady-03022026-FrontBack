/**
 * BalanceDetailsModalRemove.tsx – Contract-level drill-down modal for What-If removals.
 *
 * === ROLE IN THE SYSTEM ===
 * Opened from WhatIfRemoveTab when the user clicks the Eye icon on a subcategory.
 * Provides a two-level drill-down into the balance data:
 *
 * 1. GROUP VIEW (default):
 *    - Calls GET /api/sessions/{id}/balance/details with filters (currency,
 *      rate_type, counterparty, maturity_bucket) to get aggregated groups.
 *    - Displays a table: Group | Amount | Contracts | Avg Rate | Avg Maturity.
 *    - "Add filtered to Pending Removals" button: Creates a single WhatIfModification
 *      for all positions matching the current filter set.
 *
 * 2. CONTRACT VIEW (drill-down):
 *    - Click a group row → calls GET /api/sessions/{id}/balance/contracts with
 *      the group filter to list individual contracts.
 *    - Each contract has a checkbox. Selected contracts can be batch-added
 *      to pending removals.
 *
 * === FILTER SYSTEM ===
 * Four independent facet filters: Currency, Rate Type, Counterparty, Maturity Bucket.
 * Filter options come from the backend's `facets` field in BalanceDetailsResponse.
 * Active filters are shown as badges and can be cleared individually or all at once.
 *
 * === CURRENT LIMITATIONS ===
 * - Removals are stored in WhatIfContext only (not sent to backend).
 * - The "filtered removal" creates a modification with removeMode='contracts'
 *   but does NOT enumerate individual contract_ids — it stores the total count
 *   and notional. Phase 1 will need to either enumerate or send filter criteria.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { FileSpreadsheet, X, Filter, ChevronLeft, Minus, Search, ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import {
  getBalanceContracts,
  getBalanceDetails,
  type BalanceContract,
  type BalanceDetailsResponse,
} from '@/lib/api';
import { DETAIL_CONTEXT_LABELS } from '@/config/balanceSchema';
import { FilterDropdown } from '@/components/shared/FilterDropdown';
import { HierarchicalFilterDropdown } from '@/components/shared/HierarchicalFilterDropdown';
import { useBalanceFilters, type BalanceFilters } from '@/hooks/useBalanceFilters';
import { formatAmount, formatPercent, formatMaturity, getErrorMessage, toTitleCase, compactValues } from '@/lib/formatters';
import { useWhatIf } from './WhatIfContext';

interface BalanceDetailsModalRemoveProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCategory: string;
  searchQuery?: string;
  sessionId: string | null;
  subcategoryLocked?: boolean;
}

function normalizeCategory(category: string): 'asset' | 'liability' {
  return category.toLowerCase().startsWith('liab') ? 'liability' : 'asset';
}

export function BalanceDetailsModalRemove({
  open,
  onOpenChange,
  selectedCategory,
  searchQuery: externalSearchQuery,
  sessionId,
  subcategoryLocked = false,
}: BalanceDetailsModalRemoveProps) {
  const { addModification } = useWhatIf();
  const { filters, debouncedFilters, toggleFilter, setFilterCategory, clearFilters: clearAllFilters, activeFilterCount } = useBalanceFilters();
  const [drillDownGroup, setDrillDownGroup] = useState<string | null>(null);
  const [showContracts, setShowContracts] = useState(false);
  const [selectedContracts, setSelectedContracts] = useState<Set<string>>(new Set());
  const [localSearchQuery, setLocalSearchQuery] = useState(externalSearchQuery || '');

  const [detailsData, setDetailsData] = useState<BalanceDetailsResponse | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);

  const [contractsData, setContractsData] = useState<BalanceContract[]>([]);
  const [contractsLoading, setContractsLoading] = useState(false);
  const [contractsError, setContractsError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setSelectedContracts(new Set());
  }, [open, selectedCategory]);

  useEffect(() => {
    if (!open) return;
    setLocalSearchQuery(externalSearchQuery || '');
  }, [externalSearchQuery, open]);

  // Multi-dimensional groupby: when a filter dimension has >1 selected value,
  // that dimension becomes a grouping axis.
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
    if (!open || !sessionId) return;
    let active = true;

    setDetailsLoading(true);
    setDetailsError(null);

    getBalanceDetails(sessionId, {
      subcategory_id: selectedCategory,
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
        setDetailsData(response);
      })
      .catch((error) => {
        if (!active) return;
        setDetailsData(null);
        setDetailsError(getErrorMessage(error));
      })
      .finally(() => {
        if (active) setDetailsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [debouncedFilters, open, selectedCategory, sessionId]);

  useEffect(() => {
    if (!open || !showContracts || !sessionId || !drillDownGroup) return;
    let active = true;
    const q = localSearchQuery.trim();

    setContractsLoading(true);
    setContractsError(null);

    getBalanceContracts(sessionId, {
      subcategory_id: selectedCategory,
      group: [drillDownGroup],
      currency: debouncedFilters.currencies,
      rate_type: debouncedFilters.rateTypes,
      segment: debouncedFilters.segments,
      strategic_segment: debouncedFilters.strategicSegments,
      maturity: debouncedFilters.maturityBuckets,
      remuneration: debouncedFilters.remunerations,
      book_value: debouncedFilters.bookValues,
      query: q.length >= 2 ? q : undefined,
      page: 1,
      page_size: 1000,
    })
      .then((response) => {
        if (!active) return;
        setContractsData(response.contracts);
      })
      .catch((error) => {
        if (!active) return;
        setContractsData([]);
        setContractsError(getErrorMessage(error));
      })
      .finally(() => {
        if (active) setContractsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [
    drillDownGroup,
    debouncedFilters,
    localSearchQuery,
    open,
    selectedCategory,
    sessionId,
    showContracts,
  ]);

  const currencyFacets = useMemo(() => detailsData?.facets.currencies ?? [], [detailsData]);
  const rateTypeFacets = useMemo(() => detailsData?.facets.rate_types ?? [], [detailsData]);
  const segmentFacets = useMemo(() => detailsData?.facets.segments ?? [], [detailsData]);
  const segmentTree = useMemo(() => detailsData?.facets.segment_tree ?? {}, [detailsData]);
  const maturityFacets = useMemo(() => detailsData?.facets.maturities ?? [], [detailsData]);
  const remunerationFacets = useMemo(() => detailsData?.facets.remunerations ?? [], [detailsData]);
  const bookValueFacets = useMemo(() => detailsData?.facets.book_values ?? [], [detailsData]);

  // Sorting
  type SortField = 'group' | 'amount' | 'positions' | 'avg_rate' | 'avg_maturity';
  type SortDir = 'asc' | 'desc';
  const [sortField, setSortField] = useState<SortField>('amount');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

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
    if (!detailsData?.groups) return [];
    return [...detailsData.groups].sort((a, b) => {
      if (sortField === 'group') {
        const va = a.group.toLowerCase();
        const vb = b.group.toLowerCase();
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      const va = (a[sortField] ?? 0) as number;
      const vb = (b[sortField] ?? 0) as number;
      return sortDir === 'asc' ? va - vb : vb - va;
    });
  }, [detailsData?.groups, sortField, sortDir]);

  const maxAmount = useMemo(() => {
    if (!detailsData?.groups.length) return 1;
    return Math.max(...detailsData.groups.map((g) => Math.abs(g.amount)), 1);
  }, [detailsData?.groups]);

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-30" />;
    return sortDir === 'asc'
      ? <ArrowUp className="h-3 w-3 ml-1 text-primary" />
      : <ArrowDown className="h-3 w-3 ml-1 text-primary" />;
  };

  const getContextLabel = () => {
    return DETAIL_CONTEXT_LABELS[selectedCategory] || selectedCategory;
  };

  const handleClearFilters = () => {
    clearAllFilters();
    setDrillDownGroup(null);
    setShowContracts(false);
  };

  const handleClearSegments = useCallback(() => {
    setFilterCategory('segments', []);
    setFilterCategory('strategicSegments', []);
  }, [setFilterCategory]);

  const toggleContractSelection = (contractId: string) => {
    setSelectedContracts((prev) => {
      const next = new Set(prev);
      if (next.has(contractId)) next.delete(contractId);
      else next.add(contractId);
      return next;
    });
  };

  const handleAddSelectedToRemoval = () => {
    if (subcategoryLocked) return;

    const contractsToRemove = contractsData.filter((c) => selectedContracts.has(c.contract_id));
    contractsToRemove.forEach((contract) => {
      addModification({
        type: 'remove',
        removeMode: 'contracts',
        contractIds: [contract.contract_id],
        label: contract.contract_id,
        details: `${contract.group ?? contract.subcategoria_ui ?? selectedCategory} - ${formatAmount(contract.amount ?? 0)}`,
        notional: contract.amount ?? 0,
        category: normalizeCategory(contract.category),
        subcategory: contract.subcategory,
        rate: contract.rate ?? undefined,
        maturity: contract.maturity_years ?? 0,
        positionDelta: 1,
      });
    });

    setSelectedContracts(new Set());
    onOpenChange(false);
  };

  const buildFilterSummary = () => {
    const parts: string[] = [];
    if (filters.currencies.length > 0) parts.push(`Currency: ${filters.currencies.join(', ')}`);
    if (filters.rateTypes.length > 0) parts.push(`Rate Type: ${filters.rateTypes.join(', ')}`);
    if (filters.segments.length > 0) parts.push(`Segment: ${filters.segments.join(', ')}`);
    if (filters.strategicSegments.length > 0) parts.push(`Strategic: ${filters.strategicSegments.join(', ')}`);
    if (filters.maturityBuckets.length > 0) parts.push(`Maturity: ${filters.maturityBuckets.join(', ')}`);
    if (filters.remunerations.length > 0) parts.push(`Remuneration: ${filters.remunerations.join(', ')}`);
    if (filters.bookValues.length > 0) parts.push(`Book Value: ${filters.bookValues.join(', ')}`);
    return parts.join(' | ');
  };

  const buildFilteredLabel = (subcategoryLabel: string) => {
    const labelParts: string[] = [];

    if (filters.segments.length > 0) {
      labelParts.push(compactValues(filters.segments.map(toTitleCase), 2));
    }

    if (filters.rateTypes.length > 0) {
      labelParts.push(compactValues(filters.rateTypes.map(toTitleCase), 2));
    }

    if (filters.currencies.length > 0) {
      labelParts.push(compactValues(filters.currencies.map((c) => c.toUpperCase()), 2));
    }

    if (filters.maturityBuckets.length > 0) {
      labelParts.push(compactValues(filters.maturityBuckets, 1));
    }

    if (filters.remunerations.length > 0) {
      labelParts.push(compactValues(filters.remunerations, 1));
    }

    labelParts.push(subcategoryLabel);
    return `${labelParts.join(' ')} (filtered)`;
  };

  const [filterRemoveLoading, setFilterRemoveLoading] = useState(false);

  const handleRemoveFilteredAsSingleWhatIf = async () => {
    if (subcategoryLocked || !detailsData || !sessionId) return;
    const totals = detailsData.totals;
    if ((totals.positions ?? 0) <= 0) return;

    // Fetch ALL contract IDs matching the active filters so the backend
    // can actually identify which positions to remove.
    setFilterRemoveLoading(true);
    try {
      const resp = await getBalanceContracts(sessionId, {
        subcategory_id: selectedCategory,
        currency: filters.currencies,
        rate_type: filters.rateTypes,
        segment: filters.segments,
        strategic_segment: filters.strategicSegments,
        maturity: filters.maturityBuckets,
        remuneration: filters.remunerations,
        book_value: filters.bookValues,
        page: 1,
        page_size: 50_000,
      });

      const contractIds = resp.contracts.map((c) => c.contract_id);
      if (contractIds.length === 0) return;

      // Build per-contract maturity distribution for accurate chart allocation
      const maturityProfile = resp.contracts.map((c) => ({
        amount: c.amount ?? 0,
        maturityYears: c.maturity_years ?? 0,
        rate: c.rate ?? undefined,
      }));

      const filterSummary = buildFilterSummary();
      const subcategoryLabel = detailsData.subcategoria_ui ?? selectedCategory;
      const filteredLabel = buildFilteredLabel(subcategoryLabel);
      const detailsParts = [
        `${totals.positions} contract${totals.positions !== 1 ? 's' : ''}`,
        formatAmount(totals.amount ?? 0),
      ];
      if (filterSummary) detailsParts.push(filterSummary);

      addModification({
        type: 'remove',
        removeMode: 'contracts',
        contractIds,
        label: filteredLabel,
        details: detailsParts.join(' • '),
        notional: totals.amount ?? 0,
        category: normalizeCategory(detailsData.categoria_ui ?? selectedCategory),
        subcategory: selectedCategory,
        rate: totals.avg_rate ?? undefined,
        maturity: totals.avg_maturity ?? 0,
        positionDelta: totals.positions,
        maturityProfile,
      });

      onOpenChange(false);
    } catch (err) {
      console.error('Failed to fetch contract IDs for filtered removal:', err);
    } finally {
      setFilterRemoveLoading(false);
    }
  };

  const handleDrillDown = (group: string) => {
    setDrillDownGroup(group);
    setShowContracts(true);
  };

  const handleBack = () => {
    if (!showContracts) return;
    setShowContracts(false);
    setDrillDownGroup(null);
    setSelectedContracts(new Set());
  };

  const canRemoveFilteredAsOne =
    !showContracts &&
    !subcategoryLocked &&
    activeFilterCount > 0 &&
    !detailsLoading &&
    !detailsError &&
    (detailsData?.totals.positions ?? 0) > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader className="pb-2 border-b border-border">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2 text-base">
              <FileSpreadsheet className="h-4 w-4 text-primary" />
              Select Contracts for Removal — {getContextLabel()}
            </DialogTitle>
            <div className="flex items-center gap-2">
              {canRemoveFilteredAsOne && (
                <Button
                  size="sm"
                  onClick={handleRemoveFilteredAsSingleWhatIf}
                  className="h-7 text-xs"
                  disabled={subcategoryLocked || filterRemoveLoading}
                >
                  <Minus className="mr-1.5 h-3 w-3" />
                  {filterRemoveLoading ? 'Loading contracts...' : 'Add filtered to Pending Removals'}
                </Button>
              )}
              {selectedContracts.size > 0 && (
                <Button
                  size="sm"
                  onClick={handleAddSelectedToRemoval}
                  className="h-7 text-xs"
                  disabled={subcategoryLocked}
                >
                  <Minus className="mr-1.5 h-3 w-3" />
                  Add {selectedContracts.size} to Pending Removals
                </Button>
              )}
            </div>
          </div>
        </DialogHeader>

        <div className="flex items-center gap-2 py-3 border-b border-border/50 flex-wrap">
          {showContracts && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleBack}
              className="h-6 text-xs px-2"
            >
              <ChevronLeft className="h-3 w-3 mr-1" />
              Back to groups
            </Button>
          )}

          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
            <Input
              placeholder="Search by Contract ID..."
              value={localSearchQuery}
              onChange={(e) => setLocalSearchQuery(e.target.value)}
              className="h-6 w-48 pl-7 text-xs"
            />
          </div>

          <div className="h-4 w-px bg-border" />

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
              onClick={handleClearFilters}
              className="h-6 text-xs px-2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3 mr-1" />
              Clear all
            </Button>
          )}
        </div>

        {activeFilterCount > 0 && (() => {
          const allBadges: { key: string; category: keyof BalanceFilters; value: string }[] = [
            ...filters.currencies.map((v) => ({ key: `cur-${v}`, category: 'currencies' as const, value: v })),
            ...filters.rateTypes.map((v) => ({ key: `rt-${v}`, category: 'rateTypes' as const, value: v })),
            ...filters.segments.map((v) => ({ key: `seg-${v}`, category: 'segments' as const, value: v })),
            ...filters.strategicSegments.map((v) => ({ key: `sseg-${v}`, category: 'strategicSegments' as const, value: v })),
            ...filters.maturityBuckets.map((v) => ({ key: `mat-${v}`, category: 'maturityBuckets' as const, value: v })),
            ...filters.remunerations.map((v) => ({ key: `rem-${v}`, category: 'remunerations' as const, value: v })),
            ...filters.bookValues.map((v) => ({ key: `bv-${v}`, category: 'bookValues' as const, value: v })),
          ];
          return (
            <div className="flex items-center gap-1.5 py-2 flex-wrap">
              {allBadges.map((b) => (
                <Badge key={b.key} variant="outline" className="text-[10px] h-5">
                  {b.value}
                  <button onClick={() => toggleFilter(b.category, b.value)} className="ml-1">
                    <X className="h-2.5 w-2.5" />
                  </button>
                </Badge>
              ))}
            </div>
          );
        })()}

        {subcategoryLocked && (
          <div className="py-2 text-[11px] text-muted-foreground border-b border-border/40">
            This subcategory is already marked as remove-all. Contract-level removals are disabled.
          </div>
        )}

        {!showContracts ? (
          <ScrollArea className="flex-1 min-h-0" type="always">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-card z-10">
                <tr className="text-muted-foreground border-b border-border">
                  <th className="text-left font-medium py-2.5 pl-3 bg-muted/50 cursor-pointer select-none" onClick={() => handleSort('group')}>
                    <span className="inline-flex items-center">{groupByLabel}<SortIcon field="group" /></span>
                  </th>
                  <th className="text-right font-medium py-2.5 bg-muted/50 cursor-pointer select-none" onClick={() => handleSort('amount')}>
                    <span className="inline-flex items-center justify-end">Amount (Mln)<SortIcon field="amount" /></span>
                  </th>
                  <th className="text-right font-medium py-2.5 bg-muted/50 cursor-pointer select-none" onClick={() => handleSort('positions')}>
                    <span className="inline-flex items-center justify-end">Contracts<SortIcon field="positions" /></span>
                  </th>
                  <th className="text-right font-medium py-2.5 bg-muted/50 cursor-pointer select-none" onClick={() => handleSort('avg_rate')}>
                    <span className="inline-flex items-center justify-end">Avg Rate<SortIcon field="avg_rate" /></span>
                  </th>
                  <th className="text-right font-medium py-2.5 pr-3 bg-muted/50 cursor-pointer select-none" onClick={() => handleSort('avg_maturity')}>
                    <span className="inline-flex items-center justify-end">Avg Maturity<SortIcon field="avg_maturity" /></span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {detailsLoading && (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-muted-foreground">
                      Loading groups...
                    </td>
                  </tr>
                )}
                {!detailsLoading && detailsError && (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-destructive whitespace-pre-wrap">
                      {detailsError}
                    </td>
                  </tr>
                )}
                {!detailsLoading && !detailsError && (detailsData?.groups.length ?? 0) === 0 && (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-muted-foreground">
                      No positions match the current filters
                    </td>
                  </tr>
                )}
                {!detailsLoading &&
                  !detailsError &&
                  sortedGroups.map((row) => {
                    const barWidth = Math.round((Math.abs(row.amount) / maxAmount) * 100);
                    return (
                      <tr
                        key={row.group}
                        className="border-b border-border/50 cursor-pointer hover:bg-muted/30 transition-colors"
                        onClick={() => handleDrillDown(row.group)}
                      >
                        <td className="py-2.5 pl-3">
                          <span className="text-foreground underline decoration-dotted underline-offset-2">
                            {row.group}
                          </span>
                        </td>
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
              </tbody>
            </table>
          </ScrollArea>
        ) : (
          <div className="flex-1 min-h-0 overflow-y-auto pr-1">
            <div className="space-y-1 p-2">
              {drillDownGroup && (
                <div className="text-xs font-medium text-muted-foreground mb-2 px-1">
                  Contracts in: {drillDownGroup}
                </div>
              )}

              {contractsLoading && (
                <div className="text-center py-8 text-muted-foreground text-sm">Loading contracts...</div>
              )}
              {!contractsLoading && contractsError && (
                <div className="text-center py-8 text-destructive text-sm whitespace-pre-wrap">{contractsError}</div>
              )}
              {!contractsLoading && !contractsError && contractsData.length === 0 && (
                <div className="text-center py-8 text-muted-foreground text-sm">No contracts found</div>
              )}

              {!contractsLoading &&
                !contractsError &&
                contractsData.map((contract) => (
                  <div
                    key={contract.contract_id}
                    className={cn(
                      'flex items-center gap-3 p-2 rounded-md border transition-colors',
                      selectedContracts.has(contract.contract_id)
                        ? 'border-primary/50 bg-primary/5'
                        : 'border-border/50 hover:bg-muted/30'
                    )}
                  >
                    <Checkbox
                      checked={selectedContracts.has(contract.contract_id)}
                      onCheckedChange={() => toggleContractSelection(contract.contract_id)}
                      className="h-4 w-4"
                      disabled={subcategoryLocked}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-medium text-foreground">{contract.contract_id}</span>
                        {contract.currency && (
                          <Badge variant="outline" className="text-[9px] h-4">
                            {contract.currency}
                          </Badge>
                        )}
                        {contract.rate_type && (
                          <Badge variant="outline" className="text-[9px] h-4">
                            {contract.rate_type}
                          </Badge>
                        )}
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        {(contract.business_segment ?? 'n/a')} • {(contract.maturity_bucket ?? 'n/a')} • Rate:{' '}
                        {formatPercent(contract.rate)}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-mono font-medium text-foreground">
                        {formatAmount(contract.amount ?? 0)}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        <div className="pt-2 border-t border-border/30 flex items-center justify-between">
          <p className="text-[10px] text-muted-foreground">
            {showContracts
              ? `${contractsData.length} contract${contractsData.length !== 1 ? 's' : ''} • ${selectedContracts.size} selected for removal`
              : `${detailsData?.groups.length ?? 0} group${(detailsData?.groups.length ?? 0) !== 1 ? 's' : ''} • Click to drill down to contracts`}
          </p>
          <p className="text-[10px] text-muted-foreground italic">
            Select contracts to add to pending removals
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
