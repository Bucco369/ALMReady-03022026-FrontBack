/**
 * whatif.ts – Types for the What-If modification system.
 *
 * ╔═══════════════════════════════════════════════════════════════════════╗
 * ║                     WHAT-IF SYSTEM ARCHITECTURE                      ║
 * ╚═══════════════════════════════════════════════════════════════════════╝
 *
 * The What-If system lets users simulate hypothetical changes to the bank's
 * balance sheet and instantly see the EVE (Economic Value of Equity) and
 * NII (Net Interest Income) impact under multiple interest rate scenarios.
 *
 * ── DATA FLOW ─────────────────────────────────────────────────────────
 *
 *   User builds modifications in WhatIfWorkbench (modal dialog)
 *        ↓
 *   Modifications stored in WhatIfContext (React state, ephemeral)
 *        ↓
 *   BalancePositionsCard shows green/red delta overlays on balance tree
 *        ↓
 *   User clicks "Apply to Analysis" → ResultsCard sends to backend
 *        ↓
 *   Backend (two engines, see below) computes EVE/NII deltas
 *        ↓
 *   ResultsCard displays per-scenario impact values
 *
 * ── MODIFICATION TYPES ────────────────────────────────────────────────
 *
 *   type='add'         → Synthetic position (new loan, bond, deposit, etc.)
 *   type='remove'      → Exclude existing positions by subcategory or contract ID
 *   type='behavioural' → Override NMD/prepayment/TDRR assumptions
 *   type='pricing'     → Repricing simulation (change rates on existing portfolio)
 *
 * ── BACKEND ENDPOINTS ─────────────────────────────────────────────────
 *
 *   OLD (legacy, basic):
 *     POST /api/sessions/{id}/calculate/whatif
 *     • Request: { modifications: WhatIfModificationRequest[] }
 *     • Creates 1:1 synthetic motor rows — NO decomposition
 *     • IGNORES: amortization, floor/cap, mixed rates, grace periods
 *     • Used by: ResultsCard "Apply to Analysis" (pending migration)
 *
 *   NEW (V2, with decomposer):
 *     POST /api/sessions/{id}/whatif/calculate
 *     • Request: { additions: LoanSpec[], removals: WhatIfModificationItem[] }
 *     • Uses decomposer to convert 1 instrument → 1-5 motor positions
 *     • SUPPORTS: amortization (bullet/linear/annuity), mixed rates,
 *       floor/cap, grace periods, daycount conventions
 *     • Used by: FindLimitCompartment, Calculate Impact preview
 *
 *   PREVIEW (no calculation, shows decomposition):
 *     POST /api/sessions/{id}/whatif/decompose
 *     • Returns the motor positions without running EVE/NII
 *
 *   FIND LIMIT (binary search solver):
 *     POST /api/sessions/{id}/whatif/find-limit
 *     • Finds max notional/rate/maturity/spread within an EVE/NII limit
 *
 * ── FIELDS NOT YET SUPPORTED BY ANY BACKEND ───────────────────────────
 *
 *   • callDate      — Callable instrument truncation (not in decomposer)
 *   • repricingBeta — NMD pass-through rate (behavioural, not cashflow)
 *   • payingLeg     — IRS direction (derivatives not in decomposer)
 *
 *   These fields are captured in the frontend form and stored in
 *   WhatIfModification for future backend implementation.
 *
 * ── PRODUCT CATALOG ───────────────────────────────────────────────────
 *
 *   PRODUCT_FAMILIES (10 families, grouped by asset/liability/derivative)
 *        ↓ each has
 *   ProductVariant[] (16 active variants, each with a templateId)
 *        ↓ maps to
 *   PRODUCT_TEMPLATES (16 templates with field definitions)
 *        ↓ rendered by
 *   shared/ProductConfigForm.tsx (CascadingDropdowns → StructuralConfig → Fields)
 *
 *   The same form is used by AddCatalog (Buy/Sell) and FindLimitCompartment.
 */

