import React, { useState, useCallback } from 'react';
import { BalanceUploader } from '@/components/BalanceUploader';
import { InterestRateCurveUploader } from '@/components/InterestRateCurveUploader';
import { ScenarioSelector } from '@/components/ScenarioSelector';
import { CalculateButton } from '@/components/CalculateButton';
import { ResultsDisplay } from '@/components/ResultsDisplay';
import { runCalculation } from '@/lib/calculationEngine';
import type { Position, YieldCurve, Scenario, CalculationResults } from '@/types/financial';
import { DEFAULT_SCENARIOS, SAMPLE_POSITIONS, SAMPLE_YIELD_CURVE } from '@/types/financial';
import { Button } from '@/components/ui/button';
import { FileSpreadsheet, TrendingUp } from 'lucide-react';

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
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="container mx-auto flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary">
              <TrendingUp className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground">EVE/NII Calculator</h1>
              <p className="text-xs text-muted-foreground">
                Interest Rate Risk in the Banking Book
              </p>
            </div>
          </div>
          
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadSampleData}
            className="gap-2"
          >
            <FileSpreadsheet className="h-4 w-4" />
            Load Sample Data
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left Column - Inputs */}
          <div className="space-y-6">
            <BalanceUploader
              positions={positions}
              onPositionsChange={setPositions}
            />
            
            <InterestRateCurveUploader
              curves={curves}
              selectedBaseCurve={selectedBaseCurve}
              selectedDiscountCurve={selectedDiscountCurve}
              onCurvesChange={setCurves}
              onBaseCurveSelect={setSelectedBaseCurve}
              onDiscountCurveSelect={setSelectedDiscountCurve}
            />
          </div>

          {/* Right Column - Scenarios & Results */}
          <div className="space-y-6">
            <ScenarioSelector
              scenarios={scenarios}
              onScenariosChange={setScenarios}
            />

            <CalculateButton
              onClick={handleCalculate}
              disabled={!canCalculate}
              isCalculating={isCalculating}
            />

            <ResultsDisplay
              results={results}
              isCalculating={isCalculating}
            />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border bg-card py-4">
        <div className="container mx-auto px-6 text-center text-xs text-muted-foreground">
          EVE/NII Calculator • Prototype for regulatory IRRBB analysis
        </div>
      </footer>
    </div>
  );
};

export default Index;
