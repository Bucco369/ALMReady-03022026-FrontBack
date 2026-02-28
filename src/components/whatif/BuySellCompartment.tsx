/**
 * BuySellCompartment.tsx – Add + Remove positions for the What-If Workbench.
 *
 * ── LAYOUT ────────────────────────────────────────────────────────────
 *
 *   ┌──────────────────────┬──────────────────────┐
 *   │   Remove Position    │    Add Position       │
 *   │   (RemoveAccordion)  │    (AddCatalog)       │
 *   ├──────────────────────┼──────────────────────┤
 *   │ • Contract search    │ • Cascading dropdowns │
 *   │   (by contract ID)   │   (Side → Family →    │
 *   │ • Balance tree       │    Variant)            │
 *   │   accordion          │ • Structural config   │
 *   │   (Asset/Liability   │   (Currency, Daycount, │
 *   │    → subcategories)  │    Grace, Amortization)│
 *   │ • "Remove All" per   │ • Template fields     │
 *   │   subcategory        │   (Notional, Rate,     │
 *   │ • "View Contracts"   │    Dates, etc.)        │
 *   │   modal for cherry-  │ • [Add to Modifications│
 *   │   pick removal       │ • [Calculate Impact]   │
 *   └──────────────────────┴──────────────────────┘
 *
 * ── ADD SIDE (AddCatalog) ─────────────────────────────────────────────
 *
 *   Product catalog flow:
 *     PRODUCT_FAMILIES (whatif.ts) → variants → PRODUCT_TEMPLATES
 *     → shared/ProductConfigForm renders the form
 *     → buildModificationFromForm() (shared/constants.ts) creates the modification
 *     → useWhatIf().addModification() stores it in context
 *
 *   "Calculate Impact" button:
 *     Calls calculateWhatIf() to preview EVE/NII deltas for the SINGLE
 *     position being configured, before adding it to modifications.
 *     Currently uses the OLD endpoint (V1) — pending migration to V2
 *     which supports amortization, floor/cap, mixed rates, and grace.
 *     Results displayed in ImpactResultsPanel (per-scenario table).
 *
 *   Edit mode:
 *     When editingModification is set, the form pre-fills from the
 *     existing modification and the submit button says "Save Changes".
 *     resolveModificationSelections() reverse-maps templateId → family/variant.
 *
 * ── REMOVE SIDE (RemoveAccordion) ─────────────────────────────────────
 *
 *   Two removal modes:
 *     removeMode='all'       → Remove entire subcategory (e.g. all "deposits")
 *     removeMode='contracts' → Remove specific contract IDs
 *
 *   Balance tree structure mirrors balanceSchema.ts (ASSET_SUBCATEGORIES /
 *   LIABILITY_SUBCATEGORIES) so adding a new subcategory there automatically
 *   appears in the remove accordion.
 *
 *   "Remove All" fetches all contracts for the subcategory and stores
 *   maturityProfile[] for accurate chart tenor allocation.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Plus,
  Minus,
  Check,
  ChevronRight,
  ChevronDown,
  Search,
  FileText,
  Eye,
  Lock,
  TrendingUp,
  Landmark,
  Pencil,
  Calculator,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import {
  ASSET_SUBCATEGORIES,
  LIABILITY_SUBCATEGORIES,
} from '@/config/balanceSchema';
import type { WhatIfModification } from '@/types/whatif';
import type { Scenario } from '@/types/financial';
import type { BalanceUiTree, BalanceSubcategoryUiRow } from '@/lib/balanceUi';
import {
  getBalanceContracts,
  calculateWhatIf,
  type BalanceContract,
  type WhatIfModificationRequest,
  type WhatIfResultsResponse,
} from '@/lib/api';
import { useWhatIf } from './WhatIfContext';
import { BalanceDetailsModalRemove } from './BalanceDetailsModalRemove';
import {
  useProductFormState,
  CascadingDropdowns,
  StructuralConfigRow,
  TemplateFieldsForm,
  ComingSoonPlaceholder,
} from './shared/ProductConfigForm';
import {
  resolveModificationSelections,
  buildModificationFromForm,
  shouldShowTemplateFields,
} from './shared/constants';

// ── Helpers (Remove-side only) ───────────────────────────────────────────

function formatAmount(num: number) {
  const millions = num / 1e6;
  return (
    millions.toLocaleString('en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }) + '€'
  );
}

function normalizeCategory(category: string): 'asset' | 'liability' {
  return category.toLowerCase().startsWith('liab') ? 'liability' : 'asset';
}

function contractDetailLine(contract: BalanceContract): string {
  const bucket = contract.maturity_bucket ?? 'n/a';
  const group = contract.group ?? contract.subcategoria_ui ?? contract.subcategory;
  const amount = contract.amount ?? 0;
  const path =
    contract.categoria_ui && contract.subcategoria_ui
      ? `${contract.categoria_ui} / ${contract.subcategoria_ui}`
      : (contract.subcategoria_ui ?? contract.subcategory);
  return `${path} • ${group} • ${bucket} • ${formatAmount(amount)}`;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

// ── Props ───────────────────────────────────────────────────────────────

interface BuySellCompartmentProps {
  sessionId: string | null;
  balanceTree: BalanceUiTree | null;
  editingModification?: WhatIfModification | null;
  onEditComplete?: () => void;
  scenarios?: Scenario[];
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════

export function BuySellCompartment({
  sessionId,
  balanceTree,
  editingModification,
  onEditComplete,
  scenarios,
}: BuySellCompartmentProps) {
  const isEditing = !!editingModification;

  return (
    <div className="flex h-full min-h-0">
      {/* Left: Remove Position (balance tree — visual continuity with dashboard card) */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex items-center gap-1.5 px-4 pb-2.5 pt-3 border-b border-border/40 shrink-0">
          <Minus className="h-3.5 w-3.5 text-destructive" />
          <span className="text-xs font-semibold text-foreground">Remove Position</span>
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-4 py-3">
            <RemoveAccordion sessionId={sessionId} balanceTree={balanceTree} />
          </div>
        </ScrollArea>
      </div>

      {/* Vertical divider */}
      <div className="w-px bg-border/60 shrink-0" />

      {/* Right: Add / Edit Position */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex items-center justify-between px-4 pb-2.5 pt-3 border-b border-border/40 shrink-0">
          <div className="flex items-center gap-1.5">
            {isEditing ? (
              <Pencil className="h-3.5 w-3.5 text-primary" />
            ) : (
              <Plus className="h-3.5 w-3.5 text-success" />
            )}
            <span className="text-xs font-semibold text-foreground">
              {isEditing ? 'Edit Position' : 'Add Position'}
            </span>
          </div>
          {isEditing && onEditComplete && (
            <button
              onClick={onEditComplete}
              className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
            >
              Cancel edit
            </button>
          )}
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-4 py-3">
            <AddCatalog
              editingModification={editingModification}
              onEditComplete={onEditComplete}
              sessionId={sessionId}
              scenarios={scenarios}
            />
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ADD CATALOG – Uses shared ProductConfigForm components.
// ═══════════════════════════════════════════════════════════════════════════

interface AddCatalogProps {
  editingModification?: WhatIfModification | null;
  onEditComplete?: () => void;
  sessionId?: string | null;
  scenarios?: Scenario[];
}

function AddCatalog({ editingModification, onEditComplete, sessionId, scenarios }: AddCatalogProps) {
  const { addModification, updateModification } = useWhatIf();
  const { state, callbacks, derived, prefill, setFormValues } = useProductFormState();

  const isEditing = !!editingModification;

  // ── Impact preview state ────────────────────────────────────────────────
  const [impactResult, setImpactResult] = useState<WhatIfResultsResponse | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactError, setImpactError] = useState<string | null>(null);

  // Clear impact results when form inputs change
  useEffect(() => {
    setImpactResult(null);
    setImpactError(null);
  }, [state.formValues, state.selectedVariantId, state.selectedAmortization]);

  // ── Pre-fill from editingModification ──────────────────────────────────

  useEffect(() => {
    if (!editingModification) return;

    const resolved = resolveModificationSelections(editingModification);
    if (!resolved) return;

    prefill({
      selectedSide: resolved.side,
      selectedFamilyId: resolved.familyId,
      selectedAmortization: editingModification.amortization || '',
      selectedVariantId: resolved.variantId,
      formValues: editingModification.formValues ?? {},
    });
  }, [editingModification, prefill]);

  // ── Submit handler ─────────────────────────────────────────────────────

  const handleAddToModifications = () => {
    if (!derived.selectedTemplate) return;

    const modData = buildModificationFromForm(
      derived.selectedTemplate,
      state.selectedAmortization,
      state.formValues,
    );

    if (isEditing && editingModification) {
      updateModification(editingModification.id, modData);
      onEditComplete?.();
    } else {
      addModification(modData);
    }

    setFormValues({});
  };

  // ── Calculate Impact handler ───────────────────────────────────────────

  const handleCalculateImpact = async () => {
    if (!derived.selectedTemplate || !sessionId) return;

    const modData = buildModificationFromForm(
      derived.selectedTemplate,
      state.selectedAmortization,
      state.formValues,
    );

    const payload: WhatIfModificationRequest = {
      id: 'preview',
      type: modData.type as 'add' | 'remove',
      label: modData.label,
      notional: modData.notional,
      currency: modData.currency,
      category: modData.category,
      subcategory: modData.subcategory,
      rate: modData.rate,
      maturity: modData.maturity,
      productTemplateId: modData.productTemplateId,
      startDate: modData.startDate,
      maturityDate: modData.maturityDate,
      paymentFreq: modData.paymentFreq,
      repricingFreq: modData.repricingFreq,
      refIndex: modData.refIndex,
      spread: modData.spread,
    };

    setImpactLoading(true);
    setImpactError(null);
    setImpactResult(null);

    try {
      const result = await calculateWhatIf(sessionId, { modifications: [payload] });
      setImpactResult(result);
    } catch (err) {
      setImpactError(err instanceof Error ? err.message : String(err));
    } finally {
      setImpactLoading(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────

  const showFields = shouldShowTemplateFields(
    state.selectedFamilyId,
    state.formValues,
    derived.selectedTemplate,
    derived.selectedVariant,
  );

  const canCalculateImpact =
    derived.allRequiredFormFieldsFilled && !!sessionId && !isEditing;

  return (
    <div className="space-y-4">
      <CascadingDropdowns state={state} callbacks={callbacks} derived={derived} />
      <StructuralConfigRow state={state} callbacks={callbacks} derived={derived} />

      {derived.selectedVariant?.comingSoon && (
        <ComingSoonPlaceholder name={derived.selectedVariant.name} />
      )}

      {showFields && (
        <>
          <div className="h-px bg-border/60" />
          <TemplateFieldsForm state={state} callbacks={callbacks} derived={derived} />

          {derived.allRequiredFormFieldsFilled && (
            <div className="space-y-2">
              <Button
                size="sm"
                className="h-7 text-xs w-full"
                onClick={handleAddToModifications}
              >
                {isEditing ? (
                  <>
                    <Check className="h-3 w-3 mr-1" />
                    Save Changes
                  </>
                ) : (
                  <>
                    <Plus className="h-3 w-3 mr-1" />
                    Add to Modifications
                  </>
                )}
              </Button>

              {canCalculateImpact && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs w-full"
                  onClick={handleCalculateImpact}
                  disabled={impactLoading}
                >
                  {impactLoading ? (
                    <>
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      Calculating...
                    </>
                  ) : (
                    <>
                      <Calculator className="h-3 w-3 mr-1" />
                      Calculate Impact
                    </>
                  )}
                </Button>
              )}

              {impactError && (
                <div className="rounded-md border border-destructive/50 bg-destructive/5 px-3 py-2 text-[11px] text-destructive">
                  {impactError}
                </div>
              )}

              {impactResult && (
                <ImpactResultsPanel result={impactResult} scenarios={scenarios} />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// IMPACT RESULTS PANEL – Per-scenario EVE / NII preview
// ═══════════════════════════════════════════════════════════════════════════

function formatDelta(value: number): string {
  const millions = value / 1e6;
  const sign = millions >= 0 ? '+' : '';
  if (Math.abs(millions) >= 1) {
    return `${sign}${millions.toFixed(1)}M`;
  }
  const thousands = value / 1e3;
  if (Math.abs(thousands) >= 1) {
    return `${sign}${thousands.toFixed(0)}K`;
  }
  return `${sign}${value.toFixed(0)}`;
}

function ImpactResultsPanel({
  result,
  scenarios,
}: {
  result: WhatIfResultsResponse;
  scenarios?: Scenario[];
}) {
  const eveDeltas = result.scenario_eve_deltas ?? {};
  const niiDeltas = result.scenario_nii_deltas ?? {};

  // Build rows from enabled scenarios (if provided) or from response keys
  const rows = useMemo(() => {
    if (scenarios && scenarios.length > 0) {
      return scenarios
        .filter((s) => s.enabled)
        .map((s) => ({
          name: s.name,
          eve: eveDeltas[s.id] ?? eveDeltas[s.name] ?? 0,
          nii: niiDeltas[s.id] ?? niiDeltas[s.name] ?? 0,
        }));
    }
    // Fallback: derive rows from response keys
    const keys = new Set([...Object.keys(eveDeltas), ...Object.keys(niiDeltas)]);
    return Array.from(keys).map((k) => ({
      name: k,
      eve: eveDeltas[k] ?? 0,
      nii: niiDeltas[k] ?? 0,
    }));
  }, [scenarios, eveDeltas, niiDeltas]);

  return (
    <div className="rounded-md border border-border bg-card overflow-hidden">
      <div className="px-3 py-1.5 bg-muted/30 border-b border-border/50">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          Position Impact Preview
        </span>
      </div>

      <div className="text-[11px]">
        {/* Column headers */}
        <div className="grid grid-cols-[1fr_80px_80px] px-3 py-1 border-b border-border/30 text-[10px] text-muted-foreground font-medium">
          <span>Scenario</span>
          <span className="text-right">&Delta;EVE</span>
          <span className="text-right">&Delta;NII</span>
        </div>

        {/* Scenario rows */}
        {rows.map((row) => (
          <div
            key={row.name}
            className="grid grid-cols-[1fr_80px_80px] px-3 py-1 border-b border-border/20 last:border-0"
          >
            <span className="text-foreground truncate">{row.name}</span>
            <span className={cn('text-right font-mono', row.eve >= 0 ? 'text-success' : 'text-destructive')}>
              {formatDelta(row.eve)}
            </span>
            <span className={cn('text-right font-mono', row.nii >= 0 ? 'text-success' : 'text-destructive')}>
              {formatDelta(row.nii)}
            </span>
          </div>
        ))}

        {/* Worst-case summary */}
        <div className="grid grid-cols-[1fr_80px_80px] px-3 py-1.5 bg-muted/20 border-t border-border/50 font-semibold">
          <span className="text-foreground">Worst Case</span>
          <span className={cn('text-right font-mono', result.worst_eve_delta >= 0 ? 'text-success' : 'text-destructive')}>
            {formatDelta(result.worst_eve_delta)}
          </span>
          <span className={cn('text-right font-mono', result.worst_nii_delta >= 0 ? 'text-success' : 'text-destructive')}>
            {formatDelta(result.worst_nii_delta)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// REMOVE ACCORDION – Contract search + Category → Subcategory → Actions
// ═══════════════════════════════════════════════════════════════════════════

function RemoveAccordion({
  sessionId,
  balanceTree,
}: {
  sessionId: string | null;
  balanceTree: BalanceUiTree | null;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<BalanceContract[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [removeAllLoading, setRemoveAllLoading] = useState<string | null>(null);
  const [showDetailsModal, setShowDetailsModal] = useState(false);
  const [selectedCategoryForDetails, setSelectedCategoryForDetails] =
    useState<string | null>(null);
  const { addModification, modifications } = useWhatIf();

  const removeAllSubcategories = useMemo(() => {
    return new Set(
      modifications
        .filter(
          (mod) =>
            mod.type === 'remove' &&
            mod.removeMode === 'all' &&
            mod.subcategory,
        )
        .map((mod) => mod.subcategory as string),
    );
  }, [modifications]);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // ── Contract search (debounced) ───────────────────────────────────────
  useEffect(() => {
    let active = true;
    const q = searchQuery.trim();

    if (!sessionId || q.length < 2) {
      setSearchResults([]);
      setSearchLoading(false);
      setSearchError(null);
      return () => {
        active = false;
      };
    }

    setSearchLoading(true);
    setSearchError(null);

    const timer = window.setTimeout(async () => {
      try {
        const response = await getBalanceContracts(sessionId, {
          query: q,
          page: 1,
          page_size: 100,
        });
        if (!active) return;
        setSearchResults(response.contracts);
      } catch (error) {
        if (!active) return;
        setSearchResults([]);
        setSearchError(getErrorMessage(error));
      } finally {
        if (active) setSearchLoading(false);
      }
    }, 250);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [searchQuery, sessionId]);

  const availableSearchResults = useMemo(() => {
    return searchResults.filter(
      (c) => !removeAllSubcategories.has(c.subcategory),
    );
  }, [removeAllSubcategories, searchResults]);

  const handleRemoveContract = (contract: BalanceContract) => {
    if (removeAllSubcategories.has(contract.subcategory)) return;
    addModification({
      type: 'remove',
      removeMode: 'contracts',
      contractIds: [contract.contract_id],
      label: contract.contract_id,
      details: contractDetailLine(contract),
      notional: contract.amount ?? 0,
      category: normalizeCategory(contract.category),
      subcategory: contract.subcategory,
      rate: contract.rate ?? undefined,
      maturity: contract.maturity_years ?? 0,
      positionDelta: 1,
    });
  };

  const handleRemoveAll = async (
    subId: string,
    subLabel: string,
    catType: 'asset' | 'liability',
    runtimeData?: BalanceSubcategoryUiRow,
  ) => {
    if (removeAllSubcategories.has(subId)) return;

    let maturityProfile:
      | Array<{ amount: number; maturityYears: number; rate?: number }>
      | undefined;

    if (sessionId) {
      setRemoveAllLoading(subId);
      try {
        const resp = await getBalanceContracts(sessionId, {
          subcategory_id: subId,
          page: 1,
          page_size: 50_000,
        });
        maturityProfile = resp.contracts.map((c) => ({
          amount: c.amount ?? 0,
          maturityYears: c.maturity_years ?? 0,
          rate: c.rate ?? undefined,
        }));
      } catch {
        // Fall back to single avg maturity if fetch fails
      } finally {
        setRemoveAllLoading(null);
      }
    }

    addModification({
      type: 'remove',
      removeMode: 'all',
      label: subLabel,
      details: `${formatAmount(runtimeData?.amount ?? 0)} (all)`,
      notional: runtimeData?.amount ?? 0,
      category: catType,
      subcategory: subId,
      rate: runtimeData?.avgRate ?? undefined,
      maturity: runtimeData?.avgMaturity ?? 0,
      positionDelta: runtimeData?.positions ?? 0,
      maturityProfile,
    });
  };

  const handleViewDetails = (subId: string) => {
    setSelectedCategoryForDetails(subId);
    setShowDetailsModal(true);
  };

  // Build categories from balanceSchema (single source of truth)
  const categories = [
    {
      id: 'assets' as const,
      label: 'Assets',
      icon: TrendingUp,
      iconColor: 'text-success',
      catType: 'asset' as const,
      schemaSubs: ASSET_SUBCATEGORIES,
      treeSubs: balanceTree?.assets.subcategories ?? [],
    },
    {
      id: 'liabilities' as const,
      label: 'Liabilities',
      icon: Landmark,
      iconColor: 'text-destructive',
      catType: 'liability' as const,
      schemaSubs: LIABILITY_SUBCATEGORIES,
      treeSubs: balanceTree?.liabilities.subcategories ?? [],
    },
  ];

  return (
    <div className="flex flex-col gap-3">
      {/* ── Contract search ──────────────────────────────────────────── */}
      <div className="space-y-2">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search by Contract ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-7 pl-7 text-xs"
          />
        </div>

        {searchQuery.trim().length >= 2 && (
          <div className="rounded-md border border-border bg-card overflow-hidden">
            {searchLoading && (
              <div className="px-2.5 py-2 text-[11px] text-muted-foreground">
                Searching contracts...
              </div>
            )}
            {!searchLoading && searchError && (
              <div className="px-2.5 py-2 text-[11px] text-destructive whitespace-pre-wrap">
                {searchError}
              </div>
            )}
            {!searchLoading &&
              !searchError &&
              availableSearchResults.length === 0 && (
                <div className="px-2.5 py-2 text-[11px] text-muted-foreground">
                  No contracts found.
                </div>
              )}
            {!searchLoading &&
              !searchError &&
              availableSearchResults.map((contract) => (
                <div
                  key={`${contract.contract_id}-${contract.sheet ?? 'sheet'}`}
                  className="flex items-center justify-between px-2.5 py-1.5 border-b border-border/50 last:border-0 hover:bg-accent/30"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="text-xs font-mono text-foreground truncate">
                        {contract.contract_id}
                      </span>
                    </div>
                    <div className="text-[10px] text-muted-foreground ml-4.5">
                      {contractDetailLine(contract)}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-5 px-1.5 text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={() => handleRemoveContract(contract)}
                  >
                    <Minus className="h-3 w-3" />
                  </Button>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* ── Divider ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-px bg-border" />
        <span className="text-[9px] text-muted-foreground uppercase tracking-wide">
          Or browse balance
        </span>
        <div className="flex-1 h-px bg-border" />
      </div>

      {/* ── Progressive accordion tree ───────────────────────────────── */}
      <div className="space-y-1">
        {categories.map((cat) => {
          const isCatExpanded = expanded.has(cat.id);
          const CatIcon = cat.icon;
          return (
            <div key={cat.id}>
              <button
                onClick={() => toggle(cat.id)}
                className="w-full flex items-center gap-2 px-2 py-2 rounded-md hover:bg-accent/50 transition-colors"
              >
                {isCatExpanded ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <CatIcon className={cn('h-3.5 w-3.5', cat.iconColor)} />
                <span className="text-xs font-semibold text-foreground">
                  {cat.label}
                </span>
              </button>

              {isCatExpanded && (
                <div className="ml-4 space-y-0.5">
                  {cat.schemaSubs.map((schemaSub) => {
                    const runtimeData = cat.treeSubs.find(
                      (s) => s.id === schemaSub.id,
                    );
                    const isLocked = removeAllSubcategories.has(schemaSub.id);
                    const isLoading = removeAllLoading === schemaSub.id;

                    return (
                      <div
                        key={schemaSub.id}
                        className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-accent/40 transition-colors group"
                      >
                        <span className="text-xs text-foreground flex-1">
                          {schemaSub.label}
                        </span>

                        {runtimeData && runtimeData.amount !== 0 && (
                          <span className="text-[10px] font-mono text-muted-foreground">
                            {formatAmount(runtimeData.amount)}
                          </span>
                        )}
                        {runtimeData && runtimeData.positions > 0 && (
                          <span className="text-[9px] text-muted-foreground/70 bg-muted px-1 rounded">
                            {runtimeData.positions}
                          </span>
                        )}

                        {isLocked && (
                          <Lock className="h-2.5 w-2.5 text-muted-foreground/70" />
                        )}

                        {/* View contracts */}
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={isLocked}
                          className="h-4 w-4 p-0 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-primary hover:bg-primary/10 transition-opacity disabled:opacity-30"
                          onClick={() => handleViewDetails(schemaSub.id)}
                          title="View contracts for removal"
                        >
                          <Eye className="h-2.5 w-2.5" />
                        </Button>

                        {/* Remove all */}
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={isLocked || isLoading}
                          className="h-4 w-4 p-0 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive hover:bg-destructive/10 transition-opacity disabled:opacity-30"
                          onClick={() =>
                            handleRemoveAll(
                              schemaSub.id,
                              schemaSub.label,
                              cat.catType,
                              runtimeData,
                            )
                          }
                        >
                          {isLoading ? (
                            <div className="h-2.5 w-2.5 animate-spin rounded-full border border-destructive border-t-transparent" />
                          ) : (
                            <Minus className="h-2.5 w-2.5" />
                          )}
                        </Button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Details modal for individual contract removal ─────────────── */}
      {selectedCategoryForDetails && (
        <BalanceDetailsModalRemove
          open={showDetailsModal}
          onOpenChange={setShowDetailsModal}
          selectedCategory={selectedCategoryForDetails}
          searchQuery={searchQuery}
          sessionId={sessionId}
          subcategoryLocked={removeAllSubcategories.has(
            selectedCategoryForDetails,
          )}
        />
      )}
    </div>
  );
}
