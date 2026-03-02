# Variables pendientes de mapear en unicaja/mapping.py

Documento de seguimiento: variables que existen en los CSVs de Unicaja
pero actualmente NO se leen (no estan en el diccionario BANK_COLUMNS_MAP).

Fichero de mapping: backend/engine/banks/unicaja/mapping.py

---

## Fixed annuity.csv

Variables no mapeadas que importan para construir flujos:

| Variable en el CSV       | Importa para...                  | Estado  |
|--------------------------|----------------------------------|---------|
| Payment anchor date      | Fecha ancla de pago              | Pendiente |
| Initial principal        | Principal inicial (vs saldo vivo)| Pendiente |
| Principal grace period   | Periodo de carencia              | Pendiente |
| F18 Primario             | Clasificacion contable           | Pendiente |
| F18 Secundario           | Clasificacion contable           | Pendiente |
| Coste amort.             | Coste amortizado                 | Pendiente |
| Clasificacion            | Clasificacion interna del banco  | Pendiente |
| Opcion Compra            | Opcion call (compra anticipada)  | Pendiente |
| Opcion Venta             | Opcion put (venta anticipada)    | Pendiente |
| FINREP                   | Codigo FINREP regulatorio        | Pendiente |

---

## Fixed bullet.csv

Variables no mapeadas:

| Variable en el CSV       | Importa para...                  | Estado  |
|--------------------------|----------------------------------|---------|
| F18 Primario             | Clasificacion contable           | Pendiente |
| F18 Secundario 1         | Clasificacion contable           | Pendiente |
| F18 Secundario 2         | Clasificacion contable           | Pendiente |
| Mes de reprecio          | Mes en que se reprecia           | Pendiente |
| Interest anchor date     | Fecha ancla de intereses         | Pendiente |

## Fixed linear.csv

Variables no mapeadas:

| Variable en el CSV       | Importa para...                  | Estado  |
|--------------------------|----------------------------------|---------|
| Principal anchor date    | Fecha ancla de principal         | Pendiente |
| Principal payment period | Periodo de pago de principal     | Pendiente |
| Prepayment allowed       | Si permite amortizacion anticipada | Pendiente |
| Fair value acc...        | Valor razonable (solo si book_value_def = Fair value) | Pendiente |

## Fixed scheduled.csv

Variables no mapeadas:

| Variable en el CSV       | Importa para...                  | Estado  |
|--------------------------|----------------------------------|---------|
| Epigrafe RI2             | Clasificacion regulatoria        | Pendiente |
| Categoria RI3            | Clasificacion regulatoria        | Pendiente |
| Codigo DRC               | Codigo jerarquico interno banco (ej: 01010102) - revisar con banco | Pendiente |
| Sensible                 | Si la posicion es sensible a tipo de interes (IRRBB) | Pendiente |

## Non-maturity.csv

(Pendiente de revisar)

## Variable annuity.csv

Variables no mapeadas:

| Variable en el CSV       | Importa para...                  | Estado  |
|--------------------------|----------------------------------|---------|
| Teaser spread            | Spread del periodo teaser/promocional | Pendiente |
| Teaser period end        | Fin del periodo teaser/promocional | Pendiente |
| Indexed term             | Plazo del indice de referencia   | Pendiente |
| Indexed rate scaling     | Factor de escala del tipo indexado | Pendiente |
| Reset lag                | Dias de desfase en el repricing  | Pendiente |

## Variable bullet.csv

Mismas variables no mapeadas que Variable annuity.csv

## Variable linear.csv

Mismas variables no mapeadas que Variable annuity.csv

## Variable non-maturity.csv

Mismas variables no mapeadas que Variable annuity.csv

## Variable scheduled.csv

Mismas variables no mapeadas que Variable annuity.csv

---

## Variables ya mapeadas (referencia rapida)

| Variable en el CSV              | Se asigna como       |
|---------------------------------|----------------------|
| Identifier                      | contract_id          |
| Start date                      | start_date           |
| Maturity date                   | maturity_date        |
| Outstanding principal           | notional             |
| Position                        | side                 |
| Day count convention            | daycount_base        |
| Indexed curve                   | index_name           |
| Interest spread                 | spread               |
| Indexed rate / Last adjusted rate | fixed_rate         |
| Reset period                    | repricing_freq       |
| Payment period / Interest payment period | payment_freq |
| Annuity Payment Mode            | annuity_payment_mode |
| Reset anchor date               | next_reprice_date    |
| Interest rate floor             | floor_rate           |
| Interest rate cap               | cap_rate             |
| Producto                        | balance_product      |
| Apartado                        | balance_section      |
| Epigrafe M1                     | balance_epigrafe     |
| Moneda original                 | original_currency    |
| Segmento negocio                | business_segment     |
| Segmento estrategico            | strategic_segment    |
| Book value definition           | book_value_def       |
