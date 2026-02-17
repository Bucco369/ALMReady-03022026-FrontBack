/**
 * Index.tsx – Main orchestrator page for the ALMReady IRRBB dashboard.
 *
 * === ROLE IN THE SYSTEM ===
 * This is the ROOT COMPONENT of the application. It:
 * 1. Holds the top-level state: positions, curves, scenarios, results.
 * 2. Wraps everything in BehaviouralProvider and WhatIfProvider contexts.
 * 3. Renders the 3-quadrant dashboard layout:
 *    - Top-left: BalancePositionsCardConnected (balance upload + tree view)
 *    - Top-right: CurvesAndScenariosCard (curves upload + scenario toggles)
 *    - Bottom: ResultsCard (EVE/NII results + charts)
 * 4. Owns the "Calculate EVE & NII" button and orchestrates the calculation.
 *
 * === CURRENT LIMITATIONS ===
 * - CALCULATION IS LOCAL: handleCalculate() calls runCalculation() from
 *   calculationEngine.ts, which is a simplified frontend-only engine.
 *   Phase 1 will replace this with a POST /api/sessions/{id}/calculate
 *   call to the backend, which delegates to the external Python engine.
 * - NO WHAT-IF IN CALCULATION: The What-If overlay (WhatIfContext) is not
 *   passed to the calculation. Phase 1 will send modifications to the backend.
 * - NO BEHAVIOURAL IN CALCULATION: BehaviouralContext params are not used.
 * - SAMPLE CURVE FALLBACK: If no curves are uploaded, a hardcoded USD sample
 *   curve is used. This is a demo convenience, not production behavior.
 * - SYNCHRONOUS FEEL: setTimeout(500ms) simulates async; the real backend
 *   call will be genuinely async and may take seconds for large balances.
 */

import React, { useState, useCallback } from 'react';
import { BalancePositionsCardConnected } from '@/components/connected/BalancePositionsCardConnected';
import { CurvesAndScenariosCard } from '@/components/CurvesAndScenariosCard';
import { ResultsCard } from '@/components/ResultsCard';
import { WhatIfProvider } from '@/components/whatif/WhatIfContext';
import { BehaviouralProvider } from '@/components/behavioural/BehaviouralContext';
import { runCalculation } from '@/lib/calculationEngine';
import type { Position, YieldCurve, Scenario, CalculationResults } from '@/types/financial';
import { DEFAULT_SCENARIOS, SAMPLE_YIELD_CURVE } from '@/types/financial';
import { Button } from '@/components/ui/button';
import { Calculator, TrendingUp } from 'lucide-react';

const Index = () => {
  // ─── Top-level application state ───────────────────────────────────────
  // These are the 4 inputs needed for calculation + the result output.
  // Each child card "owns" one input and reports changes via callbacks.
  const [positions, setPositions] = useState<Position[]>([]);
  const [curves, setCurves] = useState<YieldCurve[]>([]);
  const [selectedCurves, setSelectedCurves] = useState<string[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>(DEFAULT_SCENARIOS);
  const [results, setResults] = useState<CalculationResults | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);

  // All 3 conditions must be met to enable the Calculate button.
  const canCalculate =
    positions.length > 0 &&
    selectedCurves.length > 0 &&
    scenarios.some((s) => s.enabled);

  // ─── Calculation handler ───────────────────────────────────────────────
  // LIMITATION: This runs the SIMPLIFIED LOCAL engine (calculationEngine.ts).
  // Phase 1 will replace this with: await calculateEveNii(sessionId, request)
  // which calls POST /api/sessions/{id}/calculate on the backend.
  const handleCalculate = useCallback(() => {
    if (!canCalculate) return;

    // Fallback to sample curve if user hasn't uploaded real curves
    const baseCurve = curves.length > 0 ? curves[0] : SAMPLE_YIELD_CURVE;
    const discountCurve = baseCurve;

    setIsCalculating(true);

    // setTimeout simulates async; will become a real await in Phase 1
    setTimeout(() => {
      const calculationResults = runCalculation(
        positions,
        baseCurve,
        discountCurve,
        scenarios
      );
      setResults(calculationResults);
      setIsCalculating(false);
    }, 500);
  }, [canCalculate, positions, curves, scenarios]);

  return (
    <BehaviouralProvider>
      <WhatIfProvider>
      <div className="h-screen flex flex-col bg-background overflow-hidden">
        {/* Apple-style Glass Header */}
        <header className="shrink-0 bg-white/70 backdrop-blur-xl border-b border-border/50 sticky top-0 z-50">
          <div className="flex items-center justify-between px-5 py-3">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary shadow-sm">
                <TrendingUp className="h-4 w-4 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-sm font-semibold text-foreground leading-tight tracking-tight">EVE/NII Calculator</h1>
                <p className="text-[11px] text-muted-foreground leading-tight">IRRBB Analysis Dashboard</p>
              </div>
            </div>
            
            <div className="flex items-center gap-2.5">
              <Button
                size="sm"
                className="h-8 text-xs gap-2 rounded-lg shadow-sm transition-all duration-200 hover:shadow-md"
                onClick={handleCalculate}
                disabled={!canCalculate || isCalculating}
              >
                {isCalculating ? (
                  <>
                    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
                    Calculating...
                  </>
                ) : (
                  <>
                    <Calculator className="h-3.5 w-3.5" />
                    Calculate EVE & NII
                  </>
                )}
              </Button>
            </div>
          </div>
        </header>

        {/* Dashboard Grid - 3 quadrants: 1 left, 2 stacked right */}
        <main className="flex-1 p-3 overflow-hidden">
          <div className="grid grid-cols-2 grid-rows-2 gap-3 h-full">
            {/* Top-left: Balance Positions */}
            <BalancePositionsCardConnected
              positions={positions}
              onPositionsChange={setPositions}
            />
            
            {/* Top-right: Curves & Scenarios (merged) */}
            <CurvesAndScenariosCard
              scenarios={scenarios}
              onScenariosChange={setScenarios}
              selectedCurves={selectedCurves}
              onSelectedCurvesChange={setSelectedCurves}
            />
            
            {/* Bottom: Results (spans full width) */}
            <div className="col-span-2">
              <ResultsCard
                results={results}
                isCalculating={isCalculating}
              />
            </div>
          </div>
        </main>

        {/* Apple-style Footer */}
        <footer className="shrink-0 border-t border-border/40 bg-white/50 backdrop-blur-sm py-2 px-5">
          <p className="text-[11px] text-muted-foreground text-center font-normal">
            Illustrative IRRBB prototype • Results are indicative only
          </p>
        </footer>
      </div>
      </WhatIfProvider>
    </BehaviouralProvider>
  );
};

export default Index;
