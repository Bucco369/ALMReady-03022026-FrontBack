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
 * === CALCULATION FLOW ===
 * handleCalculate() calls POST /api/sessions/{id}/calculate on the backend,
 * which runs EVE/NII via the ALMReady motor engine. The backend requires:
 * - Balance positions uploaded via /balance or /balance/zip
 * - Yield curves uploaded via /curves
 * The response is mapped from the backend's snake_case schema to the
 * frontend's camelCase CalculationResults interface.
 *
 * Falls back to the local calculationEngine.ts if no session is available
 * (e.g. when using sample data without a backend connection).
 */

import React, { useState, useCallback, useRef } from 'react';
import { BalancePositionsCardConnected } from '@/components/connected/BalancePositionsCardConnected';
import { CurvesAndScenariosCard } from '@/components/CurvesAndScenariosCard';
import { ResultsCard } from '@/components/ResultsCard';
import { WhatIfProvider } from '@/components/whatif/WhatIfContext';
import { BehaviouralProvider } from '@/components/behavioural/BehaviouralContext';
import { useSession } from '@/hooks/useSession';
import { calculateEveNii, getCalcProgress } from '@/lib/api';
import { runCalculation } from '@/lib/calculationEngine';
import { useProgressETA } from '@/hooks/useProgressETA';
import type { Position, YieldCurve, Scenario, CalculationResults } from '@/types/financial';
import { DEFAULT_SCENARIOS, SAMPLE_YIELD_CURVE } from '@/types/financial';
import { Button } from '@/components/ui/button';
import { Calculator } from 'lucide-react';

const Index = () => {
  // ─── Top-level application state ───────────────────────────────────────
  const [positions, setPositions] = useState<Position[]>([]);
  const [curves, setCurves] = useState<YieldCurve[]>([]);
  const [selectedCurves, setSelectedCurves] = useState<string[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>(DEFAULT_SCENARIOS);
  const [results, setResults] = useState<CalculationResults | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [calcProgress, setCalcProgress] = useState(0);
  const [calcPhase, setCalcPhase] = useState('');
  const calcPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { sessionId, sessionMeta } = useSession();

  const calcEta = useProgressETA(calcProgress, isCalculating);

  // Called by child components when balance or curves are deleted.
  // Invalidates calculation results since they depend on the deleted data.
  const handleDataReset = useCallback(() => {
    setResults(null);
  }, []);

  // All 3 conditions must be met to enable the Calculate button.
  const canCalculate =
    positions.length > 0 &&
    selectedCurves.length > 0 &&
    scenarios.some((s) => s.enabled);

  // ─── Calculation handler ───────────────────────────────────────────────
  // Calls the backend /calculate endpoint when a session is available.
  // Falls back to the local engine for demo/offline usage.
  const handleCalculate = useCallback(async () => {
    if (!canCalculate) return;

    const enabledScenarios = sessionId
      ? scenarios.filter((s) => s.enabled).map((s) => s.id)
      : [];

    setIsCalculating(true);
    setCalcProgress(0);
    setCalcPhase('');

    // Clean up any leftover poll timer
    if (calcPollRef.current) {
      clearInterval(calcPollRef.current);
      calcPollRef.current = null;
    }

    // Start polling backend for real-time calculation progress
    if (sessionId) {
      calcPollRef.current = setInterval(async () => {
        try {
          const p = await getCalcProgress(sessionId);
          if (p.phase !== 'idle') {
            // Monotonicity: never let progress decrease
            setCalcProgress(prev => Math.max(prev, p.pct));
            if (p.phase_label) setCalcPhase(p.phase_label);
          }
        } catch {
          // Ignore transient poll errors
        }
      }, 500);
    }

    try {
      if (sessionId) {
        // Backend calculation via ALMReady motor
        const response = await calculateEveNii(sessionId, {
          scenarios: enabledScenarios,
          discount_curve_id: selectedCurves[0] || "EUR_ESTR_OIS",
        });

        // Map backend snake_case → frontend camelCase CalculationResults
        const calculationResults: CalculationResults = {
          baseEve: response.base_eve,
          baseNii: response.base_nii,
          worstCaseEve: response.worst_case_eve,
          worstCaseDeltaEve: response.worst_case_delta_eve,
          worstCaseScenario: response.worst_case_scenario,
          scenarioResults: response.scenario_results.map((sr) => ({
            scenarioId: sr.scenario_id,
            scenarioName: sr.scenario_name,
            eve: sr.eve,
            nii: sr.nii,
            deltaEve: sr.delta_eve,
            deltaNii: sr.delta_nii,
          })),
          calculatedAt: response.calculated_at,
        };

        setResults(calculationResults);
      } else {
        // Fallback: local calculation engine (demo/offline mode)
        const baseCurve = curves.length > 0 ? curves[0] : SAMPLE_YIELD_CURVE;
        const calculationResults = runCalculation(
          positions,
          baseCurve,
          baseCurve,
          scenarios
        );
        setResults(calculationResults);
      }
    } catch (err) {
      console.error("Calculation failed:", err);
      // TODO: show user-facing error toast
    } finally {
      if (calcPollRef.current) {
        clearInterval(calcPollRef.current);
        calcPollRef.current = null;
      }
      setCalcProgress(100);
      setCalcPhase('');
      // Brief pause at 100% before hiding the bar
      setTimeout(() => {
        setIsCalculating(false);
        setCalcProgress(0);
      }, 400);
    }
  }, [canCalculate, sessionId, positions, curves, selectedCurves, scenarios]);

  return (
    <BehaviouralProvider>
      <WhatIfProvider>
      <div className="h-screen flex flex-col bg-background overflow-hidden">
        {/* Apple-style Glass Header */}
        <header className="shrink-0 bg-white/70 backdrop-blur-xl border-b border-border/50 sticky top-0 z-50">
          <div className="flex items-center justify-between px-5 py-3">
            <div className="flex items-center gap-3">
              <img src="/logo.svg" alt="ALMReady" className="h-8 w-8" />
              <div>
                <h1 className="text-sm font-semibold text-foreground leading-tight tracking-tight">ALMReady</h1>
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
          <div className="grid grid-cols-2 gap-3 h-full" style={{gridTemplateRows: '1fr 1fr'}}>
            {/* Top-left: Balance Positions */}
            <BalancePositionsCardConnected
              positions={positions}
              onPositionsChange={setPositions}
              sessionId={sessionId}
              hasBalance={sessionMeta?.has_balance ?? false}
              onDataReset={handleDataReset}
            />

            {/* Top-right: Curves & Scenarios (merged) */}
            <CurvesAndScenariosCard
              scenarios={scenarios}
              onScenariosChange={setScenarios}
              selectedCurves={selectedCurves}
              onSelectedCurvesChange={setSelectedCurves}
              sessionId={sessionId}
              hasCurves={sessionMeta?.has_curves ?? false}
              onDataReset={handleDataReset}
            />

            {/* Bottom: Results (spans full width) */}
            <div className="col-span-2 h-full">
              <ResultsCard
                results={results}
                isCalculating={isCalculating}
                calcProgress={calcProgress}
                calcPhase={calcPhase}
                calcEta={calcEta}
                sessionId={sessionId}
                scenarios={scenarios}
              />
            </div>
          </div>
        </main>

      </div>
      </WhatIfProvider>
    </BehaviouralProvider>
  );
};

export default Index;