// ── Behavioural Override types ─────────────────────────────────────────

export type BehaviouralFamily = 'nmd' | 'loan-prepayments' | 'term-deposits';

export interface BehaviouralOverride {
  family: BehaviouralFamily;
  // NMD parameters
  coreProportion?: number;      // 0-100 (%)
  coreAverageMaturity?: number; // years (2-10)
  passThrough?: number;         // 0-100 (%)
  // Loan Prepayment parameters
  smm?: number;                 // 0-50 (%) Single Monthly Mortality
  // Term Deposit parameters
  tdrr?: number;                // 0-50 (%) Term Deposit Redemption Rate (monthly)
}

// ── Repricing Override (Pricing tab) ─────────────────────────────────

export interface RepricingOverride {
  // Target
  subcategoryId: string;                // 'deposits', 'mortgages', 'term-deposits', etc.
  side: 'asset' | 'liability';
  productLabel: string;                 // Human-readable: "Deposits", "Mortgages"

  // Current state (from balance snapshot)
  currentVolume: number;                // Total notional
  currentAvgRate: number;               // Decimal, e.g. 0.02 for 2%
  currentAnnualInterest: number;        // volume × rate

  // Scope
  scope: 'entire' | 'new-production';
  newProductionPct?: number;            // 0–100, only when scope = 'new-production'
  affectedVolume: number;               // entire → currentVolume, new-prod → volume × pct/100

  // Rate override
  rateMode: 'absolute' | 'delta';
  newRate: number;                      // Decimal (always resolved)
  deltaBps: number;                     // Signed integer (always resolved)

  // Computed impact
  newAnnualInterest: number;
  deltaInterest: number;                // newAnnualInterest − currentAnnualInterest
  deltaNii: number;                     // liabilities: −deltaInterest; assets: deltaInterest
  deltaNimBps: number;                  // deltaNii / totalAssets × 10_000
}

// ── Core modification type ────────────────────────────────────────────

export interface WhatIfModification {
  id: string;                     // Auto-generated unique ID
  type: 'add' | 'remove' | 'behavioural' | 'pricing';
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
  payingLeg?: 'Fixed' | 'Floating'; // IRS direction — what leg does the bank pay
  amortization?: AmortizationType; // Amortization profile (bullet, linear, annuity, scheduled)
  floorRate?: number;             // Interest rate floor (decimal) — embedded optionality
  capRate?: number;               // Interest rate cap (decimal) — embedded optionality
  repricingBeta?: number;         // NMD pass-through rate (0–1) — sensitivity to rate changes
  callDate?: string;              // First call date (ISO) — for callable instruments
  mixedFixedYears?: number;       // Years of initial fixed-rate period (mixed-rate loans)
  // Behavioural override data (only for type === 'behavioural')
  behaviouralOverride?: BehaviouralOverride;
  // Repricing override data (only for type === 'pricing')
  repricingOverride?: RepricingOverride;
  // Raw form input values — stored for lossless edit round-trips.
  // Frontend-only field — not sent to the backend.
  formValues?: Record<string, string>;
  // Per-position maturity distribution for accurate chart tenor allocation.
  // Used by bulk removals where many positions have different maturities.
  // Frontend-only field — not sent to the backend.
  maturityProfile?: Array<{ amount: number; maturityYears: number; rate?: number }>;
}

export interface ProductTemplate {
  id: string;
  name: string;
  category: 'asset' | 'liability' | 'derivative';
  fields: ProductField[];
  /** When present, grouped fields render as side-by-side bordered panels. */
  fieldGroups?: FieldGroup[];
}

export interface ProductField {
  id: string;
  label: string;
  type: 'number' | 'text' | 'date' | 'select';
  required: boolean;
  options?: string[];
  placeholder?: string;
  disabled?: boolean;
  /** Only show this field when another field has a specific value. */
  showWhen?: { field: string; value: string };
  /** Auto-derived readonly field: maps source field values → display values. */
  derivedFrom?: { field: string; map: Record<string, string> };
  /** Assigns this field to a visual group (e.g. 'fixed-leg'). */
  group?: string;
}

