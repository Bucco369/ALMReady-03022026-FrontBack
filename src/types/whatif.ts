/**
 * whatif.ts – Types for the What-If modification system.
 *
 * === ROLE IN THE SYSTEM ===
 * What-If modifications represent hypothetical changes to the balance:
 * - "add": Create a synthetic position (e.g. new loan portfolio)
 * - "remove": Exclude existing positions from calculation
 *
 * These modifications live in WhatIfContext (frontend state only) and are
 * displayed as green/red overlays in the BalancePositionsCard.
 *
 * === BACKEND INTEGRATION ===
 * When the user clicks "Apply to Analysis", ResultsCard sends the modifications
 * to POST /api/sessions/{id}/calculate/whatif. The backend converts 'add'
 * modifications to synthetic motor positions (via productTemplateId mapping)
 * and 'remove' modifications to extracted existing positions, then runs
 * EVE/NII on just the delta to compute impact values.
 */

export interface WhatIfModification {
  id: string;                     // Auto-generated unique ID
  type: 'add' | 'remove';
  label: string;                  // Display name (e.g. "Fixed-rate Loan Portfolio")
  details?: string;               // Extra info (e.g. "€10M EUR")
  notional?: number;              // Amount for adds
  currency?: string;
  category?: 'asset' | 'liability' | 'derivative';  // Balance tree placement
  subcategory?: string;           // e.g., 'mortgages', 'deposits'
  rate?: number;                  // Interest rate (decimal) for avg rate delta
  maturity?: number;              // Residual maturity in years
  positionDelta?: number;         // For remove_all: count of positions removed
  removeMode?: 'all' | 'contracts';  // Remove entire subcategory vs specific contracts
  contractIds?: string[];         // Specific contract_ids to remove
  // Motor-specific fields for backend EVE/NII calculation (Phase 2)
  productTemplateId?: string;     // e.g. 'fixed-loan', 'floating-loan'
  startDate?: string;             // ISO date for start
  maturityDate?: string;          // ISO date for maturity
  paymentFreq?: string;           // 'Monthly'|'Quarterly'|'Semi-Annual'|'Annual'
  repricingFreq?: string;         // For floating products
  refIndex?: string;              // Reference index for floating (e.g. 'EURIBOR 3M')
  spread?: number;                // Spread in bps for floating products
}

export interface ProductTemplate {
  id: string;
  name: string;
  category: 'asset' | 'liability' | 'derivative';
  fields: ProductField[];
}

export interface ProductField {
  id: string;
  label: string;
  type: 'number' | 'text' | 'date' | 'select';
  required: boolean;
  options?: string[];
  placeholder?: string;
  disabled?: boolean;
}

export const PRODUCT_TEMPLATES: ProductTemplate[] = [
  {
    id: 'fixed-loan',
    name: 'Fixed-rate Loan Portfolio',
    category: 'asset',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '10,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'coupon', label: 'Coupon Rate (%)', type: 'number', required: true, placeholder: '3.50' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
    ],
  },
  {
    id: 'floating-loan',
    name: 'Floating-rate Loan Portfolio',
    category: 'asset',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '10,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'refIndex', label: 'Reference Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'SOFR', 'SONIA'] },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: true, placeholder: '150' },
      { id: 'repricingFreq', label: 'Repricing Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual'] },
    ],
  },
  {
    id: 'bond-portfolio',
    name: 'Bond Portfolio (Fixed Income)',
    category: 'asset',
    fields: [
      { id: 'notional', label: 'Face Value', type: 'number', required: true, placeholder: '50,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Settlement Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'coupon', label: 'Coupon Rate (%)', type: 'number', required: true, placeholder: '2.75' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Semi-Annual', 'Annual'] },
    ],
  },
  {
    id: 'nmd',
    name: 'Non-Maturing Deposits (NMD)',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Deposit Balance', type: 'number', required: true, placeholder: '100,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'depositRate', label: 'Deposit Rate (%)', type: 'number', required: true, placeholder: '0.50' },
      { id: 'coreRatio', label: 'Core Deposit Ratio (%)', type: 'number', required: false, placeholder: '70' },
      { id: 'avgLife', label: 'Average Life (years)', type: 'number', required: false, placeholder: '3.5' },
    ],
  },
  {
    id: 'term-deposit',
    name: 'Term Deposits',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Deposit Amount', type: 'number', required: true, placeholder: '25,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'depositRate', label: 'Deposit Rate (%)', type: 'number', required: true, placeholder: '3.25' },
    ],
  },
  {
    id: 'wholesale',
    name: 'Wholesale Funding',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Principal Amount', type: 'number', required: true, placeholder: '75,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Issue Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'coupon', label: 'Coupon Rate (%)', type: 'number', required: true, placeholder: '4.00' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Quarterly', 'Semi-Annual', 'Annual'] },
    ],
  },
  {
    id: 'irs-hedge',
    name: 'Interest Rate Swap (Hedge)',
    category: 'derivative',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '50,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Effective Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'payFixed', label: 'Pay Leg', type: 'select', required: true, options: ['Pay Fixed', 'Receive Fixed'] },
      { id: 'fixedRate', label: 'Fixed Rate (%)', type: 'number', required: true, placeholder: '2.50' },
      { id: 'floatIndex', label: 'Float Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'SOFR', 'SONIA'] },
    ],
  },
  {
    id: 'securitised',
    name: 'Securitised Assets',
    category: 'asset',
    fields: [
      { id: 'notional', label: 'Pool Balance', type: 'number', required: true, placeholder: '200,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Settlement Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Expected Maturity', type: 'date', required: true },
      { id: 'wac', label: 'Weighted Avg Coupon (%)', type: 'number', required: true, placeholder: '4.25' },
      { id: 'cpr', label: 'Prepayment Speed (CPR %)', type: 'number', required: false, placeholder: '8' },
    ],
  },
];
