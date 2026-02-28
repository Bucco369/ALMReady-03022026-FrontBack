/**
 * BehaviouralContext.tsx – Global state for behavioural assumption overrides.
 *
 * Manages user-defined behavioural parameters for three product families:
 * - NMD (Non-Maturing Deposits): core/non-core split, distribution across
 *   19 EBA buckets, pass-through rate for NII repricing sensitivity.
 * - Loan Prepayments: SMM (Single Monthly Mortality) -> CPR (annual).
 * - Term Deposits: TDRR (monthly early redemption rate -> annual).
 *
 * All parameters start as null (blank). A product is considered "active"
 * when any of its parameters is non-null.
 *
 * Persistence: on Apply, the state is written to localStorage under
 * `almready_behavioural_v1`. On provider mount, it hydrates from storage.
 */
import { createContext, useContext, useState, useCallback, useMemo, useEffect, type ReactNode } from 'react';

// ── 19 EBA regulatory time buckets ────────────────────────────────────────
/** EBA IRRBB maximum weighted-average maturity for NMD core deposits (years). */
export const MAX_TOTAL_MATURITY = 5.0;

export const NMD_BUCKETS = [
  { id: 'ON',       label: 'O/N',        midpoint: 0.003 },
  { id: 'ON_1M',    label: '>O/N\u20131M',   midpoint: 0.042 },
  { id: '1M_3M',    label: '>1M\u20133M',    midpoint: 0.167 },
  { id: '3M_6M',    label: '>3M\u20136M',    midpoint: 0.375 },
  { id: '6M_9M',    label: '>6M\u20139M',    midpoint: 0.625 },
  { id: '9M_1Y',    label: '>9M\u20131Y',    midpoint: 0.875 },
  { id: '1Y_1H',    label: '>1Y\u20131.5Y',  midpoint: 1.25  },
  { id: '1H_2Y',    label: '>1.5Y\u20132Y',  midpoint: 1.75  },
  { id: '2Y_3Y',    label: '>2Y\u20133Y',    midpoint: 2.5   },
  { id: '3Y_4Y',    label: '>3Y\u20134Y',    midpoint: 3.5   },
  { id: '4Y_5Y',    label: '>4Y\u20135Y',    midpoint: 4.5   },
  { id: '5Y_6Y',    label: '>5Y\u20136Y',    midpoint: 5.5   },
  { id: '6Y_7Y',    label: '>6Y\u20137Y',    midpoint: 6.5   },
  { id: '7Y_8Y',    label: '>7Y\u20138Y',    midpoint: 7.5   },
  { id: '8Y_9Y',    label: '>8Y\u20139Y',    midpoint: 8.5   },
  { id: '9Y_10Y',   label: '>9Y\u201310Y',   midpoint: 9.5   },
  { id: '10Y_15Y',  label: '>10Y\u201315Y',  midpoint: 12.5  },
  { id: '15Y_20Y',  label: '>15Y\u201320Y',  midpoint: 17.5  },
  { id: '20Y_PLUS', label: '>20Y',       midpoint: 25.0  },
] as const;

export type BucketId = (typeof NMD_BUCKETS)[number]['id'];

// ── Parameter interfaces (null = blank/not set) ──────────────────────────

export interface NMDParameters {
  coreProportion: number | null;       // 0-100 (%)
  coreAverageMaturity: number | null;  // years (informational, derived from distribution)
  passThrough: number | null;          // 0-100 (%), NII repricing pass-through rate
  distribution: Record<string, number>; // bucket_id -> % of total NMDs
}

export interface LoanPrepaymentParameters {
  smm: number | null; // 0-50 (%) monthly
}

export interface TermDepositParameters {
  tdrr: number | null; // 0-50 (%) monthly
}

// ── Context type ──────────────────────────────────────────────────────────

interface BehaviouralContextType {
  // Current editing state
  nmdParams: NMDParameters;
  setNmdParams: (params: NMDParameters) => void;
  loanPrepaymentParams: LoanPrepaymentParameters;
  setLoanPrepaymentParams: (params: LoanPrepaymentParameters) => void;
  termDepositParams: TermDepositParameters;
  setTermDepositParams: (params: TermDepositParameters) => void;

