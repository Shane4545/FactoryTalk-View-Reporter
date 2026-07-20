import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API } from "../api";
import { BusyOverlay } from "../components/BusyOverlay";
import "./ConnectDistribute.css";
import "./SetupPage.css";

type RowKind = "trend" | "motor" | "feedback" | "skip";

type EditRow = {
  historian: string;
  model: string;
  include: boolean;
  kind: RowKind;
  tag: string;
  description: string;
  section: string;
  units: string;
  totalize: boolean;
  confidence?: number;
  reasons?: string[];
  needs_review?: boolean;
  confirmed?: boolean;
  exception?: boolean;
};

type BusyKind = "activate" | null;

/** Green only for clear successes — never for "Validation failed" / "Preview failed". */
function setupStatusOk(status: string): boolean {
  if (/fail|error|cannot|cancelled|denied|offline/i.test(status)) return false;
  return /^(Saved|Imported|Reset|Scan|Applied|Cleared|Activated|Inventory|Preview|Validation passed|Loaded|Draft)/.test(
    status,
  );
}


type SectionChoice = { id: string; title: string };
type CtRole = { role: string; label: string; which: string };
type InsightRole = { role: string; label: string; kind: "single" | "multi" };

/** Parse fetch JSON; never throw cryptic SyntaxError for text/plain 500s. */
async function readApiJson(res: Response): Promise<Record<string, unknown>> {
  const text = await res.text();
  if (!text) {
    throw new Error(
      res.ok
        ? "Empty response from server"
        : `Server error ${res.status} (empty body)`,
    );
  }
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    const snippet = text.replace(/\s+/g, " ").trim().slice(0, 160);
    throw new Error(
      `Server returned non-JSON (${res.status}): ${snippet || res.statusText}`,
    );
  }
}

function apiErrorMessage(data: Record<string, unknown>, fallback: string): string {
  const detail = data.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; errors?: string[] };
    if (d.message) return d.message;
    if (Array.isArray(d.errors) && d.errors.length)
      return d.errors.join("; ");
  }
  if (Array.isArray(detail)) {
    return detail
      .map((x) =>
        typeof x === "object" && x && "msg" in x
          ? String((x as { msg: unknown }).msg)
          : String(x),
      )
      .join("; ");
  }
  if (typeof data.message === "string") return data.message;
  return fallback;
}

type Profile = {
  profile_name: string;
  profile_id?: string;
  builtin?: boolean;
  status?: string;
  revision?: number;
  revision_hash?: string;
  sections: SectionChoice[];
  signals?: {
    tag: string;
    description: string;
    historian: string;
    model?: string;
    class?: RowKind;
    section?: string;
    units?: string;
    totalize?: boolean;
    total_units?: string | null;
    include?: boolean;
  }[];
  trend: {
    tag: string;
    description: string;
    historian: string;
    model?: string;
    section: string;
    units: string;
    totalize?: boolean;
    total_units?: string | null;
    include?: boolean;
  }[];
  motors: {
    tag: string;
    description: string;
    historian: string;
    model?: string;
    section?: string;
    units?: string;
    include?: boolean;
  }[];
  feedback: {
    tag: string;
    description: string;
    historian: string;
    model?: string;
    section?: string;
    units?: string;
    include?: boolean;
  }[];
  roles: Record<string, string | string[]>;
  ct: Record<string, unknown> & {
    enabled?: boolean;
    inputs?: Record<string, [string, string]>;
    reports?: Partial<
      Record<"daily" | "weekly" | "monthly" | "yearly" | "custom", boolean>
    >;
  };
};

type SetupState = {
  ok: boolean;
  error?: string | null;
  dlglog?: string;
  models_on_disk?: string[];
  configured: boolean;
  match?: { found: number; total: number; pct: number | null };
  profile: Profile;
  /** Pending Save-draft sidecar — editor prefers this when present. */
  draft_profile?: Profile | null;
  draft_pending?: boolean;
  section_choices: SectionChoice[];
  ct_roles: CtRole[];
  insight_roles: InsightRole[];
  hmi_tag_export?: {
    imported: boolean;
    source_filename?: string | null;
    imported_at?: string | null;
    tag_count?: number;
    folder_count?: number;
    format_version?: string | null;
  };
};

type DiscoverTag = {
  historian: string;
  model: string;
  mapped: boolean;
  exception?: boolean;
  confidence?: number;
  reasons?: string[];
  suggestion: {
    kind: RowKind;
    tag: string;
    description: string;
    section?: string;
    units?: string;
    totalize?: boolean;
    confidence?: number;
    reasons?: string[];
    needs_review?: boolean;
  };
};

const CT_GEOMETRY_FIELDS: [string, string][] = [
  ["clearwell_volume_m3", "Clearwell volume (m³)"],
  ["pipe_volume_m3", "Pipe contact volume (m³)"],
  ["tower_volume_m3", "Tower / reservoir volume (m³)"],
  ["tower_volume_offset_m3", "Tower fixed volume offset (m³)"],
  ["baffle_clearwell", "Baffling factor — clearwell"],
  ["baffle_tower", "Baffling factor — tower"],
  ["baffle_pipe", "Baffling factor — pipe"],
  ["target_giardia_log", "Target Giardia log inactivation"],
  ["target_virus_log", "Target virus log inactivation"],
];

const CT_REPORT_TOGGLES: { id: "daily" | "weekly" | "monthly" | "yearly" | "custom"; label: string }[] =
  [
    { id: "daily", label: "Daily" },
    { id: "weekly", label: "Weekly" },
    { id: "monthly", label: "Monthly" },
    { id: "yearly", label: "Yearly" },
    { id: "custom", label: "Custom" },
  ];

function defaultCtReports(
  enabled: boolean,
  reports?: Partial<
    Record<"daily" | "weekly" | "monthly" | "yearly" | "custom", boolean>
  > | null,
): Record<"daily" | "weekly" | "monthly" | "yearly" | "custom", boolean> {
  if (reports && typeof reports === "object") {
    return {
      daily: !!reports.daily,
      weekly: !!reports.weekly,
      monthly: !!reports.monthly,
      yearly: !!reports.yearly,
      custom: !!reports.custom,
    };
  }
  // Legacy: master on → Daily only
  return {
    daily: enabled,
    weekly: false,
    monthly: false,
    yearly: false,
    custom: false,
  };
}

const EQUIPMENT_SECTION_CHOICES: SectionChoice[] = [
  { id: "runtime", title: "Equipment Runtime Summary" },
  { id: "feedback", title: "Pump & Compressor Feedback" },
];

function mergeSectionChoices(
  profileSections: SectionChoice[],
  defaults: SectionChoice[],
): SectionChoice[] {
  const out: SectionChoice[] = [];
  const seen = new Set<string>();
  for (const s of profileSections) {
    if (!s.id || seen.has(s.id) || s.id === "runtime" || s.id === "feedback") {
      continue;
    }
    out.push(s);
    seen.add(s.id);
  }
  for (const s of defaults) {
    if (!seen.has(s.id) && s.id !== "runtime" && s.id !== "feedback") {
      out.push(s);
      seen.add(s.id);
    }
  }
  return out.length ? out : [{ id: "other", title: "Other Analog" }];
}

