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
import React, { useEffect, useMemo, useState } from 'react';
import { FileSpreadsheet, X, Filter, ChevronLeft, Minus, Search } from 'lucide-react';
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import {
  getBalanceContracts,
  getBalanceDetails,
  type BalanceContract,
  type BalanceDetailsResponse,
} from '@/lib/api';
import { useWhatIf } from './WhatIfContext';

interface BalanceDetailsModalRemoveProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedCategory: string;
  searchQuery?: string;
  sessionId: string | null;
  subcategoryLocked?: boolean;
}

interface Filters {
  currencies: string[];
  rateTypes: string[];
  counterparties: string[];
  maturityBuckets: string[];
}

function normalizeCategory(category: string): 'asset' | 'liability' {
  return category.toLowerCase().startsWith('liab') ? 'liability' : 'asset';
}

function formatAmount(num: number) {
  const millions = num / 1e6;
  return millions.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + '€';
}

function formatPercent(num: number | null | undefined) {
  if (num === null || num === undefined || Number.isNaN(num)) return '—';
  return `${(num * 100).toFixed(2)}%`;
}

function formatMaturity(num: number | null | undefined) {
  if (num === null || num === undefined || Number.isNaN(num)) return '—';
  return `${num.toFixed(1)}Y`;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function toTitleCase(value: string): string {
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((chunk) => chunk.charAt(0).toUpperCase() + chunk.slice(1).toLowerCase())
    .join(' ');
}

function compactValues(values: string[], max = 2): string {
  if (values.length <= max) return values.join(' ');
  return `${values.slice(0, max).join(' ')} +${values.length - max}`;
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
  const [filters, setFilters] = useState<Filters>({
    currencies: [],
    rateTypes: [],
    counterparties: [],
    maturityBuckets: [],
  });
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

  useEffect(() => {
    if (!open || !sessionId) return;
    let active = true;

    setDetailsLoading(true);
    setDetailsError(null);

    getBalanceDetails(sessionId, {
      subcategory_id: selectedCategory,
      currency: filters.currencies,
      rate_type: filters.rateTypes,
      counterparty: filters.counterparties,
      maturity: filters.maturityBuckets,
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
  }, [
    filters.counterparties,
    filters.currencies,
    filters.maturityBuckets,
    filters.rateTypes,
    open,
    selectedCategory,
    sessionId,
  ]);

  useEffect(() => {
    if (!open || !showContracts || !sessionId || !drillDownGroup) return;
    let active = true;
    const q = localSearchQuery.trim();

    setContractsLoading(true);
    setContractsError(null);

    getBalanceContracts(sessionId, {
      subcategory_id: selectedCategory,
      group: [drillDownGroup],
      currency: filters.currencies,
      rate_type: filters.rateTypes,
      counterparty: filters.counterparties,
      maturity: filters.maturityBuckets,
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
    filters.counterparties,
    filters.currencies,
    filters.maturityBuckets,
    filters.rateTypes,
    localSearchQuery,
    open,
    selectedCategory,
    sessionId,
    showContracts,
  ]);

  const currencyOptions = useMemo(
    () => detailsData?.facets.currencies.map((it) => it.value) ?? [],
    [detailsData]
  );
  const rateTypeOptions = useMemo(
    () => detailsData?.facets.rate_types.map((it) => it.value) ?? [],
    [detailsData]
  );
  const counterpartyOptions = useMemo(
    () => detailsData?.facets.counterparties.map((it) => it.value) ?? [],
    [detailsData]
  );
  const maturityOptions = useMemo(
    () => detailsData?.facets.maturities.map((it) => it.value) ?? [],
    [detailsData]
  );

  const activeFilterCount =
    filters.currencies.length +
    filters.rateTypes.length +
    filters.counterparties.length +
    filters.maturityBuckets.length;

  const getContextLabel = () => {
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
    return labels[selectedCategory] || selectedCategory;
  };

  const clearFilters = () => {
    setFilters({ currencies: [], rateTypes: [], counterparties: [], maturityBuckets: [] });
    setDrillDownGroup(null);
    setShowContracts(false);
  };

  const toggleFilter = (category: keyof Filters, value: string) => {
    setFilters((prev) => ({
      ...prev,
      [category]: prev[category].includes(value)
        ? prev[category].filter((v) => v !== value)
        : [...prev[category], value],
    }));
  };

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
    if (filters.counterparties.length > 0) parts.push(`Counterparty: ${filters.counterparties.join(', ')}`);
    if (filters.maturityBuckets.length > 0) parts.push(`Maturity: ${filters.maturityBuckets.join(', ')}`);
    return parts.join(' | ');
  };

  const buildFilteredLabel = (subcategoryLabel: string) => {
    const labelParts: string[] = [];

    if (filters.counterparties.length > 0) {
      labelParts.push(compactValues(filters.counterparties.map(toTitleCase), 2));
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

    labelParts.push(subcategoryLabel);
    return `${labelParts.join(' ')} (filtered)`;
  };

  const handleRemoveFilteredAsSingleWhatIf = () => {
    if (subcategoryLocked) return;
    if (!detailsData) return;
    const totals = detailsData.totals;
    if ((totals.positions ?? 0) <= 0) return;

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
      label: filteredLabel,
      details: detailsParts.join(' • '),
      notional: totals.amount ?? 0,
      category: normalizeCategory(detailsData.categoria_ui ?? selectedCategory),
      subcategory: selectedCategory,
      rate: totals.avg_rate ?? undefined,
      maturity: totals.avg_maturity ?? 0,
      positionDelta: totals.positions,
    });

    onOpenChange(false);
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
                  disabled={subcategoryLocked}
                >
                  <Minus className="mr-1.5 h-3 w-3" />
                  Add filtered to Pending Removals
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
                  <th className="text-left font-medium py-2.5 pl-3 bg-muted/50">Group</th>
                  <th className="text-right font-medium py-2.5 bg-muted/50">Amount (Mln)</th>
                  <th className="text-right font-medium py-2.5 bg-muted/50">Contracts</th>
                  <th className="text-right font-medium py-2.5 bg-muted/50">Avg Rate</th>
                  <th className="text-right font-medium py-2.5 pr-3 bg-muted/50">Avg Maturity</th>
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
                  detailsData?.groups.map((row) => (
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
                      <td className="text-right py-2.5 font-mono text-foreground">{formatAmount(row.amount)}</td>
                      <td className="text-right py-2.5 font-mono text-muted-foreground">{row.positions}</td>
                      <td className="text-right py-2.5 font-mono text-muted-foreground">{formatPercent(row.avg_rate)}</td>
                      <td className="text-right py-2.5 pr-3 font-mono text-muted-foreground">
                        {formatMaturity(row.avg_maturity)}
                      </td>
                    </tr>
                  ))}
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
                        {(contract.counterparty ?? 'n/a')} • {(contract.maturity_bucket ?? 'n/a')} • Rate:{' '}
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