/** Visual field group rendered as a bordered panel (e.g. swap legs). */
export interface FieldGroup {
  id: string;
  label: string;
  /** Dynamic subtitle derived from a form field value. */
  subtitle?: { field: string; map: Record<string, string> };
}

// ── What-If V2: Generalized Loan Specification ──────────────────────────
// These types match the backend LoanSpec / DecomposeResponse and support
// grace periods, mixed rates, and multiple amortization types.

export type RateType = 'fixed' | 'variable' | 'mixed';
export type AmortizationType = 'bullet' | 'linear' | 'annuity' | 'scheduled';
export type Side = 'A' | 'L';

/**
 * Rich loan specification sent to POST /api/sessions/{id}/whatif/decompose
 * and POST /api/sessions/{id}/whatif/calculate.
 *
 * The backend decomposes this into 1–5 motor-compatible positions depending
 * on rate_type, amortization, and grace_years.
 */
export interface LoanSpec {
  id: string;
  notional: number;
  termYears: number;
  side?: Side;
  currency?: string;
  rateType: RateType;
  fixedRate?: number;           // decimal (e.g. 0.024 = 2.4%)
  variableIndex?: string;       // e.g. "EUR_EURIBOR_12M"
  spreadBps?: number;
  mixedFixedYears?: number;     // years of fixed period for mixed
  amortization: AmortizationType;
  graceYears?: number;          // interest-only period
  daycount?: string;            // "30/360" | "ACT/360" | "ACT/365"
  paymentFreq?: string;         // "1M" | "3M" | "6M" | "12M"
  repricingFreq?: string;
  startDate?: string;           // ISO date
  floorRate?: number;
  capRate?: number;
  callDate?: string;            // First call date (ISO) — callable instruments
  label?: string;
}

/** Single motor position returned by the decompose preview. */
export interface DecomposedPosition {
  contractId: string;
  side: string;
  sourceContractType: string;
  notional: number;
  fixedRate: number;
  spread: number;
  startDate: string;
  maturityDate: string;
  indexName?: string;
  nextRepriceDate?: string;
  daycountBase: string;
  paymentFreq: string;
  repricingFreq?: string;
  currency: string;
  floorRate?: number;
  capRate?: number;
  rateType: string;
}

/** Response from POST /api/sessions/{id}/whatif/decompose */
export interface DecomposeResponse {
  sessionId: string;
  positions: DecomposedPosition[];
  positionCount: number;
}

/** Request body for POST /api/sessions/{id}/whatif/calculate */
export interface WhatIfV2CalculateRequest {
  additions: LoanSpec[];
  removals: WhatIfModification[];
  repricing_overrides?: RepricingPayload[];
}

/** Backend-facing repricing payload (snake_case). */
export interface RepricingPayload {
  subcategory_id: string;
  side: 'asset' | 'liability';
  scope: 'entire' | 'new-production';
  new_production_pct?: number;
  new_rate: number;                 // Decimal
}

// ── Find Limit types ─────────────────────────────────────────────────────

export type FindLimitMetric = 'eve' | 'nii';
export type FindLimitSolveFor = 'notional' | 'rate' | 'maturity' | 'spread';

export interface FindLimitRequest {
  product_spec: LoanSpec;
  target_metric: FindLimitMetric;
  target_scenario: string;       // "base" | "worst" | specific scenario id
  limit_value: number;           // absolute metric value target
  solve_for: FindLimitSolveFor;
}

export interface FindLimitResponse {
  session_id: string;
  found_value: number;
  achieved_metric: number;
  target_metric: string;
  target_scenario: string;
  solve_for: string;
  converged: boolean;
  iterations: number;
  tolerance: number;
  product_spec: LoanSpec;        // echo back with solved value filled
}

// ── Reference index options for variable/mixed rates ─────────────────────