/** Sections a tag may be assigned to (instruments vs motors/feedback). */
function sectionOptionsForKind(
  kind: RowKind,
  sections: SectionChoice[],
  defaults: SectionChoice[],
): SectionChoice[] {
  const profile = sections.length ? sections : defaults;
  if (kind === "trend") {
    // Always offer Other Analog so instrument type/section never orphan silently.
    return ensureOtherSection(profile);
  }
  const out: SectionChoice[] = [];
  const seen = new Set<string>();
  for (const s of [...EQUIPMENT_SECTION_CHOICES, ...profile]) {
    if (!s.id || seen.has(s.id)) continue;
    out.push(s);
    seen.add(s.id);
  }
  return out;
}

function defaultSectionForKind(kind: RowKind): string {
  if (kind === "motor") return "runtime";
  if (kind === "feedback") return "feedback";
  return "other";
}

/** Ensure Process Values / Other Analog exists so type changes never “lose” a tag. */
function ensureOtherSection(sections: SectionChoice[]): SectionChoice[] {
  if (sections.some((s) => s.id === "other")) return sections;
  return [...sections, { id: "other", title: "Other Analog" }];
}

function isEquipmentSection(secId: string): boolean {
  return secId === "runtime" || secId === "feedback";
}

function slugSectionId(title: string, existing: Set<string>): string {
  let base =
    title
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "") || "section";
  if (base === "runtime" || base === "feedback") base = `${base}_custom`;
  let id = base;
  let n = 2;
  while (existing.has(id)) {
    id = `${base}_${n++}`;
  }
  return id;
}

function sectionIndexMap(sections: SectionChoice[]): Map<string, number> {
  return new Map(sections.map((s, i) => [s.id, i]));
}

function rowSectionId(row: EditRow): string {
  if (row.section) return row.section;
  return defaultSectionForKind(row.kind);
}

function sectionSortIndex(
  secId: string,
  secIdx: Map<string, number>,
): number {
  if (secIdx.has(secId)) return secIdx.get(secId)!;
  if (secId === "runtime") return 900;
  if (secId === "feedback") return 901;
  return 999;
}

function sortRowsBySections(
  rows: EditRow[],
  sections: SectionChoice[],
): EditRow[] {
  const secIdx = sectionIndexMap(sections);
  const withPos = rows.map((r, i) => ({ r, i }));
  withPos.sort((a, b) => {
    const cmp =
      sectionSortIndex(rowSectionId(a.r), secIdx) -
      sectionSortIndex(rowSectionId(b.r), secIdx);
    return cmp !== 0 ? cmp : a.i - b.i;
  });
  return withPos.map((x) => x.r);
}

