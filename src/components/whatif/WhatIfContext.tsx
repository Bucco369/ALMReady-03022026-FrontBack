/**
 * WhatIfContext.tsx – Global state for the What-If modification system.
 *
 * === ROLE IN THE SYSTEM ===
 * Manages a list of hypothetical balance modifications (adds/removes) that
 * the user builds through the WhatIfBuilder side-sheet. The state is consumed by:
 * - BalancePositionsCard: Shows green/red delta overlays on the balance tree.
 * - ResultsCard: Shows What-If impact columns (currently HARDCODED mock values).
 * - EVEChart: Adjusts visualization bars based on What-If asset/liability deltas.
 *
 * === STATE ===
 * - modifications[]: Array of WhatIfModification (add/remove entries)
 * - isApplied: Whether the user clicked "Apply to Analysis"
 * - analysisDate: Optional date for calendar label display in charts
 * - cet1Capital: CET1 capital amount for %CET1 calculations in ResultsCard
 *
 * === BACKEND INTEGRATION ===
 * When isApplied becomes true, ResultsCard sends the modifications array
 * to POST /api/sessions/{id}/calculate/whatif. The backend runs EVE/NII
 * only on the delta positions and returns 4 impact values.
 * Modifications exist in React state and are lost on page refresh.
 */

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import type { WhatIfModification } from '@/types/whatif';

interface WhatIfContextType {
  modifications: WhatIfModification[];
  addModification: (mod: Omit<WhatIfModification, 'id'>) => void;
  removeModification: (id: string) => void;
  clearModifications: () => void;
  isApplied: boolean;
  applyModifications: () => void;
  addCount: number;
  removeCount: number;
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
  const [analysisDate, setAnalysisDate] = useState<Date | null>(null);
  const [cet1Capital, setCet1Capital] = useState<number | null>(null);

  const addModification = useCallback((mod: Omit<WhatIfModification, 'id'>) => {
    const id = `${mod.type}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setModifications(prev => [...prev, { ...mod, id }]);
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
  }, []);

  const resetAll = useCallback(() => {
    setModifications([]);
    setIsApplied(false);
    setAnalysisDate(null);
    setCet1Capital(null);
  }, []);

  const addCount = modifications.filter(m => m.type === 'add').length;
  const removeCount = modifications.filter(m => m.type === 'remove').length;

  return (
    <WhatIfContext.Provider value={{
      modifications,
      addModification,
      removeModification,
      clearModifications,
      isApplied,
      applyModifications,
      addCount,
      removeCount,
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