export const VARIABLE_INDEX_OPTIONS = [
  { value: 'EUR_EURIBOR_3M',  label: 'EURIBOR 3M' },
  { value: 'EUR_EURIBOR_6M',  label: 'EURIBOR 6M' },
  { value: 'EUR_EURIBOR_12M', label: 'EURIBOR 12M' },
  { value: 'EUR_ESTR_OIS',    label: 'ESTR OIS' },
  { value: 'USD_SOFR',        label: 'SOFR' },
  { value: 'GBP_SONIA',       label: 'SONIA' },
] as const;

export const PAYMENT_FREQ_OPTIONS = [
  { value: '1M',  label: 'Monthly' },
  { value: '3M',  label: 'Quarterly' },
  { value: '6M',  label: 'Semi-Annual' },
  { value: '12M', label: 'Annual' },
] as const;

// ── Product Catalog: Progressive selection for What-If Add ───────────────
// Families → Variants → Form (conditions). Each variant optionally maps to
// a PRODUCT_TEMPLATES entry via templateId. Variants without a template show
// a "coming soon" placeholder.

export interface ProductVariant {
  id: string;
  name: string;
  description: string;
  templateId?: string;     // maps to PRODUCT_TEMPLATES[].id
  comingSoon?: boolean;    // true = no template yet, show placeholder
}

export interface AmortizationOption {
  id: AmortizationType;
  name: string;
  description: string;
}

export interface ProductFamily {
  id: string;
  name: string;
  description: string;
  icon: string;            // lucide-react icon name for dynamic rendering
  side: 'asset' | 'liability' | 'derivative';
  amortizationTypes?: AmortizationType[];  // When present, shows amortization dropdown
  noAmortization?: boolean;  // true = skip amortization entirely (e.g. derivatives)
  variants: ProductVariant[];
}

/** Amortization options available for the Loans family dropdown. */
export const AMORTIZATION_OPTIONS: AmortizationOption[] = [
  { id: 'bullet',    name: 'Bullet',           description: 'Interest-only during life, full principal at maturity' },
  { id: 'linear',    name: 'Linear',           description: 'Equal principal repayments with declining interest' },
  { id: 'annuity',   name: 'Annuity (French)', description: 'Equal total payments throughout the life' },
  { id: 'scheduled', name: 'Scheduled',        description: 'Custom amortization schedule' },
];

