from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from engine.io.positions_pipeline import load_positions_from_specs
from engine.io.positions_reader import read_positions_tabular


def _mapping_for_csv_mixed_rows() -> dict:
    return {
        "REQUIRED_CANONICAL_COLUMNS": (
            "contract_id",
            "start_date",
            "maturity_date",
            "notional",
            "side",
            "rate_type",
            "daycount_base",
        ),
        "OPTIONAL_CANONICAL_COLUMNS": (
            "index_name",
            "spread",
            "fixed_rate",
            "repricing_freq",
            "payment_freq",
            "next_reprice_date",
            "floor_rate",
            "cap_rate",
        ),
        "BANK_COLUMNS_MAP": {
            "Identifier": "contract_id",
            "Start date": "start_date",
            "Maturity date": "maturity_date",
            "Outstanding principal": "notional",
            "Position": "side",
            "Tipo tasa": "rate_type",
            "Day count convention": "daycount_base",
            "Indexed curve": "index_name",
            "Interest spread": "spread",
        },
        "SIDE_MAP": {
            "LONG": "A",
            "SHORT": "L",
        },
        "RATE_TYPE_MAP": {
            "VAR": "float",
            "FIX": "fixed",
        },
        "DATE_DAYFIRST": True,
        "NUMERIC_SCALE_MAP": {
            "spread": 0.01,
        },
        "INDEX_NAME_ALIASES": {
            "DEUDA_ESPA?OLA": "DEUDA_ESPAÑOLA",
        },
    }


def _mapping_for_pipeline_excel() -> dict:
    return {
        "REQUIRED_CANONICAL_COLUMNS": (
            "contract_id",
            "start_date",
            "maturity_date",
            "notional",
            "side",
            "rate_type",
            "daycount_base",
        ),
        "OPTIONAL_CANONICAL_COLUMNS": (
            "index_name",
            "spread",
            "fixed_rate",
            "repricing_freq",
            "payment_freq",
            "next_reprice_date",
            "floor_rate",
            "cap_rate",
        ),
        "BANK_COLUMNS_MAP": {
            "Contract ID": "contract_id",
            "Start": "start_date",
            "Maturity": "maturity_date",
            "Notional": "notional",
            "Fixed": "fixed_rate",
        },
        "SIDE_MAP": {
            "A": "A",
            "L": "L",
        },
        "RATE_TYPE_MAP": {
            "FIXED": "fixed",
            "FLOAT": "float",
        },
        "DATE_DAYFIRST": True,
        "SOURCE_SPECS": [
            {
                "name": "assets_sheet",
                "pattern": "fiare_mock.xlsx",
                "file_type": "excel",
                "sheet_name": "Assets",
                "defaults": {
                    "side": "A",
                    "rate_type": "fixed",
                    "daycount_base": "ACT/360",
                },
                "source_bank": "fiare",
                "source_contract_type": "assets",
            },
            {
                "name": "liabilities_sheet",
                "pattern": "fiare_mock.xlsx",
                "file_type": "excel",
                "sheet_name": "Liabilities",
                "defaults": {
                    "side": "L",
                    "rate_type": "fixed",
                    "daycount_base": "ACT/360",
                },
                "source_bank": "fiare",
                "source_contract_type": "liabilities",
            },
        ],
    }


class TestPositionsPipeline(unittest.TestCase):
    def test_csv_with_header_token_and_row_kind_filter(self) -> None:
        csv_content = """File type;Contracts
Charset;ISO-8859-1
Contract type;Variable scheduled
Reference day;30/11/2024
;Identifier;Start date;Maturity date;Position;Outstanding principal;Tipo tasa;Day count convention;Indexed curve;Interest spread
contract;CTR_1;01/01/2025;01/01/2026;Long;1000,0;VAR;Actual/360;EUR_EURIBOR_3M;1,50
payment;Principal;01/02/2025;100
        contract;CTR_2;15/01/2025;15/01/2027;Short;2500,0;VAR;Actual/360;DEUDA_ESPA?OLA;2,00
"""

        mapping = _mapping_for_csv_mixed_rows()
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "unicaja_sample.csv"
            path.write_text(csv_content, encoding="cp1252")

            out = read_positions_tabular(
                path=path,
                mapping_module=mapping,
                file_type="csv",
                header_token="Identifier",
                row_kind_column=0,
                include_row_kinds=["contract"],
                delimiter=";",
                encoding="cp1252",
                source_row_column="source_row",
                reset_index=True,
            )

        self.assertEqual(len(out), 2)
        self.assertListEqual(out["contract_id"].tolist(), ["CTR_1", "CTR_2"])
        self.assertListEqual(out["side"].tolist(), ["A", "L"])
        self.assertAlmostEqual(float(out["spread"].iloc[0]), 0.015)
        self.assertAlmostEqual(float(out["spread"].iloc[1]), 0.02)
        self.assertEqual(str(out["index_name"].iloc[1]), "DEUDA_ESPAÑOLA")
        self.assertListEqual(out["source_row"].tolist(), [6, 8])

    def test_load_positions_from_specs_adds_lineage_and_defaults(self) -> None:
        mapping = _mapping_for_pipeline_excel()

        assets = pd.DataFrame(
            [
                {
                    "Contract ID": "A_1",
                    "Start": "2025-01-01",
                    "Maturity": "2026-01-01",
                    "Notional": 100.0,
                    "Fixed": 0.02,
                }
            ]
        )
        liabilities = pd.DataFrame(
            [
                {
                    "Contract ID": "L_1",
                    "Start": "2025-01-01",
                    "Maturity": "2026-01-01",
                    "Notional": 250.0,
                    "Fixed": 0.03,
                }
            ]
        )

        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            xlsx_path = root / "fiare_mock.xlsx"
            with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                assets.to_excel(writer, sheet_name="Assets", index=False)
                liabilities.to_excel(writer, sheet_name="Liabilities", index=False)

            out = load_positions_from_specs(root, mapping)

        self.assertEqual(len(out), 2)
        self.assertSetEqual(set(out["contract_id"].tolist()), {"A_1", "L_1"})
        self.assertSetEqual(set(out["side"].tolist()), {"A", "L"})
        self.assertSetEqual(set(out["rate_type"].tolist()), {"fixed"})
        self.assertSetEqual(set(out["daycount_base"].tolist()), {"ACT/360"})
        self.assertSetEqual(set(out["source_bank"].tolist()), {"fiare"})
        self.assertSetEqual(set(out["source_spec"].tolist()), {"assets_sheet", "liabilities_sheet"})
        self.assertTrue((out["source_file"].astype(str).str.endswith("fiare_mock.xlsx")).all())
        self.assertSetEqual(set(out["source_row"].tolist()), {2})


if __name__ == "__main__":
    unittest.main()
