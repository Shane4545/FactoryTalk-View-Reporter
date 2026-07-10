import type { CSSProperties } from "react";

export type Aggregate = {
  min: number | null;
  max: number | null;
  avg: number | null;
  total: number | null;
  timeOfMin: string | null;
  timeOfMax: string | null;
  units: string;
  totalUnits?: string;
  count?: number;
  /** Rising-edge count for digital RUNNING tags (runtime section). */
  starts?: number | null;
  /** Falling-edge count for digital RUNNING tags (runtime section). */
  stops?: number | null;
};

export type TagRow = {
  tag: string;
  description: string;
  historianTag?: string;
  aggregate: Aggregate;
  emphasize?: boolean;
  /** Which aggregate cell is a CT worst-case input ("min" | "max"). */
  ctCell?: "min" | "max" | null;
};

export type Section = {
  id: string;
  title: string;
  kind: "minmax_total" | "minmax_avg" | "runtime" | "efficiency" | "ct";
  rows: TagRow[];
};

export type CtMetric = {
  label: string;
  giardia: number | null;
  viruses: number | null;
  note?: string;
  giardiaDisplay?: string;
  virusesDisplay?: string;
};

export type DailyReport = {
  plant: string;
  subtitle: string;
  municipality: string;
  periodLabel: string;
  startDate: string;
  endDate: string;
  sections: Section[];
  ct: CtMetric[];
  ctNote: string;
  meta?: {
    source?: string;
    kind?: string;
    days_loaded?: number;
    days_missing?: number;
    tag_count_trend?: number;
    tag_count_motors?: number;
    tag_count_feedback?: number;
    proof?: {
      FIT101_samples?: number;
      FIT101_min?: number;
      FIT101_max?: number;
      CT_Achieved?: number;
    };
  };
};

const u = (
  units: string,
  partial: Partial<Aggregate> & { units?: string } = {},
): Aggregate => ({
  min: null,
  max: null,
  avg: null,
  total: null,
  timeOfMin: null,
  timeOfMax: null,
  units,
  ...partial,
});

