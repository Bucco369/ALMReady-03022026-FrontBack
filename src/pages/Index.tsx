import React, { useState, useCallback } from 'react';
import { BalancePositionsCard } from '@/components/BalancePositionsCard';
import { CurvesAndScenariosCard } from '@/components/CurvesAndScenariosCard';
import { ResultsCard } from '@/components/ResultsCard';
import { WhatIfProvider } from '@/components/whatif/WhatIfContext';
import { runCalculation } from '@/lib/calculationEngine';
import type { Position, YieldCurve, Scenario, CalculationResults } from '@/types/financial';
import { DEFAULT_SCENARIOS, SAMPLE_POSITIONS, SAMPLE_YIELD_CURVE } from '@/types/financial';
import { Button } from '@/components/ui/button';
import { FileSpreadsheet, Calculator, TrendingUp } from 'lucide-react';

const Index = () => {
  // State management
  const [positions, setPositions] = useState<Position[]>([]);
  const [curves, setCurves] = useState<YieldCurve[]>([]);
  const [selectedCurves, setSelectedCurves] = useState<string[]>(['risk-free', 'euribor-3m']);
  const [scenarios, setScenarios] = useState<Scenario[]>(DEFAULT_SCENARIOS);
  const [results, setResults] = useState<CalculationResults | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);

  // Check if calculation is possible
  const canCalculate = 
    positions.length > 0 && 
    selectedCurves.length > 0 &&
    scenarios.some((s) => s.enabled);

  // Handle calculation
  const handleCalculate = useCallback(() => {
    if (!canCalculate) return;

    // Use sample curve for calculation (placeholder)
    const baseCurve = curves.length > 0 ? curves[0] : SAMPLE_YIELD_CURVE;
    const discountCurve = baseCurve;

    setIsCalculating(true);
    
    // Simulate async calculation
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

  // Load sample data
  const handleLoadSampleData = useCallback(() => {
    setPositions(SAMPLE_POSITIONS);
    setCurves([SAMPLE_YIELD_CURVE]);
  }, []);

  return (
    <WhatIfProvider>
      <div className="h-screen flex flex-col bg-background overflow-hidden">
        {/* Compact Header */}
        <header className="shrink-0 border-b border-border bg-card">
          <div className="flex items-center justify-between px-4 py-2">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
                <TrendingUp className="h-3.5 w-3.5 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-sm font-semibold text-foreground leading-tight">EVE/NII Calculator</h1>
                <p className="text-[10px] text-muted-foreground leading-tight">IRRBB Analysis Dashboard</p>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleLoadSampleData}
                className="h-7 text-xs gap-1.5"
              >
                <FileSpreadsheet className="h-3.5 w-3.5" />
                Load Sample
              </Button>
              <Button
                size="sm"
                className="h-7 text-xs gap-1.5"
                onClick={handleCalculate}
                disabled={!canCalculate || isCalculating}
              >
                {isCalculating ? (
                  <>
                    <div className="h-3 w-3 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
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
            <BalancePositionsCard
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

        {/* Minimal Footer */}
        <footer className="shrink-0 border-t border-border bg-card py-1.5 px-4">
          <p className="text-[10px] text-muted-foreground text-center">
            Illustrative IRRBB prototype • Results are indicative only
          </p>
        </footer>
      </div>
    </WhatIfProvider>
  );
};

export default Index;