"""Published aggregate figures that the build is compared against.

Every figure was read from the cited document (FFIEC or CFPB press releases, CFPB "Data Point:
Mortgage Market Activity and Trends" reports, Federal Reserve Bulletin articles on the HMDA
data). Where a figure could not be found it is absent; none are estimated. Read dates:
2026-11-19.

Semantics of the metrics (all computed on ``hmda_lar_core`` for the year):

- ``records``: every LAR row.
- ``actions``: applications plus purchased loans (action_taken 1-6); excludes preapproval
  requests that did not become applications (7, 8). Used by FFIEC releases before 2018.
- ``applications``: action_taken 1-5.
- ``originations``: action_taken 1. ``denied``: 3. ``purchased``: 6.
- ``preapproval_denied``: 7. ``preapproval_approved_not_accepted``: 8.
- ``*_hp``, ``*_rf``, ``*_hi``: home purchase / refinance / home improvement, restricted to
  one-to-four family property types (1, 2) when ``*_mf`` (multifamily, property type 3) is
  published separately (Federal Reserve tables), and over all property types otherwise
  (CFPB 2018+ tables, where ``*_other`` is "other purpose").
- ``institutions``: rows in ``lenders`` for the year with a Transmittal Sheet (``ts_present``).

Tolerance: ``exact`` must match to the unit. ``rounded`` figures are published to a unit
(e.g. thousands, or 0.1 million); the check passes when the actual value rounds to it, i.e.
|actual - expected| <= unit / 2. ``vintage`` notes when the source describes an earlier or
later release of the data than the file this project uses, which can cause small differences.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Expected:
    year: int
    metric: str
    value: float
    unit: float  # 1 for exact; 1000 for "thousands"; 100_000 for "x.x million"
    source: str
    note: str = ""

    @property
    def exact(self) -> bool:
        return self.unit == 1


FED_2008 = (
    "Federal Reserve Bulletin, 'The 2009 HMDA Data: The Mortgage Market in a Time of Low "
    "Interest Rates and Economic Distress' (Dec 2010), "
    "https://www.federalreserve.gov/pubs/bulletin/2010/pdf/2009_HMDA_final.pdf"
)
FED_2008B = (
    "Federal Reserve Bulletin, 'The 2008 HMDA Data: The Mortgage Market during a Turbulent "
    "Year' (2010), https://www.federalreserve.gov/pubs/bulletin/2010/pdf/hmda08final.pdf"
)
FED_2007 = (
    "Federal Reserve Bulletin, 'The 2007 HMDA Data' (Dec 2008), "
    "https://www.federalreserve.gov/pubs/bulletin/2008/pdf/hmda07final.pdf"
)
FED_2010 = (
    "Federal Reserve Bulletin, 'The Mortgage Market in 2010: Highlights from the Data Reported "
    "under HMDA' (Dec 2011), https://www.federalreserve.gov/pubs/bulletin/2011/pdf/"
    "2010_HMDA_final.pdf"
)
FED_2011 = (
    "Federal Reserve Bulletin, 'The Mortgage Market in 2011: Highlights from the Data Reported "
    "under HMDA' (Dec 2012), https://www.federalreserve.gov/pubs/bulletin/2012/PDF/2011_HMDA.pdf"
)
FED_2012 = (
    "Federal Reserve Bulletin, 'Mortgage Market Conditions and Borrower Outcomes: Evidence from "
    "the 2012 HMDA Data and Matched HMDA-Credit Record Data' (Nov 2013), "
    "https://www.federalreserve.gov/pubs/bulletin/2013/pdf/2012_HMDA.pdf"
)
FED_T1 = {
    2013: "https://www.federalreserve.gov/pubs/bulletin/2014/pdf/2013_HMDA.pdf",
    2014: "https://www.federalreserve.gov/pubs/bulletin/2015/pdf/2014_HMDA.pdf",
    2015: "https://www.federalreserve.gov/pubs/bulletin/2016/pdf/2015_HMDA.pdf",
    2016: "https://www.federalreserve.gov/publications/"
    "2017-november-residential-mortgage-lending-in-2016.htm",
}
CFPB_2017 = (
    "CFPB, 'Data Point: 2017 Mortgage Market Activity and Trends' (May 2018), "
    "https://files.consumerfinance.gov/f/documents/bcfp_hmda_2017-mortgage-market-activity-"
    "trends_report.pdf"
)
CFPB_2023 = (
    "CFPB, 'Data Point: 2023 Mortgage Market Activity and Trends' (Dec 2024), "
    "https://files.consumerfinance.gov/f/documents/cfpb_2023-mortgage-market-activity-and-"
    "trends_2024-12.pdf"
)
FFIEC_RELEASE = {
    2018: "https://www.consumerfinance.gov/about-us/newsroom/ffiec-announces-availability-2018-"
    "data-mortgage-lending",
    2019: "https://www.consumerfinance.gov/about-us/newsroom/ffiec-announces-availability-2019-"
    "data-mortgage-lending",
    2020: "https://www.consumerfinance.gov/about-us/newsroom/ffiec-announces-availability-of-"
    "2020-data-on-mortgage-lending/",
    2021: "https://www.consumerfinance.gov/about-us/newsroom/ffiec-announces-availability-of-"
    "2021-data-on-mortgage-lending",
    2022: "https://www.consumerfinance.gov/about-us/newsroom/ffiec-announces-availability-of-"
    "2022-data-on-mortgage-lending",
    2023: "https://www.consumerfinance.gov/about-us/newsroom/ffiec-publishes-2023-data-on-"
    "mortgage-lending",
    2024: "FFIEC, 'FFIEC Publishes 2024 Data on Mortgage Lending' (7 Jul 2025), "
    "https://www.ffiec.gov/news/press-releases/2025/an-07-07 (read via web.archive.org)",
    2025: "FFIEC, 'FFIEC Publishes 2025 Data on Mortgage Lending' (23 Jun 2026), "
    "https://www.ffiec.gov/news/press-releases/2026/an-06-23 (read via web.archive.org)",
}

THOUSAND = 1000.0
TENTH_MILLION = 100_000.0

_E: list[Expected] = []


def _add(year: int, metric: str, value: float, unit: float, source: str, note: str = "") -> None:
    _E.append(Expected(year, metric, value, unit, source, note))


# 2007 ------------------------------------------------------------------------------------------
_add(2007, "institutions", 8610, 1, FED_2007 + ", Table 2")
_add(2007, "actions", 26.2e6, TENTH_MILLION, FED_2007 + ", Table 1")
_T3 = "Table 3 excludes applications taken before 2004; so does this metric."
for _metric, _value in (
    ("originations_2004on", 10_441_353),
    ("denied_2004on", 5_952_496),
    ("applications_2004on", 21_389_258),
):
    _add(2007, _metric, _value, 1, FED_2007 + ", Table 3", _T3)

# 2008-2012: exact counts from Federal Reserve Bulletin tables -----------------------------------
_add(2008, "institutions", 8388, 1, FED_2008B + ", Table 1")
_add(
    2008,
    "records",
    17_391_570,
    1,
    FED_2008 + ", Table 2.A",
    "Initial public release of the 2008 data.",
)
for metric, v in {
    "applications_hp": 5_017_998,
    "applications_rf": 7_729_143,
    "applications_hi": 1_404_008,
    "applications_mf": 42_792,
    "purchased": 2_921_821,
    "preapproval_requests": 275_808,
}.items():
    _add(2008, metric, v, 1, FED_2008 + ", Table 2.A")
for metric, v in {
    "originations_hp": 3_119_692,
    "originations_rf": 3_457_774,
    "originations_hi": 568_287,
    "originations_mf": 31_509,
    "originations": 7_177_262,
}.items():
    _add(2008, metric, v, 1, FED_2008 + ", Table 2.B")
_add(2008, "applications", 14_193_941, 1, FED_2008B + ", Table 9")
_add(2008, "denied", 3_944_602, 1, FED_2008B + ", Table 9")

_add(2009, "institutions", 8124, 1, FED_2008 + ", Table 1")
_add(2009, "records", 19_493_491, 1, FED_2008 + ", Table 2.A")
for metric, v in {
    "applications_hp": 4_201_057,
    "applications_rf": 9_935_678,
    "applications_hi": 826_916,
    "applications_mf": 26_257,
    "purchased": 4_294_528,
    "preapproval_requests": 209_055,
}.items():
    _add(2009, metric, v, 1, FED_2008 + ", Table 2.A")
for metric, v in {
    "originations_hp": 2_784_956,
    "originations_rf": 5_758_875,
    "originations_hi": 387_970,
    "originations_mf": 19_135,
    "originations": 8_950_936,
}.items():
    _add(2009, metric, v, 1, FED_2008 + ", Table 2.B")

_add(2010, "institutions", 7923, 1, FED_2010 + ", Table 1")
_add(2010, "records", 16_348_557, 1, FED_2010 + ", Table 3.A")
for metric, v in {
    "applications_hp": 3_838_896,
    "applications_rf": 8_421_592,
    "applications_hi": 668_903,
    "applications_mf": 25_484,
    "purchased": 3_229_010,
    "preapproval_requests": 164_672,
}.items():
    _add(2010, metric, v, 1, FED_2010 + ", Table 3.A")
for metric, v in {
    "originations_hp": 2_541_791,
    "originations_rf": 4_961_814,
    "originations_hi": 340_604,
    "originations_mf": 19_128,
    "originations": 7_863_337,
}.items():
    _add(2010, metric, v, 1, FED_2010 + ", Table 3.B")
_add(2010, "applications", 12_954_875, 1, FED_2010 + ", Table 11")
_add(2010, "denied", 2_556_789, 1, FED_2010 + ", Table 11")

_add(2011, "institutions", 7632, 1, FED_2011 + ", Table 1")
_add(2011, "records", 14_873_415, 1, FED_2011 + ", Table 3.A")
for metric, v in {
    "applications_hp": 3_630_284,
    "applications_rf": 7_390_690,
    "applications_hi": 686_788,
    "applications_mf": 35_048,
    "purchased": 2_944_662,
    "preapproval_requests": 185_943,
}.items():
    _add(2011, metric, v, 1, FED_2011 + ", Table 3.A")
for metric, v in {
    "originations_hp": 2_416_854,
    "originations_rf": 4_311_870,
    "originations_hi": 339_427,
    "originations_mf": 27_111,
    "originations": 7_095_262,
}.items():
    _add(2011, metric, v, 1, FED_2011 + ", Table 3.B")
_add(2011, "applications", 11_742_810, 1, FED_2011 + ", Table 11")
_add(2011, "denied", 2_354_846, 1, FED_2011 + ", Table 11")

_add(2012, "institutions", 7400, 1, FED_2012 + ", Table 1")
_add(2012, "records", 18_691_550, 1, FED_2012 + ", Table 3.A")
for metric, v in {
    "applications_hp": 4_006_445,
    "applications_rf": 10_480_189,
    "applications_hi": 777_017,
    "applications_mf": 46_999,
    "purchased": 3_167_578,
    "preapproval_requests": 213_322,
}.items():
    _add(2012, metric, v, 1, FED_2012 + ", Table 3.A")
for metric, v in {
    "originations_hp": 2_729_592,
    "originations_rf": 6_637_360,
    "originations_hi": 380_251,
    "originations_mf": 36_761,
    "originations": 9_783_964,
}.items():
    _add(2012, metric, v, 1, FED_2012 + ", Table 3.B")
_add(2012, "applications", 15_310_651, 1, FED_2012 + ", Table 11")
_add(2012, "denied", 2_761_964, 1, FED_2012 + ", Table 11")

# 2013-2016: Federal Reserve Table 1, thousands ---------------------------------------------------
_T1 = {
    2013: (7190, (4554, 8549, 833, 51, 13987), (3112, 5131, 425, 40, 8707), 2794, (72, 163)),
    2014: (7062, (4662, 4386, 840, 45, 9933), (3235, 2301, 408, 35, 5980), 1752, (64, 126)),
    2015: (6913, (5181, 5940, 921, 52, 12094), (3662, 3228, 474, 41, 7404), 2102, (63, 114)),
    2016: (6762, (5693, 7178, 1005, 50, 13926), (4046, 3755, 537, 40, 8378), 2232, (60, 115)),
}
for y, (inst, apps, origs, purch, (pre_8, pre_7)) in _T1.items():
    src = f"Federal Reserve Bulletin article on the {y} HMDA data, Table 1, {FED_T1[y]}"
    _add(y, "institutions", inst, 1, src.replace("Table 1", "text"))
    for suffix, a, o in zip(("hp", "rf", "hi", "mf", ""), apps, origs, strict=True):
        name_a = f"applications_{suffix}" if suffix else "applications"
        name_o = f"originations_{suffix}" if suffix else "originations"
        _add(y, name_a, a * THOUSAND, THOUSAND, src)
        _add(y, name_o, o * THOUSAND, THOUSAND, src)
    _add(y, "purchased", purch * THOUSAND, THOUSAND, src)
    _add(y, "preapproval_approved_not_accepted", pre_8 * THOUSAND, THOUSAND, src)
    _add(y, "preapproval_denied", pre_7 * THOUSAND, THOUSAND, src)

# 2017: CFPB Data Point, thousands ---------------------------------------------------------------
_add(
    2017,
    "institutions",
    5852,
    1,
    "FFIEC release 7 May 2018, https://www.consumerfinance.gov/"
    "archive/newsroom/ffiec-announces-availability-2017-data-mortgage-lending/",
)
for suffix, a, o in zip(
    ("hp", "rf", "hi", "mf", ""),
    (6018, 4938, 1052, 48, 12056),
    (4237, 2516, 548, 38, 7339),
    strict=True,
):
    _add(
        2017,
        f"applications_{suffix}" if suffix else "applications",
        a * THOUSAND,
        THOUSAND,
        CFPB_2017 + ", Table 1A",
    )
    _add(
        2017,
        f"originations_{suffix}" if suffix else "originations",
        o * THOUSAND,
        THOUSAND,
        CFPB_2017 + ", Table 1A",
    )
_add(2017, "purchased", 2087 * THOUSAND, THOUSAND, CFPB_2017 + ", Table 1C")
_add(2017, "preapproval_approved_not_accepted", 36 * THOUSAND, THOUSAND, CFPB_2017 + ", Table 1C")
_add(2017, "preapproval_denied", 107 * THOUSAND, THOUSAND, CFPB_2017 + ", Table 1C")

# 2018-2023: snapshot, CFPB Data Point 2023 Tables 1A-1E (thousands) and FFIEC releases ------------
_SNAP = {
    # year: institutions, (apps, origs, purchased, pre_8, pre_7)
    2018: (5683, (12940, 7721, 2003, 75, 102)),
    2019: (5508, (15129, 9325, 2266, 74, 77)),
    2020: (4475, (22667, 14541, 2756, 71, 58)),
    2021: (4338, (23313, 15007, 2680, 96, 53)),
    2022: (4460, (14322, 8394, 1558, 129, 72)),
    2023: (5113, (9987, 5692, 1263, 171, 62)),
}
_PURPOSE = {
    # year: {purpose: (applications, originations, purchased)}
    2018: {"hp": (6208, 4345, 1386), "rf": (4418, 2293, 358), "hi": (1181, 570, 15),
           "other": (1120, 508, 10)},
    2019: {"hp": (6412, 4513, 1396), "rf": (6469, 3774, 674), "hi": (1143, 541, 8),
           "other": (1088, 490, 11)},
    2020: {"hp": (7077, 4904, 1189), "rf": (13834, 8791, 1189), "hi": (915, 456, 7),
           "other": (839, 389, 12)},
    2021: {"hp": (7659, 5364, 1374), "rf": (13725, 8670, 1172), "hi": (1063, 547, 7),
           "other": (861, 424, 13)},
    2022: {"hp": (6570, 4366, 1143), "rf": (4992, 2630, 315), "hi": (1475, 783, 10),
           "other": (1281, 613, 21)},
    2023: {"hp": (5289, 3449, 1018), "rf": (2234, 1084, 146), "hi": (1218, 604, 15),
           "other": (1244, 555, 30)},
}  # fmt: skip
for _yr, (_inst, (_apps, _origs, _purch, _pre8, _pre7)) in _SNAP.items():
    _add(_yr, "institutions", _inst, 1, f"FFIEC release on the {_yr} data, {FFIEC_RELEASE[_yr]}")
    src = CFPB_2023 + ", Table 1A-1E"
    _add(_yr, "applications", _apps * THOUSAND, THOUSAND, src)
    _add(_yr, "originations", _origs * THOUSAND, THOUSAND, src)
    _add(_yr, "purchased", _purch * THOUSAND, THOUSAND, src)
    _add(_yr, "preapproval_approved_not_accepted", _pre8 * THOUSAND, THOUSAND, src)
    _add(
        _yr,
        "preapproval_denied",
        _pre7 * THOUSAND,
        THOUSAND,
        src,
        "Table 1A figure; Table 1E's row is shifted by one column in the PDF.",
    )
    for _p, (_a, _o, _pu) in _PURPOSE[_yr].items():
        _add(_yr, f"applications_{_p}_all", _a * THOUSAND, THOUSAND, src)
        _add(_yr, f"originations_{_p}_all", _o * THOUSAND, THOUSAND, src)
        _add(_yr, f"purchased_{_p}_all", _pu * THOUSAND, THOUSAND, src)
for _yr, _rec in {2018: 15.1e6, 2019: 17.5e6, 2020: 25.6e6}.items():
    _add(
        _yr,
        "records",
        _rec,
        TENTH_MILLION,
        f"FFIEC release on the {_yr} data, {FFIEC_RELEASE[_yr]}",
    )
_add(2024, "institutions", 4908, 1, FFIEC_RELEASE[2024])
_add(2025, "institutions", 4782, 1, FFIEC_RELEASE[2025])

EXPECTED: list[Expected] = list(_E)

# Metric definitions: SQL predicate over hmda_lar_core (and lenders for institutions).
_ONE_TO_FOUR = "property_type IN (1, 2)"
METRICS: dict[str, str] = {
    "records": "true",
    "actions": "action_taken BETWEEN 1 AND 6",
    "applications": "action_taken BETWEEN 1 AND 5",
    "originations": "action_taken = 1",
    "denied": "action_taken = 3",
    "purchased": "action_taken = 6",
    "preapproval_denied": "action_taken = 7",
    "preapproval_approved_not_accepted": "action_taken = 8",
    "preapproval_requests": "action_taken IN (7, 8)",
}
for _p, _code in (("hp", 1), ("rf", 3), ("hi", 2)):
    METRICS[f"applications_{_p}"] = (
        f"action_taken BETWEEN 1 AND 5 AND loan_purpose = {_code} AND {_ONE_TO_FOUR}"
    )
    METRICS[f"originations_{_p}"] = (
        f"action_taken = 1 AND loan_purpose = {_code} AND {_ONE_TO_FOUR}"
    )
for _m in ("applications", "originations", "denied"):
    METRICS[f"{_m}_2004on"] = f"{METRICS[_m]} AND application_date_before_2004 IS NOT TRUE"
METRICS["applications_mf"] = "action_taken BETWEEN 1 AND 5 AND property_type = 3"
METRICS["originations_mf"] = "action_taken = 1 AND property_type = 3"
for _p, _code in (("hp", 1), ("rf", 3), ("hi", 2), ("other", 4)):
    METRICS[f"applications_{_p}_all"] = f"action_taken BETWEEN 1 AND 5 AND loan_purpose = {_code}"
    METRICS[f"originations_{_p}_all"] = f"action_taken = 1 AND loan_purpose = {_code}"
    METRICS[f"purchased_{_p}_all"] = f"action_taken = 6 AND loan_purpose = {_code}"
