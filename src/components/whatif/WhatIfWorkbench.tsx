/**
 * WhatIfWorkbench.tsx – Main modal dialog for the What-If analysis system.
 *
 * ── UI STRUCTURE ──────────────────────────────────────────────────────
 *
 *   ┌─────────────────────────────────────────────────────────┐
 *   │  Header: "What-If Workbench"                    [Close] │
 *   ├──────────┬───────────┬─────────────┬───────────────────-┤
 *   │ Add/Remove│ Find Limit│ Behavioural │     Pricing        │ ← Tab bar
 *   ├──────────┴───────────┴─────────────┴───────────────────-┤
 *   │  [Pending Modifications summary — badges with counts]   │
 *   ├─────────────────────────────────────────────────────────┤
 *   │                                                         │
 *   │  Active compartment content (all stay mounted,          │
 *   │  inactive ones hidden with CSS to preserve form state)  │
 *   │                                                         │
 *   ├─────────────────────────────────────────────────────────┤
 *   │  [Clear All]                         [Apply to Analysis] │
 *   └─────────────────────────────────────────────────────────┘
 *
 * ── COMPARTMENTS ──────────────────────────────────────────────────────
 *
 *   1. Add/Remove (BuySellCompartment):
 *      - LEFT: Remove positions from existing balance (tree accordion + contract search)
 *      - RIGHT: Add synthetic positions (product catalog → form → "Add to Modifications")
 *      - Includes "Calculate Impact" preview button (calls V1 endpoint currently)
 *
 *   2. Find Limit (FindLimitCompartment):
 *      - LEFT: Constraint definition (metric, scenario, limit value, solve-for variable)
 *      - RIGHT: Same product form as Add (shared ProductConfigForm components)
 *      - Calls POST /api/sessions/{id}/whatif/find-limit (V2 decomposer backend)
 *
 *   3. Behavioural (BehaviouralCompartment):
 *      - LEFT: Current assumptions (NMD core%, maturity, pass-through; prepayment SMM; TDRR)
 *      - RIGHT: Override form → creates type='behavioural' modifications
 *
 *   4. Pricing (PricingCompartment):
 *      - LEFT: Portfolio snapshot (volumes, rates, annual interest, NII, NIM)
 *      - RIGHT: Repricing simulation → creates type='pricing' modifications
 *
 * ── PROPS FLOW ────────────────────────────────────────────────────────
 *
 *   Index.tsx → BalancePositionsCardConnected → BalancePositionsCard → WhatIfWorkbench
 *     • sessionId: Backend session for API calls
 *     • balanceTree: Current balance for remove-side accordion and pricing snapshot
 *     • scenarios: Interest rate scenarios for impact preview display
 *
 * ── APPLY TO ANALYSIS ─────────────────────────────────────────────────
 *
 *   "Apply to Analysis" button sets isApplied=true in WhatIfContext.
 *   ResultsCard watches applyCounter and sends all modifications to the
 *   backend for EVE/NII delta calculation. The workbench closes on apply.
 */
import React, { useState } from 'react';
import {
  ArrowLeftRight,
  Target,
  Brain,
  DollarSign,
  Plus,
  Minus,
  Trash2,
  Check,
  SlidersHorizontal,
  Pencil,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
} from '@/components/ui/dialog';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useWhatIf } from './WhatIfContext';
import { BuySellCompartment } from './BuySellCompartment';
import { BehaviouralCompartment } from './BehaviouralCompartment';
import { FindLimitCompartment } from './FindLimitCompartment';
import { PricingCompartment } from './PricingCompartment';
import type { BalanceUiTree } from '@/lib/balanceUi';
import type { Scenario } from '@/types/financial';

// ── Compartment definitions ──────────────────────────────────────────────

type CompartmentId = 'buy-sell' | 'find-limit' | 'behavioural' | 'pricing';

const COMPARTMENTS: readonly {
  id: CompartmentId;
  label: string;
  icon: React.ElementType;
}[] = [
  { id: 'buy-sell',    label: 'Add / Remove',  icon: ArrowLeftRight },
  { id: 'find-limit',  label: 'Find Limit',   icon: Target },
  { id: 'behavioural', label: 'Behavioural',  icon: Brain },
  { id: 'pricing',     label: 'Pricing',      icon: DollarSign },
];

// (No placeholders needed — all compartments are now implemented)

// ── Component ────────────────────────────────────────────────────────────

interface WhatIfWorkbenchProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId?: string | null;
  balanceTree?: BalanceUiTree | null;
  scenarios?: Scenario[];
}

