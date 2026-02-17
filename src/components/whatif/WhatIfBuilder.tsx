/**
 * WhatIfBuilder.tsx – Side-sheet for building What-If balance modifications.
 *
 * === ROLE IN THE SYSTEM ===
 * Opens as a right-side Sheet when the user clicks the What-If button.
 * Contains two tabs: "Add Position" (WhatIfAddTab) and "Remove Position"
 * (WhatIfRemoveTab). Shows pending modifications as green/red badges.
 * "Apply to Analysis" calls applyModifications() → sets isApplied=true.
 *
 * === CURRENT LIMITATIONS ===
 * - "Apply" only flips a boolean flag in React state. It does NOT trigger
 *   backend calculation. ResultsCard shows HARDCODED impact deltas.
 * - Phase 1: Apply will POST modifications to /api/sessions/{id}/calculate.
 */
import React, { useState } from 'react';
import { X, Plus, Minus, Trash2, Check, SlidersHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { useWhatIf } from './WhatIfContext';
import { WhatIfAddTab } from './WhatIfAddTab';
import { WhatIfRemoveTab } from './WhatIfRemoveTab';
import type { BalanceUiTree } from '@/lib/balanceUi';

interface WhatIfBuilderProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId?: string | null;
  balanceTree?: BalanceUiTree | null;
}

export function WhatIfBuilder({
  open,
  onOpenChange,
  sessionId,
  balanceTree,
}: WhatIfBuilderProps) {
  const [activeTab, setActiveTab] = useState<'add' | 'remove'>('add');
  const { 
    modifications, 
    removeModification, 
    clearModifications, 
    applyModifications,
    isApplied,
    addCount, 
    removeCount 
  } = useWhatIf();

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[420px] sm:w-[480px] flex flex-col p-0">
        <SheetHeader className="px-4 py-3 border-b border-border shrink-0">
          <SheetTitle className="flex items-center gap-2 text-sm">
            <SlidersHorizontal className="h-4 w-4 text-primary" />
            Balance What-If Builder
          </SheetTitle>
        </SheetHeader>

        {/* Pending Modifications Summary */}
        <div className="px-4 py-2 bg-muted/30 border-b border-border shrink-0">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide">
              Pending Balance Modifications
            </span>
            <div className="flex items-center gap-2 text-[10px]">
              <span className="text-success">Adds: {addCount}</span>
              <span className="text-muted-foreground">|</span>
              <span className="text-destructive">Removes: {removeCount}</span>
            </div>
          </div>

          {modifications.length > 0 ? (
            <ScrollArea className="max-h-32">
              <div className="flex flex-wrap gap-1.5">
                {modifications.map(mod => (
                  <Badge
                    key={mod.id}
                    variant="outline"
                    className={`text-[10px] py-0.5 px-1.5 gap-1 ${
                      mod.type === 'add' 
                        ? 'border-success/50 bg-success/5 text-success' 
                        : 'border-destructive/50 bg-destructive/5 text-destructive'
                    }`}
                  >
                    {mod.type === 'add' ? <Plus className="h-2.5 w-2.5" /> : <Minus className="h-2.5 w-2.5" />}
                    <span className="max-w-[120px] truncate">{mod.label}</span>
                    {mod.details && (
                      <span className="text-muted-foreground font-mono">({mod.details})</span>
                    )}
                    <button
                      onClick={() => removeModification(mod.id)}
                      className="ml-0.5 hover:bg-background/50 rounded p-0.5"
                    >
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </Badge>
                ))}
              </div>
            </ScrollArea>
          ) : (
            <p className="text-[10px] text-muted-foreground italic">
              No modifications yet. Add or remove positions below.
            </p>
          )}

          {isApplied && modifications.length > 0 && (
            <div className="flex items-center gap-1 mt-2 text-[10px] text-success">
              <Check className="h-3 w-3" />
              <span>Modifications applied to analysis</span>
            </div>
          )}
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'add' | 'remove')} className="flex-1 flex flex-col min-h-0">
          <TabsList className="mx-4 mt-3 grid grid-cols-2 h-8">
            <TabsTrigger value="add" className="text-xs gap-1.5">
              <Plus className="h-3 w-3" />
              Add Position
            </TabsTrigger>
            <TabsTrigger value="remove" className="text-xs gap-1.5">
              <Minus className="h-3 w-3" />
              Remove Position
            </TabsTrigger>
          </TabsList>

          <TabsContent value="add" className="flex-1 px-4 py-3 m-0 min-h-0">
            <WhatIfAddTab />
          </TabsContent>

          <TabsContent value="remove" className="flex-1 px-4 py-3 m-0 min-h-0">
            <WhatIfRemoveTab
              sessionId={sessionId ?? null}
              balanceTree={balanceTree ?? null}
            />
          </TabsContent>
        </Tabs>

        {/* Action Buttons */}
        <div className="px-4 py-3 border-t border-border bg-muted/20 flex gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 h-8 text-xs"
            onClick={clearModifications}
            disabled={modifications.length === 0}
          >
            <Trash2 className="h-3 w-3 mr-1.5" />
            Clear All
          </Button>
          <Button
            size="sm"
            className="flex-1 h-8 text-xs"
            onClick={() => {
              applyModifications();
              onOpenChange(false);
            }}
            disabled={modifications.length === 0}
          >
            <Check className="h-3 w-3 mr-1.5" />
            Apply to Analysis
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