  // Applied (committed) state -- what gets sent to backend
  appliedNmdParams: NMDParameters;
  appliedLoanParams: LoanPrepaymentParameters;
  appliedTermParams: TermDepositParameters;

  // Computed values
  cprFromSmm: number;       // annual CPR from monthly SMM
  annualTdrr: number;       // annual TDRR from monthly
  coreWam: number;          // WAM of core buckets
  distributionSum: number;  // sum of all bucket weights (should = 100)

  // Actions
  applyAssumptions: () => void;
  resetAssumptions: () => void;

  // Derived flags
  hasActiveAssumptions: boolean; // true if any product has non-null applied params
  isNmdActive: boolean;
  isLoanActive: boolean;
  isTermActive: boolean;
}

// ── Defaults ──────────────────────────────────────────────────────────────

const BLANK_NMD: NMDParameters = {
  coreProportion: 0,
  coreAverageMaturity: 0,
  passThrough: 0,
  distribution: {},
};

const BLANK_LOAN: LoanPrepaymentParameters = { smm: 0 };
const BLANK_TERM: TermDepositParameters = { tdrr: 0 };

const STORAGE_KEY = 'almready_behavioural_v1';

// ── Helpers ───────────────────────────────────────────────────────────────

function checkNmdActive(p: NMDParameters): boolean {
  return (p.coreProportion ?? 0) > 0 || (p.passThrough ?? 0) > 0 || Object.keys(p.distribution).length > 0;
}
function checkLoanActive(p: LoanPrepaymentParameters): boolean {
  return (p.smm ?? 0) > 0;
}
function checkTermActive(p: TermDepositParameters): boolean {
  return (p.tdrr ?? 0) > 0;
}

function loadFromStorage(): { nmd: NMDParameters; loan: LoanPrepaymentParameters; term: TermDepositParameters } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return {
      nmd: { ...BLANK_NMD, ...parsed.nmd },
      loan: { ...BLANK_LOAN, ...parsed.loanPrepayment },
      term: { ...BLANK_TERM, ...parsed.termDeposit },
    };
  } catch {
    return null;
  }
}