export function SetupPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, setState] = useState<SetupState | null>(null);
  const [rows, setRows] = useState<EditRow[]>([]);
  const [sections, setSections] = useState<SectionChoice[]>([]);
  const [profileName, setProfileName] = useState("");
  const [roles, setRoles] = useState<Record<string, string | string[]>>({});
  const [ctEnabled, setCtEnabled] = useState(false);
  const [ctReports, setCtReports] = useState(defaultCtReports(false));
  const [ctGeo, setCtGeo] = useState<Record<string, string>>({});
  const [ctInputs, setCtInputs] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [filter, setFilter] = useState("");
  const [onlyIncluded, setOnlyIncluded] = useState(false);
  const [busyKind, setBusyKind] = useState<BusyKind>(null);
  /** Fingerprint of last loaded/activated include set — detects unsaved Use toggles. */
  const [activatedIncludeKey, setActivatedIncludeKey] = useState("");
  /** Any editor change since last load/activate — warn on hard refresh. */
  const [editorDirty, setEditorDirty] = useState(false);
  const importRef = useRef<HTMLInputElement | null>(null);
  const tagsCsvRef = useRef<HTMLInputElement | null>(null);
  const statusRef = useRef<HTMLElement | null>(null);
  const tagsRef = useRef<HTMLElement | null>(null);
  const autoScanStarted = useRef(false);
  const dragHistRef = useRef<string | null>(null);
  const dragSectionRef = useRef<string | null>(null);

  const flashSection = useCallback((target: "status" | "tags") => {
    const ref = target === "status" ? statusRef : tagsRef;
    const el = ref.current;
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.remove("cfg-card--flash");
    void el.offsetWidth;
    el.classList.add("cfg-card--flash");
  }, []);

  const applyProfile = useCallback((s: SetupState) => {
    // Editor: prefer pending draft sidecar; live profile stays for include-dirty
    const live = s.profile;
    const prof = s.draft_profile || s.profile;
    setProfileName(prof.builtin ? "" : prof.profile_name || "");
    const next: EditRow[] = [];
    const signals = Array.isArray(prof.signals) ? prof.signals : [];
    if (signals.length) {
      for (const r of signals) {
        const kind = (r.class || "trend") as RowKind;
        if (kind === "skip") continue;
        next.push({
          historian: r.historian,
          model: r.model || "",
          include: r.include !== false,
          kind: kind === "motor" || kind === "feedback" ? kind : "trend",
          tag: r.tag,
          description: r.description,
          section:
            r.section ||
            (kind === "motor"
              ? "runtime"
              : kind === "feedback"
                ? "feedback"
                : "other"),
          units: r.units || (kind === "feedback" ? "%" : kind === "motor" ? "h" : ""),
          totalize: !!r.totalize,
          confirmed: true,
        });
      }
    } else {
      for (const r of prof.trend) {
        next.push({
          historian: r.historian,
          model: r.model || "",
          include: r.include !== false,
          kind: "trend",
          tag: r.tag,
          description: r.description,
          section: r.section,
          units: r.units || "",
          totalize: !!r.totalize,
          confirmed: true,
        });
      }
      for (const r of prof.motors) {
        next.push({
          historian: r.historian,
          model: r.model || "",
          include: r.include !== false,
          kind: "motor",
          tag: r.tag,
          description: r.description,
          section: r.section || "runtime",
          units: r.units || "h",
          totalize: false,
          confirmed: true,
        });
      }
      for (const r of prof.feedback) {
        next.push({
          historian: r.historian,
          model: r.model || "",
          include: r.include !== false,
          kind: "feedback",
          tag: r.tag,
          description: r.description,
          section: r.section || "feedback",
          units: r.units || "%",
          totalize: false,
          confirmed: true,
        });
      }
    }
    const mergedSections = ensureOtherSection(
      mergeSectionChoices(
        Array.isArray(prof.sections) ? prof.sections : [],
        s.section_choices || [],
      ),
    );
    setRows(sortRowsBySections(next, mergedSections));
    setSections(mergedSections);
    // Dirty vs live activated include set (not the draft catalog)
    const liveSignals = Array.isArray(live.signals) ? live.signals : [];
    const liveRows = liveSignals.length
      ? liveSignals.filter((r) => (r.class || "trend") !== "skip")
      : [...(live.trend || []), ...(live.motors || []), ...(live.feedback || [])];
    const includeKey = (
      s.configured && liveRows.length
        ? liveRows.filter((r) => r.include !== false)
        : next.filter((r) => r.include)
    )
      .map((r) => r.historian)
      .sort()
      .join("|");
    setActivatedIncludeKey(includeKey);
    setEditorDirty(false);
    setRoles(prof.roles || {});
    setCtEnabled(!!prof.ct?.enabled);
    setCtReports(defaultCtReports(!!prof.ct?.enabled, prof.ct?.reports));
    const geo: Record<string, string> = {};
    for (const [key] of CT_GEOMETRY_FIELDS) {
      const v = prof.ct?.[key];
      geo[key] = v == null ? "" : String(v);
    }
    setCtGeo(geo);
    const inputs: Record<string, string> = {};
    for (const [role, spec] of Object.entries(prof.ct?.inputs || {})) {
      if (Array.isArray(spec) && spec[0]) inputs[role] = String(spec[0]);
    }
    setCtInputs(inputs);
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/setup`);
      const data: SetupState = await res.json();
      setState(data);
      applyProfile(data);
    } catch {
      setStatus("API unreachable — start Plant Reporter");
    }
  }, [applyProfile]);

  useEffect(() => {
    void load();
  }, [load]);

  const scan = useCallback(async () => {
    setScanning(true);
    setStatus(null);
    try {
      const res = await fetch(`${API}/api/setup/inventory`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(
          typeof err.detail === "string" ? err.detail : res.statusText,
        );
      }
      const data: {
        tags: DiscoverTag[];
        exception_count?: number;
        sample_day?: string;
      } = await res.json();
      setRows((prev) => {
        const have = new Set(prev.map((r) => `${r.model}|${r.historian}`));
        const added: EditRow[] = [];
        for (const t of data.tags) {
          const key = `${t.model}|${t.historian}`;
          if (have.has(key) || have.has(`|${t.historian}`)) {
            continue;
          }
          const s = t.suggestion;
          const needs = !!s.needs_review || !!t.exception;
          const conf = s.confidence ?? t.confidence ?? 0;
          // Default Use on for clear matches so Daily works after Activate.
          // needs_review is advisory — only hard-block low confidence.
          const include =
            conf >= 0.75 ||
            (s.kind === "motor" && conf >= 0.7) ||
            (s.kind === "feedback" && conf >= 0.7);
          added.push({
            historian: t.historian,
            model: t.model,
            include,
            kind: s.kind,
            tag: s.tag,
            description: s.description,
            section:
              s.section ||
              defaultSectionForKind(
                s.kind === "motor" || s.kind === "feedback" ? s.kind : "trend",
              ),
            units: s.units || "",
            totalize: !!s.totalize,
            confidence: conf,
            reasons: s.reasons || t.reasons,
            needs_review: needs,
            confirmed: !needs,
            exception: !!t.exception && conf < 0.6,
          });
        }
        const byHist = new Map(data.tags.map((t) => [t.historian, t]));
        const patched = prev.map((r) => {
          const t = byHist.get(r.historian);
          if (!t) return r;
          return {
            ...r,
            model: r.model || t.model,
            confidence: r.confidence ?? t.suggestion?.confidence,
            reasons: r.reasons || t.suggestion?.reasons,
            needs_review: r.needs_review ?? t.suggestion?.needs_review,
            exception: r.exception ?? t.exception,
          };
        });
        if (added.length) {
          setStatus(
            `Inventory: ${data.tags.length} logged tags — ${added.length} new` +
              (data.exception_count
                ? ` (${data.exception_count} need review)`
                : ""),
          );
        } else {
          setStatus(
            `Inventory: ${data.tags.length} logged tags — list already up to date`,
          );
        }
        // Ensure section folders exist for suggested buckets (FIT→Flows, etc.)
        setSections((prev) => {
          const known = new Map(prev.map((s) => [s.id, s]));
          const titles = new Map(
            (state?.section_choices || []).map((s) => [s.id, s.title]),
          );
          for (const eq of EQUIPMENT_SECTION_CHOICES) {
            titles.set(eq.id, eq.title);
          }
          let changed = false;
          for (const row of added) {
            const sid = row.section || defaultSectionForKind(row.kind);
            if (sid === "runtime" || sid === "feedback") continue;
            if (!known.has(sid)) {
              known.set(sid, {
                id: sid,
                title: titles.get(sid) || sid,
              });
              changed = true;
            }
          }
          return changed ? Array.from(known.values()) : prev;
        });
        setFilter("");
        setOnlyIncluded(false);
        return [...patched, ...added];
      });
      flashSection("tags");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Scan failed");
      flashSection("status");
    } finally {
      setScanning(false);
    }
  }, [flashSection, state?.section_choices]);

  // After Connect (or blank plant): pull historian tags and Activate when needed.
  useEffect(() => {
    if (!state?.ok || scanning || autoScanStarted.current) return;
    const fromConnect = searchParams.get("autoscan") === "1";
    const liveN = Array.isArray(state.profile?.signals)
      ? state.profile.signals.length
      : 0;
    const draftN = Array.isArray(state.draft_profile?.signals)
      ? state.draft_profile.signals.length
      : 0;
    const blankPlant = liveN === 0 && draftN === 0 && rows.length === 0;
    const needsBootstrap = !state.configured && (fromConnect || blankPlant);
    if (!fromConnect && !blankPlant && state.configured) return;
    if (!fromConnect && !blankPlant && !needsBootstrap) return;
    autoScanStarted.current = true;
    if (fromConnect) {
      setSearchParams({}, { replace: true });
    }
    void (async () => {
      if (needsBootstrap) {
        setScanning(true);
        setStatus("Scanning DLGLOG and activating profile…");
        try {
          const res = await fetch(`${API}/api/setup/bootstrap-from-dlglog`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          });
          const data = await res.json();
          if (!res.ok) {
            throw new Error(
              typeof data.detail === "string" ? data.detail : "Bootstrap failed",
            );
          }
          setStatus(
            `Activated · ${data.included ?? "?"} tags on reports (${data.tag_count ?? "?"} scanned)`,
          );
          await load();
          flashSection("tags");
        } catch (e) {
          setStatus(e instanceof Error ? e.message : "Bootstrap failed");
          flashSection("status");
          void scan();
        } finally {
          setScanning(false);
        }
        return;
      }
      void scan();
    })();
  }, [
    state,
    rows.length,
    scanning,
    searchParams,
    scan,
    setSearchParams,
    load,
    flashSection,
  ]);

  const update = (
    hist: string,
    patch: Partial<EditRow>,
    sectionsOverride?: SectionChoice[],
  ) => {
    const secs = sectionsOverride ?? sections;
    setEditorDirty(true);
    setRows((prev) => {
      const next = prev.map((r) =>
        r.historian === hist ? { ...r, ...patch } : r,
      );
      if (patch.section !== undefined || patch.kind !== undefined) {
        return sortRowsBySections(next, secs);
      }
      return next;
    });
  };

  const changeRowKind = (row: EditRow, kind: RowKind) => {
    const patch: Partial<EditRow> = { kind };
    let secs = sections;
    let destLabel = "";

    if (kind === "motor") {
      if (!row.section || row.section === "feedback" || !isEquipmentSection(row.section)) {
        patch.section = "runtime";
        destLabel = "Equipment Runtime";
      }
    } else if (kind === "feedback") {
      if (!row.section || row.section === "runtime" || !isEquipmentSection(row.section)) {
        patch.section = "feedback";
        destLabel = "Pump & Compressor Feedback";
      }
    } else {
      // instrument (trend) — leave runtime/feedback or the row looks like it vanished.
      const sec = row.section || "";
      if (!sec || isEquipmentSection(sec) || !secs.some((s) => s.id === sec)) {
        secs = ensureOtherSection(secs);
        if (secs !== sections) setSections(secs);
        patch.section = "other";
        destLabel = "Other Analog";
      }
    }

    update(row.historian, patch, secs);
    const who = row.tag || row.historian;
    const typeLabel =
      kind === "trend" ? "instrument" : kind === "motor" ? "motor" : "feedback";
    setStatus(
      destLabel
        ? `${who} → ${typeLabel} (now under “${destLabel}”). Scroll that section if you don’t see it.`
        : `${who} → ${typeLabel}.`,
    );
    window.requestAnimationFrame(() => {
      document
        .querySelector(`[data-historian="${CSS.escape(row.historian)}"]`)
        ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  };

  const updateSectionTitle = (id: string, title: string) => {
    setEditorDirty(true);
    setSections((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title } : s)),
    );
  };

  const addSection = () => {
    setEditorDirty(true);
    setSections((prev) => {
      const existing = new Set(prev.map((s) => s.id));
      const id = slugSectionId("New section", existing);
      return [...prev, { id, title: "New section" }];
    });
  };

  const removeSection = (id: string) => {
    const title = sections.find((s) => s.id === id)?.title || id;
    const nextSections = sections.filter((s) => s.id !== id);
    if (!nextSections.length) {
      window.alert("Keep at least one report section.");
      return;
    }
    // Prefer Process Values / other; never fall back to the section being removed.
    const instrumentDest =
      nextSections.find((s) => s.id === "other") || nextSections[0];
    const instrumentDestLabel = instrumentDest.title || instrumentDest.id;
    const inSection = rows.filter((r) => r.section === id);
    const nTrend = inSection.filter((r) => r.kind === "trend").length;
    const nMotor = inSection.filter((r) => r.kind === "motor").length;
    const nFb = inSection.filter((r) => r.kind === "feedback").length;
    const lines = [
      `Remove section "${title}"?`,
      "",
      "Tags assigned here will move:",
    ];
    if (nTrend) lines.push(`• ${nTrend} instrument(s) → ${instrumentDestLabel}`);
    if (nMotor) lines.push(`• ${nMotor} motor(s) → Equipment Runtime Summary`);
    if (nFb) lines.push(`• ${nFb} feedback → Pump & Compressor Feedback`);
    if (!nTrend && !nMotor && !nFb) {
      lines.push("• (no tags in this section)");
    }
    if (!window.confirm(lines.join("\n"))) {
      return;
    }
    setEditorDirty(true);
    setRows((prev) =>
      sortRowsBySections(
        prev.map((r) => {
          if (r.section !== id) return r;
          if (r.kind === "motor") return { ...r, section: "runtime" };
          if (r.kind === "feedback") return { ...r, section: "feedback" };
          return { ...r, section: instrumentDest.id };
        }),
        nextSections,
      ),
    );
    setSections(nextSections);
  };

  /** Insert fromId immediately before toId. Tags keep their section ids — only order changes. */
  const moveSection = (fromId: string, toId: string) => {
    if (fromId === toId) return;
    const from = sections.findIndex((s) => s.id === fromId);
    let to = sections.findIndex((s) => s.id === toId);
    if (from < 0 || to < 0) return;
    setEditorDirty(true);
    const nextSections = [...sections];
    const [item] = nextSections.splice(from, 1);
    // After removal, indices after `from` shift left.
    if (from < to) to -= 1;
    nextSections.splice(to, 0, item);
    setSections(nextSections);
    setRows((prev) => sortRowsBySections(prev, nextSections));
  };

  const moveSectionByDelta = (id: string, delta: -1 | 1) => {
    const from = sections.findIndex((s) => s.id === id);
    if (from < 0) return;
    const to = from + delta;
    if (to < 0 || to >= sections.length) return;
    setEditorDirty(true);
    const nextSections = [...sections];
    const [item] = nextSections.splice(from, 1);
    nextSections.splice(to, 0, item);
    setSections(nextSections);
    setRows((prev) => sortRowsBySections(prev, nextSections));
  };

  const moveRow = (fromHist: string, toHist: string) => {
    if (fromHist === toHist) return;
    setEditorDirty(true);
    setRows((prev) => {
      const fromIdx = prev.findIndex((r) => r.historian === fromHist);
      const toIdx = prev.findIndex((r) => r.historian === toHist);
      if (fromIdx < 0 || toIdx < 0) return prev;
      const next = [...prev];
      const target = next[toIdx];
      const [item] = next.splice(fromIdx, 1);
      // Dropping onto a row in another section moves the tag into that section.
      let moved = item;
      if (rowSectionId(item) !== rowSectionId(target)) {
        moved = { ...item, section: rowSectionId(target) };
      }
      const insertAt = next.findIndex((r) => r.historian === toHist);
      next.splice(insertAt < 0 ? toIdx : insertAt, 0, moved);
      return next;
    });
  };

  const moveRowToSection = (hist: string, sectionId: string) => {
    setEditorDirty(true);
    setRows((prev) =>
      sortRowsBySections(
        prev.map((r) =>
          r.historian === hist ? { ...r, section: sectionId } : r,
        ),
        sections,
      ),
    );
  };

  const trendIncluded = useMemo(
    () => rows.filter((r) => r.include && r.kind === "trend"),
    [rows],
  );
  const motorIncluded = useMemo(
    () => rows.filter((r) => r.include && r.kind === "motor"),
    [rows],
  );

  const buildProfile = () => {
    const cleanRoles: Record<string, string | string[]> = {};
    const trendHists = new Set(trendIncluded.map((r) => r.historian));
    for (const ir of state?.insight_roles || []) {
      const v = roles[ir.role];
      if (ir.kind === "multi") {
        const list = (Array.isArray(v) ? v : []).filter((x) =>
          ir.role === "high_lift_pumps"
            ? motorIncluded.some((m) => m.tag === x)
            : trendHists.has(x),
        );
        if (list.length) cleanRoles[ir.role] = list;
      } else if (typeof v === "string" && v) {
        // Efficiency may live only in a reports model (not on Daily trend list).
        if (ir.role === "plant_efficiency" || trendHists.has(v)) {
          cleanRoles[ir.role] = v;
        }
      }
    }
    const inputs: Record<string, [string, string]> = {};
    for (const cr of state?.ct_roles || []) {
      const hist = ctInputs[cr.role];
      if (hist && trendHists.has(hist)) inputs[cr.role] = [hist, cr.which];
    }
    const geo: Record<string, unknown> = {};
    for (const [key] of CT_GEOMETRY_FIELDS) {
      const raw = (ctGeo[key] || "").trim();
      if (raw !== "" && !Number.isNaN(Number(raw))) geo[key] = Number(raw);
    }
    const catalog = rows.filter((r) => r.kind !== "skip");
    const orderedCatalog = sortRowsBySections(catalog, sections);
    // Persist the full catalog with include=true/false so Use checkboxes survive
    // Activate/reload. Reports only use include=true (server filters).
    const signals = orderedCatalog.map((r, i) => ({
      historian: r.historian,
      model: r.model,
      class: r.kind,
      tag: r.tag,
      description: r.description,
      section: r.section || defaultSectionForKind(r.kind),
      units:
        r.kind === "motor"
          ? r.units?.trim() || "h"
          : r.units || (r.kind === "feedback" ? "%" : ""),
      totalize: r.kind === "trend" ? r.totalize : false,
      total_units: r.kind === "trend" && r.totalize ? "m3" : null,
      include: !!r.include,
      confirmed: true,
      confidence: r.confidence ?? 1,
      reasons: r.reasons || [],
      order: i,
    }));
    const live = state?.draft_profile || state?.profile;
    return {
      profile_name: profileName.trim() || "My plant",
      // Keep identity across Activate so revision bumps instead of resetting to 1
      profile_id: live?.profile_id,
      revision: live?.revision,
      sections,
      signals,
      // Keep projected arrays for older clients / validation fallbacks
      trend: trendIncluded.map((r) => ({
        tag: r.tag,
        description: r.description,
        historian: r.historian,
        model: r.model,
        section: r.section || "other",
        units: r.units,
        totalize: r.totalize,
        total_units: r.totalize ? "m3" : null,
        include: true,
        confirmed: true,
        confidence: r.confidence ?? 1,
        reasons: r.reasons || [],
      })),
      motors: motorIncluded.map((r) => ({
        tag: r.tag,
        description: r.description,
        historian: r.historian,
        model: r.model,
        section: r.section || "runtime",
        units: r.units?.trim() || "h",
        include: true,
        confirmed: true,
        confidence: r.confidence ?? 1,
      })),
      feedback: rows
        .filter((r) => r.include && r.kind === "feedback")
        .map((r) => ({
          tag: r.tag,
          description: r.description,
          historian: r.historian,
          model: r.model,
          section: r.section || "feedback",
          units: r.units || "%",
          include: true,
          confirmed: true,
          confidence: r.confidence ?? 1,
        })),
      roles: cleanRoles,
      ct: { enabled: ctEnabled, reports: ctReports, ...geo, inputs },
    };
  };

  const currentIncludeKey = useMemo(
    () =>
      rows
        .filter((r) => r.include)
        .map((r) => r.historian)
        .sort()
        .join("|"),
    [rows],
  );
  const includeDirty =
    !!activatedIncludeKey && currentIncludeKey !== activatedIncludeKey;

  useEffect(() => {
    if (!editorDirty && !includeDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [editorDirty, includeDirty]);

  const save = async () => {
    if (!trendIncluded.length && !motorIncluded.length) {
      setStatus("Include at least one instrument or motor before saving");
      return;
    }
    setBusy(true);
    setBusyKind("activate");
    setStatus(null);
    try {
      const res = await fetch(`${API}/api/setup/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...buildProfile(), activate: true }),
      });
      const data = await readApiJson(res);
      if (!res.ok) {
        throw new Error(apiErrorMessage(data, "Activate failed"));
      }
      const prof = data.profile as Profile | undefined;
      const name = prof?.profile_name || profileName || "plant";
      setStatus(`Activated "${name}" revision ${prof?.revision ?? "?"}`);
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Activate failed");
    } finally {
      setBusy(false);
      setBusyKind(null);
    }
  };


  const runActivate = async () => {
    const name = profileName.trim() || "My plant";
    if (
      !window.confirm(
        `Activate profile "${name}"?\n\nReports will use this mapping. Continue?`,
      )
    ) {
      setStatus("Activate cancelled");
      flashSection("tags");
      return;
    }
    flashSection("tags");
    await save();
  };

  const exportProfile = async () => {
    try {
      const res = await fetch(`${API}/api/setup/export`);
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const name = (data.tag_config?.profile_name || "plant")
        .replace(/[^\w-]+/g, "_")
        .toLowerCase();
      a.download = `ops_reporter_profile_${name}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Export failed");
    }
  };

  const importProfile = async (file: File) => {
    if (
      !window.confirm(
        `Import and Activate profile from "${file.name}"?\n\nThis replaces your current live mapping. Continue?`,
      )
    ) {
      setStatus("Import cancelled");
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      const text = await file.text();
      const res = await fetch(`${API}/api/setup/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: text,
      });
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Import failed",
        );
      setStatus(`Imported profile "${data.profile.profile_name}"`);
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  };

  const importTagsCsv = async (file: File) => {
    setBusy(true);
    setStatus(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API}/api/setup/hmi-tags`, {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Tags CSV import failed",
        );
      const match = data.dlglog_match;
      const matchNote = match
        ? ` · ${match.with_description}/${match.total} DLGLOG tags have descriptions`
        : "";
      setStatus(
        `Imported FactoryTalk Tags.CSV "${data.source_filename}" (${data.tag_count} tags)${matchNote}. Scan or Apply descriptions to use them.`,
      );
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Tags CSV import failed");
    } finally {
      setBusy(false);
    }
  };

  const clearTagsCsv = async () => {
    setBusy(true);
    setStatus(null);
    try {
      await fetch(`${API}/api/setup/hmi-tags`, { method: "DELETE" });
      setStatus("Cleared FactoryTalk Tags.CSV enrichment");
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Clear failed");
    } finally {
      setBusy(false);
    }
  };

  const applyTagsCsvDescriptions = async () => {
    setBusy(true);
    setStatus(null);
    try {
      const res = await fetch(`${API}/api/setup/hmi-tags/apply`, {
        method: "POST",
      });
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Apply failed",
        );
      const patches: {
        historian: string;
        description: string;
        units?: string;
      }[] = data.profile_patches || [];
      const byHist = new Map(patches.map((p) => [p.historian, p]));
      const unmapped = data.unmapped_with_descriptions || [];
      setRows((prev) => {
        let next = prev.map((r) => {
          const p = byHist.get(r.historian);
          if (!p) return r;
          return {
            ...r,
            description: p.description,
            units: p.units != null ? p.units : r.units,
          };
        });
        const have = new Set(next.map((r) => r.historian));
        const extras: EditRow[] = [];
        for (const u of unmapped) {
          if (have.has(u.historian)) continue;
          const s = u.suggestion || {};
          extras.push({
            historian: u.historian,
            model: u.model || "",
            include: false,
            kind: (s.kind as RowKind) || "trend",
            tag: s.tag || u.historian,
            description: s.description || u.historian,
            section: s.section || "other",
            units: s.units || "",
            totalize: !!s.totalize,
          });
          have.add(u.historian);
        }
        return extras.length ? [...next, ...extras] : next;
      });

      const applied = patches.length;
      const extraCount = unmapped.length;
      setStatus(
        `Applied HMI descriptions to ${applied} mapped tag${applied === 1 ? "" : "s"}` +
          (extraCount
            ? ` · ${extraCount} additional DLGLOG tag${extraCount === 1 ? "" : "s"} with descriptions listed (unchecked)`
            : "") +
          " — review and Save when ready",
      );
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setBusy(false);
    }
  };

  const q = filter.trim().toUpperCase();
  const exceptionRows = rows.filter(
    (r) =>
      r.include &&
      (r.needs_review ||
        r.exception ||
        (r.kind === "trend" && !r.units)),
  );
  const visible = rows.filter((r) => {
    if (onlyIncluded && !r.include) return false;
    if (!q) return true;
    return (
      r.historian.toUpperCase().includes(q) ||
      r.tag.toUpperCase().includes(q) ||
      r.description.toUpperCase().includes(q) ||
      (r.model || "").toUpperCase().includes(q)
    );
  });

  const includedCount = rows.filter((r) => r.include).length;
  const canReorder = !q && !onlyIncluded;

  const sectionTitleOf = (secId: string): string => {
    const fromProf = sections.find((s) => s.id === secId);
    if (fromProf) return fromProf.title || secId;
    const eq = EQUIPMENT_SECTION_CHOICES.find((s) => s.id === secId);
    if (eq) return eq.title;
    return secId;
  };

  const tagsInSection = (secId: string) =>
    rows.filter((r) => rowSectionId(r) === secId);

  /** Tag table grouped under section titles (live preview before Activate). */
  const visibleGroups = (() => {
    const bySec = new Map<string, EditRow[]>();
    for (const r of visible) {
      const sid = rowSectionId(r);
      const list = bySec.get(sid);
      if (list) list.push(r);
      else bySec.set(sid, [r]);
    }
    const out: { id: string; title: string; rows: EditRow[] }[] = [];
    const seen = new Set<string>();
    // Always list every Setup section — including brand-new empty ones —
    // so operators can drop/assign tags into them immediately.
    for (const s of sections) {
      out.push({
        id: s.id,
        title: s.title || s.id,
        rows: bySec.get(s.id) || [],
      });
      seen.add(s.id);
    }
    for (const eq of EQUIPMENT_SECTION_CHOICES) {
      if (seen.has(eq.id)) continue;
      const group = bySec.get(eq.id);
      if (!group?.length) continue;
      out.push({ id: eq.id, title: eq.title, rows: group });
      seen.add(eq.id);
    }
    for (const [id, group] of bySec) {
      if (seen.has(id)) continue;
      out.push({ id, title: sectionTitleOf(id), rows: group });
    }
    return out;
  })();

  const activateLabel = busy
    ? "Working…"
    : includeDirty
      ? "Activate profile (apply Use)"
      : editorDirty
        ? "Activate profile (apply edits)"
        : "Activate profile";

  return (
    <div className="page">
      <header className="page__head">
        <div>
          <p className="eyebrow">Plant Builder</p>
          <h1>Map this plant's tags</h1>
          <p className="lede">
            Scan DLGLOG tags, optionally import FactoryTalk Tags.CSV, edit Use /
            units / sections, then Activate. Reports stay blocked until a profile
            is activated.
          </p>
        </div>
      </header>


      <section className="cfg-card" ref={statusRef}>
        <h2>Status</h2>
        <p className="cfg-live">
          {state?.ok ? (
            <>
              <span className="ok">DLGLOG connected</span> · {state.dlglog}
              <br />
              Profile:{" "}
              <strong>
                {state.configured
                  ? state.profile.profile_name
                  : "Unconfigured — Activate required"}
              </strong>
              {(state.profile as { revision?: number }).revision ? (
                <> · rev {(state.profile as { revision?: number }).revision}</>
              ) : null}
              {state.match?.total ? (
                <>
                  {" "}
                  · {state.match.found}/{state.match.total} mapped tags exist in
                  this DLGLOG ({state.match.pct}%)
                </>
              ) : null}
              {exceptionRows.length > 0 && (
                <>
                  <br />
                  <span className="warn">
                    {exceptionRows.length} exception(s) need review before
                    activation
                  </span>
                </>
              )}
            </>
          ) : (
            <span className="warn">
              {state?.error || "Not connected"} —{" "}
              <Link to="/connect">open Connect</Link> first
            </span>
          )}
        </p>
        <div className="cfg-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={scanning || !state?.ok}
            onClick={() => void scan()}
          >
            {scanning ? "Scanning…" : "Scan DLGLOG tags"}
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void exportProfile()}
          >
            Export profile
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => importRef.current?.click()}
          >
            Import profile…
          </button>
          <input
            ref={importRef}
            type="file"
            accept=".json,application/json"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importProfile(f);
              e.target.value = "";
            }}
          />
        </div>
        <BusyOverlay
          active={scanning}
          label="Scanning DLGLOG inventory…"
          detail="Reading Tagname.DAT and sampling recent days from every model…"
          taskKey="setup-scan"
          expectSeconds={30}
        />
        <BusyOverlay
          active={busy && !scanning}
          label={busyKind === "activate" ? "Activating profile…" : "Working…"}
          detail="Please wait — this uses your current in-editor mapping."
          taskKey="setup-busy"
          expectSeconds={15}
        />
        {status && !scanning && (
          <p
            className={`status ${setupStatusOk(status) ? "ok" : "warn"}`}
          >
            {status}
          </p>
        )}
      </section>

      <section className="cfg-card">
        <h2>Optional · FactoryTalk Tags.CSV</h2>
        <p className="cfg-hint">
          Export from FactoryTalk View Studio →{" "}
          <strong>Tools → Tag Import and Export Wizard</strong>. Not required —
          DLGLOG alone is enough to scan tags — but the CSV fills HMI
          descriptions, ranges, and units (recommended when available).
        </p>
        <p className="cfg-live">
          {state?.hmi_tag_export?.imported ? (
            <>
              <span className="ok">Tags.CSV loaded</span> ·{" "}
              {state.hmi_tag_export.source_filename} ·{" "}
              {state.hmi_tag_export.tag_count} tags
              {state.hmi_tag_export.imported_at
                ? ` · imported ${state.hmi_tag_export.imported_at}`
                : ""}
            </>
          ) : (
            <span className="warn">No Tags.CSV imported — using name-based suggestions only</span>
          )}
        </p>
        <div className="cfg-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => tagsCsvRef.current?.click()}
          >
            Import Tags.CSV…
          </button>
          <input
            ref={tagsCsvRef}
            type="file"
            accept=".csv,.txt,text/csv,text/plain"
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importTagsCsv(f);
              e.target.value = "";
            }}
          />
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || !state?.hmi_tag_export?.imported}
            onClick={() => void applyTagsCsvDescriptions()}
            title="Fill descriptions on mapped tags from the imported HMI database"
          >
            Apply descriptions
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy || !state?.hmi_tag_export?.imported}
            onClick={() => void clearTagsCsv()}
          >
            Clear Tags.CSV
          </button>
        </div>
      </section>

      <section className="cfg-card">
        <h2>1 · Profile</h2>
        <div className="cfg-row">
          <label className="cfg-label">
            Profile name
            <input
              className="cfg-input"
              value={profileName}
              onChange={(e) => setProfileName(e.target.value)}
              placeholder="My Water Treatment Plant"
            />
          </label>
        </div>
        <p className="cfg-hint">
          Plant name and municipality for report headers are on the{" "}
          <Link to="/connect">Connect</Link> page.
        </p>
      </section>

      <section className="cfg-card" ref={tagsRef}>
        <h2>
          2 · Tags on reports{" "}
          <small className="setup-count">
            {includedCount} included / {rows.length} listed
          </small>
        </h2>
        <p className="cfg-hint">
          Tick <strong>Use</strong> for every tag you want on Daily / Weekly /
          Monthly / Yearly reports (and Insights). Unticked tags stay in this
          list but are omitted from reports after you{" "}
          <strong>Activate profile</strong>. Changing Use does not apply until
          Activate.
        </p>
        {includeDirty && (
          <p className="status warn" role="status">
            Use checkboxes changed — click Activate profile below before opening
            reports, or unchecked tags will still appear.
          </p>
        )}
        {editorDirty && !includeDirty && (
          <p className="status warn" role="status">
            Description / units / section edits are local until you Activate
            profile below.
          </p>
        )}
        <div className="setup-sections">
          <h3 className="setup-sub">Report sections</h3>
          <p className="cfg-hint">
            One Setup drives Daily, Weekly, Monthly, Yearly, and Custom — same
            sections and tags. Drag the ⋮⋮ handle (or use ↑ ↓) to set report
            order — tags stay under their section and move with it. Edit titles,
            add sections, then assign tags below before you Activate.
          </p>
          <ul className="setup-section-list" aria-label="Report sections">
            {sections.map((sec, secIdx) => {
              const assigned = tagsInSection(sec.id);
              const used = assigned.filter((r) => r.include).length;
              return (
              <li
                key={sec.id}
                className="setup-section-item"
                onDragOver={(e) => {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  const fromTag =
                    dragHistRef.current ||
                    e.dataTransfer.getData("text/historian") ||
                    null;
                  const fromSec =
                    dragSectionRef.current ||
                    e.dataTransfer.getData("text/section-id") ||
                    null;
                  dragSectionRef.current = null;
                  dragHistRef.current = null;
                  if (fromTag) {
                    moveRowToSection(fromTag, sec.id);
                    return;
                  }
                  if (fromSec) moveSection(fromSec, sec.id);
                }}
              >
                <span
                  className="setup-drag"
                  title="Drag to reorder sections"
                  aria-label={`Drag to reorder ${sec.title || sec.id}`}
                  draggable={!busy}
                  onDragStart={(e) => {
                    dragHistRef.current = null;
                    dragSectionRef.current = sec.id;
                    e.dataTransfer.effectAllowed = "move";
                    e.dataTransfer.setData("text/section-id", sec.id);
                    e.dataTransfer.setData("text/plain", sec.id);
                  }}
                  onDragEnd={() => {
                    dragSectionRef.current = null;
                  }}
                >
                  ⋮⋮
                </span>
                <input
                  className="cfg-input setup-section-item__title"
                  value={sec.title}
                  disabled={busy}
                  onChange={(e) => updateSectionTitle(sec.id, e.target.value)}
                />
                <span
                  className="setup-section-item__count"
                  title={`${used} on reports · ${assigned.length} assigned`}
                >
                  {used}/{assigned.length}
                </span>
                <code className="setup-section-item__id">{sec.id}</code>
                <span className="setup-section-item__move">
                  <button
                    type="button"
                    className="btn btn-secondary setup-section-item__move-btn"
                    disabled={busy || secIdx === 0}
                    title="Move section up"
                    aria-label={`Move ${sec.title || sec.id} up`}
                    onClick={() => moveSectionByDelta(sec.id, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary setup-section-item__move-btn"
                    disabled={busy || secIdx >= sections.length - 1}
                    title="Move section down"
                    aria-label={`Move ${sec.title || sec.id} down`}
                    onClick={() => moveSectionByDelta(sec.id, 1)}
                  >
                    ↓
                  </button>
                </span>
                <button
                  type="button"
                  className="btn btn-secondary setup-section-item__remove"
                  disabled={busy || sections.length <= 1}
                  onClick={() => removeSection(sec.id)}
                >
                  Remove
                </button>
              </li>
              );
            })}
          </ul>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={addSection}
          >
            Add section
          </button>
        </div>
        <div className="setup-filter-row">
          <input
            className="cfg-input"
            placeholder="Filter tags…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <label className="setup-check">
            <input
              type="checkbox"
              checked={onlyIncluded}
              onChange={(e) => setOnlyIncluded(e.target.checked)}
            />
            Only included
          </label>
        </div>
        {!canReorder && rows.length > 1 && (
          <p className="cfg-hint setup-reorder-hint">
            Clear the tag filter and turn off “Only included” to drag-reorder
            rows on reports.
          </p>
        )}
        <div className="setup-table-wrap">
          <table className="setup-table">
            <thead>
              <tr>
                {canReorder ? (
                  <th className="setup-th-drag" aria-label="Reorder" />
                ) : null}
                <th>Use</th>
                <th>Logged tag (historian)</th>
                <th>Type</th>
                <th>Report tag</th>
                <th>Description</th>
                <th>Section</th>
                <th title="Edit freely — not locked to the auto-guess">Units</th>
                <th title="Tick on any analog to show a daily volume total (integral). Guess only pre-checks FIT flows.">
                  Total
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleGroups.map((group) => {
                const used = group.rows.filter((r) => r.include).length;
                const colSpan = canReorder ? 9 : 8;
                return (
                  <Fragment key={`grp-${group.id}`}>
                    <tr
                      className="setup-section-head"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={() => {
                        const from = dragHistRef.current;
                        dragHistRef.current = null;
                        if (from) moveRowToSection(from, group.id);
                      }}
                    >
                      <td colSpan={colSpan}>
                        <span className="setup-section-head__title">
                          {group.title}
                        </span>
                        <span className="setup-section-head__meta">
                          {used} on report · {group.rows.length} assigned
                          {group.id === "runtime" || group.id === "feedback"
                            ? " · equipment block"
                            : ""}
                        </span>
                      </td>
                    </tr>
                    {group.rows.length === 0 ? (
                      <tr className="setup-section-empty">
                        <td colSpan={colSpan}>
                          No tags here yet — drag a tag onto this heading, or
                          choose “{group.title}” in the Section column on a tag
                          row.
                        </td>
                      </tr>
                    ) : null}
                    {group.rows.map((r) => (
                <tr
                  key={r.historian}
                  data-historian={r.historian}
                  className={r.include ? "" : "is-off"}
                  draggable={canReorder}
                  onDragStart={() => {
                    dragHistRef.current = r.historian;
                  }}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={() => {
                    const from = dragHistRef.current;
                    dragHistRef.current = null;
                    if (from) moveRow(from, r.historian);
                  }}
                >
                  {canReorder ? (
                    <td className="setup-drag-cell">
                      <span className="setup-drag" title="Drag to reorder" aria-hidden>
                        ⋮⋮
                      </span>
                    </td>
                  ) : null}
                  <td>
                    <input
                      type="checkbox"
                      checked={r.include}
                      onChange={(e) =>
                        update(r.historian, { include: e.target.checked })
                      }
                    />
                  </td>
                  <td className="setup-hist" title={r.model || undefined}>
                    {r.historian}
                    {r.model ? <small> · {r.model}</small> : null}
                  </td>
                  <td>
                    <select
                      value={r.kind}
                      onChange={(e) =>
                        changeRowKind(r, e.target.value as RowKind)
                      }
                    >
                      <option value="trend">instrument</option>
                      <option value="motor">motor</option>
                      <option value="feedback">feedback</option>
                    </select>
                  </td>
                  <td>
                    <input
                      className="setup-mini"
                      value={r.tag}
                      onChange={(e) =>
                        update(r.historian, { tag: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    <input
                      className="setup-desc"
                      value={r.description}
                      onChange={(e) =>
                        update(r.historian, { description: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    <select
                      value={
                        sectionOptionsForKind(
                          r.kind,
                          sections,
                          state?.section_choices || [],
                        ).some((s) => s.id === rowSectionId(r))
                          ? rowSectionId(r)
                          : r.kind === "trend"
                            ? "other"
                            : rowSectionId(r)
                      }
                      onChange={(e) => {
                        const sid = e.target.value;
                        update(r.historian, { section: sid });
                        const title =
                          sections.find((s) => s.id === sid)?.title ||
                          EQUIPMENT_SECTION_CHOICES.find((s) => s.id === sid)
                            ?.title ||
                          sid;
                        setStatus(
                          `${r.tag || r.historian} moved to “${title}”.`,
                        );
                        window.requestAnimationFrame(() => {
                          document
                            .querySelector(
                              `[data-historian="${CSS.escape(r.historian)}"]`,
                            )
                            ?.scrollIntoView({
                              block: "nearest",
                              behavior: "smooth",
                            });
                        });
                      }}
                    >
                      {sectionOptionsForKind(
                        r.kind,
                        sections,
                        state?.section_choices || [],
                      ).map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.title}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      className="setup-mini setup-units"
                      value={r.units}
                      placeholder={r.kind === "motor" ? "h / min / s" : "e.g. L/s"}
                      title={
                        r.kind === "motor"
                          ? "Runtime display units: h (hours), min, or s — value converts"
                          : "Click to edit units"
                      }
                      onChange={(e) =>
                        update(r.historian, { units: e.target.value })
                      }
                    />
                  </td>
                  <td>
                    {r.kind === "trend" ? (
                      <input
                        type="checkbox"
                        checked={r.totalize}
                        title="Show daily total (m³) from rate × time"
                        onChange={(e) =>
                          update(r.historian, { totalize: e.target.checked })
                        }
                      />
                    ) : (
                      <span className="setup-dash">—</span>
                    )}
                  </td>
                </tr>
                    ))}
                  </Fragment>
                );
              })}
              {!visible.length && (
                <tr>
                  <td colSpan={canReorder ? 9 : 8} className="setup-empty">
                    {rows.length
                      ? "No tags match the filter."
                      : scanning
                        ? "Scanning DLGLOG for logged tags…"
                        : state?.ok
                          ? "No tags listed yet — click “Scan DLGLOG tags” (runs automatically after Connect)."
                          : "Press “Scan DLGLOG tags” to list everything this SCADA logs."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="setup-activate-row">
          <p className="cfg-hint setup-activate-row__hint">
            After ticking Use (or editing descriptions/units),{" "}
            <strong>Activate profile</strong> so Daily and other reports pick up
            the change.
          </p>
          {state?.draft_pending && state.configured && (
            <p className="status warn" role="status">
              An old draft sidecar is pending — Activate applies it to live
              reports.
            </p>
          )}
          <div className="setup-activate-row__actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void runActivate()}
            >
              {activateLabel}
            </button>
          </div>
        </div>
      </section>

      <section className="cfg-card">
        <h2>3 · Insight roles (optional)</h2>
        <p className="cfg-hint">
          Optional: map which of this plant&apos;s included tags feed Insights
          cards (flows, levels, Cl₂, pH, efficiency). Dropdowns list your mapped
          tags — any naming style. Leave blank to hide that metric. CT
          disinfection is section 4 below — separate from this.
        </p>
        <div className="setup-roles">
          {(state?.insight_roles || [])
            .filter((ir) => ir.kind === "single")
            .map((ir) => (
              <label key={ir.role} className="cfg-label">
                {ir.label}
                <select
                  className="cfg-input"
                  value={
                    typeof roles[ir.role] === "string"
                      ? (roles[ir.role] as string)
                      : ""
                  }
                  onChange={(e) =>
                    setRoles((p) => ({ ...p, [ir.role]: e.target.value }))
                  }
                >
                  <option value="">— not used —</option>
                  {ir.role === "plant_efficiency" ? (
                    <option value="PLANT_DAY_EFFICIENCY">
                      PLANT_DAY_EFFICIENCY (reports model)
                    </option>
                  ) : null}
                  {trendIncluded.map((r) => (
                    <option key={r.historian} value={r.historian}>
                      {r.tag} — {r.description}
                    </option>
                  ))}
                </select>
              </label>
            ))}
        </div>
        <details className="setup-roles-advanced">
          <summary>
            Advanced — Insights multi-tag roles (optional)
          </summary>
          <p className="cfg-hint">
            Optional: pick which of <em>this plant&apos;s</em> mapped tags Insights
            should treat as filter-effluent turbidity (tight NTU grading) and which
            motors form one high-lift / distribution duty group. Leave empty if
            you do not want those Insights cards — nothing is assumed from tag
            names. Ctrl/Cmd-click to select multiple; then Activate.
          </p>
          <div className="setup-roles">
            {(state?.insight_roles || [])
              .filter((ir) => ir.kind === "multi")
              .map((ir) => {
                const options =
                  ir.role === "high_lift_pumps"
                    ? motorIncluded.map((m) => ({
                        id: m.tag,
                        label: `${m.tag} — ${m.description || "motor"}`,
                      }))
                    : trendIncluded.map((t) => ({
                        id: t.historian,
                        label: `${t.tag} — ${t.description || t.historian}`,
                      }));
                const cur = Array.isArray(roles[ir.role])
                  ? (roles[ir.role] as string[])
                  : [];
                return (
                  <label key={ir.role} className="cfg-label">
                    {ir.label}
                    <select
                      className="cfg-input"
                      multiple
                      size={Math.min(8, Math.max(4, options.length || 4))}
                      value={cur}
                      onChange={(e) => {
                        const next = Array.from(
                          e.target.selectedOptions,
                          (o) => o.value,
                        );
                        setRoles((p) => ({ ...p, [ir.role]: next }));
                        setEditorDirty(true);
                      }}
                    >
                      {options.length === 0 ? (
                        <option value="" disabled>
                          No included tags yet — tick Use on tags above first
                        </option>
                      ) : (
                        options.map((opt) => (
                          <option key={opt.id} value={opt.id}>
                            {opt.label}
                          </option>
                        ))
                      )}
                    </select>
                    <small className="setup-which">
                      {ir.role === "filter_turbidity"
                        ? "Any included instruments — pick filter effluent only (Ctrl/Cmd-click)."
                        : "Any included motors — pick the duty group to sum together (Ctrl/Cmd-click)."}
                    </small>
                  </label>
                );
              })}
          </div>
        </details>
      </section>

      <section className="cfg-card">
        <h2>4 · CT disinfection (optional)</h2>
        <label className="setup-check setup-ct-toggle">
          <input
            type="checkbox"
            checked={ctEnabled}
            onChange={(e) => {
              const on = e.target.checked;
              setCtEnabled(on);
              setEditorDirty(true);
              if (on) {
                setCtReports((prev) =>
                  prev.daily || prev.weekly || prev.monthly || prev.yearly || prev.custom
                    ? prev
                    : { ...prev, daily: true },
                );
              }
            }}
          />
          Enable CT disinfection for this plant (volumes &amp; inputs)
        </label>
        {ctEnabled && (
          <>
            <p className="cfg-hint">
              Enter contact volumes and baffling for this plant, then map CT
              instruments. Use the checkboxes below to put the CT table on
              some reports and leave it off others — e.g. Daily + Weekly on,
              Monthly off. Multi-day CT uses period-worst-case min/max.
              Activate profile to apply.
            </p>
            <fieldset className="setup-ct-reports">
              <legend className="setup-ct-reports__label">
                Put CT Achieved / Required on these reports
              </legend>
              {CT_REPORT_TOGGLES.map(({ id, label }) => (
                <label key={id} className="setup-check setup-ct-report">
                  <input
                    type="checkbox"
                    checked={!!ctReports[id]}
                    onChange={(e) => {
                      setCtReports((p) => ({ ...p, [id]: e.target.checked }));
                      setEditorDirty(true);
                    }}
                  />
                  {label} report
                </label>
              ))}
            </fieldset>
            <div className="setup-geo">
              {CT_GEOMETRY_FIELDS.map(([key, label]) => (
                <label key={key} className="cfg-label">
                  {label}
                  <input
                    className="cfg-input"
                    inputMode="decimal"
                    value={ctGeo[key] ?? ""}
                    onChange={(e) => {
                      setCtGeo((p) => ({ ...p, [key]: e.target.value }));
                      setEditorDirty(true);
                    }}
                  />
                </label>
              ))}
            </div>
            <h3 className="setup-sub">CT inputs (worst case per day)</h3>
            <div className="setup-roles">
              {(state?.ct_roles || []).map((cr) => (
                <label key={cr.role} className="cfg-label">
                  {cr.label}{" "}
                  <small className="setup-which">daily {cr.which}</small>
                  <select
                    className="cfg-input"
                    value={ctInputs[cr.role] || ""}
                    onChange={(e) => {
                      setCtInputs((p) => ({ ...p, [cr.role]: e.target.value }));
                      setEditorDirty(true);
                    }}
                  >
                    <option value="">— not used —</option>
                    {trendIncluded.map((r) => (
                      <option key={r.historian} value={r.historian}>
                        {r.tag} — {r.description}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </>
        )}
      </section>

    </div>
  );
}
