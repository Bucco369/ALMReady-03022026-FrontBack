// What-If modification types

export interface WhatIfModification {
  id: string;
  type: 'add' | 'remove';
  label: string;
  details?: string;
  notional?: number;
  currency?: string;
  // Target category for placement in balance tree
  category?: 'asset' | 'liability' | 'derivative';
  subcategory?: string; // e.g., 'mortgages', 'bonds', 'sight-deposits'
  rate?: number; // Interest rate for avg rate delta calculation
  maturity?: number; // Residual maturity in years for weighted maturity delta calculation
  positionDelta?: number; // Allows remove_all to deduct full subcategory count.
  removeMode?: 'all' | 'contracts';
  contractIds?: string[];
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
