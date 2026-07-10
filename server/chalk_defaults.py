"""Built-in Chalk River WTP tag mapping — the default profile.

These constants were verified against the legacy XLReporter Daily screenshots
(field_tag_map.md / history_data_binding.md). They are used verbatim when no
custom tag_config exists in config/plant.json, and they seed the bundled
example profile for other plants to start from.
"""
from __future__ import annotations

# (section, kind, tag, description, historian, units, total_units)
TREND_ROWS = [
    ("flows", "minmax_total", "FIT101", "Raw Water Flow", "WTP_FIT101_VALUE", "L/s", "m3"),
    ("flows", "minmax_total", "FIT102", "Treated Water Flow", "WTP_FIT102_VALUE", "L/s", "m3"),
    ("flows", "minmax_total", "FIT103", "Water Flow to SCU 1", "WTP_FIT103_VALUE", "L/s", "m3"),
    ("flows", "minmax_total", "FIT104", "Water Flow to SCU 2", "WTP_FIT104_VALUE", "L/s", "m3"),
    ("flows", "minmax_total", "FIT105", "Treated Flow Before Chem. Injection", "WTP_FIT105_VALUE", "L/s", "m3"),
    ("flows", "minmax_total", "FIT106", "Distribution Flow", "TOWER_FIT106_VALUE", "L/s", "m3"),
    ("fluoride", "minmax_avg", "FL01", "Treated Water Fluoride", "TOWER_FL01_VALUE", "mg/L", None),
    ("chlorine", "minmax_avg", "FRC01", "Elevated Tower Water free chlorine residual", "TOWER_FRC01_VALUE", "mg/L", None),
    ("chlorine", "minmax_avg", "FRC02", "Treated Water Cl2 Residual", "WTP_FRC02_VALUE", "mg/L", None),
    ("levels", "minmax_avg", "LIT01", "Sludge Holding Tank Level", "WTP_LIT01_VALUE", "%", None),
    ("levels", "minmax_avg", "LIT02", "Treated Clearwell Well Level", "WTP_LIT02_VALUE", "%", None),
    ("levels", "minmax_avg", "LIT03", "Elevated Water Tower Level", "TOWER_LIT03_VALUE", "%", None),
    ("ph", "minmax_avg", "PH01", "Raw Water pH", "WTP_PH01_VALUE", "pH", None),
    ("ph", "minmax_avg", "PH02", "Treated Water pH", "WTP_PH02_VALUE", "pH", None),
    ("ph", "minmax_avg", "PH03", "Elevated Water pH", "TOWER_PH03_VALUE", "pH", None),
    ("ph", "minmax_avg", "PH04", "Corry Lake Raw Water pH", "LOW_PH04_VALUE", "pH", None),
    ("temp", "minmax_avg", "TEM01", "Tower Water Temperature", "TOWER_TEM01_VALUE", "C", None),
    ("turbidity", "minmax_avg", "TUR01", "Filter 1 Turbidity", "F1_TUR01_VALUE", "NTU", None),
    ("turbidity", "minmax_avg", "TUR02", "Filter 2 Turbidity", "F2_TUR02_VALUE", "NTU", None),
    ("turbidity", "minmax_avg", "TUR03", "Raw Water Turbidity", "WTP_TUR03_VALUE", "NTU", None),
]

SECTION_TITLES = {
    "flows": "Flows",
    "fluoride": "Fluoride Analyzer",
    "chlorine": "Free Chlorine Analyzers",
    "levels": "Level Transmitters",
    "ph": "pH Analyzers",
    "temp": "Temperature Transmitter",
    "turbidity": "Turbidity Analyzers",
    "runtime": "Equipment Runtime Summary",
    "feedback": "Pump & Compressor Feedback",
}

# (tag, description, historian)
MOTOR_ROWS = [
    ("SP1", "Sludge Holding Tank Pump 1 Run time", "WTP_SP1_RUNNING"),
    ("SP2", "Sludge Holding Tank Pump 2 Run time", "WTP_SP2_RUNNING"),
    ("M1", "Solid Contact Unit #1 Mixer1 Run time", "WTP_M1_RUNNING"),
    ("M2", "Sludge Holding Tank Mixer Run time", "WTP_M2_RUNNING"),
    ("M3", "Alkalinity M3 Run time", "WTP_M3_RUNNING"),
    ("M4", "Alkalinity M4 Run time", "WTP_M4_RUNNING"),
    ("M5", "PH Control Tank Mixer M5 Run time", "WTP_M5_RUNNING"),
    ("M6", "Polymer Tank Mixer 6 Run time", "WTP_M6_RUNNING"),
    ("RD1", "Solid Contact Unit #2 Rake Drive Run time", "WTP_RD1_RUNNING"),
    ("TD1", "Turbin Drive TD1 Run time", "WTP_TD1_RUNNING"),
    ("HLP3", "High Lift Pump #1 Run time", "WTP_HLP3_RUNNING"),
    ("HLP4", "High Lift Pump #2 Run time", "WTP_HLP4_RUNNING"),
    ("HLP5", "High Lift Pump #3 Run time", "WTP_HLP5_RUNNING"),
    ("AB1", "Air Scour Blower Run time", "WTP_AB1_RUNNING"),
    ("LLP1", "Low Lift Pump #1 Run time", "LOW_LLP1_RUNNING"),
    ("LLP2", "Low Lift Pump #2 Run time", "LOW_LLP2_RUNNING"),
]

