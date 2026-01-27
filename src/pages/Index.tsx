import React, { useState, useCallback } from 'react';
import { BalancePositionsCard } from '@/components/BalancePositionsCard';
import { InterestRateCurvesCard } from '@/components/InterestRateCurvesCard';
import { ScenariosCard } from '@/components/ScenariosCard';
import { ResultsCard } from '@/components/ResultsCard';
import { runCalculation } from '@/lib/calculationEngine';
import type { Position, YieldCurve, Scenario, CalculationResults } from '@/types/financial';
import { DEFAULT_SCENARIOS, SAMPLE_POSITIONS, SAMPLE_YIELD_CURVE } from '@/types/financial';
import { Button } from '@/components/ui/button';
import { FileSpreadsheet, Calculator, TrendingUp } from 'lucide-react';

const Index = () => {
  // State management
  const [positions, setPositions] = useState<Position[]>([]);
  const [curves, setCurves] = useState<YieldCurve[]>([]);
  const [selectedBaseCurve, setSelectedBaseCurve] = useState<string | null>(null);
  const [selectedDiscountCurve, setSelectedDiscountCurve] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>(DEFAULT_SCENARIOS);
  const [results, setResults] = useState<CalculationResults | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);

  // Check if calculation is possible
  const canCalculate = 
    positions.length > 0 && 
    curves.length > 0 && 
    selectedBaseCurve !== null &&
    selectedDiscountCurve !== null &&
    scenarios.some((s) => s.enabled);

  // Handle calculation
  const handleCalculate = useCallback(() => {
    if (!canCalculate) return;

    const baseCurve = curves.find((c) => c.id === selectedBaseCurve);
    const discountCurve = curves.find((c) => c.id === selectedDiscountCurve);

    if (!baseCurve || !discountCurve) return;

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
  }, [canCalculate, positions, curves, selectedBaseCurve, selectedDiscountCurve, scenarios]);

  // Load sample data
  const handleLoadSampleData = useCallback(() => {
    setPositions(SAMPLE_POSITIONS);
    setCurves([SAMPLE_YIELD_CURVE]);
    setSelectedBaseCurve(SAMPLE_YIELD_CURVE.id);
    setSelectedDiscountCurve(SAMPLE_YIELD_CURVE.id);
  }, []);

  return (
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

      {/* 2x2 Dashboard Grid */}
      <main className="flex-1 p-3 overflow-hidden">
        <div className="grid grid-cols-2 grid-rows-2 gap-3 h-full">
          <BalancePositionsCard
            positions={positions}
            onPositionsChange={setPositions}
          />
          <InterestRateCurvesCard
            curves={curves}
            selectedBaseCurve={selectedBaseCurve}
            selectedDiscountCurve={selectedDiscountCurve}
            onCurvesChange={setCurves}
            onBaseCurveSelect={setSelectedBaseCurve}
            onDiscountCurveSelect={setSelectedDiscountCurve}
          />
          <ScenariosCard
            scenarios={scenarios}
            onScenariosChange={setScenarios}
          />
          <ResultsCard
            results={results}
            isCalculating={isCalculating}
          />
        </div>
      </main>

      {/* Minimal Footer */}
      <footer className="shrink-0 border-t border-border bg-card py-1.5 px-4">
        <p className="text-[10px] text-muted-foreground text-center">
          Illustrative IRRBB prototype • Results are indicative only
        </p>
      </footer>
    </div>
  );
};

export default Index;