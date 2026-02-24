from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from engine.io.scheduled_reader import load_scheduled_from_specs, read_scheduled_tabular


def _mapping_for_scheduled_csv() -> dict:
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
    }


def _sample_scheduled_csv() -> str:
    return """File type;Contracts
Charset;ISO-8859-1
Contract type;Variable scheduled
Reference day;30/11/2024
;Identifier;Start date;Maturity date;Position;Outstanding principal;Tipo tasa;Day count convention;Indexed curve;Interest spread
contract;CTR_1;01/01/2025;01/01/2027;Long;1000,0;VAR;Actual/360;EUR_EURIBOR_3M;1,50
payment;Principal;01/02/2025;100,5
payment;Fee;01/03/2025;5,0
contract;CTR_2;15/01/2025;15/01/2026;Short;2500,0;VAR;30E/360;EUR_EURIBOR_6M;0
payment;Principal;15/02/2025;-50,25
"""


class TestScheduledReader(unittest.TestCase):
    def test_read_scheduled_tabular_links_payments_to_contracts(self) -> None:
        mapping = _mapping_for_scheduled_csv()

        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "scheduled_sample.csv"
            path.write_text(_sample_scheduled_csv(), encoding="cp1252")

            out = read_scheduled_tabular(
                path=path,
                mapping_module=mapping,
                file_type="csv",
                header_token="Identifier",
                row_kind_column=0,
                delimiter=";",
                encoding="cp1252",
                include_payment_types=["Principal"],
            )

        self.assertEqual(len(out.contracts), 2)
        self.assertListEqual(out.contracts["contract_id"].tolist(), ["CTR_1", "CTR_2"])
        self.assertListEqual(out.contracts["side"].tolist(), ["A", "L"])
        self.assertListEqual(out.contracts["rate_type"].tolist(), ["float", "float"])

        self.assertEqual(len(out.principal_flows), 2)
        self.assertListEqual(out.principal_flows["contract_id"].tolist(), ["CTR_1", "CTR_2"])
        self.assertListEqual(out.principal_flows["principal_amount"].round(2).tolist(), [100.5, -50.25])
        self.assertListEqual(out.principal_flows["source_row"].tolist(), [7, 10])
        self.assertListEqual(out.contracts["source_row"].tolist(), [6, 9])

    def test_load_scheduled_from_specs_adds_lineage(self) -> None:
        mapping = _mapping_for_scheduled_csv()
        mapping["SOURCE_SPECS"] = [
            {
                "name": "scheduled_a",
                "pattern": "scheduled_a.csv",
                "file_type": "csv",
                "header_token": "Identifier",
                "delimiter": ";",
                "encoding": "cp1252",
                "row_kind_column": 0,
                "source_bank": "unicaja",
                "source_contract_type": "variable_scheduled",
            },
            {
                "name": "scheduled_b",
                "pattern": "scheduled_b.csv",
                "file_type": "csv",
                "header_token": "Identifier",
                "delimiter": ";",
                "encoding": "cp1252",
                "row_kind_column": 0,
                "source_bank": "unicaja",
                "source_contract_type": "fixed_scheduled",
            },
        ]

        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "scheduled_a.csv").write_text(_sample_scheduled_csv(), encoding="cp1252")
            (root / "scheduled_b.csv").write_text(_sample_scheduled_csv(), encoding="cp1252")

            out = load_scheduled_from_specs(root, mapping)

        self.assertEqual(len(out.contracts), 4)
        self.assertEqual(len(out.principal_flows), 4)
        self.assertSetEqual(set(out.contracts["source_spec"].tolist()), {"scheduled_a", "scheduled_b"})
        self.assertSetEqual(set(out.principal_flows["source_spec"].tolist()), {"scheduled_a", "scheduled_b"})
        self.assertSetEqual(set(out.contracts["source_bank"].tolist()), {"unicaja"})
        self.assertSetEqual(set(out.principal_flows["source_bank"].tolist()), {"unicaja"})
        self.assertSetEqual(
            set(out.principal_flows["source_contract_type"].tolist()),
            {"variable_scheduled", "fixed_scheduled"},
        )


if __name__ == "__main__":
    unittest.main()
