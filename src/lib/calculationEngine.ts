import type {
  Position,
  YieldCurve,
  Scenario,
  Cashflow,
  DiscountedCashflow,
  ScenarioResult,
  CalculationResults,
} from '@/types/financial';

/**
 * Generate cash flows for a given position
 * This is a simplified stub that creates annual cash flows
 */
export function generateCashflows(position: Position): Cashflow[] {
  const cashflows: Cashflow[] = [];
  const today = new Date();
  const maturity = new Date(position.maturityDate);
  
  // Calculate years to maturity
  const yearsToMaturity = Math.max(
    0,
    (maturity.getTime() - today.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
  );
  
  // Generate annual interest payments
  for (let year = 1; year <= Math.ceil(yearsToMaturity); year++) {
    const paymentDate = new Date(today);
    paymentDate.setFullYear(paymentDate.getFullYear() + year);
    
    if (paymentDate <= maturity) {
      cashflows.push({
        positionId: position.id,
        date: paymentDate.toISOString().split('T')[0],
        amount: position.notional * position.couponRate * (position.instrumentType === 'Liability' ? -1 : 1),
        type: 'Interest',
      });
    }
  }
  
  // Add principal at maturity
  cashflows.push({
    positionId: position.id,
    date: position.maturityDate,
    amount: position.notional * (position.instrumentType === 'Liability' ? -1 : 1),
    type: 'Principal',
  });
  
  return cashflows;
}

/**
 * Get interpolated rate from yield curve for a given time
 */
function getInterpolatedRate(curve: YieldCurve, yearsToMaturity: number): number {
  const points = curve.points.sort((a, b) => a.tenorYears - b.tenorYears);
  
  // Handle edge cases
  if (yearsToMaturity <= points[0].tenorYears) {
    return points[0].rate;
  }
  if (yearsToMaturity >= points[points.length - 1].tenorYears) {
    return points[points.length - 1].rate;
  }
  
  // Linear interpolation
  for (let i = 0; i < points.length - 1; i++) {
    if (yearsToMaturity >= points[i].tenorYears && yearsToMaturity <= points[i + 1].tenorYears) {
      const t = (yearsToMaturity - points[i].tenorYears) / (points[i + 1].tenorYears - points[i].tenorYears);
      return points[i].rate + t * (points[i + 1].rate - points[i].rate);
    }
  }
  
  return points[0].rate;
}

/**
 * Apply scenario shock to yield curve
 */
function applyScenarioShock(curve: YieldCurve, scenario: Scenario): YieldCurve {
  const shockedCurve = { ...curve, points: [...curve.points] };
  const shockDecimal = scenario.shockBps / 10000;
  
  shockedCurve.points = curve.points.map((point) => {
    let shock = shockDecimal;
    
    // Apply different shocks based on scenario type
    switch (scenario.name) {
      case 'Steepener':
        // Short rates down, long rates up
        shock = point.tenorYears <= 2 ? -shockDecimal : shockDecimal * (point.tenorYears / 10);
        break;
      case 'Flattener':
        // Short rates up, long rates down
        shock = point.tenorYears <= 2 ? shockDecimal : -shockDecimal * (point.tenorYears / 10);
        break;
      case 'Short Up':
        // Only shock short end
        shock = point.tenorYears <= 3 ? shockDecimal * Math.max(0, (3 - point.tenorYears) / 3) : 0;
        break;
      case 'Short Down':
        // Only shock short end
        shock = point.tenorYears <= 3 ? shockDecimal * Math.max(0, (3 - point.tenorYears) / 3) : 0;
        break;
      default:
        // Parallel shift
        shock = shockDecimal;
    }
    
    return {
      ...point,
      rate: Math.max(0, point.rate + shock), // Floor at 0
    };
  });
  
  return shockedCurve;
}

/**
 * Discount cash flows using the given yield curve
 */
export function discountCashflows(
  cashflows: Cashflow[],
  curve: YieldCurve
): DiscountedCashflow[] {
  const today = new Date();
  
  return cashflows.map((cf) => {
    const cfDate = new Date(cf.date);
    const yearsToPayment = Math.max(
      0,
      (cfDate.getTime() - today.getTime()) / (365.25 * 24 * 60 * 60 * 1000)
    );
    
    const rate = getInterpolatedRate(curve, yearsToPayment);
    const discountFactor = Math.exp(-rate * yearsToPayment); // Continuous discounting
    
    return {
      ...cf,
      discountFactor,
      presentValue: cf.amount * discountFactor,
    };
  });
}

/**
 * Calculate EVE (Economic Value of Equity) from discounted cash flows
 */
export function calculateEVE(discountedCashflows: DiscountedCashflow[]): number {
  return discountedCashflows.reduce((sum, cf) => sum + cf.presentValue, 0);
}

/**
 * Calculate NII (Net Interest Income) for next 12 months
 * Simplified: sum of interest cash flows in the next year
 */
export function calculateNII(cashflows: Cashflow[]): number {
  const today = new Date();
  const oneYearLater = new Date(today);
  oneYearLater.setFullYear(oneYearLater.getFullYear() + 1);
  
  return cashflows
    .filter((cf) => {
      const cfDate = new Date(cf.date);
      return cf.type === 'Interest' && cfDate >= today && cfDate <= oneYearLater;
    })
    .reduce((sum, cf) => sum + cf.amount, 0);
}

/**
 * Main calculation function that runs all scenarios
 */
export function runCalculation(
  positions: Position[],
  baseCurve: YieldCurve,
  _discountCurve: YieldCurve,
  scenarios: Scenario[]
): CalculationResults {
  // Generate all cash flows
  const allCashflows = positions.flatMap(generateCashflows);
  
  // Calculate base case
  const baseDiscountedCF = discountCashflows(allCashflows, baseCurve);
  const baseEve = calculateEVE(baseDiscountedCF);
  const baseNii = calculateNII(allCashflows);
  
  // Run enabled scenarios
  const scenarioResults: ScenarioResult[] = scenarios
    .filter((s) => s.enabled)
    .map((scenario) => {
      const shockedCurve = applyScenarioShock(baseCurve, scenario);
      const shockedDiscountedCF = discountCashflows(allCashflows, shockedCurve);
      const scenarioEve = calculateEVE(shockedDiscountedCF);
      const scenarioNii = calculateNII(allCashflows); // Simplified: NII stays same
      
      return {
        scenarioId: scenario.id,
        scenarioName: scenario.name,
        eve: scenarioEve,
        nii: scenarioNii,
        deltaEve: scenarioEve - baseEve,
        deltaNii: scenarioNii - baseNii,
      };
    });
  
  // Find worst case
  let worstCaseEve = baseEve;
  let worstCaseDeltaEve = 0;
  let worstCaseScenario: ScenarioResult['scenarioName'] = 'Parallel Up';
  
  if (scenarioResults.length > 0) {
    const worstCase = scenarioResults.reduce(
      (worst, result) => (result.deltaEve < worst.deltaEve ? result : worst),
      scenarioResults[0]
    );
    worstCaseEve = worstCase.eve;
    worstCaseDeltaEve = worstCase.deltaEve;
    worstCaseScenario = worstCase.scenarioName;
  }
  
  return {
    baseEve,
    baseNii,
    worstCaseEve,
    worstCaseDeltaEve,
    worstCaseScenario,
    scenarioResults,
    calculatedAt: new Date().toISOString(),
  };
}