export const PRODUCT_FAMILIES: ProductFamily[] = [
  // ── Assets ──────────────────────────────────────────────────────────────
  {
    id: 'loans',
    name: 'Loans',
    description: 'All lending: corporate, retail, consumer, and mortgages',
    icon: 'Landmark',
    side: 'asset',
    amortizationTypes: ['bullet', 'linear', 'annuity', 'scheduled'],
    variants: [
      { id: 'loan-fixed',    name: 'Fixed Rate',    description: 'Fixed coupon throughout the life of the loan',          templateId: 'fixed-loan' },
      { id: 'loan-floating', name: 'Floating Rate', description: 'Reprices periodically against a reference index',       templateId: 'floating-loan' },
      { id: 'loan-mixed',    name: 'Mixed Rate',    description: 'Fixed rate initial period, then switches to floating',  templateId: 'mixed-loan' },
    ],
  },
  {
    id: 'securities',
    name: 'Securities',
    description: 'Fixed-income investment portfolio',
    icon: 'TrendingUp',
    side: 'asset',
    variants: [
      { id: 'bond-fixed', name: 'Fixed Coupon Bond',       description: 'Government or corporate bond with fixed coupon',           templateId: 'bond-portfolio' },
      { id: 'bond-frn',   name: 'Floating Rate Note (FRN)', description: 'Coupon reprices periodically against a reference index',  templateId: 'bond-frn' },
    ],
  },
  {
    id: 'securitisations',
    name: 'Securitisations',
    description: 'Securitised asset pools (RMBS, ABS)',
    icon: 'Layers',
    side: 'asset',
    variants: [
      { id: 'securitised-pool', name: 'RMBS / ABS Pool', description: 'Residential mortgage or asset-backed securities pool', templateId: 'securitised' },
    ],
  },
  // ── Liabilities ─────────────────────────────────────────────────────────
  {
    id: 'deposits',
    name: 'Deposits',
    description: 'Customer deposit accounts',
    icon: 'Wallet',
    side: 'liability',
    variants: [
      { id: 'deposit-demand', name: 'Demand Deposits (NMD)', description: 'Non-maturing demand deposits and savings accounts', templateId: 'nmd' },
      { id: 'deposit-term',   name: 'Term Deposits',          description: 'Fixed maturity and rate',                           templateId: 'term-deposit' },
    ],
  },
  {
    id: 'senior-unsecured',
    name: 'Senior Unsecured',
    description: 'Senior unsecured wholesale funding instruments',
    icon: 'Building2',
    side: 'liability',
    variants: [
      { id: 'senior-fixed',    name: 'Fixed Rate',    description: 'Fixed coupon senior unsecured debt',  templateId: 'wholesale-fixed' },
      { id: 'senior-floating', name: 'Floating Rate', description: 'Floating rate senior unsecured debt', templateId: 'wholesale-floating' },
    ],
  },
  {
    id: 'covered-bonds',
    name: 'Covered Bonds',
    description: 'Covered bonds backed by mortgage portfolios',
    icon: 'ShieldCheck',
    side: 'liability',
    variants: [
      { id: 'covered-fixed',    name: 'Fixed Rate',    description: 'Fixed coupon covered bond (cédulas hipotecarias)', templateId: 'covered-bond' },
      { id: 'covered-floating', name: 'Floating Rate', description: 'Floating rate covered bond (FRN)',                  templateId: 'covered-bond-floating' },
    ],
  },
  {
    id: 'subordinated-debt',
    name: 'Subordinated / Tier 2',
    description: 'Subordinated debt and Tier 2 capital instruments',
    icon: 'ArrowDownToLine',
    side: 'liability',
    variants: [
      { id: 'sub-fixed',           name: 'Fixed Rate',        description: 'Fixed coupon subordinated debt',                              templateId: 'subordinated' },
      { id: 'sub-floating',        name: 'Floating Rate',    description: 'Floating rate subordinated debt',                            templateId: 'subordinated-floating' },
      { id: 'sub-fixed-to-float',  name: 'Fixed-to-Floating', description: 'Fixed rate until call date, then floating (typical 10NC5)', templateId: 'subordinated-fix2float' },
    ],
  },
  // ── Derivatives ─────────────────────────────────────────────────────────
  {
    id: 'derivatives',
    name: 'Derivatives',
    description: 'Interest rate hedging instruments',
    icon: 'ArrowLeftRight',
    side: 'derivative',
    noAmortization: true,
    variants: [
      { id: 'irs',       name: 'Interest Rate Swap (IRS)', description: 'Pay fixed / receive float or vice versa',      templateId: 'irs-hedge' },
      { id: 'ccs',       name: 'Cross-Currency Swap',      description: 'FX and rate risk hedging across currencies',   comingSoon: true },
      { id: 'cap-floor', name: 'Cap / Floor',              description: 'Interest rate cap or floor option',            comingSoon: true },
    ],
  },
];

