// Core financial data types for EVE/NII Calculator

export interface Position {
  id: string;
  instrumentType: 'Asset' | 'Liability';
  description: string;
  notional: number;
  maturityDate: string;
  couponRate: number;
  repriceFrequency: 'Fixed' | 'Monthly' | 'Quarterly' | 'Semi-Annual' | 'Annual';
  currency: string;
}

export interface YieldCurvePoint {
  tenor: string; // e.g., "1M", "3M", "1Y", "5Y"
  tenorYears: number;
  rate: number; // as decimal, e.g., 0.05 for 5%
}

export interface YieldCurve {
  id: string;
  name: string;
  currency: string;
  asOfDate: string;
  points: YieldCurvePoint[];
}

export type ScenarioType = 
  | 'Parallel Up'
  | 'Parallel Down'
  | 'Steepener'
  | 'Flattener'
  | 'Short Up'
  | 'Short Down'
  | string; // Allow custom scenario names

export interface Scenario {
  id: string;
  name: string; // Changed from ScenarioType to string to support custom names
  description?: string;
  shockBps: number; // basis points
  enabled: boolean;
}

export interface Cashflow {
  positionId: string;
  date: string;
  amount: number;
  type: 'Principal' | 'Interest';
}

export interface DiscountedCashflow extends Cashflow {
  discountFactor: number;
  presentValue: number;
}

export interface ScenarioResult {
  scenarioId: string;
  scenarioName: ScenarioType;
  eve: number;
  nii: number;
  deltaEve: number;
  deltaNii: number;
}

export interface CalculationResults {
  baseEve: number;
  baseNii: number;
  worstCaseEve: number;
  worstCaseDeltaEve: number;
  worstCaseScenario: ScenarioType;
  scenarioResults: ScenarioResult[];
  calculatedAt: string;
}

// Default IRRBB scenarios per regulatory guidelines
export const DEFAULT_SCENARIOS: Scenario[] = [
  {
    id: 'parallel-up',
    name: 'Parallel Up',
    description: 'Parallel increase of +200 bps across all tenors',
    shockBps: 200,
    enabled: true,
  },
  {
    id: 'parallel-down',
    name: 'Parallel Down',
    description: 'Parallel decrease of -200 bps across all tenors',
    shockBps: -200,
    enabled: true,
  },
  {
    id: 'steepener',
    name: 'Steepener',
    description: 'Short rates down, long rates up',
    shockBps: 150,
    enabled: true,
  },
  {
    id: 'flattener',
    name: 'Flattener',
    description: 'Short rates up, long rates down',
    shockBps: 150,
    enabled: true,
  },
  {
    id: 'short-up',
    name: 'Short Up',
    description: 'Short-term rates increase by +250 bps',
    shockBps: 250,
    enabled: true,
  },
  {
    id: 'short-down',
    name: 'Short Down',
    description: 'Short-term rates decrease by -250 bps',
    shockBps: -250,
    enabled: true,
  },
];

// Sample data for demonstration
export const SAMPLE_POSITIONS: Position[] = [
  {
    id: '1',
    instrumentType: 'Asset',
    description: 'Fixed Rate Mortgage Portfolio',
    notional: 50000000,
    maturityDate: '2029-12-31',
    couponRate: 0.045,
    repriceFrequency: 'Fixed',
    currency: 'USD',
  },
  {
    id: '2',
    instrumentType: 'Asset',
    description: 'Floating Rate Commercial Loans',
    notional: 30000000,
    maturityDate: '2027-06-30',
    couponRate: 0.055,
    repriceFrequency: 'Quarterly',
    currency: 'USD',
  },
  {
    id: '3',
    instrumentType: 'Liability',
    description: 'Term Deposits',
    notional: 40000000,
    maturityDate: '2025-12-31',
    couponRate: 0.035,
    repriceFrequency: 'Fixed',
    currency: 'USD',
  },
  {
    id: '4',
    instrumentType: 'Liability',
    description: 'Savings Accounts',
    notional: 25000000,
    maturityDate: '2025-06-30',
    couponRate: 0.02,
    repriceFrequency: 'Monthly',
    currency: 'USD',
  },
];

export const SAMPLE_YIELD_CURVE: YieldCurve = {
  id: 'usd-base',
  name: 'USD Base Curve',
  currency: 'USD',
  asOfDate: new Date().toISOString().split('T')[0],
  points: [
    { tenor: '1M', tenorYears: 1 / 12, rate: 0.0525 },
    { tenor: '3M', tenorYears: 0.25, rate: 0.054 },
    { tenor: '6M', tenorYears: 0.5, rate: 0.0545 },
    { tenor: '1Y', tenorYears: 1, rate: 0.0495 },
    { tenor: '2Y', tenorYears: 2, rate: 0.0445 },
    { tenor: '3Y', tenorYears: 3, rate: 0.0425 },
    { tenor: '5Y', tenorYears: 5, rate: 0.0415 },
    { tenor: '7Y', tenorYears: 7, rate: 0.042 },
    { tenor: '10Y', tenorYears: 10, rate: 0.0435 },
    { tenor: '20Y', tenorYears: 20, rate: 0.047 },
    { tenor: '30Y', tenorYears: 30, rate: 0.0475 },
  ],
};
