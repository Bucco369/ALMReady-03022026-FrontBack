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

// Balance hierarchy for Remove flow
export interface BalanceNode {
  id: string;
  label: string;
  type: 'category' | 'subcategory' | 'group' | 'contract';
  children?: BalanceNode[];
  amount?: number;
  count?: number;
}

export const BALANCE_HIERARCHY: BalanceNode[] = [
  {
    id: 'assets',
    label: 'Assets',
    type: 'category',
    amount: 2_450_000_000,
    count: 72,
    children: [
      {
        id: 'mortgages',
        label: 'Mortgages',
        type: 'subcategory',
        amount: 1_200_000_000,
        count: 34,
        children: [
          { id: 'mtg-residential', label: 'Residential Mortgages', type: 'group', amount: 850_000_000, count: 28 },
          { id: 'mtg-commercial', label: 'Commercial Mortgages', type: 'group', amount: 350_000_000, count: 6 },
        ],
      },
      {
        id: 'bonds',
        label: 'Bonds',
        type: 'subcategory',
        amount: 850_000_000,
        count: 22,
        children: [
          { id: 'bonds-govt', label: 'Government Bonds', type: 'group', amount: 500_000_000, count: 12 },
          { id: 'bonds-corp', label: 'Corporate Bonds', type: 'group', amount: 350_000_000, count: 10 },
        ],
      },
      {
        id: 'loans',
        label: 'Loans',
        type: 'subcategory',
        amount: 400_000_000,
        count: 16,
        children: [
          { id: 'loans-corp', label: 'Corporate Loans', type: 'group', amount: 300_000_000, count: 10 },
          { id: 'loans-sme', label: 'SME Loans', type: 'group', amount: 100_000_000, count: 6 },
        ],
      },
    ],
  },
  {
    id: 'liabilities',
    label: 'Liabilities',
    type: 'category',
    amount: 2_280_000_000,
    count: 52,
    children: [
      {
        id: 'sight-deposits',
        label: 'Sight Deposits',
        type: 'subcategory',
        amount: 680_000_000,
        count: 18,
        children: [
          { id: 'sight-retail', label: 'Retail Sight Deposits', type: 'group', amount: 450_000_000, count: 12 },
          { id: 'sight-corp', label: 'Corporate Sight Deposits', type: 'group', amount: 230_000_000, count: 6 },
        ],
      },
      {
        id: 'term-deposits',
        label: 'Term Deposits',
        type: 'subcategory',
        amount: 920_000_000,
        count: 24,
        children: [
          { id: 'term-retail', label: 'Retail Term Deposits', type: 'group', amount: 620_000_000, count: 18 },
          { id: 'term-corp', label: 'Corporate Term Deposits', type: 'group', amount: 300_000_000, count: 6 },
        ],
      },
      {
        id: 'wholesale-funding',
        label: 'Wholesale Funding',
        type: 'subcategory',
        amount: 680_000_000,
        count: 10,
        children: [
          { id: 'wholesale-senior', label: 'Senior Unsecured', type: 'group', amount: 400_000_000, count: 6 },
          { id: 'wholesale-covered', label: 'Covered Bonds Issued', type: 'group', amount: 280_000_000, count: 4 },
        ],
      },
    ],
  },
];
