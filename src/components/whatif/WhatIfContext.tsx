/**
 * WhatIfContext.tsx – Global state for the What-If modification system.
 *
 * ── ROLE IN THE SYSTEM ────────────────────────────────────────────────
 *
 *   Central store for all hypothetical balance modifications. Consumed by:
 *
 *   • WhatIfWorkbench: Reads/writes modifications (add/remove/edit/clear)
 *   • BalancePositionsCard: Shows green/red delta overlays on the balance tree
 *   • ResultsCard: Sends modifications to backend for EVE/NII calculation
 *   • EVEChart: Adjusts visualization bars based on What-If deltas
 *
 * ── STATE ─────────────────────────────────────────────────────────────
 *
 *   modifications[]:  Array of WhatIfModification (add/remove/behavioural/pricing)
 *   isApplied:        Whether the user clicked "Apply to Analysis"
 *   applyCounter:     Monotonic counter — increments only on explicit Apply clicks.
 *                     ResultsCard watches this (not isApplied) to trigger calculation.
 *   analysisDate:     Date for chart calendar labels
 *   cet1Capital:      CET1 capital amount for %CET1 calculations
 *
 * ── LIFECYCLE ─────────────────────────────────────────────────────────
 *
 *   1. User adds modifications → isApplied becomes false (stale results)
 *   2. User clicks "Apply to Analysis" → isApplied=true, applyCounter++
 *   3. ResultsCard detects applyCounter change → sends to backend
 *   4. User edits/removes a modification → isApplied goes back to false
 *   5. Modifications are ephemeral (React state only, lost on refresh)
 *
 * ── NOTES ─────────────────────────────────────────────────────────────
 *
 *   • Scenarios are NOT stored here — they live in Index.tsx and are
 *     threaded as props to components that need them.
 *   • Each modification gets a unique ID: `${type}-${timestamp}-${random}`
 */

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import type { WhatIfModification } from '@/types/whatif';

interface WhatIfContextType {
  modifications: WhatIfModification[];
  addModification: (mod: Omit<WhatIfModification, 'id'>) => void;
  updateModification: (id: string, mod: Omit<WhatIfModification, 'id'>) => void;
  removeModification: (id: string) => void;
  clearModifications: () => void;
  isApplied: boolean;
  applyModifications: () => void;
  /** Monotonic counter incremented only on explicit "Apply to Analysis" clicks. */
  applyCounter: number;
  addCount: number;
  removeCount: number;
  behaviouralCount: number;
  pricingCount: number;
  // New: Analysis Date & CET1 Capital
  analysisDate: Date | null;
  setAnalysisDate: (date: Date | null) => void;
  cet1Capital: number | null;
  setCet1Capital: (value: number | null) => void;
  // Reset all
  resetAll: () => void;
}

const WhatIfContext = createContext<WhatIfContextType | null>(null);

export function WhatIfProvider({ children }: { children: ReactNode }) {
  const [modifications, setModifications] = useState<WhatIfModification[]>([]);
  const [isApplied, setIsApplied] = useState(false);
  const [applyCounter, setApplyCounter] = useState(0);
  const [analysisDate, setAnalysisDate] = useState<Date | null>(new Date());
  const [cet1Capital, setCet1Capital] = useState<number | null>(null);

  const addModification = useCallback((mod: Omit<WhatIfModification, 'id'>) => {
    const id = `${mod.type}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setModifications(prev => [...prev, { ...mod, id }]);
    setIsApplied(false);
  }, []);

  const updateModification = useCallback((id: string, mod: Omit<WhatIfModification, 'id'>) => {
    setModifications(prev => prev.map(m => m.id === id ? { ...mod, id } : m));
    setIsApplied(false);
  }, []);

  const removeModification = useCallback((id: string) => {
    setModifications(prev => prev.filter(m => m.id !== id));
    setIsApplied(false);
  }, []);

  const clearModifications = useCallback(() => {
    setModifications([]);
    setIsApplied(false);
  }, []);

  const applyModifications = useCallback(() => {
    setIsApplied(true);
    setApplyCounter(prev => prev + 1);
  }, []);

  const resetAll = useCallback(() => {
    setModifications([]);
    setIsApplied(false);
    setApplyCounter(0);
    setAnalysisDate(new Date());
    setCet1Capital(null);
  }, []);

  const addCount = modifications.filter(m => m.type === 'add').length;
  const removeCount = modifications.filter(m => m.type === 'remove').length;
  const behaviouralCount = modifications.filter(m => m.type === 'behavioural').length;
  const pricingCount = modifications.filter(m => m.type === 'pricing').length;

  return (
    <WhatIfContext.Provider value={{
      modifications,
      addModification,
      updateModification,
      removeModification,
      clearModifications,
      isApplied,
      applyModifications,
      applyCounter,
      addCount,
      removeCount,
      behaviouralCount,
      pricingCount,
      analysisDate,
      setAnalysisDate,
      cet1Capital,
      setCet1Capital,
      resetAll,
    }}>
      {children}
    </WhatIfContext.Provider>
  );
}

export function useWhatIf() {
  const context = useContext(WhatIfContext);
  if (!context) {
    throw new Error('useWhatIf must be used within a WhatIfProvider');
  }
  return context;
}
