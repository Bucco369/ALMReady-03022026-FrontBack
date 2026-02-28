"""Pydantic models defining the REST contract between frontend and backend."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Session & Metadata ──────────────────────────────────────────────────────

class SessionMeta(BaseModel):
    session_id: str
    created_at: str
    status: str = "active"
    schema_version: str = "v1"
    has_balance: bool = False
    has_curves: bool = False


# ── Balance Tree ────────────────────────────────────────────────────────────

class BalanceSheetSummary(BaseModel):
    sheet: str
    rows: int
    columns: list[str]
    total_saldo_ini: float | None = None
    total_book_value: float | None = None
    avg_tae: float | None = None


class BalanceTreeNode(BaseModel):
    id: str
    label: str
    amount: float
    positions: int
    avg_rate: float | None = None
    avg_maturity: float | None = None


class BalanceTreeCategory(BaseModel):
    id: str
    label: str
    amount: float
    positions: int
    avg_rate: float | None = None
    avg_maturity: float | None = None
    subcategories: list[BalanceTreeNode] = Field(default_factory=list)


class BalanceSummaryTree(BaseModel):
    assets: BalanceTreeCategory | None = None
    liabilities: BalanceTreeCategory | None = None
    equity: BalanceTreeCategory | None = None
    derivatives: BalanceTreeCategory | None = None


class BalanceUploadResponse(BaseModel):
    session_id: str
    filename: str
    uploaded_at: str
    sheets: list[BalanceSheetSummary]
    sample_rows: dict[str, list[dict[str, Any]]]
    summary_tree: BalanceSummaryTree
    bank_id: str | None = None


# ── Balance Contracts & Details ─────────────────────────────────────────────

class BalanceContract(BaseModel):
    contract_id: str
    sheet: str | None = None
    category: str
    categoria_ui: str | None = None
    subcategory: str
    subcategoria_ui: str | None = None
    group: str | None = None
    currency: str | None = None
    counterparty: str | None = None
    business_segment: str | None = None
    strategic_segment: str | None = None
    book_value_def: str | None = None
    rate_type: str | None = None
    maturity_bucket: str | None = None
    remuneration_bucket: str | None = None
    maturity_years: float | None = None
    amount: float | None = None
    rate: float | None = None


class BalanceContractsResponse(BaseModel):
    session_id: str
    total: int
    page: int
    page_size: int
    contracts: list[BalanceContract]


class FacetOption(BaseModel):
    value: str
    count: int


class BalanceDetailsFacets(BaseModel):
    currencies: list[FacetOption] = Field(default_factory=list)
    rate_types: list[FacetOption] = Field(default_factory=list)
    segments: list[FacetOption] = Field(default_factory=list)
    strategic_segments: list[FacetOption] = Field(default_factory=list)
    segment_tree: dict[str, list[FacetOption]] = Field(default_factory=dict)
    maturities: list[FacetOption] = Field(default_factory=list)
    remunerations: list[FacetOption] = Field(default_factory=list)
    book_values: list[FacetOption] = Field(default_factory=list)


class BalanceDetailsGroup(BaseModel):
    group: str
    amount: float
    positions: int
    avg_rate: float | None = None
    avg_maturity: float | None = None


class BalanceDetailsTotals(BaseModel):
    amount: float
    positions: int
    avg_rate: float | None = None
    avg_maturity: float | None = None


class BalanceDetailsResponse(BaseModel):
    session_id: str
    categoria_ui: str | None = None
    subcategoria_ui: str | None = None
    groups: list[BalanceDetailsGroup]
    totals: BalanceDetailsTotals
    facets: BalanceDetailsFacets


# ── Curves ──────────────────────────────────────────────────────────────────

class CurvePoint(BaseModel):
    tenor: str
    t_years: float
    rate: float


class CurveCatalogItem(BaseModel):
    curve_id: str
    currency: str | None = None
    label_tech: str
    points_count: int
    min_t: float | None = None
    max_t: float | None = None


class CurvesSummaryResponse(BaseModel):
    session_id: str
    filename: str
    uploaded_at: str
    default_discount_curve_id: str | None = None
    curves: list[CurveCatalogItem] = Field(default_factory=list)


class CurvePointsResponse(BaseModel):
    session_id: str
    curve_id: str
    points: list[CurvePoint]


# ── Behavioural Assumptions ─────────────────────────────────────────────────

class NMDBehaviouralParams(BaseModel):
    core_proportion: float          # 0–100 (%)
    core_average_maturity: float    # years (informational — derived from distribution)
    pass_through_rate: float        # 0–100 (%), NII repricing sensitivity
    distribution: dict[str, float]  # bucket_id → % of total NMDs

    @property
    def pass_through_fraction(self) -> float:
        """Convert pass-through rate from % to 0–1 fraction for engine use."""
        return self.pass_through_rate / 100.0


class LoanPrepaymentParams(BaseModel):
    smm: float                      # 0–50 (%) monthly

    @property
    def cpr_annual(self) -> float:
        """Convert SMM (monthly %) to CPR (annual fraction) for engine use."""
        return 1.0 - (1.0 - self.smm / 100.0) ** 12


class TermDepositParams(BaseModel):
    tdrr: float                     # 0–50 (%) monthly

    @property
    def tdrr_annual(self) -> float:
        """Convert monthly TDRR (%) to annual fraction for engine use."""
        return 1.0 - (1.0 - self.tdrr / 100.0) ** 12


class BehaviouralAssumptions(BaseModel):
    nmd: NMDBehaviouralParams | None = None
    loan_prepayment: LoanPrepaymentParams | None = None
    term_deposit: TermDepositParams | None = None


# ── Calculation ─────────────────────────────────────────────────────────────

class CalculateRequest(BaseModel):
    discount_curve_id: str = "EUR_ESTR_OIS"
    scenarios: list[str] = Field(
        default=["parallel-up", "parallel-down", "steepener", "flattener", "short-up", "short-down"],
    )
    analysis_date: str | None = None
    currency: str = "EUR"
    risk_free_index: str | None = None
    behavioural: BehaviouralAssumptions | None = None


class ScenarioResultItem(BaseModel):
    scenario_id: str
    scenario_name: str
    eve: float
    nii: float
    delta_eve: float
    delta_nii: float


class CalculationResultsResponse(BaseModel):
    session_id: str
    base_eve: float
    base_nii: float
    worst_case_eve: float
    worst_case_delta_eve: float
    worst_case_scenario: str
    scenario_results: list[ScenarioResultItem]
    calculated_at: str
    warnings: list[str] = []


# ── What-If ─────────────────────────────────────────────────────────────────

class WhatIfModificationItem(BaseModel):
    id: str
    type: str
    label: str = ""
    notional: float | None = None
    currency: str | None = None
    category: str | None = None
    subcategory: str | None = None
    rate: float | None = None
    maturity: float | None = None
    removeMode: str | None = None
    contractIds: list[str] | None = None
    productTemplateId: str | None = None
    startDate: str | None = None
    maturityDate: str | None = None
    paymentFreq: str | None = None
    repricingFreq: str | None = None
    refIndex: str | None = None
    spread: float | None = None
    # V2 fields (from What-If Workbench)
    amortization: str | None = None       # 'bullet' | 'linear' | 'annuity'
    floorRate: float | None = None        # Interest rate floor (decimal)
    capRate: float | None = None          # Interest rate cap (decimal)
    grace_years: float | None = None      # Grace period (years) — approximated in V1
    mixedFixedYears: float | None = None  # Mixed rate fixed period — approximated in V1


class WhatIfCalculateRequest(BaseModel):
    modifications: list[WhatIfModificationItem]


class WhatIfBucketDelta(BaseModel):
    scenario: str
    bucket_name: str
    bucket_start_years: float
    asset_pv_delta: float
    liability_pv_delta: float


class WhatIfMonthDelta(BaseModel):
    scenario: str
    month_index: int
    month_label: str
    income_delta: float
    expense_delta: float


class WhatIfResultsResponse(BaseModel):
    session_id: str
    base_eve_delta: float
    worst_eve_delta: float
    base_nii_delta: float
    worst_nii_delta: float
    scenario_eve_deltas: dict[str, float] = {}
    scenario_nii_deltas: dict[str, float] = {}
    eve_bucket_deltas: list[WhatIfBucketDelta] = []
    nii_month_deltas: list[WhatIfMonthDelta] = []
    calculated_at: str


# ── Chart Data ──────────────────────────────────────────────────────────────

class ChartBucketRow(BaseModel):
    scenario: str
    bucket_name: str
    bucket_start_years: float
    bucket_end_years: float | None
    asset_pv: float
    liability_pv: float
    net_pv: float


class ChartNiiMonthRow(BaseModel):
    scenario: str
    month_index: int
    month_label: str
    interest_income: float
    interest_expense: float
    net_nii: float


class ChartDataResponse(BaseModel):
    session_id: str
    eve_buckets: list[ChartBucketRow]
    nii_monthly: list[ChartNiiMonthRow]


# ── What-If V2 (Decomposer) ──────────────────────────────────────────────

class LoanSpecItem(BaseModel):
    """Rich loan spec sent from frontend — maps to decomposer.LoanSpec."""
    id: str
    notional: float
    term_years: float
    side: str = "A"
    currency: str = "EUR"
    rate_type: str = "fixed"
    fixed_rate: float | None = None
    variable_index: str | None = None
    spread_bps: float = 0.0
    mixed_fixed_years: float | None = None
    amortization: str = "bullet"
    grace_years: float = 0.0
    daycount: str = "30/360"
    payment_freq: str = "12M"
    repricing_freq: str | None = None
    start_date: str | None = None
    floor_rate: float | None = None
    cap_rate: float | None = None
    label: str = ""


class DecomposedPosition(BaseModel):
    """Single motor position from decomposer."""
    contract_id: str
    side: str
    source_contract_type: str
    notional: float
    fixed_rate: float
    spread: float
    start_date: str
    maturity_date: str
    index_name: str | None = None
    next_reprice_date: str | None = None
    daycount_base: str
    payment_freq: str
    repricing_freq: str | None = None
    currency: str
    floor_rate: float | None = None
    cap_rate: float | None = None
    rate_type: str


class DecomposeResponse(BaseModel):
    session_id: str
    positions: list[DecomposedPosition]
    position_count: int


class WhatIfV2CalculateRequest(BaseModel):
    additions: list[LoanSpecItem] = Field(default_factory=list)
    removals: list[WhatIfModificationItem] = Field(default_factory=list)


class FindLimitRequest(BaseModel):
    product_spec: LoanSpecItem
    target_metric: str          # "eve" | "nii"
    target_scenario: str        # "base" | "worst" | scenario name
    limit_value: float          # absolute target
    solve_for: str              # "notional" | "rate" | "maturity" | "spread"


class FindLimitResponse(BaseModel):
    session_id: str
    found_value: float
    achieved_metric: float
    target_metric: str
    target_scenario: str
    solve_for: str
    converged: bool
    iterations: int
    tolerance: float
    product_spec: LoanSpecItem
