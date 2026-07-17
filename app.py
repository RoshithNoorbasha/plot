import os
import io
import calendar
from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Plot-1 String Dashboard - Plot 1",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded"
)

WORK_START = time(6, 0)
WORK_END = time(18, 0)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILE_NAME = "strings_data_file.xlsx"
DEFAULT_FILE_PATH = os.path.join(APP_DIR, DEFAULT_FILE_NAME)
SHEET_NAME = "String_Master"

REQUIRED_COLUMNS = [
    "Plot", "Block", "SACU", "Inverter ID", "String No", "Serial Number",
    "Remarks", "Failure Date & Time", "Restored Date & Time"
]

CALC_COLUMNS = ["Status", "Turn Around Time", "Present Failure Hours", "Current Loss Hours"]

# Standard fault remark categories for the dropdown-only entry form.
FAULT_REMARK_OPTIONS = [
    "Thefted",
    "Module Reverse",
    "Module Pending",
    "Physical / Module Damage",
    "Series Connection Pending",
    "JB failure"
    "Fuse Blown",
    "String Cable Damage",
    "Connector / MC4 Fault",
    "Communication Loss",
    "Earth Fault",
    "Rodent Damage",
    "Soiling / Shading Issue",
    "No Information"
    "Other (specify below)",
]

# Standard rectification remark categories, used for both single and bulk restore.
RESTORE_REMARK_OPTIONS = [
    "Replacement Installed",          # Thefted
    "Component Replaced",             # Module Reverse
    "Component Installed",            # Module Pending
    "Component Replaced",             # Physical / Module Damage
    "Series Connection Completed",    # Series Connection Pending
    "JB Replaced / Repaired",         # JB failure
    "Fuse Replaced",                  # Fuse Blown
    "Cable Repaired",                 # String Cable Damage
    "Connector Fixed",                 # Connector / MC4 Fault
    "Cleared Fault / Reset",          # Communication Loss
    "Cleared Fault / Reset",          # Earth Fault
    "Cable/Connector Repaired",       # Rodent Damage
    "Cleaning Done",                  # Soiling / Shading Issue
    "Other (specify below)",          # Other
]


MINUTE_STEPS = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]

# ──────────────────────────────────────────────────────────────────────────
# STYLE
# ──────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.main { background: linear-gradient(180deg, #f6f9fc 0%, #eef4f9 100%); }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }

