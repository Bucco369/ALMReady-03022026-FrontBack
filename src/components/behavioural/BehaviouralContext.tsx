import React, { createContext, useContext, useState, useCallback, ReactNode, useMemo } from 'react';

export type BehaviouralProfile = 'none' | 'nmd' | 'loan-prepayments' | 'term-deposits';

export interface NMDParameters {
  enabled: boolean;
  coreProportion: number; // 0-100 (%)
  coreAverageMaturity: number; // years (2-10)
  passThrough: number; // 0-100 (%)
}

export interface LoanPrepaymentParameters {
  enabled: boolean;
  smm: number; // 0-50 (%) - Single Monthly Mortality
}

export interface TermDepositParameters {
  enabled: boolean;
  tdrr: number; // 0-50 (%) - Term Deposit Redemption Rate (monthly)
}

interface BehaviouralContextType {
  // Profile selection
  activeProfile: BehaviouralProfile;
  setActiveProfile: (profile: BehaviouralProfile) => void;
  
  // NMD parameters
  nmdParams: NMDParameters;
  setNmdParams: (params: NMDParameters) => void;
  
  // Loan Prepayment parameters
  loanPrepaymentParams: LoanPrepaymentParameters;
  setLoanPrepaymentParams: (params: LoanPrepaymentParameters) => void;
  
  // Term Deposit parameters
  termDepositParams: TermDepositParameters;
  setTermDepositParams: (params: TermDepositParameters) => void;
  
  // Computed values - NMD
  totalAverageMaturity: number;
  isValidMaturity: boolean;
  
  // Computed values - Loan Prepayments
  cprFromSmm: number;
  
  // Computed values - Term Deposits
  annualTdrr: number;
  
  // Application state
  isApplied: boolean;
  applyAssumptions: () => void;
  resetAssumptions: () => void;
  
  // Check if custom assumptions are active
  hasCustomAssumptions: boolean;
}

const DEFAULT_NMD_PARAMS: NMDParameters = {
  enabled: false,
  coreProportion: 75,
  coreAverageMaturity: 6.25,
  passThrough: 10,
};

const DEFAULT_LOAN_PREPAYMENT_PARAMS: LoanPrepaymentParameters = {
  enabled: false,
  smm: 0.50,
};

const DEFAULT_TERM_DEPOSIT_PARAMS: TermDepositParameters = {
  enabled: false,
  tdrr: 0.10,
};

const MAX_TOTAL_MATURITY = 5.0; // Supervisory limit

const BehaviouralContext = createContext<BehaviouralContextType | null>(null);

