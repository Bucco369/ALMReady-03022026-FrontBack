from .bank_mapping_template import (
    REQUIRED_CANONICAL_COLUMNS,
    OPTIONAL_CANONICAL_COLUMNS,
    BANK_COLUMNS_MAP,
    SIDE_MAP,
    RATE_TYPE_MAP,
    DATE_DAYFIRST,
    NUMERIC_SCALE_MAP,
    DEFAULT_CANONICAL_VALUES,
    INDEX_NAME_ALIASES,
    PRESERVE_UNMAPPED_COLUMNS,
    UNMAPPED_PREFIX,
    SOURCE_SPECS,
)

# NII calculation hyperparameters.
# EBA GL/2022/14 prescribes 12 months; configurable for internal analysis.
NII_HORIZON_MONTHS: int = 12