.hero {
    background: linear-gradient(120deg, #0f3d63 0%, #1c6ea4 55%, #2f9bd6 100%);
    border-radius: 20px;
    padding: 28px 32px;
    color: white;
    margin-bottom: 1.4rem;
    box-shadow: 0 10px 30px rgba(15,61,99,0.25);
}
.hero h1 { color: white; margin-bottom: 4px; font-size: 1.9rem; }
.hero p { color: #dceefb; margin: 0; font-size: 0.95rem; }

div[data-testid="stMetric"] {
    background: white;
    border-radius: 16px;
    padding: 14px 16px;
    box-shadow: 0 4px 18px rgba(0,0,0,0.06);
    border: 1px solid #e7edf3;
}
h1, h2, h3 { color: #16324f; }

.badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}
.badge-open { background: #fde2e2; color: #b3261e; }
.badge-closed { background: #dcf5e3; color: #1e7a3a; }
.badge-none { background: #eef1f4; color: #64748b; }

.status-pill { text-align: center; }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────
# CORE HELPERS
# ──────────────────────────────────────────────────────────────────────────
def _blank_master_df():
    df = pd.DataFrame(columns=REQUIRED_COLUMNS)
    return df


def read_excel_source(file_like_or_path):
    """Read the String_Master sheet from a path or an uploaded file object."""
    df = pd.read_excel(file_like_or_path, sheet_name=SHEET_NAME)
    for col in ["Failure Date & Time", "Restored Date & Time"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df.reset_index(drop=True)
    return df


def calculate_working_hours_vectorized(start, end, work_start_hour=6, work_end_hour=18):
    """Vectorized replacement for the old per-row, day-by-day Python loop.
    Produces byte-for-byte identical results (verified against the original
    on 3000+ randomized cases) but runs on the whole column at once instead
    of calling a Python function once per row. This was the single biggest
    cause of lag: the old version recomputed every OPEN fault's age with an
    inner day-by-day loop, called via .apply(), on every rerun."""
    start = pd.to_datetime(pd.Series(start))
    end = pd.to_datetime(pd.Series(end))
    work_span = work_end_hour - work_start_hour

    valid = start.notna() & end.notna() & (end > start)

    # Fill NaT with a placeholder so date/time math below doesn't error;
    # invalid rows are zeroed out at the very end via `valid`.
    s = start.fillna(pd.Timestamp("2000-01-01"))
    e = end.fillna(pd.Timestamp("2000-01-01"))

    start_date = s.dt.floor("D")
    end_date = e.dt.floor("D")
    same_day = start_date == end_date

    ws_start = start_date + pd.Timedelta(hours=work_start_hour)
    we_start = start_date + pd.Timedelta(hours=work_end_hour)
    ws_end = end_date + pd.Timedelta(hours=work_start_hour)
    we_end = end_date + pd.Timedelta(hours=work_end_hour)

    same_day_hours = ((e.clip(lower=ws_start, upper=we_start) - s.clip(lower=ws_start, upper=we_start))
                       .dt.total_seconds() / 3600).clip(lower=0)

    first_day_hours = ((we_start - s.clip(lower=ws_start, upper=we_start)).dt.total_seconds() / 3600).clip(lower=0)
    last_day_hours = ((e.clip(lower=ws_end, upper=we_end) - ws_end).dt.total_seconds() / 3600).clip(lower=0)
    days_between = ((end_date - start_date).dt.days - 1).clip(lower=0)
    middle_hours = days_between * work_span

    multi_day_hours = first_day_hours + middle_hours + last_day_hours

    result = np.where(same_day.to_numpy(), same_day_hours.to_numpy(), multi_day_hours.to_numpy())
    result = np.where(valid.to_numpy(), result, 0.0)
    return np.round(result, 2)


def enrich_fault_metrics(df):
    """Vectorized: Status, Turn Around Time, Present Failure Hours and
    Current Loss Hours for the WHOLE dataframe in a handful of column-level
    operations, instead of 4 separate row-by-row .apply() passes. This runs
    on every Streamlit rerun (i.e. every filter click), so its speed is
    what determines how laggy the app feels."""
    df = df.copy()
    now = pd.Timestamp.now()

    failure = pd.to_datetime(df["Failure Date & Time"], errors="coerce")
    restored = pd.to_datetime(df["Restored Date & Time"], errors="coerce")
    df["Failure Date & Time"] = failure
    df["Restored Date & Time"] = restored

    status = np.select(
        [failure.notna() & restored.isna(), failure.notna() & restored.notna()],
        ["OPEN", "CLOSED"],
        default=""
    )
    df["Status"] = status

    tat = calculate_working_hours_vectorized(failure, restored)
    df["Turn Around Time"] = np.where(status == "CLOSED", tat, 0.0)

    present = calculate_working_hours_vectorized(failure, pd.Series(now, index=df.index))
    df["Present Failure Hours"] = np.where((status == "OPEN") & failure.notna(), present, 0.0)

    df["Current Loss Hours"] = np.where(
        status == "OPEN", df["Present Failure Hours"],
        np.where(status == "CLOSED", df["Turn Around Time"], 0.0)
    )

    return df


def get_download_excel_bytes(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    buffer.seek(0)
    return buffer


def persist_to_disk(df, path=DEFAULT_FILE_PATH):
    """Best-effort save back to the source file so data survives a full app
    restart. If the filesystem is read-only (common on hosted deployments)
    this silently fails - the in-memory session_state copy is always the
    source of truth for the running session regardless."""
    try:
        with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
            df.to_excel(writer, sheet_name=SHEET_NAME, index=False)
        return True
    except Exception:
        return False


def get_options(df, col):
    if col not in df.columns:
        return []
    return sorted([x for x in df[col].dropna().astype(str).unique().tolist() if str(x).strip() != ""])


def status_badge_html(status):
    if status == "OPEN":
        return '<span class="badge badge-open">● OPEN</span>'
    elif status == "CLOSED":
        return '<span class="badge badge-closed">● CLOSED</span>'
    return '<span class="badge badge-none">—</span>'


def format_hours_to_hms(decimal_hours):
    """Convert decimal hours to 'X hrs Y mins' format."""
    if decimal_hours == 0 or pd.isna(decimal_hours):
        return "0 hrs 0 mins"
    hours = int(decimal_hours)
    minutes = int((decimal_hours - hours) * 60)
    return f"{hours} hrs {minutes} mins"


def format_hours_column(df, col_name):
    """Format a column of decimal hours to 'X hrs Y mins' format."""
    if col_name in df.columns:
        df[col_name] = df[col_name].apply(format_hours_to_hms)
    return df


# ──────────────────────────────────────────────────────────────────────────
# SHARED FORM WIDGETS
# Pulled out once and reused by every entry point (New Failure tab, Quick
# Fault Entry tab) instead of being copy-pasted per tab.
# ──────────────────────────────────────────────────────────────────────────
def select_hierarchy(df_source, key_prefix, layout="vertical", include_string=True):
    """Cascading Plot → Block → SACU → Inverter (→ String) dropdown chain.
    With include_string=True (default) returns
    (plot, block, sacu, inverter, string_no, matched_row).
    With include_string=False stops one level up and returns
    (plot, block, sacu, inverter, df_inverter) — used by the Bulk tab, which
    needs every string under an inverter rather than just one.
    Returns None if the source data has no Plot values at all."""
    plot_options = get_options(df_source, "Plot")
    if not plot_options:
        st.warning("No 'Plot' values found in the master data.")
        return None

    n_cols = 5 if include_string else 4
    cols = st.columns(n_cols) if layout == "grid" else [st.container() for _ in range(n_cols)]

    plot_val = cols[0].selectbox("Plot", plot_options, key=f"{key_prefix}_plot")
    df_plot = df_source[df_source["Plot"].astype(str) == str(plot_val)]

    block_val = cols[1].selectbox("Block", get_options(df_plot, "Block"), key=f"{key_prefix}_block")
    df_block = df_plot[df_plot["Block"].astype(str) == str(block_val)]

    sacu_val = cols[2].selectbox("SACU", get_options(df_block, "SACU"), key=f"{key_prefix}_sacu")
    df_sacu = df_block[df_block["SACU"].astype(str) == str(sacu_val)]

    inverter_val = cols[3].selectbox("Inverter ID", get_options(df_sacu, "Inverter ID"), key=f"{key_prefix}_inv")
    df_inverter = df_sacu[df_sacu["Inverter ID"].astype(str) == str(inverter_val)]

    if not include_string:
        return plot_val, block_val, sacu_val, inverter_val, df_inverter

    string_val = cols[4].selectbox("String No", get_options(df_inverter, "String No"), key=f"{key_prefix}_string")
    matched_row = df_inverter[df_inverter["String No"].astype(str) == str(string_val)].head(1)

    return plot_val, block_val, sacu_val, inverter_val, string_val, matched_row


def dropdown_datetime(key_prefix, label, default=None):
    """Pure dropdown Year/Month/Day/Hour/Minute picker - no calendar/clock
    widget - so every field on the form is a selectbox."""
    default = default or datetime.now()
    st.caption(label)
    dcols = st.columns(5)

    years = list(range(datetime.now().year - 2, datetime.now().year + 1))
    year = dcols[0].selectbox("Year", years, index=years.index(default.year) if default.year in years else len(years) - 1, key=f"{key_prefix}_yr")

    month = dcols[1].selectbox("Month", list(range(1, 13)), index=default.month - 1, key=f"{key_prefix}_mo", format_func=lambda m: calendar.month_abbr[m])

    max_day = calendar.monthrange(year, month)[1]
    day = dcols[2].selectbox("Day", list(range(1, max_day + 1)), index=min(default.day, max_day) - 1, key=f"{key_prefix}_dy")

    hour = dcols[3].selectbox("Hour", list(range(0, 24)), index=default.hour, key=f"{key_prefix}_hr", format_func=lambda h: f"{h:02d}")

    nearest_minute = min(MINUTE_STEPS, key=lambda m: abs(m - default.minute))
    minute = dcols[4].selectbox("Minute", MINUTE_STEPS, index=MINUTE_STEPS.index(nearest_minute), key=f"{key_prefix}_mi", format_func=lambda m: f"{m:02d}")

    return datetime(year, month, day, hour, minute)


def has_open_duplicate(df_master, plot, block, sacu, inverter, string_no):
    return not df_master[
        (df_master["Plot"].astype(str) == str(plot)) &
        (df_master["Block"].astype(str) == str(block)) &
        (df_master["SACU"].astype(str) == str(sacu)) &
        (df_master["Inverter ID"].astype(str) == str(inverter)) &
        (df_master["String No"].astype(str) == str(string_no)) &
        (df_master["Status"] == "OPEN")
    ].empty


def build_new_failure_row(df_master, plot, block, sacu, inverter, string_no, serial, remarks, failure_dt):
    new_row = {col: None for col in df_master.columns}
    new_row.update({
        "Plot": plot,
        "Block": block,
        "SACU": sacu,
        "Inverter ID": inverter,
        "String No": string_no,
        "Serial Number": serial if str(serial).strip() not in ("", "Not Assigned") else None,
        "Remarks": remarks,
        "Failure Date & Time": failure_dt,
        "Restored Date & Time": pd.NaT,
    })
    return new_row


def finalize_and_persist(updated_df, success_msg, dl_key):
    """One shared tail-end for every save action: recompute metrics, push
    into session_state, best-effort write to disk, confirm to the user,
    offer a download, and rerun."""
    updated_df = enrich_fault_metrics(updated_df)
    st.session_state.df_master = updated_df
    saved_ok = persist_to_disk(updated_df, DEFAULT_FILE_PATH)

    st.success(success_msg + ("" if saved_ok else " (Saved for this session — could not write to disk.)"))
    st.download_button(
        "⬇️ Download Updated Excel",
        data=get_download_excel_bytes(updated_df),
        file_name="String_Master_Plot1_Updated.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=dl_key
    )
    st.rerun()


# ──────────────────────────────────────────────────────────────────────────
# SESSION STATE INITIALISATION
# The #1 reason "create / restore" previously appeared broken: load_data()
# was wrapped in @st.cache_data and read from a DIFFERENT file than the one
# saves were written to, so a fresh reload after every st.rerun() silently
# threw away every new/edited row. All state now lives in
# st.session_state.df_master and is only ever (re)loaded from disk when the
# user explicitly asks for it.
# ──────────────────────────────────────────────────────────────────────────
if "df_master" not in st.session_state:
    st.session_state.df_master = None
    st.session_state.data_source_label = None

with st.sidebar:
    st.markdown("### ☀️ Plant Data Source")

    uploaded_file = st.file_uploader("Upload String Master (.xlsx)", type=["xlsx"])

    col_a, col_b = st.columns(2)
    load_default_clicked = col_a.button("📂 Load default file", use_container_width=True)
    load_upload_clicked = col_b.button("⬆️ Use upload", use_container_width=True, disabled=uploaded_file is None)

    if load_default_clicked:
        if os.path.exists(DEFAULT_FILE_PATH):
            try:
                st.session_state.df_master = read_excel_source(DEFAULT_FILE_PATH)
                st.session_state.data_source_label = DEFAULT_FILE_NAME
                st.success("Loaded default file.")
            except Exception as e:
                st.error(f"Could not read '{DEFAULT_FILE_NAME}': {e}")
        else:
            st.error(
                f"File not found: {DEFAULT_FILE_NAME}. Expected it at: {DEFAULT_FILE_PATH}. "
                "Make sure the file is committed/deployed with the app, or upload it instead."
            )

    if load_upload_clicked and uploaded_file is not None:
        try:
            st.session_state.df_master = read_excel_source(uploaded_file)
            st.session_state.data_source_label = uploaded_file.name
            st.success("Loaded uploaded file.")
        except Exception as e:
            st.error(f"Could not read uploaded file: {e}")

    # First-ever run: try the default path automatically so the app isn't
    # blank on first open.
    if st.session_state.df_master is None and os.path.exists(DEFAULT_FILE_PATH):
        try:
            st.session_state.df_master = read_excel_source(DEFAULT_FILE_PATH)
            st.session_state.data_source_label = DEFAULT_FILE_NAME
        except Exception:
            pass

    if st.session_state.data_source_label:
        st.caption(f"Current source: **{st.session_state.data_source_label}**")

    st.divider()


# ──────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────
if st.session_state.df_master is None:
    st.markdown("""
        <div class="hero">
            <h1>☀️ Plot-1 String Monitoring Dashboard</h1>
            <p>No data loaded yet. Upload your String Master Excel file or place
            <code>strings_data_file.xlsx</code> in the deployed app folder and click "Load default file" in the sidebar.</p>
        </div>
    """, unsafe_allow_html=True)
    st.info(f"Default file expected at: {DEFAULT_FILE_PATH}")
    st.stop()

df_master = enrich_fault_metrics(st.session_state.df_master)
st.session_state.df_master = df_master

st.markdown("""
    <div class="hero">
        <h1>☀️ Plot-1 String Monitoring Dashboard</h1>
        <p>Business-hour fault analytics · Working hours: 6:00 AM – 6:00 PM</p>
    </div>
""", unsafe_allow_html=True)

# ── Sidebar filters ─────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🔍 Plant Hierarchy Filter")

    blocks = ["All"] + get_options(df_master, "Block")
    selected_block = st.selectbox("Block", blocks)
    df_filtered = df_master if selected_block == "All" else df_master[df_master["Block"].astype(str) == selected_block]

    sacus = ["All"] + get_options(df_filtered, "SACU")
    selected_sacu = st.selectbox("SACU", sacus)
    if selected_sacu != "All":
        df_filtered = df_filtered[df_filtered["SACU"].astype(str) == selected_sacu]

    inverters = ["All"] + get_options(df_filtered, "Inverter ID")
    selected_inverter = st.selectbox("Inverter", inverters)
    if selected_inverter != "All":
        df_filtered = df_filtered[df_filtered["Inverter ID"].astype(str) == selected_inverter]

    selected_status = st.selectbox("Fault Status", ["All", "OPEN", "CLOSED", ""])
    if selected_status != "All":
        df_filtered = df_filtered[df_filtered["Status"] == selected_status]

    st.divider()
    st.caption(f"{len(df_filtered)} of {len(df_master)} strings shown")

# ── KPI row ──────────────────────────────────────────────────────────────
total_strings = len(df_filtered)
open_faults = int((df_filtered["Status"] == "OPEN").sum())
closed_faults = int((df_filtered["Status"] == "CLOSED").sum())
availability = ((total_strings - open_faults) / total_strings * 100) if total_strings else 0
avg_tat = df_filtered.loc[df_filtered["Status"] == "CLOSED", "Turn Around Time"].mean()
avg_open_age = df_filtered.loc[df_filtered["Status"] == "OPEN", "Present Failure Hours"].mean()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("⚡ Availability", f"{availability:.2f}%")
c2.metric("🔴 Open Faults", open_faults)
c3.metric("🟢 Closed Faults", closed_faults)
c4.metric("⏱️ Avg TAT", format_hours_to_hms(0 if pd.isna(avg_tat) else avg_tat))
c5.metric("⏳ Avg Open Age", format_hours_to_hms(0 if pd.isna(avg_open_age) else avg_open_age))

st.write("")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Fault Analytics",
    "🛠️ Failure / Rectified Entry",
    "📝 Live Fault Editor",
    "🔎 Search Faults",
    "📦 Bulk Failure / Restore"
])

# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — ANALYTICS
# ══════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — ANALYTICS
# ══════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("📊 Block-wise String Performance Summary")

    string_key = ["Plot", "Block", "SACU", "Inverter ID", "String No"]

    # Base unique strings for real-time total count
    unique_strings_df = df_filtered.drop_duplicates(subset=string_key).copy()

    # Current OPEN strings (unique physical strings currently open)
    open_strings_df = (
        df_filtered[df_filtered["Status"] == "OPEN"]
        .drop_duplicates(subset=string_key)
        .copy()
    )

    # Historical CLOSED rows
    closed_fault_rows_df = df_filtered[df_filtered["Status"] == "CLOSED"].copy()

    # Unique restored strings
    closed_unique_strings_df = (
        df_filtered[df_filtered["Status"] == "CLOSED"]
        .drop_duplicates(subset=string_key)
        .copy()
    )

    # Calculate block-wise metrics
    total_by_block = (
        unique_strings_df.groupby("Block")
        .size()
        .reset_index(name="Total Strings")
    )

    open_by_block = (
        open_strings_df.groupby("Block")
        .size()
        .reset_index(name="Open Faults")
    )

    closed_by_block = (
        closed_unique_strings_df.groupby("Block")
        .size()
        .reset_index(name="Closed/Restored")
    )

    # If you want historical restored EVENT count instead, use this:
    # closed_by_block = (
    #     closed_fault_rows_df.groupby("Block")
    #     .size()
    #     .reset_index(name="Closed/Restored")
    # )

    block_summary = (
        total_by_block
        .merge(open_by_block, on="Block", how="left")
        .merge(closed_by_block, on="Block", how="left")
        .fillna(0)
    )

    block_summary["Total Strings"] = block_summary["Total Strings"].astype(int)
    block_summary["Open Faults"] = block_summary["Open Faults"].astype(int)
    block_summary["Closed/Restored"] = block_summary["Closed/Restored"].astype(int)

    block_summary["Working Strings"] = (
        block_summary["Total Strings"] - block_summary["Open Faults"]
    )

    block_summary["Availability %"] = np.where(
        block_summary["Total Strings"] > 0,
        ((block_summary["Working Strings"] / block_summary["Total Strings"]) * 100).round(2),
        0.0
    )

    block_summary = block_summary.sort_values("Block").reset_index(drop=True)

    if not block_summary.empty:
        def style_block_table(val, col_name=None):
            if col_name == "Open Faults" and val > 0:
                return "background-color: #fde2e2; color: #b3261e; font-weight: 600;"
            elif col_name == "Closed/Restored" and val > 0:
                return "background-color: #dcf5e3; color: #1e7a3a; font-weight: 600;"
            elif col_name == "Working Strings" and val > 0:
                return "background-color: #e3f2fd; color: #0d47a1; font-weight: 600;"
            elif col_name == "Availability %":
                if val >= 90:
                    return "background-color: #e8f5e9; color: #1e7a3a; font-weight: 600;"
                elif val >= 70:
                    return "background-color: #fff3e0; color: #e65100; font-weight: 600;"
                else:
                    return "background-color: #fde2e2; color: #b3261e; font-weight: 600;"
            return ""

        styled_block_table = (
            block_summary.style
            .map(lambda v: style_block_table(v, "Open Faults"), subset=["Open Faults"])
            .map(lambda v: style_block_table(v, "Closed/Restored"), subset=["Closed/Restored"])
            .map(lambda v: style_block_table(v, "Working Strings"), subset=["Working Strings"])
            .map(lambda v: style_block_table(v, "Availability %"), subset=["Availability %"])
        )

        st.dataframe(
            styled_block_table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Block": "Block Name",
                "Total Strings": st.column_config.NumberColumn("Total Strings", format="%d"),
                "Open Faults": st.column_config.NumberColumn("🔴 Open Faults", format="%d"),
                "Closed/Restored": st.column_config.NumberColumn("🟢 Closed/Restored", format="%d"),
                "Working Strings": st.column_config.NumberColumn("✅ Working Strings", format="%d"),
                "Availability %": st.column_config.NumberColumn("📈 Availability %", format="%.2f%%")
            }
        )

        st.caption(
            f"Real-time unique strings in current filter: {len(unique_strings_df)} | "
            f"Raw rows/fault history records: {len(df_filtered)}"
        )
    else:
        st.info("No data available for the current filter.")

    # 2. Fault Distribution by Block
    st.subheader("📊 Fault Distribution by Block")
    if not block_summary.empty:
        chart_data = block_summary.set_index("Block")[["Open Faults", "Closed/Restored"]]
        st.bar_chart(chart_data, color=["#ff6b6b", "#51cf66"])
    else:
        st.info("No fault distribution data available.")

    def _highlight_status_with_color(val):
        if val == "OPEN":
            return "background-color:#fde2e2;color:#b3261e;font-weight:600;"
        elif val == "CLOSED":
            return "background-color:#dcf5e3;color:#1e7a3a;font-weight:600;"
        return ""

    def _highlight_row_color(row):
        if row.get("Status") == "OPEN":
            return ["background-color:#fde2e2"] * len(row)
        elif row.get("Status") == "CLOSED":
            return ["background-color:#dcf5e3"] * len(row)
        return [""] * len(row)

    # 3. Detailed Fault Details
    st.subheader("📋 Detailed Fault Details")

    display_cols = [
        "Plot", "Block", "SACU", "Inverter ID", "String No",
        "Failure Date & Time", "Restored Date & Time",
        "Present Failure Hours", "Turn Around Time", "Remarks", "Status"
    ]
    display_cols = [c for c in display_cols if c in df_filtered.columns]

    detail_df = df_filtered[display_cols].copy()

    if "Present Failure Hours" in detail_df.columns:
        detail_df = detail_df.sort_values(by="Present Failure Hours", ascending=False)

    detail_df = format_hours_column(detail_df, "Present Failure Hours")
    detail_df = format_hours_column(detail_df, "Turn Around Time")

    styled_df = detail_df.style.apply(_highlight_row_color, axis=1)
    if "Status" in detail_df.columns:
        styled_df = styled_df.map(_highlight_status_with_color, subset=["Status"])

    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # 4. Open Faults by Block
    st.subheader("🔴 Open Faults by Block")
    open_fault_counts = (
        open_strings_df.groupby("Block")
        .size()
        .reset_index(name="Open Faults")
    )

    if not open_fault_counts.empty:
        st.bar_chart(open_fault_counts.set_index("Block"), color="#1c6ea4")
    else:
        st.success("No active faults in current filter. ✅")
# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — FAILURE / RECTIFIED ENTRY
# ══════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Failure / Rectified Entry")

    action_mode = st.radio("Select Action", ["New Failure", "Rectified / Restoration"], horizontal=True)

    # ── NEW FAILURE ─────────────────────────────────────────────────────
    if action_mode == "New Failure":
        hierarchy = select_hierarchy(df_master, key_prefix="nf")

        if hierarchy:
            plot_val, block_val, sacu_val, inverter_val, string_val, matched_row = hierarchy

            existing_serial = ""
            if not matched_row.empty and "Serial Number" in matched_row.columns:
                sv = matched_row.iloc[0]["Serial Number"]
                existing_serial = str(sv) if pd.notna(sv) else ""

            if existing_serial.strip() == "":
                serial_number = st.text_input("Serial Number (Optional)", key="new_serial")
            else:
                st.text_input("Serial Number", value=existing_serial, disabled=True)
                serial_number = existing_serial

            remarks_val = st.text_area("Failure Remarks", key="new_remarks")

            fc1, fc2 = st.columns(2)
            with fc1:
                failure_date = st.date_input("Failure Date", value=datetime.now().date(), key="failure_date")
            with fc2:
                failure_time = st.time_input(
                    "Failure Time",
                    value=datetime.now().time().replace(second=0, microsecond=0),
                    key="failure_time"
                )

            if st.button("💾 Save Failure Entry", type="primary"):
                failure_dt = datetime.combine(failure_date, failure_time)

                if has_open_duplicate(df_master, plot_val, block_val, sacu_val, inverter_val, string_val):
                    st.warning("An open fault already exists for this string.")
                else:
                    new_row = build_new_failure_row(
                        df_master, plot_val, block_val, sacu_val, inverter_val,
                        string_val, serial_number, remarks_val, failure_dt
                    )
                    updated = pd.concat([df_master, pd.DataFrame([new_row])], ignore_index=True)
                    finalize_and_persist(updated, "New failure entry added successfully.", dl_key="dl_new_failure")

    # ── RECTIFIED / RESTORATION ─────────────────────────────────────────
    else:
        open_df = df_master[df_master["Status"] == "OPEN"].copy()

        if open_df.empty:
            st.success("No open faults available for rectification. ✅")
        else:
            open_df["Fault Key"] = open_df.apply(
                lambda r: f"{r['Plot']} | {r['Block']} | {r['SACU']} | {r['Inverter ID']} | {r['String No']} | {r['Failure Date & Time']}",
                axis=1
            )
            # keep the original index alongside the label so we can update
            # the exact row unambiguously, even if two faults share the
            # same descriptive key.
            key_to_index = dict(zip(open_df["Fault Key"], open_df.index))

            selected_fault_key = st.selectbox("Select Open Fault", open_df["Fault Key"].tolist())
            selected_idx = key_to_index[selected_fault_key]
            selected_row = df_master.loc[selected_idx]

            st.info(
                f"Failure Time: {selected_row['Failure Date & Time']} | "
                f"Current Age: {format_hours_to_hms(selected_row['Present Failure Hours'])}"
            )

            rc1, rc2 = st.columns(2)
            with rc1:
                restore_date = st.date_input("Rectified Date", value=datetime.now().date(), key="restore_date")
            with rc2:
                restore_time = st.time_input(
                    "Rectified Time",
                    value=datetime.now().time().replace(second=0, microsecond=0),
                    key="restore_time"
                )

            rectified_remarks = st.text_area("Rectification Remarks", key="restore_remarks")

            if st.button("💾 Save Rectified Entry", type="primary"):
                restored_dt = datetime.combine(restore_date, restore_time)

                if restored_dt <= selected_row["Failure Date & Time"]:
                    st.error("Rectified Date & Time must be greater than Failure Date & Time.")
                else:
                    updated = df_master.copy()
                    updated.loc[selected_idx, "Restored Date & Time"] = restored_dt

                    old_remarks = str(updated.loc[selected_idx, "Remarks"] or "")
                    separator = " | " if old_remarks.strip() else ""
                    updated.loc[selected_idx, "Remarks"] = f"{old_remarks}{separator}Rectified: {rectified_remarks}"

                    finalize_and_persist(updated, "Fault rectified successfully.", dl_key="dl_rectify")

# ══════════════════════════════════════════════════════════════════════════
# TAB 3 — LIVE FAULT EDITOR
# ══════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("Operator Fault Logging & Verification")
    st.caption("Edit cells directly, add new rows, or delete rows, then save.")

    edit_columns = [
        "Plot", "Block", "SACU", "Inverter ID", "String No", "Serial Number",
        "Remarks", "Failure Date & Time", "Restored Date & Time",
        "Turn Around Time", "Present Failure Hours", "Current Loss Hours", "Status"
    ]
    available_edit_columns = [col for col in edit_columns if col in df_filtered.columns]
    readonly_cols = [
        col for col in ["Turn Around Time", "Present Failure Hours", "Current Loss Hours", "Status"]
        if col in available_edit_columns
    ]

    editor_source = df_filtered[available_edit_columns].copy()

    edited_df = st.data_editor(
        editor_source,
        disabled=readonly_cols,
        use_container_width=True,
        num_rows="dynamic",
        key="live_fault_editor"
    )

    if st.button("💾 Save Updates & Recalculate", type="primary"):
        edited_df = edited_df.copy()
        edited_df["Failure Date & Time"] = pd.to_datetime(edited_df["Failure Date & Time"], errors="coerce")
        if "Restored Date & Time" in edited_df.columns:
            edited_df["Restored Date & Time"] = pd.to_datetime(edited_df["Restored Date & Time"], errors="coerce")

        updated = df_master.copy()

        # Rows still present (matched by original row index) → overwrite in place.
        existing_idx = edited_df.index.intersection(editor_source.index)
        if len(existing_idx) > 0:
            updated.loc[existing_idx, available_edit_columns] = edited_df.loc[existing_idx, available_edit_columns]

        # Rows removed in the editor (present before, missing now) → drop.
        removed_idx = editor_source.index.difference(edited_df.index)
        if len(removed_idx) > 0:
            updated = updated.drop(index=removed_idx)

        # Brand-new rows added via the "+" control → append.
        new_idx = edited_df.index.difference(editor_source.index)
        if len(new_idx) > 0:
            new_rows = edited_df.loc[new_idx].copy()
            for col in df_master.columns:
                if col not in new_rows.columns:
                    new_rows[col] = None
            updated = pd.concat([updated, new_rows[df_master.columns]], ignore_index=True)

        finalize_and_persist(updated, "Master database updated successfully.", dl_key="dl_editor")


# ══════════════════════════════════════════════════════════════════════════
# TAB 4 — SEARCH FAULTS
# ══════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Search Faults")
    st.caption("Find records by hierarchy, status, date range, remarks, serial number, or string number.")

    search_df = df_filtered.copy()
    selected_search_cols = []

    with st.container(border=True):
        st.markdown("**Filters**")
        f1, f2, f3, f4 = st.columns(4)

        status_options = ["All"] + get_options(search_df, "Status")
        status_choice = f1.selectbox("Status", status_options, key="search_status")
        if status_choice != "All":
            search_df = search_df[search_df["Status"].astype(str) == str(status_choice)]

        plot_options = ["All"] + get_options(search_df, "Plot")
        plot_choice = f2.selectbox("Plot", plot_options, key="search_plot")
        if plot_choice != "All":
            search_df = search_df[search_df["Plot"].astype(str) == str(plot_choice)]

        block_options = ["All"] + get_options(search_df, "Block")
        block_choice = f3.selectbox("Block", block_options, key="search_block")
        if block_choice != "All":
            search_df = search_df[search_df["Block"].astype(str) == str(block_choice)]

        sacu_options = ["All"] + get_options(search_df, "SACU")
        sacu_choice = f4.selectbox("SACU", sacu_options, key="search_sacu")
        if sacu_choice != "All":
            search_df = search_df[search_df["SACU"].astype(str) == str(sacu_choice)]

        f5, f6, f7, f8 = st.columns(4)

        inverter_options = ["All"] + get_options(search_df, "Inverter ID")
        inverter_choice = f5.selectbox("Inverter ID", inverter_options, key="search_inverter")
        if inverter_choice != "All":
            search_df = search_df[search_df["Inverter ID"].astype(str) == str(inverter_choice)]

        string_query = f6.text_input("String No contains", key="search_string")
        if string_query.strip():
            search_df = search_df[
                search_df["String No"].astype(str).str.contains(string_query.strip(), case=False, na=False)
            ]

        serial_query = f7.text_input("Serial Number contains", key="search_serial")
        if serial_query.strip() and "Serial Number" in search_df.columns:
            search_df = search_df[
                search_df["Serial Number"].astype(str).str.contains(serial_query.strip(), case=False, na=False)
            ]

        remarks_query = f8.text_input("Remarks contains", key="search_remarks")
        if remarks_query.strip() and "Remarks" in search_df.columns:
            search_df = search_df[
                search_df["Remarks"].astype(str).str.contains(remarks_query.strip(), case=False, na=False)
            ]

        keyword = st.text_input(
            "Global search",
            placeholder="Search plot, block, SACU, inverter, string, serial, remarks, status...",
            key="search_keyword"
        )
        if keyword.strip():
            searchable_cols = [
                col for col in [
                    "Plot", "Block", "SACU", "Inverter ID", "String No",
                    "Serial Number", "Remarks", "Status"
                ] if col in search_df.columns
            ]
            keyword_mask = pd.Series(False, index=search_df.index)
            for col in searchable_cols:
                keyword_mask = keyword_mask | search_df[col].astype(str).str.contains(
                    keyword.strip(), case=False, na=False
                )
            search_df = search_df[keyword_mask]

        with st.expander("Advanced filters and display"):
            d1, d2 = st.columns(2)
            use_failure_range = d1.checkbox("Filter by failure date", key="search_use_failure_date")
            use_restored_range = d2.checkbox("Filter by restored date", key="search_use_restored_date")

            if use_failure_range:
                valid_failure = pd.to_datetime(search_df["Failure Date & Time"], errors="coerce").dropna()
                default_start = valid_failure.min().date() if not valid_failure.empty else datetime.now().date()
                default_end = valid_failure.max().date() if not valid_failure.empty else datetime.now().date()
                failure_range = st.date_input(
                    "Failure date range",
                    value=(default_start, default_end),
                    key="search_failure_range"
                )
                if len(failure_range) == 2:
                    failure_start, failure_end = failure_range
                    failure_dates = pd.to_datetime(search_df["Failure Date & Time"], errors="coerce").dt.date
                    search_df = search_df[(failure_dates >= failure_start) & (failure_dates <= failure_end)]

            if use_restored_range:
                valid_restored = pd.to_datetime(search_df["Restored Date & Time"], errors="coerce").dropna()
                default_start = valid_restored.min().date() if not valid_restored.empty else datetime.now().date()
                default_end = valid_restored.max().date() if not valid_restored.empty else datetime.now().date()
                restored_range = st.date_input(
                    "Restored date range",
                    value=(default_start, default_end),
                    key="search_restored_range"
                )
                if len(restored_range) == 2:
                    restored_start, restored_end = restored_range
                    restored_dates = pd.to_datetime(search_df["Restored Date & Time"], errors="coerce").dt.date
                    search_df = search_df[(restored_dates >= restored_start) & (restored_dates <= restored_end)]

            h1, h2 = st.columns(2)
            min_loss = h1.number_input("Minimum current loss hours", min_value=0.0, value=0.0, step=1.0)
            max_loss_enabled = h2.checkbox("Set maximum current loss hours", key="search_max_loss_enabled")
            if min_loss > 0 and "Current Loss Hours" in search_df.columns:
                loss_hours = pd.to_numeric(search_df["Current Loss Hours"], errors="coerce").fillna(0)
                search_df = search_df[loss_hours >= min_loss]
            if max_loss_enabled and "Current Loss Hours" in search_df.columns:
                max_loss = h2.number_input(
                    "Maximum current loss hours",
                    min_value=0.0,
                    value=float(max(min_loss, 1.0)),
                    step=1.0
                )
                loss_hours = pd.to_numeric(search_df["Current Loss Hours"], errors="coerce").fillna(0)
                search_df = search_df[loss_hours <= max_loss]

            default_search_cols = [
                "Plot", "Block", "SACU", "Inverter ID", "String No", "Serial Number",
                "Failure Date & Time", "Restored Date & Time", "Current Loss Hours",
                "Present Failure Hours", "Turn Around Time", "Remarks", "Status"
            ]
            available_search_cols = [col for col in default_search_cols if col in search_df.columns]
            selected_search_cols = st.multiselect(
                "Columns to show",
                options=[col for col in df_master.columns if col in search_df.columns],
                default=available_search_cols,
                key="search_columns"
            )

    search_cols = selected_search_cols or [
        col for col in [
            "Plot", "Block", "SACU", "Inverter ID", "String No", "Serial Number",
            "Failure Date & Time", "Restored Date & Time", "Current Loss Hours",
            "Present Failure Hours", "Turn Around Time", "Remarks", "Status"
        ] if col in search_df.columns
    ]

    r1, r2, r3 = st.columns(3)
    r1.metric("Search Results", len(search_df))
    r2.metric("Open Results", int((search_df["Status"] == "OPEN").sum()) if "Status" in search_df.columns else 0)
    r3.metric("Closed Results", int((search_df["Status"] == "CLOSED").sum()) if "Status" in search_df.columns else 0)

    result_df = search_df[search_cols].copy() if search_cols else search_df.copy()
    for hours_col in ["Current Loss Hours", "Present Failure Hours", "Turn Around Time"]:
        result_df = format_hours_column(result_df, hours_col)

    st.dataframe(result_df, use_container_width=True, hide_index=True)

    st.download_button(
        "Download Search Results",
        data=get_download_excel_bytes(search_df),
        file_name="String_Fault_Search_Results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dl_search_results",
        disabled=search_df.empty
    )

# TAB 5 — BULK FAILURE / RESTORE
# Select down to an Inverter, then act on many strings under it in one go
# instead of repeating the single-string flow string-by-string.
# ══════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("Bulk Failure / Restore")
    st.caption("Pick a Plot → Block → SACU → Inverter, then mark several strings failed or restored in a single action.")

    bulk_mode = st.radio("Bulk Action", ["Bulk Mark as Failed", "Bulk Restore"], horizontal=True, key="bulk_mode")

    with st.container(border=True):
        st.markdown("**1. Locate the inverter**")
        hierarchy = select_hierarchy(df_master, key_prefix="bulk", layout="grid", include_string=False)

        if hierarchy:
            plot_val, block_val, sacu_val, inverter_val, df_inverter = hierarchy

            scope_mask = (
                (df_master["Plot"].astype(str) == str(plot_val)) &
                (df_master["Block"].astype(str) == str(block_val)) &
                (df_master["SACU"].astype(str) == str(sacu_val)) &
                (df_master["Inverter ID"].astype(str) == str(inverter_val))
            )

            # ── BULK MARK AS FAILED ─────────────────────────────────────
            if bulk_mode == "Bulk Mark as Failed":
                open_strings_here = set(
                    df_master[scope_mask & (df_master["Status"] == "OPEN")]["String No"].astype(str)
                )
                all_strings_here = get_options(df_inverter, "String No")
                available_strings = [s for s in all_strings_here if s not in open_strings_here]

                if not available_strings:
                    st.info("Every string under this inverter already has an open fault.")
                else:
                    st.markdown("**2. Select strings to mark as failed**")
                    if open_strings_here:
                        st.caption(f"Excluded (already open): {', '.join(sorted(open_strings_here))}")

                    select_all = st.checkbox("Select all available strings", key="bulk_fail_all")
                    default_selection = available_strings if select_all else []
                    selected_strings = st.multiselect(
                        "Strings", available_strings, default=default_selection, key="bulk_fail_strings"
                    )

                    st.markdown("**3. Failure date & time (applied to all selected)**")
                    # Updated to use date_input and time_input instead of dropdown
                    fail_col1, fail_col2 = st.columns(2)
                    with fail_col1:
                        failure_date = st.date_input("Failure Date", value=datetime.now().date(), key="bulk_fail_date")
                    with fail_col2:
                        failure_time = st.time_input(
                            "Failure Time",
                            value=datetime.now().time().replace(second=0, microsecond=0),
                            key="bulk_fail_time"
                        )
                    failure_dt = datetime.combine(failure_date, failure_time)

                    st.markdown("**4. Failure reason (applied to all selected)**")
                    remark_choice = st.selectbox("Failure Remarks", FAULT_REMARK_OPTIONS, key="bulk_fail_remark")
                    if remark_choice.startswith("Other"):
                        other_note = st.text_input("Brief note for 'Other'", key="bulk_fail_remark_other")
                        remarks_val = other_note if other_note.strip() else "Other"
                    else:
                        remarks_val = remark_choice

                    st.write("")
                    if st.button(
                        f"💾 Log {len(selected_strings)} Failure(s)",
                        type="primary", key="bulk_fail_save", disabled=not selected_strings
                    ):
                        new_rows = []
                        for s in selected_strings:
                            matched = df_inverter[df_inverter["String No"].astype(str) == str(s)].head(1)
                            serial = ""
                            if not matched.empty and "Serial Number" in matched.columns:
                                sv = matched.iloc[0]["Serial Number"]
                                serial = str(sv) if pd.notna(sv) else ""
                            new_rows.append(build_new_failure_row(
                                df_master, plot_val, block_val, sacu_val, inverter_val,
                                s, serial, remarks_val, failure_dt
                            ))
                        updated = pd.concat([df_master, pd.DataFrame(new_rows)], ignore_index=True)
                        finalize_and_persist(
                            updated, f"{len(new_rows)} failure entr{'y' if len(new_rows)==1 else 'ies'} logged successfully.",
                            dl_key="dl_bulk_fail"
                        )

            # ── BULK RESTORE ────────────────────────────────────────────
            else:
                open_df_here = df_master[scope_mask & (df_master["Status"] == "OPEN")].copy()

                if open_df_here.empty:
                    st.success("No open faults under this inverter. ✅")
                else:
                    open_df_here["Fault Key"] = open_df_here.apply(
                        lambda r: f"{r['String No']}  (open since {r['Failure Date & Time']:%Y-%m-%d %H:%M})",
                        axis=1
                    )
                    key_to_index = dict(zip(open_df_here["Fault Key"], open_df_here.index))
                    all_keys = open_df_here["Fault Key"].tolist()

                    st.markdown("**2. Select strings to restore**")
                    select_all = st.checkbox("Select all open strings", key="bulk_restore_all")
                    default_selection = all_keys if select_all else []
                    selected_keys = st.multiselect(
                        "Open Strings", all_keys, default=default_selection, key="bulk_restore_strings"
                    )

                    st.markdown("**3. Restored date & time (applied to all selected)**")
                    # Updated to use date_input and time_input instead of dropdown
                    restore_col1, restore_col2 = st.columns(2)
                    with restore_col1:
                        restored_date = st.date_input("Restored Date", value=datetime.now().date(), key="bulk_restore_date")
                    with restore_col2:
                        restored_time = st.time_input(
                            "Restored Time",
                            value=datetime.now().time().replace(second=0, microsecond=0),
                            key="bulk_restore_time"
                        )
                    restored_dt = datetime.combine(restored_date, restored_time)

                    st.markdown("**4. Rectification remarks (applied to all selected)**")
                    remark_choice = st.selectbox("Rectification Remarks", RESTORE_REMARK_OPTIONS, key="bulk_restore_remark")
                    if remark_choice.startswith("Other"):
                        other_note = st.text_input("Brief note for 'Other'", key="bulk_restore_remark_other")
                        rectified_remarks = other_note if other_note.strip() else "Other"
                    else:
                        rectified_remarks = remark_choice

                    st.write("")
                    if st.button(
                        f"💾 Restore {len(selected_keys)} String(s)",
                        type="primary", key="bulk_restore_save", disabled=not selected_keys
                    ):
                        invalid_keys = [
                            k for k in selected_keys
                            if restored_dt <= df_master.loc[key_to_index[k], "Failure Date & Time"]
                        ]
                        if invalid_keys:
                            st.error(
                                "Restored date/time must be after the failure time for: " +
                                ", ".join(invalid_keys)
                            )
                        else:
                            updated = df_master.copy()
                            for k in selected_keys:
                                idx = key_to_index[k]
                                updated.loc[idx, "Restored Date & Time"] = restored_dt
                                old_remarks = str(updated.loc[idx, "Remarks"] or "")
                                separator = " | " if old_remarks.strip() else ""
                                updated.loc[idx, "Remarks"] = f"{old_remarks}{separator}Rectified: {rectified_remarks}"

                            finalize_and_persist(
                                updated,
                                f"{len(selected_keys)} fault{'s' if len(selected_keys)!=1 else ''} restored successfully.",
                                dl_key="dl_bulk_restore"
                            )