function saveToStorage(nmd: NMDParameters, loan: LoanPrepaymentParameters, term: TermDepositParameters) {
  const data = { nmd, loanPrepayment: loan, termDeposit: term };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

function computeCpr(smmPct: number | null): number {
  if (smmPct === null || smmPct === 0) return 0;
  return (1 - Math.pow(1 - smmPct / 100, 12)) * 100;
}

function computeAnnualTdrr(tdrrPct: number | null): number {
  if (tdrrPct === null || tdrrPct === 0) return 0;
  return (1 - Math.pow(1 - tdrrPct / 100, 12)) * 100;
}

function computeCoreWam(distribution: Record<string, number>, coreProportion: number | null): number {
  if (!coreProportion || coreProportion === 0) return 0;
  let wam = 0;
  for (const b of NMD_BUCKETS) {
    if (b.id === 'ON') continue; // O/N is non-core
    const w = distribution[b.id] ?? 0;
    wam += w * b.midpoint;
  }
  return wam / coreProportion;
}

// ── Context & Provider ────────────────────────────────────────────────────

const BehaviouralContext = createContext<BehaviouralContextType | null>(null);

export function BehaviouralProvider({ children }: { children: ReactNode }) {
  // Editing state
  const [nmdParams, setNmdParams] = useState<NMDParameters>(BLANK_NMD);
  const [loanPrepaymentParams, setLoanPrepaymentParams] = useState<LoanPrepaymentParameters>(BLANK_LOAN);
  const [termDepositParams, setTermDepositParams] = useState<TermDepositParameters>(BLANK_TERM);

  // Applied state
  const [appliedNmdParams, setAppliedNmd] = useState<NMDParameters>(BLANK_NMD);
  const [appliedLoanParams, setAppliedLoan] = useState<LoanPrepaymentParameters>(BLANK_LOAN);
  const [appliedTermParams, setAppliedTerm] = useState<TermDepositParameters>(BLANK_TERM);

  // Hydrate from localStorage on mount
  useEffect(() => {
    const stored = loadFromStorage();
    if (stored) {
      setNmdParams(stored.nmd);
      setLoanPrepaymentParams(stored.loan);
      setTermDepositParams(stored.term);
      setAppliedNmd(stored.nmd);
      setAppliedLoan(stored.loan);
      setAppliedTerm(stored.term);
    }
  }, []);

  const cprFromSmm = useMemo(() => computeCpr(loanPrepaymentParams.smm), [loanPrepaymentParams.smm]);
  const annualTdrr = useMemo(() => computeAnnualTdrr(termDepositParams.tdrr), [termDepositParams.tdrr]);
  const coreWam = useMemo(
    () => computeCoreWam(nmdParams.distribution, nmdParams.coreProportion),
    [nmdParams.distribution, nmdParams.coreProportion],
  );
  const distributionSum = useMemo(() => {
    return Object.values(nmdParams.distribution).reduce((a, b) => a + b, 0);
  }, [nmdParams.distribution]);

  const applyAssumptions = useCallback(() => {
    setAppliedNmd({ ...nmdParams });
    setAppliedLoan({ ...loanPrepaymentParams });
    setAppliedTerm({ ...termDepositParams });
    saveToStorage(nmdParams, loanPrepaymentParams, termDepositParams);
  }, [nmdParams, loanPrepaymentParams, termDepositParams]);

  const resetAssumptions = useCallback(() => {
    setNmdParams(BLANK_NMD);
    setLoanPrepaymentParams(BLANK_LOAN);
    setTermDepositParams(BLANK_TERM);
    setAppliedNmd(BLANK_NMD);
    setAppliedLoan(BLANK_LOAN);
    setAppliedTerm(BLANK_TERM);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const hasActiveAssumptions = useMemo(
    () => checkNmdActive(appliedNmdParams) || checkLoanActive(appliedLoanParams) || checkTermActive(appliedTermParams),
    [appliedNmdParams, appliedLoanParams, appliedTermParams],
  );

  return (
    <BehaviouralContext.Provider
      value={{
        nmdParams, setNmdParams,
        loanPrepaymentParams, setLoanPrepaymentParams,
        termDepositParams, setTermDepositParams,
        appliedNmdParams, appliedLoanParams, appliedTermParams,
        cprFromSmm, annualTdrr, coreWam, distributionSum,
        applyAssumptions, resetAssumptions,
        hasActiveAssumptions,
        isNmdActive: checkNmdActive(appliedNmdParams),
        isLoanActive: checkLoanActive(appliedLoanParams),
        isTermActive: checkTermActive(appliedTermParams),
      }}
    >
      {children}
    </BehaviouralContext.Provider>
  );
}

export function useBehavioural() {
  const ctx = useContext(BehaviouralContext);
  if (!ctx) throw new Error('useBehavioural must be used within BehaviouralProvider');
  return ctx;
}

/** Build the behavioural payload for the /calculate POST body.
 *  Returns undefined when no assumptions are active (backend ignores the field). */
export function buildBehaviouralPayload(ctx: BehaviouralContextType) {
  const parts: Record<string, unknown> = {};

  if (checkNmdActive(ctx.appliedNmdParams)) {
    parts.nmd = {
      core_proportion: ctx.appliedNmdParams.coreProportion ?? 0,
      core_average_maturity: ctx.appliedNmdParams.coreAverageMaturity ?? 0,
      pass_through_rate: ctx.appliedNmdParams.passThrough ?? 0,
      distribution: ctx.appliedNmdParams.distribution,
    };
  }
  if (checkLoanActive(ctx.appliedLoanParams)) {
    parts.loan_prepayment = { smm: ctx.appliedLoanParams.smm ?? 0 };
  }
  if (checkTermActive(ctx.appliedTermParams)) {
    parts.term_deposit = { tdrr: ctx.appliedTermParams.tdrr ?? 0 };
  }

  return Object.keys(parts).length > 0 ? parts : undefined;
}

export type { BehaviouralContextType };
