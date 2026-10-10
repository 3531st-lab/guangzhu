# T03 / T06 equipment provenance

Extracted on **2026-10-01** from the exact SAM commit
`cba319ded1c32a7f5b3ac76545a29e1f7181d238` specified by T03 v2.
No component power, CEC fitted parameter, or inverter rating was modified.

## Locked full catalogs and offline subsets

| Catalog | Exact source | Full-file SHA-256 | Downloaded bytes | Parsed equipment |
| --- | --- | --- | ---: | ---: |
| Modules | [CEC Modules.csv](https://raw.githubusercontent.com/NREL/SAM/cba319ded1c32a7f5b3ac76545a29e1f7181d238/deploy/libraries/CEC%20Modules.csv) | `a28cf8956a839ed98bb941809b439e4907f5b4c237bd9299bc123fb502c29aff` | 6274198 | 21677 |
| Inverters | [CEC Inverters.csv](https://raw.githubusercontent.com/NREL/SAM/cba319ded1c32a7f5b3ac76545a29e1f7181d238/deploy/libraries/CEC%20Inverters.csv) | `0c1b2188415dad6928f91f1a4c9a820dadc80962549f903d57d9282ba3753760` | 389761 | 2343 |

Both complete source files were downloaded and checked against the required
hashes before extraction. Each committed subset consists of the original first
three CSV lines (column names, units, and SAM field mapping) followed by the
selected original rows, including all original columns and line endings.
`pvlib.pvsystem.retrieve_sam(path=...)` skips the two metadata lines; omitting
them would lose the selected row during parsing.

| Subset | Original source line (1-based) | Bytes | Subset SHA-256 |
| --- | ---: | ---: | --- |
| `cec_modules_subset.csv` | 18684 and 7024 (T06 adds Runergy) | 1121 | `1d1da584463895c704aa832deedd73cc806cffe7d1d003ce1e99d7941b03b3f4` |
| `cec_inverters_subset.csv` | 2182 | 512 | `20d16c82e572e585183d980a3dbc7ee0661be1f9425902f961c6a52adfdd8eee` |

Complete files are cached under `data/cache/catalog/` and verified every time
they are used. Explicit `offline=True` selects these committed subsets without
reading the cache or contacting the network. A network request failure also
selects the complete pair of subsets and records the reason. Hash mismatches,
parse errors, or invalid equipment always raise an error; they do not trigger
a subset fallback or a fitted replacement.

## Selected monofacial module

- SAM original name: `Trina Solar TSM-550DE19`
- pvlib normalized key: `Trina_Solar_TSM_550DE19`
- Original-name count and normalized-key count in the full catalog: **1 each**
- Manufacturer: Trina Solar; technology: `Mono-c-Si`; `Bifacial=0`
- STC nameplate power: **550 W**; Vmp **31.6 V**; Imp **17.4 A**;
  Voc **37.9 V**; Isc **18.52 A**
- Library row version: `2026.7.3`; row date: `6/23/2026`
- [Manufacturer's official 2022 APAC B datasheet](https://static.trinasolar.com/sites/default/files/Vertex_DE19_EN_2022_APAC_B_web.pdf),
  version `TSM_EN_2022_APAC_B`, copyright 2022, PDF page 2:
  **2384 × 1096 × 35 mm**, **28.6 kg**, white backsheet,
  monocrystalline cells. Dimensions in `modules.csv` are expressed in meters.
- [Official company profile](https://www.trinasolar.com/en-glb/about-us/)
  identifies Changzhou as Trinasolar's global headquarters; the
  [official corporate brochure](https://static.trinasolar.com/sites/default/files/Trinasolar_Corporate_Brochure_EN_20240514.pdf)
  identifies Changzhou, Jiangsu Province.

The official 2023 APAC datasheet describes a 30 mm / 28.3 kg frame revision;
it was **not** used for the recorded physical dimensions. The selected 2022
datasheet's 110 physical cells and NOCT 43 ± 2°C are not replacements for the
CEC library's electrical `N_s=55`, `T_NOCT=45.7`, or `gamma_pmp=-0.371 %/K`.
The module Series retains the library's `A_c=2.59 m²`; the physical footprint
from the selected datasheet is a separate value, 2.384 × 1.096 m².

## Selected string inverter and T03 system

- SAM original name: `Sungrow: SG60CX-US {480V}`
- pvlib normalized key: `Sungrow__SG60CX_US_{480V}`
- Original-name count and normalized-key count in the full catalog: **1 each**
- CEC row date: `2024-09-23`
- CEC `Paco=60182 W`, `Pdco=61436 W`, `Vdco=710 V`;
  `Mppt_low=550 V`, `Mppt_high=850 V`
- The database's 60182 W AC rating is retained, rather than replacing it with
  the manufacturer's rounded 60 kVA description.
- [Official SG60CX-US datasheet Version 13, 2023](https://info-support.sungrowpower.com/application/pdf/2023/04/04/DS_20230327_SG60CX-US_Datasheet_V13_EN.pdf)
  and [official user manual Ver17, 2024-11, PDF page 85](https://info-support.sungrowpower.com/application/pdf/2024/11/29/M-D-000059-JS-105303-SG36_60CX_US-UEN-Ver17-202411_compress.pdf):
  6 MPPTs, at most 2 strings per MPPT, 26 A maximum working current and
  45 A maximum short-circuit current per MPPT; 1000 V maximum DC input;
  rated-power MPPT 550–850 V.

The T03 array uses **22 modules per string × 6 strings = 132 modules**,
one string per MPPT. Its DC nameplate capacity is **72.6 kWp** and
DC/AC ratio is **72600 / 60182 = 1.2063407663420957**, within 1.1–1.25.
STC string Vmp is **695.2 V**, inside the selected CEC MPPT range.
STC Voc is **833.8 V**; each string has Imp **17.4 A** and Isc **18.52 A**.
Annual energy is calculated for this array and normalized by 72.6 kWp.

This **US 277/480 V, 60 Hz** model is used only for its CEC efficiency model.
The CEC columns `Vdcmax=850 V` and `Idcmax=86.5296 A` are retained as-is;
they are not substituted for manufacturer limits or domestic-model electrical
constraints. Cold/hot string voltage, protection, and domestic grid suitability
remain T06 work; the STC checks above do not certify an installation.

## License and fitting fallback

SAM distributes these library files under the BSD 3-Clause license. The
unchanged [license at the locked commit](https://raw.githubusercontent.com/NREL/SAM/cba319ded1c32a7f5b3ac76545a29e1f7181d238/LICENSE)
is preserved in `LICENSE-SAM.txt`, including its copyright notice and
disclaimer (SHA-256
`22b6f0585f60c136d6d3d196acf1cea2e69b9d84ac860125f9401960a7ef5a14`).
Manufacturer datasheets are referenced by their official URLs; their PDFs
are not redistributed here.

The locked catalogs and subsets are usable, so the optional `fit_cec_sam`
fallback is neither needed nor activated. Any future explicit fitting path
must follow T03's manufacturer-data and <1% STC validation requirements;
it must never bypass an integrity failure.

## T06 second Jiangsu monofacial module

Added on **2026-10-01**, without changing the T03 selected equipment or array.
The second module's original row was extracted byte-for-byte from the same
verified full catalog, and appended after the original Trina row.

- `module_id`: `runergy-hy-wh144p8-550`
- SAM original name: `Jiangsu Runergy New Energy Technology Co Ltd HY-WH144P8-550`
- pvlib key: `Jiangsu_Runergy_New_Energy_Technology_Co_Ltd_HY_WH144P8_550`
- Original-name and normalized-key counts in the locked full catalog: **1 each**
- Source line **7024**, original row **332 bytes**, `Mono-c-Si`, `Bifacial=0`,
  `STC=550 W`, library version `2026.7.3`, date `6/23/2026`.
- [Official HY-WH144P8 datasheet](https://www.runergy.com/wp-content/uploads/download/WH144P8-35F.pdf),
  `HY-WH144P8-Global-Ver3.0`, copyright **2023**, PDF page **1**:
  P-Type, single glass; PDF page **2**: monocrystalline PERC 182 mm cells,
  **2278 × 1134 × 35 mm**, **28.1 kg**, electrical values recorded below.
- [Official company information](https://www.runergy.com/about-runergy/) and
  [official Chinese contact page](https://cn.runergy.com/about-runergy/contact/)
  identify Jiangsu Runergy and its Yancheng, Jiangsu address.
- The original CEC `A_c=1.69 m²` is retained despite differing from the
  datasheet footprint **2.278 × 1.134 = 2.583252 m²**. No CEC parameter is
  repaired or replaced using physical or datasheet values.

The alternative CSI CS6W-550MS was considered but excluded: the official
`V2.1_EN`, February 2022 datasheet only supplies **NMOT 41 ± 3°C**, with no
NOCT. T06 explicitly uses NOCT, so no NMOT-to-NOCT substitution was made.

## T06 electrical-safety values versus unchanged CEC values

`modules.csv` stores electrical-safety values from the exact datasheets above
and the existing [Trina 2022 APAC B datasheet](https://static.trinasolar.com/sites/default/files/Vertex_DE19_EN_2022_APAC_B_web.pdf),
`TSM_EN_2022_APAC_B`, copyright 2022, PDF page **2**. Temperature coefficients
are stored as **%/°C**, and consumers divide by 100 for fractional arithmetic.
`noct_c` uses the stated central NOCT, with its ±2°C tolerance recorded
separately. Runergy also explicitly supplies NMOT 42 ± 2°C; Trina does not
give NMOT. Both datasheets omit the Vmp temperature coefficient; this missing
coefficient is not filled in the catalog.

| Field | Trina datasheet | Trina CEC | Runergy datasheet | Runergy CEC |
| --- | ---: | ---: | ---: | ---: |
| Pmax / STC (W) | 550 | 550 | 550 | 550 |
| Vmp (V) | 31.6 | 31.6 | 41.96 | 41.96 |
| Imp (A) | 17.40 | 17.4 | 13.11 | 13.11 |
| Voc (V) | 37.9 | 37.9 | 49.90 | 49.9 |
| Isc (A) | 18.52 | 18.52 | 14.00 | 14.0 |
| Voc coefficient (%/°C) | -0.25 | -0.265 | -0.26 | -0.29789 |
| Pmax coefficient (%/°C) | -0.34 | -0.371 | -0.35 | -0.39941 |
| Isc coefficient (%/°C) | 0.04 | 0.044 | 0.048 | 0.07114 |
| NOCT (°C) | 43 ± 2 | 45.7 | 45 ± 2 | 44.0 |
| Maximum system voltage (V) | 1500 | Not supplied | 1500 | Not supplied |
| Maximum series fuse (A) | 30 | Not supplied | 25 | Not supplied |

CEC percentage coefficients in this table are calculated from the unchanged
absolute coefficients (`100 × beta_oc / V_oc_ref`, and
`100 × alpha_sc / I_sc_ref`). The CEC `N_s=55`/`72` remain the electrical model
cell counts. T03 generation continues using Trina's CEC Series and the original
US 60 Hz inverter; these T06 safety and domestic/IEC equipment values do not
change that model.

## T06 domestic-manufacturer IEC string inverters

`inverters.csv` stores rated AC power in **kW**, maximum apparent AC power in
**kVA**, voltage in **V**, current in **A per MPPT**, efficiency in **%**, and
weight in **kg**. `grid_frequency_hz=50/60` explicitly supports 50 Hz.
Missing numeric specifications are the literal `规格书未给出`; callers must
not invent numbers or convert these entries to floating-point values.

| ID / model | Exact official document | Version / date / PDF page |
| --- | --- | --- |
| `sungrow-sg100cx-p2` / SG100CX-P2 | [Official AU/IEC datasheet](https://info-support.sungrowpower.com/datasheet-materials/fe40521c-fd35-4a37-9b79-fdf4d29d51b2.pdf) | AU Version **4**, copyright **2026**, page **2**; no finer publication date given |
| Sungrow full-load MPPT range | [Official user manual, technical specifications](https://info-support.sungrowpower.com/product-materials/52a5cd73-4418-4314-a7a1-14a979d6300c.pdf) | `SG100_110CX-P2-UEN-Ver18-202604`, **2026-04**, PDF page **113**, printed page **106** |
| `huawei-sun2000-100ktl-m2` / SUN2000-100KTL-M2 | [Official IEC datasheet](https://solar.huawei.com/admin/asset/v1/pro/view/c5056ea20b95424fad3c62f0a5e64a84.pdf) | PDF title `SUN2000-100KTL-M2 Datasheet_20250626`, metadata creation **2025-06-26**, page **2** |

| Specification | Sungrow SG100CX-P2 | Huawei SUN2000-100KTL-M2 |
| --- | ---: | ---: |
| Rated AC active power (kW) | **99.99** | 100 |
| Maximum AC active power (kW) | 规格书未给出 | 110 at cosφ=1 |
| Maximum AC apparent power (kVA) | **99.99** | 110 |
| Maximum DC voltage (V) | 1100 | 1100 |
| Operating MPPT range (V) | 180–1000 | 200–1000 |
| Full-load MPPT range (V) | 550–850 (manual above) | 规格书未给出 |
| Startup voltage (V) | 200 | 200 |
| MPPTs × maximum strings per MPPT | 12 × 2 | 10 × 2 |
| Maximum input current per MPPT (A) | 30 | 30 |
| Maximum short-circuit current per MPPT (A) | 50 | 40 |
| Maximum / European efficiency (%) | 98.5 / 98.3 | 98.6 / 98.4 at 400 V |
| Weight (kg) | 93 | ≤93 including mounting plate |
| Rated grid frequency (Hz) | 50 / 60 | 50 / 60 |

Neither selected datasheet gives Chinese weighted efficiency, so European
efficiency is recorded. Huawei also gives 98.8% maximum and 98.6% European
efficiency at 480 V; the catalog explicitly chooses the 400 V values. Its
numeric weight is the published upper bound 93 kg. Sungrow's 99.99 kW is
retained, not rounded to 100 kW; its maximum kVA is not relabeled as active kW.
Sungrow Version 4 / manual Ver18 publish **50 A per MPPT**, whereas the older
Ver16 manual publishes 40 A. The newer stated revision is consistently used.
Both selected per-MPPT short-circuit limits exceed the Trina module's 18.52 A
STC Isc; hot-current checks still apply when multiple strings are connected.

The two temporarily downloaded official PDFs used to verify document metadata
and Sungrow PDF-versus-printed page numbering had SHA-256:

- Sungrow manual Ver18: `988ee1adc41bf5f350f1ba10d72db714d6f1752996fa4c4ef76b81bac1220f75`.
- Huawei datasheet: `8e4fab8d3d115d9ce95ce38bcd25c4edcbbc7ea5c3c0d71b6d7794639b889915`.

The PDFs were downloaded inside `TemporaryDirectory` contexts and removed
when the contexts exited. The repository contains official links and factual
equipment values only, and does not redistribute manufacturer PDF artwork or
documents. Manufacturer documents retain their stated copyrights / all rights
reserved notices; no open redistribution license is asserted. The SAM rows
remain covered by the preserved SAM BSD 3-Clause license above.

## T06 illustrative racking and ballast mass

`racking.csv` contains **6 kg of rack per module** and **30 kg of ballast per
module**, both explicitly **示意，可改**. The rack estimate is two 2.5 m rails
at an assumed 0.9 kg/m plus 1.5 kg of support legs / connections:
`2 × 2.5 × 0.9 + 1.5 = 6 kg`. Ballast is an assumed two 15 kg blocks:
`2 × 15 = 30 kg`. These are arithmetic demonstration estimates, with no
manufacturer source or wind-load basis. They support the preliminary added
load comparison only and do not specify a safe ballast or structural design.

## T06 T03 regression verification

After adding the original Runergy row, the T03 full-catalog and offline-subset
selected module / inverter Series were exactly equal. An offline four-chain
crosscheck with HTTP requests forbidden and the figure written inside a
`TemporaryDirectory` produced exactly the prior **12 monthly values, annual
values, and all six pairwise differences** in `reports/assets/T03-crosscheck.json`:
a **1110.7164461003981**, b **1137.5888500310757**, c **1116.358373918649**,
d **1275.11 kWh/kWp**. Local timed computation was **0.3557984000071883 s**.
The original T03 figure was not overwritten; its SHA-256 remains
`99a4a5f3519a982edb18c2eb948a9c415ca03fd3061aa60a1d4a2c1143734685`.
Catalog tests are run with `python -m pytest tests/test_catalog.py -q` and
continue checking offline hashes, selected-name/key uniqueness, data eligibility,
network-only fallback, and corruption errors.
