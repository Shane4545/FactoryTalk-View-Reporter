"""
Engineering-unit scaling for FactoryTalk Float.DAT values.

Float.DAT stores raw logged floats. XLReporter / FT Data Agent presents
engineering units (L/s, mg/L, %, …). Scales calibrated so min/max on
2026-06-13 match XLReporter Daily screenshots; cross-checked on 2026-06-08
and 2026-06-14 (see server/proof/calibrate_eu_scales.py).

Eng = a * raw + b
"""
from __future__ import annotations

from pathlib import Path

# tag -> (a, b)  such that eng = a * raw + b
# Source: proof/eu_scales_calibrated.json (2026-06-13 min/max fit).
# Chalk River calibration — active tables below start as copies and are
# replaced by tag_config.apply_scaling_overrides() when a custom profile
# is saved (generic plants log engineering units directly → identity).
CHALK_EU_SCALE: dict[str, tuple[float, float]] = {
    "WTP_FIT101_VALUE": (8.451944366805025, -9.085839589785232),
    "WTP_FIT102_VALUE": (6.5696719125374, 0.0),
    "WTP_FIT103_VALUE": (4.698515713073307, -4.581052652214458),
    "WTP_FIT104_VALUE": (4.698515713073307, -4.581052652214458),
    "WTP_FIT105_VALUE": (4.414455183179153, 0.0),
    "TOWER_FIT106_VALUE": (14.581922479239832, -26.525777999546044),
    "TOWER_FL01_VALUE": (3.333310021457525, -5.290165699753642),
    "TOWER_FRC01_VALUE": (3.9975067430401334, -6.496511727647892),
    "WTP_FRC02_VALUE": (8.065056158344358, -14.126208447244656),
    "WTP_LIT01_VALUE": (80.84377656600661, -208.68745047109675),
    "WTP_LIT02_VALUE": (162.31920445797786, -456.70658502815127),
    "TOWER_LIT03_VALUE": (256.17365251241637, -768.5741223320945),
    "WTP_PH01_VALUE": (21.966722356354648, -46.757848789403944),
    "WTP_PH02_VALUE": (16.230151687132334, -32.570058043545416),
    "TOWER_PH03_VALUE": (14.988221841052242, -29.520182246998807),
    "LOW_PH04_VALUE": (7.78127916144892, -13.507299754185816),
    "TOWER_TEM01_VALUE": (63.653494039502164, -159.02680046628282),
    "F1_TUR01_VALUE": (0.22662878987430682, -0.25127464051492976),
    "F2_TUR02_VALUE": (0.2637360315655441, -0.3030985794457166),
    "WTP_TUR03_VALUE": (34.58449116414185, -74.71732250783133),
}

CHALK_FLOW_TAGS = {
    "WTP_FIT101_VALUE",
    "WTP_FIT102_VALUE",
    "WTP_FIT103_VALUE",
    "WTP_FIT104_VALUE",
    "WTP_FIT105_VALUE",
    "TOWER_FIT106_VALUE",
}

# After EU integral (L/s·s → m³), apply per-tag factor so Daily TOTAL matches
# the PLC/HMI Daily report (screenshots 2026-06-13). Cross-checked 06-08/06-14
# within ~0–5%. Likely bridges rate-integral vs PLC totalizer / report math.
CHALK_FLOW_TOTAL_FACTOR: dict[str, float] = {
    "WTP_FIT101_VALUE": 0.761516,
    "WTP_FIT102_VALUE": 0.968389,
    "WTP_FIT103_VALUE": 0.770292,
    "WTP_FIT104_VALUE": 0.770292,
    "WTP_FIT105_VALUE": 0.879440,
    "TOWER_FIT106_VALUE": 0.734594,
}

# Active tables (mutated by tag_config.apply_scaling_overrides)
EU_SCALE: dict[str, tuple[float, float]] = dict(CHALK_EU_SCALE)
FLOW_TAGS: set[str] = set(CHALK_FLOW_TAGS)
FLOW_TOTAL_FACTOR: dict[str, float] = dict(CHALK_FLOW_TOTAL_FACTOR)

# Bump when scales/factors change so day_cache entries are not reused raw.
EU_CACHE_VERSION = "eu-v3"


def to_eu(tag: str, raw: float) -> float:
    ab = EU_SCALE.get(tag)
    if not ab:
        return raw
    a, b = ab
    return a * raw + b


def load_scales_json(path: Path | None = None) -> None:
    """Optional override from JSON {tag: {a, b}} — mutates EU_SCALE."""
    p = path or Path(__file__).with_name("eu_scales.json")
    if not p.is_file():
        return
    import json

    data = json.loads(p.read_text(encoding="utf-8"))
    for tag, ab in data.items():
        EU_SCALE[tag] = (float(ab["a"]), float(ab["b"]))