# (tag, description, historian, units)
FEEDBACK_ROWS = [
    ("FB-LLP1-ACT", "Low lift pump 1 — actual", "LOW_LLP1_ACTUAL", "%"),
    ("FB-LLP1-SC", "Low lift pump 1 — speed control", "LOW_LLP1_SC_ACTUAL", "%"),
    ("FB-LLP2-ACT", "Low lift pump 2 — actual", "LOW_LLP2_ACTUAL", "%"),
    ("FB-LLP2-SC", "Low lift pump 2 — speed control", "LOW_LLP2_SC_ACTUAL", "%"),
    ("FB-CMP03-ACT", "Compressor 03 — actual", "WTP_CMP03_ACTUAL", "%"),
    ("FB-CMP04-ACT", "Compressor 04 — actual", "WTP_CMP04_ACTUAL", "%"),
    ("FB-CMP05-ACT", "Compressor 05 — actual", "WTP_CMP05_ACTUAL", "%"),
    ("FB-CMP10-ACT", "Compressor 10 — actual", "WTP_CMP10_ACTUAL", "%"),
    ("FB-CMP11-ACT", "Compressor 11 — actual", "WTP_CMP11_ACTUAL", "%"),
    ("FB-CMP03-OUT", "Compressor 03 — output", "WTP_CMP03_OUT", "%"),
    ("FB-CMP04-OUT", "Compressor 04 — output", "WTP_CMP04_OUT", "%"),
    ("FB-CMP05-OUT", "Compressor 05 — output", "WTP_CMP05_OUT", "%"),
    ("FB-CMP10-OUT", "Compressor 10 — output", "WTP_CMP10_OUT", "%"),
    ("FB-CMP11-OUT", "Compressor 11 — output", "WTP_CMP11_OUT", "%"),
    ("FB-CMP0607-ACT", "Compressor 06/07 — actual", "LOW_CMP0607_ACTUAL", "%"),
    ("FB-CMP0607-MO", "Compressor 06/07 — manual out", "LOW_CMP0607_MAN_OUT", "%"),
    ("FB-CMP0809-ACT", "Compressors 08/09 — actual", "WTP_CMP0809_ACTUAL", "%"),
    ("FB-CMP0809-OUT", "Compressors 08/09 — output", "WTP_CMP0809_OUT", "%"),
    ("FB-CMP0102-ACT", "Compressors 01/02 — actual", "WTP_CMP0102_ACTUAL", "%"),
    ("FB-CMP0102-OUT", "Compressors 01/02 — output", "WTP_CMP0102_OUT", "%"),
]

# CT disinfection — Chalk River contact geometry (CT Calculator workbook)
CT_DEFAULTS = {
    "enabled": True,
    "clearwell_volume_m3": 100.0,
    "pipe_volume_m3": 23.56194490192345,
    "tower_volume_m3": 1000.0,
    "tower_volume_offset_m3": 300.0,
    "baffle_clearwell": 0.1,
    "baffle_tower": 0.1,
    "baffle_pipe": 1.0,
    "target_giardia_log": 0.5,
    "target_virus_log": 2.0,
}

# CT worst-case inputs: role -> (historian, min|max)
CT_INPUTS = {
    "tower_level": ("TOWER_LIT03_VALUE", "min"),
    "clearwell_level": ("WTP_LIT02_VALUE", "min"),
    "pre_chem_flow": ("WTP_FIT105_VALUE", "max"),
    "tower_cl2": ("TOWER_FRC01_VALUE", "min"),
    "temperature": ("TOWER_TEM01_VALUE", "min"),
    "treated_cl2": ("WTP_FRC02_VALUE", "min"),
    "treated_flow": ("WTP_FIT102_VALUE", "max"),
    "treated_ph": ("WTP_PH02_VALUE", "max"),
    "distribution_flow": ("TOWER_FIT106_VALUE", "max"),
    "tower_ph": ("TOWER_PH03_VALUE", "max"),
}

# Insights / metrics roles (historians unless noted)
ROLE_DEFAULTS = {
    "raw_flow": "WTP_FIT101_VALUE",
    "treated_flow": "WTP_FIT102_VALUE",
    "distribution_flow": "TOWER_FIT106_VALUE",
    "clearwell_level": "WTP_LIT02_VALUE",
    "tower_level": "TOWER_LIT03_VALUE",
    "treated_cl2": "WTP_FRC02_VALUE",
    "treated_ph": "WTP_PH02_VALUE",
    "filter_turbidity": ["F1_TUR01_VALUE", "F2_TUR02_VALUE"],
    "high_lift_pumps": ["HLP3", "HLP4", "HLP5"],  # short tags
}