export function BehaviouralProvider({ children }: { children: ReactNode }) {
  const [activeProfile, setActiveProfile] = useState<BehaviouralProfile>('none');
  const [nmdParams, setNmdParams] = useState<NMDParameters>(DEFAULT_NMD_PARAMS);
  const [loanPrepaymentParams, setLoanPrepaymentParams] = useState<LoanPrepaymentParameters>(DEFAULT_LOAN_PREPAYMENT_PARAMS);
  const [termDepositParams, setTermDepositParams] = useState<TermDepositParameters>(DEFAULT_TERM_DEPOSIT_PARAMS);
  const [isApplied, setIsApplied] = useState(false);
  const [appliedProfile, setAppliedProfile] = useState<BehaviouralProfile>('none');
  const [appliedNmdParams, setAppliedNmdParams] = useState<NMDParameters>(DEFAULT_NMD_PARAMS);
  const [appliedLoanPrepaymentParams, setAppliedLoanPrepaymentParams] = useState<LoanPrepaymentParameters>(DEFAULT_LOAN_PREPAYMENT_PARAMS);
  const [appliedTermDepositParams, setAppliedTermDepositParams] = useState<TermDepositParameters>(DEFAULT_TERM_DEPOSIT_PARAMS);

  // Calculate total average maturity: Core proportion × Core average maturity / 100
  const totalAverageMaturity = useMemo(() => {
    return (nmdParams.coreProportion / 100) * nmdParams.coreAverageMaturity;
  }, [nmdParams.coreProportion, nmdParams.coreAverageMaturity]);

  const isValidMaturity = totalAverageMaturity <= MAX_TOTAL_MATURITY;

  // Calculate CPR from SMM: CPR = 1 - (1 - SMM)^12
  const cprFromSmm = useMemo(() => {
    const smm = loanPrepaymentParams.smm / 100;
    const cprDecimal = 1 - Math.pow(1 - smm, 12);
    return cprDecimal * 100;
  }, [loanPrepaymentParams.smm]);

  // Calculate annual TDRR: Annual = 1 - (1 - monthly)^12
  const annualTdrr = useMemo(() => {
    const monthly = termDepositParams.tdrr / 100;
    const annualDecimal = 1 - Math.pow(1 - monthly, 12);
    return annualDecimal * 100;
  }, [termDepositParams.tdrr]);

  const applyAssumptions = useCallback(() => {
    setAppliedProfile(activeProfile);
    setAppliedNmdParams({ ...nmdParams });
    setAppliedLoanPrepaymentParams({ ...loanPrepaymentParams });
    setAppliedTermDepositParams({ ...termDepositParams });
    setIsApplied(true);
  }, [activeProfile, nmdParams, loanPrepaymentParams, termDepositParams]);

  const resetAssumptions = useCallback(() => {
    setActiveProfile('none');
    setNmdParams(DEFAULT_NMD_PARAMS);
    setLoanPrepaymentParams(DEFAULT_LOAN_PREPAYMENT_PARAMS);
    setTermDepositParams(DEFAULT_TERM_DEPOSIT_PARAMS);
    setAppliedProfile('none');
    setAppliedNmdParams(DEFAULT_NMD_PARAMS);
    setAppliedLoanPrepaymentParams(DEFAULT_LOAN_PREPAYMENT_PARAMS);
    setAppliedTermDepositParams(DEFAULT_TERM_DEPOSIT_PARAMS);
    setIsApplied(false);
  }, []);

  // Check if custom assumptions are active (applied and not default)
  const hasCustomAssumptions = useMemo(() => {
    if (!isApplied) return false;
    if (appliedProfile === 'none') return false;
    if (appliedProfile === 'nmd' && !appliedNmdParams.enabled) return false;
    if (appliedProfile === 'loan-prepayments' && !appliedLoanPrepaymentParams.enabled) return false;
    if (appliedProfile === 'term-deposits' && !appliedTermDepositParams.enabled) return false;
    return true;
  }, [isApplied, appliedProfile, appliedNmdParams, appliedLoanPrepaymentParams, appliedTermDepositParams]);

  return (
    <BehaviouralContext.Provider value={{
      activeProfile,
      setActiveProfile,
      nmdParams,
      setNmdParams,
      loanPrepaymentParams,
      setLoanPrepaymentParams,
      termDepositParams,
      setTermDepositParams,
      totalAverageMaturity,
      isValidMaturity,
      cprFromSmm,
      annualTdrr,
      isApplied,
      applyAssumptions,
      resetAssumptions,
      hasCustomAssumptions,
    }}>
      {children}
    </BehaviouralContext.Provider>
  );
}

export function useBehavioural() {
  const context = useContext(BehaviouralContext);
  if (!context) {
    throw new Error('useBehavioural must be used within a BehaviouralProvider');
  }
  return context;
}

// Export constants for use in components
export const NMD_BUCKET_DISTRIBUTION = {
  '1Y': 1.33333,
  '2Y': 2.66667,
  '3Y': 5.33333,
  '4Y': 8.00000,
  '5Y': 13.33333,
  '6Y': 16.00000,
  '7Y': 20.00000,
  '8Y': 33.33333,
} as const;

export { MAX_TOTAL_MATURITY };