/** Demo values — replace with connector aggregates. */
export const chalkRiverDaily: DailyReport = {
  plant: "CHALK RIVER WATER TREATMENT PLANT",
  subtitle: "Daily Operations Report",
  municipality: "Town of Laurentian Hills",
  periodLabel: "Calendar day 00:00–24:00",
  startDate: "2026-07-08",
  endDate: "2026-07-08",
  sections: [
    {
      id: "flows",
      title: "Flows",
      kind: "minmax_total",
      rows: [
        {
          tag: "FIT101",
          description: "Raw Water Flow",
          aggregate: u("L/s", {
            min: 12.4,
            max: 48.2,
            total: 2140,
            timeOfMin: "03:12",
            timeOfMax: "14:40",
            totalUnits: "m³",
          }),
        },
        {
          tag: "FIT102",
          description: "Treated Water Flow",
          emphasize: true,
          aggregate: u("L/s", {
            min: 11.8,
            max: 46.1,
            total: 2055,
            timeOfMin: "03:18",
            timeOfMax: "14:38",
            totalUnits: "m³",
          }),
        },
        {
          tag: "FIT103",
          description: "Water Flow to SCU 1",
          aggregate: u("L/s", {
            min: 5.2,
            max: 24.0,
            total: 1020,
            timeOfMin: "04:01",
            timeOfMax: "13:22",
            totalUnits: "m³",
          }),
        },
        {
          tag: "FIT104",
          description: "Water Flow to SCU 2",
          aggregate: u("L/s", {
            min: 5.0,
            max: 23.5,
            total: 1005,
            timeOfMin: "04:05",
            timeOfMax: "13:20",
            totalUnits: "m³",
          }),
        },
        {
          tag: "FIT105",
          description: "Treated Flow Before Chem. Injection",
          aggregate: u("L/s", {
            min: 11.5,
            max: 45.8,
            total: 2040,
            timeOfMin: "03:20",
            timeOfMax: "14:36",
            totalUnits: "m³",
          }),
        },
        {
          tag: "FIT106",
          description: "Distribution Flow",
          emphasize: true,
          aggregate: u("L/s", {
            min: 8.1,
            max: 39.4,
            total: 1880,
            timeOfMin: "02:44",
            timeOfMax: "18:10",
            totalUnits: "m³",
          }),
        },
      ],
    },
    {
      id: "fluoride",
      title: "Fluoride Analyzer",
      kind: "minmax_avg",
      rows: [
        {
          tag: "FL01",
          description: "Treated Water Fluoride",
          aggregate: u("mg/L", {
            min: 0.52,
            max: 0.71,
            avg: 0.61,
            timeOfMin: "06:12",
            timeOfMax: "16:48",
          }),
        },
      ],
    },
    {
      id: "chlorine",
      title: "Free Chlorine Analyzers",
      kind: "minmax_avg",
      rows: [
        {
          tag: "FRC01",
          description: "Elevated Tower Water free chlorine residual",
          aggregate: u("mg/L", {
            min: 0.68,
            max: 1.12,
            avg: 0.91,
            timeOfMin: "05:30",
            timeOfMax: "11:05",
          }),
        },
        {
          tag: "FRC02",
          description: "Treated Water Cl₂ Residual",
          aggregate: u("mg/L", {
            min: 0.74,
            max: 1.18,
            avg: 0.96,
            timeOfMin: "05:22",
            timeOfMax: "10:58",
          }),
        },
      ],
    },
    {
      id: "levels",
      title: "Level Transmitters",
      kind: "minmax_avg",
      rows: [
        {
          tag: "LIT01",
          description: "Sludge Holding Tank Level",
          aggregate: u("%", {
            min: 22,
            max: 61,
            avg: 41,
            timeOfMin: "08:00",
            timeOfMax: "20:15",
          }),
        },
        {
          tag: "LIT02",
          description: "Treated Clearwell Well Level",
          aggregate: u("%", {
            min: 48,
            max: 82,
            avg: 66,
            timeOfMin: "07:40",
            timeOfMax: "15:10",
          }),
        },
        {
          tag: "LIT03",
          description: "Elevated Water Tower Level",
          aggregate: u("%", {
            min: 55,
            max: 88,
            avg: 72,
            timeOfMin: "06:55",
            timeOfMax: "17:30",
          }),
        },
      ],
    },
    {
      id: "ph",
      title: "pH Analyzers",
      kind: "minmax_avg",
      rows: [
        {
          tag: "PH01",
          description: "Raw Water pH",
          aggregate: u("pH", {
            min: 6.9,
            max: 7.4,
            avg: 7.1,
            timeOfMin: "04:20",
            timeOfMax: "14:00",
          }),
        },
        {
          tag: "PH02",
          description: "Treated Water pH",
          aggregate: u("pH", {
            min: 7.2,
            max: 7.6,
            avg: 7.4,
            timeOfMin: "03:50",
            timeOfMax: "12:40",
          }),
        },
        {
          tag: "PH03",
          description: "Elevated Water pH",
          aggregate: u("pH", {
            min: 7.1,
            max: 7.5,
            avg: 7.3,
            timeOfMin: "05:10",
            timeOfMax: "13:15",
          }),
        },
        {
          tag: "PH04",
          description: "Corry Lake Raw Water pH",
          aggregate: u("pH", {
            min: 6.8,
            max: 7.3,
            avg: 7.0,
            timeOfMin: "02:30",
            timeOfMax: "15:45",
          }),
        },
      ],
    },
    {
      id: "temp",
      title: "Temperature Transmitter",
      kind: "minmax_avg",
      rows: [
        {
          tag: "TEM01",
          description: "Tower Water Temperature",
          aggregate: u("°C", {
            min: 12.1,
            max: 16.8,
            avg: 14.4,
            timeOfMin: "05:00",
            timeOfMax: "16:20",
          }),
        },
      ],
    },
    {
      id: "turbidity",
      title: "Turbidity Analyzers",
      kind: "minmax_avg",
      rows: [
        {
          tag: "TUR01",
          description: "Filter 1 Turbidity",
          aggregate: u("NTU", {
            min: 0.04,
            max: 0.12,
            avg: 0.07,
            timeOfMin: "09:00",
            timeOfMax: "01:20",
          }),
        },
        {
          tag: "TUR02",
          description: "Filter 2 Turbidity",
          aggregate: u("NTU", {
            min: 0.05,
            max: 0.14,
            avg: 0.08,
            timeOfMin: "08:40",
            timeOfMax: "01:35",
          }),
        },
        {
          tag: "TUR03",
          description: "Raw Water Turbidity",
          aggregate: u("NTU", {
            min: 0.8,
            max: 3.2,
            avg: 1.6,
            timeOfMin: "11:00",
            timeOfMax: "06:10",
          }),
        },
      ],
    },
    {
      id: "efficiency",
      title: "Plant Filter Efficiency",
      kind: "efficiency",
      rows: [
        {
          tag: "EFF",
          description: "Plant Daily Efficiency %",
          aggregate: u("%", { avg: 94.2 }),
        },
      ],
    },
    {
      id: "runtime",
      title: "Equipment Runtime Summary",
      kind: "runtime",
      rows: [
        {
          tag: "RUN-LLP1",
          description: "Low lift pump 1",
          aggregate: u("h", { total: 14.2, min: 6 }),
        },
        {
          tag: "RUN-LLP2",
          description: "Low lift pump 2",
          aggregate: u("h", { total: 9.8, min: 4 }),
        },
        {
          tag: "RUN-HLP1",
          description: "High lift pump 1",
          aggregate: u("h", { total: 11.5, min: 5 }),
        },
        {
          tag: "RUN-HLP2",
          description: "High lift pump 2",
          aggregate: u("h", { total: 12.1, min: 5 }),
        },
        {
          tag: "RUN-HLP3",
          description: "High lift pump 3",
          aggregate: u("h", { total: 0, min: 0 }),
        },
        {
          tag: "RUN-M1",
          description: "Motor / mixer 1",
          aggregate: u("h", { total: 22.0, min: 1 }),
        },
        {
          tag: "RUN-CMP01",
          description: "Chemical pumps 01–02",
          aggregate: u("h", { total: 18.4, min: 2 }),
        },
        {
          tag: "RUN-CMP03",
          description: "Chemical pump 03",
          aggregate: u("h", { total: 6.2, min: 3 }),
        },
      ],
    },
  ],
  ct: [
    { label: "CT Achieved", giardia: 48.2, viruses: 62.1 },
    { label: "CT Required", giardia: 12.0, viruses: 18.0 },
    { label: "Log Inactivation", giardia: 3.1, viruses: 4.0 },
  ],
  ctNote: "Worst case: min levels/chlorine, max flow/temp/pH",
};

export const fmt = (n: number | null | undefined, digits = 1): string => {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
};

export const brand: CSSProperties = {
  ["--ink" as string]: "#0f172a",
  ["--muted" as string]: "#64748b",
  ["--line" as string]: "#e2e8f0",
  ["--accent" as string]: "#0e7490",
  ["--accent-soft" as string]: "#ecfeff",
  ["--paper" as string]: "#f8fafc",
  ["--card" as string]: "#ffffff",
  ["--ct" as string]: "#eef2ff",
  ["--ct-ink" as string]: "#1e3a8a",
};