// ── Legacy Product Templates (backward compat) ──────────────────────────

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
      { id: 'refIndex', label: 'Reference Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'EURIBOR 12M', '€STR', 'SOFR', 'SONIA'] },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: true, placeholder: '150' },
      { id: 'repricingFreq', label: 'Repricing Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'hasFloor', label: 'Floor', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'floorRate', label: 'Floor Rate (%)', type: 'number', required: true, placeholder: '0.00', showWhen: { field: 'hasFloor', value: 'Yes' } },
      { id: 'hasCap', label: 'Cap', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'capRate', label: 'Cap Rate (%)', type: 'number', required: true, placeholder: '5.00', showWhen: { field: 'hasCap', value: 'Yes' } },
    ],
  },
  {
    id: 'mixed-loan',
    name: 'Mixed-rate Loan Portfolio',
    category: 'asset',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '10,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'fixedRate', label: 'Fixed Rate (%)', type: 'number', required: true, placeholder: '2.50' },
      { id: 'mixedFixedYears', label: 'Fixed Period (years)', type: 'number', required: true, placeholder: '5' },
      { id: 'refIndex', label: 'Reference Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'EURIBOR 12M', '€STR', 'SOFR', 'SONIA'] },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: true, placeholder: '100' },
      { id: 'repricingFreq', label: 'Repricing Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'hasFloor', label: 'Floor', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'floorRate', label: 'Floor Rate (%)', type: 'number', required: true, placeholder: '0.00', showWhen: { field: 'hasFloor', value: 'Yes' } },
      { id: 'hasCap', label: 'Cap', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'capRate', label: 'Cap Rate (%)', type: 'number', required: true, placeholder: '5.00', showWhen: { field: 'hasCap', value: 'Yes' } },
    ],
  },
  {
    id: 'bond-portfolio',
    name: 'Bond Portfolio (Fixed Income)',
    category: 'asset',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '50,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'coupon', label: 'Coupon Rate (%)', type: 'number', required: true, placeholder: '2.75' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Semi-Annual', 'Annual'] },
      { id: 'isCallable', label: 'Callable', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'callDate', label: 'First Call Date', type: 'date', required: true, showWhen: { field: 'isCallable', value: 'Yes' } },
    ],
  },
  {
    id: 'bond-frn',
    name: 'Floating Rate Note (FRN)',
    category: 'asset',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '50,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'refIndex', label: 'Reference Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'EURIBOR 12M', '€STR', 'SOFR', 'SONIA'] },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: true, placeholder: '50' },
      { id: 'repricingFreq', label: 'Repricing Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'hasFloor', label: 'Floor', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'floorRate', label: 'Floor Rate (%)', type: 'number', required: true, placeholder: '0.00', showWhen: { field: 'hasFloor', value: 'Yes' } },
      { id: 'hasCap', label: 'Cap', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'capRate', label: 'Cap Rate (%)', type: 'number', required: true, placeholder: '5.00', showWhen: { field: 'hasCap', value: 'Yes' } },
      { id: 'isCallable', label: 'Callable', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'callDate', label: 'First Call Date', type: 'date', required: true, showWhen: { field: 'isCallable', value: 'Yes' } },
    ],
  },
  {
    id: 'nmd',
    name: 'Non-Maturing Deposits (NMD)',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '100,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'depositRate', label: 'Deposit Rate (%)', type: 'number', required: true, placeholder: '0.50' },
      { id: 'repricingBeta', label: 'Repricing Beta (0–1)', type: 'number', required: false, placeholder: '0.40' },
      { id: 'coreRatio', label: 'Core Deposit Ratio (%)', type: 'number', required: false, placeholder: '70' },
      { id: 'avgLife', label: 'Average Life (years)', type: 'number', required: false, placeholder: '3.5' },
    ],
  },
  {
    id: 'term-deposit',
    name: 'Term Deposits',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '25,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'depositRate', label: 'Deposit Rate (%)', type: 'number', required: true, placeholder: '3.25' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual', 'At Maturity'] },
    ],
  },
  {
    id: 'wholesale-fixed',
    name: 'Wholesale Funding (Fixed)',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '75,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'coupon', label: 'Coupon Rate (%)', type: 'number', required: true, placeholder: '4.00' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'isCallable', label: 'Callable', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'callDate', label: 'First Call Date', type: 'date', required: true, showWhen: { field: 'isCallable', value: 'Yes' } },
    ],
  },
  {
    id: 'wholesale-floating',
    name: 'Wholesale Funding (Floating)',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '75,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'refIndex', label: 'Reference Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'EURIBOR 12M', '€STR', 'SOFR', 'SONIA'] },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: true, placeholder: '100' },
      { id: 'repricingFreq', label: 'Repricing Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'hasFloor', label: 'Floor', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'floorRate', label: 'Floor Rate (%)', type: 'number', required: true, placeholder: '0.00', showWhen: { field: 'hasFloor', value: 'Yes' } },
      { id: 'hasCap', label: 'Cap', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'capRate', label: 'Cap Rate (%)', type: 'number', required: true, placeholder: '5.00', showWhen: { field: 'hasCap', value: 'Yes' } },
      { id: 'isCallable', label: 'Callable', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'callDate', label: 'First Call Date', type: 'date', required: true, showWhen: { field: 'isCallable', value: 'Yes' } },
    ],
  },
  {
    id: 'covered-bond',
    name: 'Covered Bonds',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '100,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'coupon', label: 'Coupon Rate (%)', type: 'number', required: true, placeholder: '3.25' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Semi-Annual', 'Annual'] },
      { id: 'isCallable', label: 'Callable', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'callDate', label: 'First Call Date', type: 'date', required: true, showWhen: { field: 'isCallable', value: 'Yes' } },
    ],
  },
  {
    id: 'covered-bond-floating',
    name: 'Covered Bonds (Floating)',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '100,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'refIndex', label: 'Reference Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'EURIBOR 12M', '€STR', 'SOFR', 'SONIA'] },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: true, placeholder: '30' },
      { id: 'repricingFreq', label: 'Repricing Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'hasFloor', label: 'Floor', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'floorRate', label: 'Floor Rate (%)', type: 'number', required: true, placeholder: '0.00', showWhen: { field: 'hasFloor', value: 'Yes' } },
      { id: 'hasCap', label: 'Cap', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'capRate', label: 'Cap Rate (%)', type: 'number', required: true, placeholder: '5.00', showWhen: { field: 'hasCap', value: 'Yes' } },
      { id: 'isCallable', label: 'Callable', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'callDate', label: 'First Call Date', type: 'date', required: true, showWhen: { field: 'isCallable', value: 'Yes' } },
    ],
  },
  {
    id: 'subordinated',
    name: 'Subordinated Debt / Tier 2',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '50,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'coupon', label: 'Coupon Rate (%)', type: 'number', required: true, placeholder: '5.50' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Semi-Annual', 'Annual'] },
      { id: 'isCallable', label: 'Callable', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'callDate', label: 'First Call Date', type: 'date', required: true, showWhen: { field: 'isCallable', value: 'Yes' } },
    ],
  },
  {
    id: 'subordinated-floating',
    name: 'Subordinated Debt / Tier 2 (Floating)',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '50,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'refIndex', label: 'Reference Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'EURIBOR 12M', '€STR', 'SOFR', 'SONIA'] },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: true, placeholder: '250' },
      { id: 'repricingFreq', label: 'Repricing Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'hasFloor', label: 'Floor', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'floorRate', label: 'Floor Rate (%)', type: 'number', required: true, placeholder: '0.00', showWhen: { field: 'hasFloor', value: 'Yes' } },
      { id: 'hasCap', label: 'Cap', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'capRate', label: 'Cap Rate (%)', type: 'number', required: true, placeholder: '5.00', showWhen: { field: 'hasCap', value: 'Yes' } },
      { id: 'isCallable', label: 'Callable', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'callDate', label: 'First Call Date', type: 'date', required: true, showWhen: { field: 'isCallable', value: 'Yes' } },
    ],
  },
  {
    id: 'subordinated-fix2float',
    name: 'Subordinated Debt / Tier 2 (Fixed-to-Floating)',
    category: 'liability',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '50,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'fixedRate', label: 'Fixed Rate (%)', type: 'number', required: true, placeholder: '5.50' },
      { id: 'callDate', label: 'Switch / Call Date', type: 'date', required: true },
      { id: 'refIndex', label: 'Reference Index (post-switch)', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'EURIBOR 12M', '€STR', 'SOFR', 'SONIA'] },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: true, placeholder: '250' },
      { id: 'repricingFreq', label: 'Repricing Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly', 'Semi-Annual', 'Annual'] },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Semi-Annual', 'Annual'] },
      { id: 'hasFloor', label: 'Floor', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'floorRate', label: 'Floor Rate (%)', type: 'number', required: true, placeholder: '0.00', showWhen: { field: 'hasFloor', value: 'Yes' } },
      { id: 'hasCap', label: 'Cap', type: 'select', required: true, options: ['No', 'Yes'] },
      { id: 'capRate', label: 'Cap Rate (%)', type: 'number', required: true, placeholder: '5.00', showWhen: { field: 'hasCap', value: 'Yes' } },
    ],
  },
  {
    id: 'irs-hedge',
    name: 'Interest Rate Swap (Hedge)',
    category: 'derivative',
    fieldGroups: [
      { id: 'fixed-leg',    label: 'Fixed Leg',    subtitle: { field: 'payingLeg', map: { Fixed: 'Pay', Floating: 'Receive' } } },
      { id: 'floating-leg', label: 'Floating Leg', subtitle: { field: 'payingLeg', map: { Fixed: 'Receive', Floating: 'Pay' } } },
    ],
    fields: [
      // ── General (ungrouped) ──
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '50,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'payingLeg', label: 'Paying Leg', type: 'select', required: true, options: ['Fixed', 'Floating'] },
      { id: 'receivingLeg', label: 'Receiving Leg', type: 'text', required: false, disabled: true, derivedFrom: { field: 'payingLeg', map: { Fixed: 'Floating', Floating: 'Fixed' } } },
      // ── Fixed Leg ──
      { id: 'fixedRate', label: 'Fixed Rate (%)', type: 'number', required: true, placeholder: '2.50', group: 'fixed-leg' },
      { id: 'fixedLegDC', label: 'Day Count', type: 'select', required: true, options: ['30/360', 'ACT/360', 'ACT/365', 'ACT/ACT'], group: 'fixed-leg' },
      // ── Floating Leg ──
      { id: 'refIndex', label: 'Reference Index', type: 'select', required: true, options: ['EURIBOR 3M', 'EURIBOR 6M', 'EURIBOR 12M', '€STR', 'SOFR', 'SONIA'], group: 'floating-leg' },
      { id: 'fixingConvention', label: 'Fixing', type: 'select', required: true, options: ['In Advance', 'In Arrears'], group: 'floating-leg' },
      { id: 'spread', label: 'Spread (bps)', type: 'number', required: false, placeholder: '0', group: 'floating-leg' },
      { id: 'floatLegDC', label: 'Day Count', type: 'select', required: true, options: ['ACT/360', 'ACT/365', 'ACT/ACT', '30/360'], group: 'floating-leg' },
      // ── General (ungrouped, trailing) ──
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Quarterly', 'Semi-Annual', 'Annual'] },
    ],
  },
  {
    id: 'securitised',
    name: 'Securitised Assets',
    category: 'asset',
    fields: [
      { id: 'notional', label: 'Notional Amount', type: 'number', required: true, placeholder: '200,000,000' },
      { id: 'currency', label: 'Currency', type: 'select', required: true, options: ['USD', 'EUR', 'GBP', 'CHF'] },
      { id: 'startDate', label: 'Start Date', type: 'date', required: true },
      { id: 'maturityDate', label: 'Maturity Date', type: 'date', required: true },
      { id: 'wac', label: 'Weighted Avg Coupon (%)', type: 'number', required: true, placeholder: '4.25' },
      { id: 'paymentFreq', label: 'Payment Frequency', type: 'select', required: true, options: ['Monthly', 'Quarterly'] },
      { id: 'cpr', label: 'Prepayment Speed (CPR %)', type: 'number', required: false, placeholder: '8' },
    ],
  },
];