export function WhatIfWorkbench({
  open,
  onOpenChange,
  sessionId,
  balanceTree,
  scenarios,
}: WhatIfWorkbenchProps) {
  const [activeCompartment, setActiveCompartment] = useState<CompartmentId>('buy-sell');
  const [editingModId, setEditingModId] = useState<string | null>(null);
  const {
    modifications,
    removeModification,
    clearModifications,
    applyModifications,
    isApplied,
    addCount,
    removeCount,
    behaviouralCount,
    pricingCount,
  } = useWhatIf();

  const editingModification = editingModId
    ? modifications.find((m) => m.id === editingModId) ?? null
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPortal>
        <DialogOverlay className="bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0 duration-300" />
        <DialogPrimitive.Content
          className="workbench-dialog fixed left-[50%] top-[50%] z-50 w-[95vw] max-w-6xl h-[85vh] border bg-background shadow-lg rounded-2xl p-0 flex flex-col overflow-hidden"
        >
          {/* ── Header ─────────────────────────────────────────── */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-border/40 shrink-0">
            <DialogTitle className="flex items-center gap-2 text-sm font-semibold">
              <SlidersHorizontal className="h-4 w-4 text-primary" />
              What-If Workbench
            </DialogTitle>
            <DialogPrimitive.Close className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2">
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </DialogPrimitive.Close>
          </div>

          {/* ── Compartment Tab Bar ────────────────────────────── */}
          <div className="grid grid-cols-4 border-b border-border/40 bg-muted/20 shrink-0">
            {COMPARTMENTS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveCompartment(tab.id)}
                className={cn(
                  'flex items-center justify-center gap-2 py-2.5 text-xs font-medium transition-all duration-200',
                  activeCompartment === tab.id
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                )}
              >
                <tab.icon className="h-3.5 w-3.5" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* ── Pending Modifications Summary ──────────────────── */}
          {modifications.length > 0 && (
            <div className="px-5 py-2.5 bg-muted/20 border-b border-border/40 shrink-0">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
                  Pending Balance Modifications
                </span>
                <div className="flex items-center gap-3 text-[10px]">
                  <span className="text-success">Adds: {addCount}</span>
                  <span className="text-muted-foreground">|</span>
                  <span className="text-destructive">Removes: {removeCount}</span>
                  {behaviouralCount > 0 && (
                    <>
                      <span className="text-muted-foreground">|</span>
                      <span className="text-primary">Behavioural: {behaviouralCount}</span>
                    </>
                  )}
                  {pricingCount > 0 && (
                    <>
                      <span className="text-muted-foreground">|</span>
                      <span className="text-orange-600 dark:text-orange-400">Pricing: {pricingCount}</span>
                    </>
                  )}
                  {isApplied && (
                    <>
                      <span className="text-muted-foreground">|</span>
                      <span className="text-success flex items-center gap-0.5">
                        <Check className="h-2.5 w-2.5" /> Applied
                      </span>
                    </>
                  )}
                </div>
              </div>
              <ScrollArea className="max-h-20">
                <div className="flex flex-wrap gap-1.5">
                  {modifications.map((mod) => (
                    <Badge
                      key={mod.id}
                      variant="outline"
                      className={cn(
                        'text-[10px] py-0.5 px-1.5 gap-1',
                        mod.type === 'add'
                          ? 'border-success/50 bg-success/5 text-success'
                          : mod.type === 'remove'
                            ? 'border-destructive/50 bg-destructive/5 text-destructive'
                            : mod.type === 'pricing'
                              ? 'border-orange-400/50 bg-orange-50/50 text-orange-700 dark:bg-orange-950/30 dark:text-orange-400'
                              : 'border-primary/50 bg-primary/5 text-primary',
                      )}
                    >
                      {mod.type === 'add' ? (
                        <Plus className="h-2.5 w-2.5" />
                      ) : mod.type === 'remove' ? (
                        <Minus className="h-2.5 w-2.5" />
                      ) : mod.type === 'pricing' ? (
                        <DollarSign className="h-2.5 w-2.5" />
                      ) : (
                        <Brain className="h-2.5 w-2.5" />
                      )}
                      <span className="max-w-[140px] truncate">{mod.label}</span>
                      {mod.details && (
                        <span className="text-muted-foreground font-mono">({mod.details})</span>
                      )}
                      {mod.type === 'add' && (
                        <button
                          onClick={() => {
                            setEditingModId(mod.id);
                            setActiveCompartment('buy-sell');
                          }}
                          className="ml-0.5 hover:bg-background/50 rounded p-0.5"
                          title="Edit modification"
                        >
                          <Pencil className="h-2.5 w-2.5" />
                        </button>
                      )}
                      <button
                        onClick={() => {
                          removeModification(mod.id);
                          if (editingModId === mod.id) setEditingModId(null);
                        }}
                        className="ml-0.5 hover:bg-background/50 rounded p-0.5"
                      >
                        <X className="h-2.5 w-2.5" />
                      </button>
                    </Badge>
                  ))}
                </div>
              </ScrollArea>
            </div>
          )}

          {/* ── Compartment Content Area ───────────────────────── */}
          <div className="flex-1 min-h-0 relative">
            <div className={cn('absolute inset-0', activeCompartment !== 'buy-sell' && 'hidden')}>
              <BuySellCompartment
                sessionId={sessionId ?? null}
                balanceTree={balanceTree ?? null}
                editingModification={editingModification}
                onEditComplete={() => setEditingModId(null)}
                scenarios={scenarios}
              />
            </div>
            <div className={cn('absolute inset-0', activeCompartment !== 'behavioural' && 'hidden')}>
              <BehaviouralCompartment />
            </div>
            <div className={cn('absolute inset-0', activeCompartment !== 'find-limit' && 'hidden')}>
              <FindLimitCompartment sessionId={sessionId ?? null} />
            </div>
            <div className={cn('absolute inset-0', activeCompartment !== 'pricing' && 'hidden')}>
              <PricingCompartment balanceTree={balanceTree} />
            </div>
          </div>

          {/* ── Footer ─────────────────────────────────────────── */}
          <div className="px-5 py-3 border-t border-border/40 bg-card flex items-center justify-between shrink-0">
            <Button
              variant="outline"
              size="sm"
              className="h-8 text-xs px-4"
              onClick={clearModifications}
              disabled={modifications.length === 0}
            >
              <Trash2 className="h-3.5 w-3.5 mr-2" />
              Clear All
            </Button>
            <Button
              size="sm"
              className="h-8 text-xs px-6"
              onClick={() => {
                applyModifications();
                onOpenChange(false);
              }}
              disabled={modifications.length === 0}
            >
              <Check className="h-3.5 w-3.5 mr-2" />
              Apply to Analysis
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
