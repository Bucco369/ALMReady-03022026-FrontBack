/**
 * PricingCompartment.tsx – Commercial rate repricing & NII margin simulation.
 *
 * ── WHAT IS REPRICING SIMULATION? ─────────────────────────────────────
 *
 *   Banks periodically reprice their products (change interest rates on
 *   existing or new production). This compartment lets the user simulate
 *   how a rate change on a specific product subcategory affects NII.
 *
 *   Example: "What if we increase the mortgage rate from 2.5% to 3.0%
 *   on 30% of new production?"
 *
 *   This is purely a commercial pricing decision — different from the
 *   market rate scenarios in Curves & Scenarios (which model exogenous
 *   interest rate shocks for regulatory IRRBB).
 *
 * ── LAYOUT ────────────────────────────────────────────────────────────
 *
 *   LEFT panel: "Portfolio Snapshot" — read-only summary of products, volumes,
 *     average rates, annual interest, NII, and NIM. When repricing overrides are
 *     pending, affected rows show strike-through + override values, and a combined
 *     impact summary card appears at the bottom.
 *
 *   RIGHT panel: "Repricing Simulation" — form to select a product subcategory,
 *     choose scope (entire book vs new production %), set a new rate or delta bps,
 *     see instant impact preview, sensitivity table, and NII impact chart.
 *     Submit adds a WhatIfModification type='pricing' to the pending list.
 *
 * ── MODIFICATION FORMAT ───────────────────────────────────────────────
 *
 *   Creates modifications with type='pricing' and a repricingOverride object:
 *     • subcategoryId: Which product (e.g. 'mortgages', 'deposits')
 *     • side: 'asset' or 'liability'
 *     • scope: 'entire' (full book) or 'new-production' (only a %)
 *     • newProductionPct: % of new production affected (0-100)
 *     • newRate: The new interest rate (decimal)
 *     • currentVolume/currentAvgRate: Snapshot for impact calculation
 *
 *   Requires balanceTree prop to read current portfolio volumes and rates.
 */
import React, { useState, useMemo, useCallback } from 'react';
import {
  DollarSign,
  Eye,
  TrendingUp,
  TrendingDown,
  Plus,
  Check,
  ArrowRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useWhatIf } from './WhatIfContext';
import type { BalanceUiTree, BalanceSubcategoryUiRow } from '@/lib/balanceUi';
import type { RepricingOverride } from '@/types/whatif';
import {
  ASSET_SUBCATEGORIES,
  LIABILITY_SUBCATEGORIES,
} from '@/config/balanceSchema';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts';

// ── Helpers ──────────────────────────────────────────────────────────────

function formatEur(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return n.toFixed(0);
}

function formatRate(decimal: number): string {
  return `${(decimal * 100).toFixed(2)}%`;
}

function signPrefix(n: number): string {
  return n >= 0 ? '+' : '';
}

interface ProductRow {
  subcategoryId: string;
  label: string;
  side: 'asset' | 'liability';
  volume: number;
  avgRate: number;        // decimal
  annualInterest: number;
  positions: number;
}

function buildProductRows(balanceTree: BalanceUiTree | null): ProductRow[] {
  if (!balanceTree) return [];
  const rows: ProductRow[] = [];

  for (const sub of balanceTree.assets.subcategories) {
    if (sub.amount <= 0) continue;
    rows.push({
      subcategoryId: sub.id,
      label: sub.name,
      side: 'asset',
      volume: sub.amount,
      avgRate: sub.avgRate ?? 0,
      annualInterest: sub.amount * (sub.avgRate ?? 0),
      positions: sub.positions,
    });
  }

  for (const sub of balanceTree.liabilities.subcategories) {
    if (sub.amount <= 0) continue;
    rows.push({
      subcategoryId: sub.id,
      label: sub.name,
      side: 'liability',
      volume: sub.amount,
      avgRate: sub.avgRate ?? 0,
      annualInterest: sub.amount * (sub.avgRate ?? 0),
      positions: sub.positions,
    });
  }

  return rows;
}

interface SensitivityRow {
  deltaBps: number;
  newRate: number;
  newAnnualInterest: number;
  deltaInterest: number;
  deltaNii: number;
}

function computeSensitivity(
  currentRate: number,
  affectedVolume: number,
  unaffectedVolume: number,
  side: 'asset' | 'liability',
  currentTotalInterest: number,
  shifts: number[] = [-100, -50, -25, 0, 25, 50, 100],
): SensitivityRow[] {
  return shifts.map((deltaBps) => {
    const newRate = currentRate + deltaBps / 10_000;
    const newInterest =
      affectedVolume * newRate + unaffectedVolume * currentRate;
    const deltaInterest = newInterest - currentTotalInterest;
    const deltaNii = side === 'liability' ? -deltaInterest : deltaInterest;
    return {
      deltaBps,
      newRate,
      newAnnualInterest: newInterest,
      deltaInterest,
      deltaNii,
    };
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════

interface PricingCompartmentProps {
  balanceTree?: BalanceUiTree | null;
}

export function PricingCompartment({ balanceTree }: PricingCompartmentProps) {
  const productRows = useMemo(() => buildProductRows(balanceTree ?? null), [balanceTree]);

  const totalAssets = useMemo(
    () => productRows.filter((r) => r.side === 'asset').reduce((s, r) => s + r.volume, 0),
    [productRows],
  );

  // ── No balance guard ──
  if (!balanceTree || productRows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <div className="rounded-2xl bg-muted/40 p-6 mb-4">
          <DollarSign className="h-10 w-10 text-muted-foreground/40" />
        </div>
        <h3 className="text-sm font-semibold text-foreground mb-1">Pricing</h3>
        <p className="text-xs text-muted-foreground max-w-sm">
          Upload balance data first to simulate commercial rate repricing and
          analyse NII / margin impact.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Left: Portfolio Snapshot */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex items-center gap-1.5 px-4 pb-2.5 pt-3 border-b border-border/40 shrink-0">
          <Eye className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold text-foreground">
            Portfolio Snapshot
          </span>
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-4 py-3">
            <PortfolioSnapshot
              productRows={productRows}
              totalAssets={totalAssets}
            />
          </div>
        </ScrollArea>
      </div>

      {/* Vertical divider */}
      <div className="w-px bg-border/60 shrink-0" />

      {/* Right: Repricing Simulation */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div className="flex items-center gap-1.5 px-4 pb-2.5 pt-3 border-b border-border/40 shrink-0">
          <DollarSign className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">
            Repricing Simulation
          </span>
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="px-4 py-3">
            <RepricingForm
              productRows={productRows}
              totalAssets={totalAssets}
            />
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// LEFT PANEL – Portfolio snapshot with income statement
// ═══════════════════════════════════════════════════════════════════════════

function PortfolioSnapshot({
  productRows,
  totalAssets,
}: {
  productRows: ProductRow[];
  totalAssets: number;
}) {
  const { modifications } = useWhatIf();

  const pricingMods = useMemo(
    () => modifications.filter((m) => m.type === 'pricing' && m.repricingOverride),
    [modifications],
  );

  const overrideMap = useMemo(() => {
    const map = new Map<string, RepricingOverride>();
    for (const mod of pricingMods) {
      if (mod.repricingOverride) {
        map.set(mod.repricingOverride.subcategoryId, mod.repricingOverride);
      }
    }
    return map;
  }, [pricingMods]);

  const assetRows = productRows.filter((r) => r.side === 'asset');
  const liabilityRows = productRows.filter((r) => r.side === 'liability');

  const totalInterestIncome = assetRows.reduce((s, r) => s + r.annualInterest, 0);
  const totalInterestExpense = liabilityRows.reduce((s, r) => s + r.annualInterest, 0);
  const nii = totalInterestIncome - totalInterestExpense;
  const nim = totalAssets > 0 ? nii / totalAssets : 0;

  // Compute adjusted figures
  const totalDeltaNii = pricingMods.reduce(
    (s, m) => s + (m.repricingOverride?.deltaNii ?? 0),
    0,
  );
  const newNii = nii + totalDeltaNii;
  const newNim = totalAssets > 0 ? newNii / totalAssets : 0;

  return (
    <div className="space-y-3">
      {/* Assets table */}
      <ProductTable
        title="Assets"
        icon={TrendingUp}
        rows={assetRows}
        overrideMap={overrideMap}
        label="Income"
      />

      {/* Liabilities table */}
      <ProductTable
        title="Liabilities"
        icon={TrendingDown}
        rows={liabilityRows}
        overrideMap={overrideMap}
        label="Expense"
      />

      {/* Income Statement */}
      <div className="rounded-md border border-border/40 bg-muted/20 p-3 space-y-1.5">
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          Net Interest Income
        </span>
        <SnapshotRow
          label="Interest income"
          value={totalInterestIncome}
          hasOverride={false}
        />
        <SnapshotRow
          label="Interest expense"
          value={totalInterestExpense}
          hasOverride={false}
        />
        <div className="h-px bg-border/40 my-1" />
        <SnapshotRow
          label="NII"
          value={nii}
          overrideValue={totalDeltaNii !== 0 ? newNii : undefined}
          hasOverride={totalDeltaNii !== 0}
          bold
        />
        <SnapshotRow
          label="NIM"
          value={nim}
          overrideValue={totalDeltaNii !== 0 ? newNim : undefined}
          hasOverride={totalDeltaNii !== 0}
          isRate
          bold
        />
      </div>

      {/* Pending overrides summary */}
      {pricingMods.length > 0 && (
        <div className="rounded-md border border-orange-300/50 bg-orange-50/30 dark:bg-orange-950/20 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold text-orange-700 dark:text-orange-400 uppercase tracking-wide">
              Pending Repricing Overrides ({pricingMods.length})
            </span>
          </div>
          {pricingMods.map((mod) => {
            const ov = mod.repricingOverride!;
            return (
              <div
                key={mod.id}
                className="text-[11px] flex items-center justify-between"
              >
                <span className="text-muted-foreground">{ov.productLabel}</span>
                <span className="font-mono">
                  <span className="line-through text-muted-foreground/50">
                    {formatRate(ov.currentAvgRate)}
                  </span>
                  <span className="text-muted-foreground text-[9px] mx-1">&rarr;</span>
                  <span className="text-orange-600 dark:text-orange-400 font-medium">
                    {formatRate(ov.newRate)}
                  </span>
                  <span className={cn(
                    'ml-2',
                    ov.deltaNii >= 0 ? 'text-emerald-600' : 'text-destructive',
                  )}>
                    ({signPrefix(ov.deltaNii)}{formatEur(ov.deltaNii)})
                  </span>
                </span>
              </div>
            );
          })}
          <div className="h-px bg-orange-300/30 dark:bg-orange-700/30" />
          <div className="flex items-center justify-between text-[11px] font-semibold">
            <span className="text-orange-700 dark:text-orange-400">Combined NII impact</span>
            <span className={cn(
              'font-mono',
              totalDeltaNii >= 0 ? 'text-emerald-600' : 'text-destructive',
            )}>
              {signPrefix(totalDeltaNii)}€{formatEur(totalDeltaNii)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub-components for left panel ─────────────────────────────────────

function ProductTable({
  title,
  icon: Icon,
  rows,
  overrideMap,
  label,
}: {
  title: string;
  icon: React.ElementType;
  rows: ProductRow[];
  overrideMap: Map<string, RepricingOverride>;
  label: string;
}) {
  if (rows.length === 0) return null;

  const total = rows.reduce((s, r) => s + r.volume, 0);
  const totalInterest = rows.reduce((s, r) => s + r.annualInterest, 0);

  return (
    <div className="rounded-md border border-border/40 bg-muted/20 p-3 space-y-1.5">
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
          {title}
        </span>
      </div>

      {/* Header */}
      <div className="grid grid-cols-[1fr_70px_55px_70px] gap-1 text-[9px] font-semibold text-muted-foreground uppercase tracking-wide pb-1 border-b border-border/30">
        <span>Product</span>
        <span className="text-right">Volume</span>
        <span className="text-right">Avg %</span>
        <span className="text-right">{label}</span>
      </div>

      {/* Rows */}
      {rows.map((row) => {
        const ov = overrideMap.get(row.subcategoryId);
        return (
          <div
            key={row.subcategoryId}
            className={cn(
              'grid grid-cols-[1fr_70px_55px_70px] gap-1 text-[11px] items-center',
              ov && 'bg-orange-50/40 dark:bg-orange-950/10 rounded px-1 -mx-1',
            )}
          >
            <span className="truncate text-foreground">
              {row.label}
              {ov && (
                <Badge
                  variant="outline"
                  className="ml-1 text-[8px] py-0 px-1 border-orange-300/50 bg-orange-100/50 text-orange-700 dark:text-orange-400"
                >
                  override
                </Badge>
              )}
            </span>
            <span className="text-right font-mono text-muted-foreground">
              €{formatEur(row.volume)}
            </span>
            <span className="text-right font-mono">
              {ov ? (
                <>
                  <span className="line-through text-muted-foreground/50">
                    {formatRate(row.avgRate)}
                  </span>
                  <br />
                  <span className="text-orange-600 dark:text-orange-400 font-medium text-[10px]">
                    {formatRate(ov.newRate)}
                  </span>
                </>
              ) : (
                formatRate(row.avgRate)
              )}
            </span>
            <span className="text-right font-mono text-muted-foreground">
              €{formatEur(row.annualInterest)}
            </span>
          </div>
        );
      })}

      {/* Total */}
      <div className="grid grid-cols-[1fr_70px_55px_70px] gap-1 text-[10px] font-semibold border-t border-border/30 pt-1">
        <span>Total</span>
        <span className="text-right font-mono">€{formatEur(total)}</span>
        <span />
        <span className="text-right font-mono">€{formatEur(totalInterest)}</span>
      </div>
    </div>
  );
}

function SnapshotRow({
  label,
  value,
  overrideValue,
  hasOverride,
  isRate,
  bold,
}: {
  label: string;
  value: number;
  overrideValue?: number;
  hasOverride: boolean;
  isRate?: boolean;
  bold?: boolean;
}) {
  const fmt = isRate ? formatRate : (v: number) => `€${formatEur(v)}`;
  return (
    <div className={cn('flex items-center justify-between text-[11px]', bold && 'font-semibold')}>
      <span className="text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1.5 font-mono">
        <span className={cn(hasOverride && 'line-through text-muted-foreground/50')}>
          {fmt(value)}
        </span>
        {hasOverride && overrideValue != null && (
          <>
            <span className="text-muted-foreground text-[9px]">&rarr;</span>
            <span className="text-orange-600 dark:text-orange-400 font-medium">
              {fmt(overrideValue)}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// RIGHT PANEL – Repricing simulation form
// ═══════════════════════════════════════════════════════════════════════════

function RepricingForm({
  productRows,
  totalAssets,
}: {
  productRows: ProductRow[];
  totalAssets: number;
}) {
  const { modifications, addModification, updateModification } = useWhatIf();

  // ── Product selection ──
  const [side, setSide] = useState<'asset' | 'liability'>('liability');
  const [subcategoryId, setSubcategoryId] = useState<string>('');

  // ── Scope ──
  const [scope, setScope] = useState<'entire' | 'new-production'>('entire');
  const [newProductionPct, setNewProductionPct] = useState<string>('30');

  // ── Rate change ──
  const [rateMode, setRateMode] = useState<'absolute' | 'delta'>('absolute');
  const [rateInput, setRateInput] = useState<string>('');

  // ── Derived ──
  const currentProduct = productRows.find(
    (r) => r.subcategoryId === subcategoryId && r.side === side,
  );

  const subcategoryOptions = useMemo(() => {
    const schema = side === 'asset' ? ASSET_SUBCATEGORIES : LIABILITY_SUBCATEGORIES;
    return schema.map((s) => {
      const row = productRows.find((r) => r.subcategoryId === s.id && r.side === side);
      return { id: s.id, label: s.label, hasData: !!row && row.volume > 0 };
    });
  }, [side, productRows]);

  // Find existing pricing override for same subcategory
  const existingMod = useMemo(
    () =>
      modifications.find(
        (m) =>
          m.type === 'pricing' &&
          m.repricingOverride?.subcategoryId === subcategoryId &&
          m.repricingOverride?.side === side,
      ) ?? null,
    [modifications, subcategoryId, side],
  );

  // Parse rate input
  const pctParsed = parseFloat(newProductionPct);
  const prodPct = isNaN(pctParsed) ? 30 : Math.max(0, Math.min(100, pctParsed));

  const affectedVolume = currentProduct
    ? scope === 'entire'
      ? currentProduct.volume
      : currentProduct.volume * prodPct / 100
    : 0;

  const unaffectedVolume = currentProduct
    ? currentProduct.volume - affectedVolume
    : 0;

  const rateParsed = parseFloat(rateInput);
  const rateValid = !isNaN(rateParsed) && rateInput.trim() !== '';

  const newRate = currentProduct && rateValid
    ? rateMode === 'absolute'
      ? rateParsed / 100
      : currentProduct.avgRate + rateParsed / 10_000
    : null;

  const deltaBps = currentProduct && newRate != null
    ? Math.round((newRate - currentProduct.avgRate) * 10_000)
    : 0;

  // Compute impact
  const impact = useMemo(() => {
    if (!currentProduct || newRate == null) return null;

    const currentTotalInterest = currentProduct.annualInterest;
    const newAnnualInterest =
      affectedVolume * newRate + unaffectedVolume * currentProduct.avgRate;
    const deltaInterest = newAnnualInterest - currentTotalInterest;
    const deltaNii = currentProduct.side === 'liability' ? -deltaInterest : deltaInterest;
    const deltaNimBps = totalAssets > 0 ? (deltaNii / totalAssets) * 10_000 : 0;

    return { newAnnualInterest, deltaInterest, deltaNii, deltaNimBps };
  }, [currentProduct, newRate, affectedVolume, unaffectedVolume, totalAssets]);

  // Sensitivity rows
  const sensitivity = useMemo(() => {
    if (!currentProduct) return [];
    return computeSensitivity(
      currentProduct.avgRate,
      affectedVolume,
      unaffectedVolume,
      currentProduct.side,
      currentProduct.annualInterest,
    );
  }, [currentProduct, affectedVolume, unaffectedVolume]);

  // ── Submit ──
  const canSubmit = !!currentProduct && newRate != null && rateValid;

  const handleSubmit = useCallback(() => {
    if (!currentProduct || !impact || newRate == null) return;

    const override: RepricingOverride = {
      subcategoryId: currentProduct.subcategoryId,
      side: currentProduct.side,
      productLabel: currentProduct.label,
      currentVolume: currentProduct.volume,
      currentAvgRate: currentProduct.avgRate,
      currentAnnualInterest: currentProduct.annualInterest,
      scope,
      newProductionPct: scope === 'new-production' ? prodPct : undefined,
      affectedVolume,
      rateMode,
      newRate,
      deltaBps,
      newAnnualInterest: impact.newAnnualInterest,
      deltaInterest: impact.deltaInterest,
      deltaNii: impact.deltaNii,
      deltaNimBps: impact.deltaNimBps,
    };

    const label = currentProduct.label;
    const details = `${formatRate(currentProduct.avgRate)} \u2192 ${formatRate(newRate)} (\u0394 NII ${signPrefix(impact.deltaNii)}\u20AC${formatEur(impact.deltaNii)})`;

    if (existingMod) {
      updateModification(existingMod.id, {
        type: 'pricing',
        label,
        details,
        subcategory: currentProduct.subcategoryId,
        repricingOverride: override,
      });
    } else {
      addModification({
        type: 'pricing',
        label,
        details,
        subcategory: currentProduct.subcategoryId,
        repricingOverride: override,
      });
    }

    // Reset rate input
    setRateInput('');
  }, [
    currentProduct, impact, newRate, scope, prodPct, affectedVolume,
    rateMode, deltaBps, existingMod, addModification, updateModification,
  ]);

  // ── Reset form when side changes ──
  const handleSideChange = (newSide: 'asset' | 'liability') => {
    setSide(newSide);
    setSubcategoryId('');
    setRateInput('');
  };

  const handleSubcategoryChange = (newId: string) => {
    setSubcategoryId(newId);
    setRateInput('');
  };

  return (
    <div className="space-y-4">
      {/* ── Product selection ──────────────────────────────────── */}
      <div className="space-y-2">
        <Label className="text-[10px] text-muted-foreground">Side</Label>
        <div className="flex gap-2">
          {(['asset', 'liability'] as const).map((s) => (
            <button
              key={s}
              onClick={() => handleSideChange(s)}
              className={cn(
                'flex-1 py-1.5 text-[11px] rounded-md border transition-all',
                side === s
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-muted/30 text-muted-foreground border-border/40 hover:bg-muted/60',
              )}
            >
              {s === 'asset' ? 'Assets' : 'Liabilities'}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-[10px] text-muted-foreground">Product</Label>
        <Select value={subcategoryId} onValueChange={handleSubcategoryChange}>
          <SelectTrigger className="h-7 text-[11px]">
            <SelectValue placeholder="Select product..." />
          </SelectTrigger>
          <SelectContent>
            {subcategoryOptions.map((opt) => (
              <SelectItem
                key={opt.id}
                value={opt.id}
                className="text-xs"
                disabled={!opt.hasData}
              >
                {opt.label}
                {!opt.hasData && (
                  <span className="text-muted-foreground ml-1">(no data)</span>
                )}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Current conditions card */}
      {currentProduct && (
        <div className="rounded-md border border-border/40 bg-muted/20 p-2.5 space-y-1">
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px]">
            <span className="text-muted-foreground">Volume:</span>
            <span className="font-mono text-right">€{formatEur(currentProduct.volume)}</span>
            <span className="text-muted-foreground">Avg rate:</span>
            <span className="font-mono text-right">{formatRate(currentProduct.avgRate)}</span>
            <span className="text-muted-foreground">Annual interest:</span>
            <span className="font-mono text-right">€{formatEur(currentProduct.annualInterest)}</span>
            <span className="text-muted-foreground">Positions:</span>
            <span className="font-mono text-right">{currentProduct.positions.toLocaleString()}</span>
          </div>
        </div>
      )}

      {/* ── Scope selection ────────────────────────────────────── */}
      {currentProduct && (
        <>
          <div className="h-px bg-border/60" />
          <div className="space-y-2">
            <Label className="text-[10px] text-muted-foreground">Apply to</Label>
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 text-[11px] cursor-pointer">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === 'entire'}
                  onChange={() => setScope('entire')}
                  className="accent-primary"
                />
                <span>
                  Entire subcategory
                  <span className="text-muted-foreground ml-1">
                    (€{formatEur(currentProduct.volume)})
                  </span>
                </span>
              </label>
              <label className="flex items-center gap-2 text-[11px] cursor-pointer">
                <input
                  type="radio"
                  name="scope"
                  checked={scope === 'new-production'}
                  onChange={() => setScope('new-production')}
                  className="accent-primary"
                />
                <span>New production only</span>
              </label>
              {scope === 'new-production' && (
                <div className="flex items-center gap-2 ml-6">
                  <Input
                    type="number"
                    min={0}
                    max={100}
                    step={5}
                    value={newProductionPct}
                    onChange={(e) => setNewProductionPct(e.target.value)}
                    className="h-6 text-[11px] w-16"
                  />
                  <span className="text-[10px] text-muted-foreground">
                    % of portfolio &rarr; €{formatEur(affectedVolume)}
                  </span>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── Rate change ────────────────────────────────────────── */}
      {currentProduct && (
        <>
          <div className="h-px bg-border/60" />
          <div className="space-y-2">
            <Label className="text-[10px] text-muted-foreground">Rate Change</Label>
            <div className="flex gap-2">
              {(['absolute', 'delta'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    setRateMode(m);
                    setRateInput('');
                  }}
                  className={cn(
                    'flex-1 py-1.5 text-[11px] rounded-md border transition-all',
                    rateMode === m
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-muted/30 text-muted-foreground border-border/40 hover:bg-muted/60',
                  )}
                >
                  {m === 'absolute' ? 'New rate (%)' : 'Delta (± bps)'}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <Input
                type="number"
                step={rateMode === 'absolute' ? '0.01' : '1'}
                value={rateInput}
                onChange={(e) => setRateInput(e.target.value)}
                placeholder={
                  rateMode === 'absolute'
                    ? `e.g. ${(currentProduct.avgRate * 100).toFixed(2)}`
                    : 'e.g. -50'
                }
                className="h-7 text-[11px] w-28"
              />
              <span className="text-[10px] text-muted-foreground">
                {rateMode === 'absolute' ? '%' : 'bps'}
              </span>
              {rateValid && newRate != null && (
                <span className="text-[10px] font-mono">
                  {rateMode === 'absolute' ? (
                    <span className={cn(
                      deltaBps < 0 ? 'text-emerald-600' : deltaBps > 0 ? 'text-destructive' : 'text-muted-foreground',
                    )}>
                      {signPrefix(deltaBps)}{deltaBps} bps
                    </span>
                  ) : (
                    <span className="text-muted-foreground">
                      <ArrowRight className="inline h-3 w-3 mx-0.5" />
                      {formatRate(newRate)}
                    </span>
                  )}
                </span>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── Impact Preview ─────────────────────────────────────── */}
      {impact && currentProduct && (
        <>
          <div className="h-px bg-border/60" />
          <div className="rounded-md border-2 border-primary/30 bg-primary/5 p-3 space-y-1.5">
            <span className="text-[10px] font-semibold text-primary uppercase tracking-wide">
              Impact Preview
            </span>
            <div className="space-y-1">
              <ImpactRow
                label={currentProduct.side === 'liability' ? 'Δ Interest expense' : 'Δ Interest income'}
                value={impact.deltaInterest}
                invert={currentProduct.side === 'liability'}
              />
              <ImpactRow label="Δ NII" value={impact.deltaNii} />
              <ImpactRow
                label="Δ NIM"
                value={impact.deltaNimBps}
                suffix="bps"
                isBps
              />
            </div>
          </div>
        </>
      )}

      {/* ── Sensitivity Table ──────────────────────────────────── */}
      {currentProduct && sensitivity.length > 0 && (
        <>
          <div className="h-px bg-border/60" />
          <div className="space-y-1.5">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
              Sensitivity Analysis
            </span>
            <p className="text-[10px] text-muted-foreground italic">
              How NII changes per rate movement on {currentProduct.label}
            </p>

            <div className="rounded-md border border-border/40 overflow-hidden">
              {/* Table header */}
              <div className="grid grid-cols-4 gap-0 text-[9px] font-semibold text-muted-foreground uppercase bg-muted/30 px-2 py-1.5">
                <span>Δ bps</span>
                <span className="text-right">New rate</span>
                <span className="text-right">Δ Int.</span>
                <span className="text-right">Δ NII</span>
              </div>
              {/* Table rows */}
              {sensitivity.map((row) => {
                const isBase = row.deltaBps === 0;
                const matchesInput = rateValid && deltaBps === row.deltaBps;
                return (
                  <div
                    key={row.deltaBps}
                    className={cn(
                      'grid grid-cols-4 gap-0 text-[11px] px-2 py-1 border-t border-border/20',
                      isBase && 'bg-muted/40 font-medium',
                      matchesInput && !isBase && 'bg-orange-50/50 dark:bg-orange-950/20 font-medium',
                    )}
                  >
                    <span className="font-mono">
                      {isBase ? '► ' : '  '}
                      {row.deltaBps > 0 ? '+' : ''}{row.deltaBps}
                    </span>
                    <span className="text-right font-mono">{formatRate(row.newRate)}</span>
                    <span className={cn(
                      'text-right font-mono',
                      row.deltaInterest > 0 ? 'text-destructive' : row.deltaInterest < 0 ? 'text-emerald-600' : '',
                    )}>
                      {isBase ? 'base' : `${signPrefix(row.deltaInterest)}€${formatEur(row.deltaInterest)}`}
                    </span>
                    <span className={cn(
                      'text-right font-mono',
                      row.deltaNii > 0 ? 'text-emerald-600' : row.deltaNii < 0 ? 'text-destructive' : '',
                    )}>
                      {isBase ? 'base' : `${signPrefix(row.deltaNii)}€${formatEur(row.deltaNii)}`}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* ── NII Impact Chart ───────────────────────────────────── */}
      {currentProduct && sensitivity.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
            NII Impact
          </span>
          <div className="rounded-md border border-border/40 bg-muted/10 p-2">
            <ResponsiveContainer width="100%" height={160}>
              <BarChart
                data={sensitivity.filter((r) => r.deltaBps !== 0)}
                layout="vertical"
                margin={{ top: 5, right: 10, bottom: 5, left: 40 }}
              >
                <XAxis
                  type="number"
                  tickFormatter={(v: number) =>
                    `€${formatEur(v)}`
                  }
                  tick={{ fontSize: 9 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="deltaBps"
                  tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v}bps`}
                  tick={{ fontSize: 9 }}
                  axisLine={false}
                  tickLine={false}
                  width={45}
                />
                <ReferenceLine x={0} stroke="hsl(var(--border))" />
                <Tooltip
                  formatter={(value: number) => [
                    `€${formatEur(value)}`,
                    'Δ NII',
                  ]}
                  labelFormatter={(v: number) => `${v > 0 ? '+' : ''}${v} bps`}
                  contentStyle={{
                    fontSize: 11,
                    borderRadius: 8,
                    border: '1px solid hsl(var(--border))',
                    backgroundColor: 'hsl(var(--card))',
                  }}
                />
                <Bar dataKey="deltaNii" radius={[0, 3, 3, 0]}>
                  {sensitivity
                    .filter((r) => r.deltaBps !== 0)
                    .map((row, i) => (
                      <Cell
                        key={i}
                        fill={
                          row.deltaNii >= 0
                            ? 'hsl(142, 71%, 45%)'
                            : 'hsl(var(--destructive))'
                        }
                        fillOpacity={0.8}
                      />
                    ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ── Empty state ────────────────────────────────────────── */}
      {!currentProduct && (
        <div className="text-center py-8 text-muted-foreground">
          <DollarSign className="h-8 w-8 mx-auto mb-2 opacity-20" />
          <p className="text-xs">
            Select a product to simulate a rate change and see the NII impact.
          </p>
          <p className="text-[10px] mt-1">
            Overrides will appear in the pending modifications bar and apply
            together with other balance changes.
          </p>
        </div>
      )}

      {/* ── Submit button ──────────────────────────────────────── */}
      {currentProduct && (
        <Button
          size="sm"
          className="h-7 text-xs w-full"
          onClick={handleSubmit}
          disabled={!canSubmit}
        >
          {existingMod ? (
            <>
              <Check className="h-3 w-3 mr-1" />
              Update Repricing Override
            </>
          ) : (
            <>
              <Plus className="h-3 w-3 mr-1" />
              Add Repricing Override
            </>
          )}
        </Button>
      )}
    </div>
  );
}

// ── Impact row helper ──────────────────────────────────────────────────

function ImpactRow({
  label,
  value,
  suffix,
  invert,
  isBps,
}: {
  label: string;
  value: number;
  suffix?: string;
  invert?: boolean;
  isBps?: boolean;
}) {
  // For liabilities: negative deltaInterest (saving) is good
  const displayPositive = invert ? value <= 0 : value >= 0;
  const color = displayPositive ? 'text-emerald-600' : 'text-destructive';
  const arrow = displayPositive ? '▲' : '▼';

  const formatted = isBps
    ? `${signPrefix(value)}${Math.abs(value).toFixed(1)}`
    : `${signPrefix(value)}€${formatEur(value)}`;

  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('font-mono font-medium', color)}>
        {formatted}{suffix ? ` ${suffix}` : ''} {arrow}
      </span>
    </div>
  );
}
