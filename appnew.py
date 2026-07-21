import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import plotly.express as px

st.set_page_config(page_title="SCADA Realtime Dashboard", layout="wide")

# =========================================================
# CONFIG
# =========================================================
PV_VOLTAGE_COLS = [f"PV{i}" for i in range(1, 29)]
PV_CURRENT_COLS = [f"PV-I{i}" for i in range(1, 29)]
ACTUAL_STRINGS_PER_INVERTER = 19
STRING_WORKING_THRESHOLD = 0.5

DEFAULT_EXPECTED_COLUMNS = [
    "String Inverter",
    "MBUS",
    "Grid",
    "E-Daily(KWH)",
    "Active Power",
    "Reactive Power",
] + PV_VOLTAGE_COLS + PV_CURRENT_COLS + [
    "VAB", "VBC", "VCA", "IA", "IB", "IC"
]

# =========================================================
# NORMALIZATION HELPERS
# =========================================================
def normalize_text(val):
    if pd.isna(val):
        return ""
    val = str(val)
    val = val.replace("\xa0", " ")
    val = val.replace("\n", " ")
    val = val.replace("\r", " ")
    val = re.sub(r"\s+", " ", val).strip()
    return val


def canonicalize(text):
    text = normalize_text(text).lower()
    text = text.replace("(", "").replace(")", "")
    text = text.replace("-", "")
    text = text.replace("_", "")
    text = text.replace(" ", "")
    text = text.replace(".", "")

    synonyms = {
        "stringinverter": "stringinverter",
        "inverterid": "stringinverter",
        "inverter": "stringinverter",
        "devicename": "stringinverter",
        "id": "stringinverter",
        "mbus": "mbus",
        "grid": "grid",
        "edailykwh": "edailykwh",
        "edaily": "edailykwh",
        "activepower": "activepower",
        "reactivepower": "reactivepower",
        "reactive power": "reactivepower",
        "vab": "vab",
        "vbc": "vbc",
        "vca": "vca",
        "ia": "ia",
        "ib": "ib",
        "ic": "ic",
    }

    if text in synonyms:
        return synonyms[text]

    m1 = re.fullmatch(r"pv(\d+)", text)
    if m1:
        return f"pv{int(m1.group(1))}"

    m2 = re.fullmatch(r"pvi(\d+)", text)
    if m2:
        return f"pvi{int(m2.group(1))}"

    return text


def expected_schema_map():
    return {canonicalize(col): col for col in DEFAULT_EXPECTED_COLUMNS}


# =========================================================
# HEADER DETECTION
# =========================================================
def find_header_row_index(file_stream, sheet_name, max_rows_to_check=100, min_matches=6):
    schema = expected_schema_map()
    expected_keys = set(schema.keys())

    file_stream.seek(0)
    sample_df = pd.read_excel(
        file_stream,
        sheet_name=sheet_name,
        header=None,
        nrows=max_rows_to_check,
        engine="openpyxl"
    )

    best_index = None
    best_score = -1

    for i, row in sample_df.iterrows():
        row_values = [normalize_text(v) for v in row.tolist()]
        row_keys = [canonicalize(v) for v in row_values if normalize_text(v) != ""]

        score = sum(1 for key in row_keys if key in expected_keys)

        if "stringinverter" in row_keys:
            score += 3
        if "mbus" in row_keys:
            score += 1
        if "activepower" in row_keys:
            score += 1
        if "pvi1" in row_keys:
            score += 1
        if "vab" in row_keys:
            score += 1

        if score > best_score:
            best_score = score
            best_index = i

    if best_score >= min_matches:
        return best_index

    return None


# =========================================================
# COLUMN CLEANUP / STANDARDIZATION
# =========================================================
def standardize_columns(df):
    schema = expected_schema_map()
    new_cols = []
    used = set()

    for col in df.columns:
        clean_col = normalize_text(col)
        key = canonicalize(clean_col)

        if key in schema and schema[key] not in used:
            final_col = schema[key]
            used.add(final_col)
        else:
            final_col = clean_col

        new_cols.append(final_col)

    df.columns = new_cols
    return df


def detect_inverter_column(df):
    candidates = [
        "String Inverter",
        "Inverter ID",
        "Inverter",
        "Device Name",
        "ID"
    ]

    for candidate in candidates:
        ckey = canonicalize(candidate)
        for col in df.columns:
            if canonicalize(col) == ckey:
                return col

    for col in df.columns:
        sample = df[col].dropna().astype(str).head(20).tolist()
        matched = sum(bool(re.search(r"^P\d+-IB\d+-[\d\.\-]+-SI\d+$", s.strip())) for s in sample)
        if matched >= 3:
            return col

    return None


# =========================================================
# BUSINESS LOGIC
# =========================================================
def map_inverter_to_sacu(inverter_id_str):
    if not isinstance(inverter_id_str, str):
        return "Invalid Inverter ID"

    match = re.search(r'-(\d[\.\-]\d)-', inverter_id_str)
    if match:
        sacu_identifier = match.group(1)
        try:
            if "." in sacu_identifier:
                first_digit = int(sacu_identifier.split(".")[0])
            else:
                first_digit = int(sacu_identifier.split("-")[0])

            if first_digit in [1, 2]:
                return "SACU-1"
            elif first_digit in [3, 4]:
                return "SACU-2"
        except ValueError:
            pass
    return "Unknown SACU"


def classify_inverter_status(working_count):
    if working_count >= 19:
        return "Healthy"
    elif working_count == 18:
        return "1 String Failed"
    elif working_count in [16, 17]:
        return "Minor Issue"
    elif working_count in [10, 11, 12, 13, 14, 15]:
        return "Partial Failure"
    elif working_count < 10:
        return "Critical Failure"
    return "Unknown"


def add_derived_columns(df, inverter_col):
    df = df.copy()

    if inverter_col:
        df["Plot"] = df[inverter_col].apply(
            lambda x: str(x).split("-")[0] if isinstance(x, str) and "-" in str(x) else "Unknown Plot"
        )
        df["SACU"] = df[inverter_col].apply(map_inverter_to_sacu)

    existing_pv_current_cols = [c for c in PV_CURRENT_COLS if c in df.columns]
    actual_connected_pv_cols = existing_pv_current_cols[:ACTUAL_STRINGS_PER_INVERTER]

    if actual_connected_pv_cols:
        for col in actual_connected_pv_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        df["Total Strings"] = ACTUAL_STRINGS_PER_INVERTER
        df["Working String Count"] = (df[actual_connected_pv_cols] > STRING_WORKING_THRESHOLD).sum(axis=1)
        df["Failed String Count"] = ACTUAL_STRINGS_PER_INVERTER - df["Working String Count"]

        df["Failure %"] = np.where(
            df["Total Strings"] > 0,
            (df["Failed String Count"] / df["Total Strings"]) * 100,
            0
        )

        df["Inverter Status"] = df["Working String Count"].apply(classify_inverter_status)
    else:
        df["Total Strings"] = ACTUAL_STRINGS_PER_INVERTER
        df["Working String Count"] = 0
        df["Failed String Count"] = ACTUAL_STRINGS_PER_INVERTER
        df["Failure %"] = 100.0
        df["Inverter Status"] = "Unknown"

    numeric_cols = [
        "E-Daily(KWH)", "Active Power", "Reactive Power",
        "VAB", "VBC", "VCA", "IA", "IB", "IC"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    priority_cols = ["Plot"]
    if inverter_col:
        priority_cols.append(inverter_col)
    priority_cols += [
        "SACU", "Total Strings", "Working String Count", "Failed String Count",
        "Failure %", "Inverter Status"
    ]

    remaining = [c for c in df.columns if c not in priority_cols]
    ordered = [c for c in priority_cols if c in df.columns] + remaining
    df = df[ordered]

    return df


# =========================================================
# PROCESSING
# =========================================================
def process_excel_file(file_bytes):
    file_stream = io.BytesIO(file_bytes)
    xls = pd.ExcelFile(file_stream, engine="openpyxl")

    processed = {}
    logs = {}

    for sheet_name in xls.sheet_names:
        try:
            header_idx = find_header_row_index(file_stream, sheet_name)

            if header_idx is None:
                logs[sheet_name] = "Header row not found"
                continue

            file_stream.seek(0)
            df = pd.read_excel(
                file_stream,
                sheet_name=sheet_name,
                skiprows=header_idx,
                header=0,
                engine="openpyxl"
            )

            df.dropna(how="all", inplace=True)
            df = df.loc[:, ~df.columns.astype(str).str.contains(r"^Unnamed:", regex=True)]
            df.columns = [normalize_text(c) for c in df.columns]
            df = standardize_columns(df)

            inverter_col = detect_inverter_column(df)
            if inverter_col is None and "String Inverter" in df.columns:
                inverter_col = "String Inverter"

            if inverter_col is None:
                logs[sheet_name] = "String Inverter column not found"
                continue

            df = add_derived_columns(df, inverter_col)
            processed[sheet_name] = df

        except Exception as e:
            logs[sheet_name] = f"Processing error: {str(e)}"

    return processed, logs


@st.cache_data(show_spinner="Processing Excel workbook...", persist="disk")
def process_excel_cached(file_bytes):
    return process_excel_file(file_bytes)


@st.cache_data(show_spinner="Preparing workbook for download...")
def export_excel_bytes(sheets_dict):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in sheets_dict.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    output.seek(0)
    return output.getvalue()


# =========================================================
# FILTERS
# =========================================================
def apply_filters(df, plots=None, sacus=None, statuses=None, inverter_search=None):
    out = df.copy()

    if plots and "Plot" in out.columns:
        out = out[out["Plot"].astype(str).isin(plots)]

    if sacus and "SACU" in out.columns:
        out = out[out["SACU"].astype(str).isin(sacus)]

    if statuses and "Inverter Status" in out.columns:
        out = out[out["Inverter Status"].astype(str).isin(statuses)]

    if inverter_search and "String Inverter" in out.columns:
        out = out[
            out["String Inverter"].astype(str).str.contains(inverter_search, case=False, na=False)
        ]

    return out


# =========================================================
# UI
# =========================================================
st.title("SCADA Failure Analytics Dashboard")
st.caption("Processed Excel -> robust header detection -> inverter analytics -> dashboard")

uploaded_file = st.file_uploader("Upload SCADA Excel file", type=["xlsx", "xlsm", "xls"])

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    processed_sheets, logs = process_excel_cached(file_bytes)

    if not processed_sheets:
        st.error("No sheet could be processed.")
        if logs:
            with st.expander("Processing logs"):
                st.json(logs)
        st.stop()

    sheet_names = list(processed_sheets.keys())

    if "selected_sheet" not in st.session_state:
        st.session_state.selected_sheet = sheet_names[0]

    selected_sheet = st.selectbox(
        "Select sheet",
        sheet_names,
        index=sheet_names.index(st.session_state.selected_sheet)
        if st.session_state.selected_sheet in sheet_names else 0
    )
    st.session_state.selected_sheet = selected_sheet

    df = processed_sheets[selected_sheet].copy()

    with st.sidebar:
        st.header("Filters")

        plot_options = sorted(df["Plot"].dropna().astype(str).unique().tolist()) if "Plot" in df.columns else []
        sacu_options = sorted(df["SACU"].dropna().astype(str).unique().tolist()) if "SACU" in df.columns else []
        status_options = sorted(df["Inverter Status"].dropna().astype(str).unique().tolist()) if "Inverter Status" in df.columns else []

        selected_plots = st.multiselect("Plot", plot_options)
        selected_sacus = st.multiselect("SACU", sacu_options)
        selected_statuses = st.multiselect("Inverter Status", status_options)
        inverter_search = st.text_input("Search inverter")

    filtered_df = apply_filters(
        df,
        plots=selected_plots,
        sacus=selected_sacus,
        statuses=selected_statuses,
        inverter_search=inverter_search
    )

    tab1, tab2, tab3, tab4 = st.tabs([
        "Overview",
        "Block Analysis",
        "Inverter Analysis",
        "Data & Logs"
    ])

    # =====================================================
    # OVERVIEW
    # =====================================================
    with tab1:
        c1, c2, c3, c4 = st.columns(4)

        total_inverters = len(filtered_df)
        total_working = int(filtered_df["Working String Count"].sum()) if "Working String Count" in filtered_df.columns else 0
        total_failed = int(filtered_df["Failed String Count"].sum()) if "Failed String Count" in filtered_df.columns else 0
        avg_failure = round(filtered_df["Failure %"].mean(), 2) if "Failure %" in filtered_df.columns and len(filtered_df) else 0

        c1.metric("Total Inverters", total_inverters)
        c2.metric("Working Strings", total_working)
        c3.metric("Failed Strings", total_failed)
        c4.metric("Avg Failure %", avg_failure)

        col1, col2 = st.columns(2)

        with col1:
            if "Plot" in filtered_df.columns and "Failed String Count" in filtered_df.columns:
                block_fail = (
                    filtered_df.groupby("Plot", as_index=False)["Failed String Count"]
                    .sum()
                    .sort_values("Failed String Count", ascending=False)
                )
                fig1 = px.bar(
                    block_fail,
                    x="Plot",
                    y="Failed String Count",
                    color="Failed String Count",
                    title="Block-wise Failed String Count"
                )
                st.plotly_chart(fig1, use_container_width=True)

        with col2:
            if "SACU" in filtered_df.columns and "Working String Count" in filtered_df.columns:
                sacu_work = (
                    filtered_df.groupby("SACU", as_index=False)["Working String Count"]
                    .mean()
                    .sort_values("Working String Count", ascending=False)
                )
                fig2 = px.bar(
                    sacu_work,
                    x="SACU",
                    y="Working String Count",
                    color="Working String Count",
                    title="Average Working String Count by SACU"
                )
                st.plotly_chart(fig2, use_container_width=True)

        if "Inverter Status" in filtered_df.columns:
            status_count = (
                filtered_df.groupby("Inverter Status", as_index=False)
                .size()
                .rename(columns={"size": "Count"})
            )
            fig3 = px.pie(
                status_count,
                names="Inverter Status",
                values="Count",
                title="Inverter Status Distribution"
            )
            st.plotly_chart(fig3, use_container_width=True)

    # =====================================================
    # BLOCK ANALYSIS
    # =====================================================
    with tab2:
        col1, col2 = st.columns(2)

        with col1:
            if all(c in filtered_df.columns for c in ["Plot", "Failed String Count"]):
                plot_fail = (
                    filtered_df.groupby("Plot", as_index=False)["Failed String Count"]
                    .sum()
                    .sort_values("Failed String Count", ascending=False)
                )
                fig = px.bar(
                    plot_fail,
                    x="Plot",
                    y="Failed String Count",
                    text="Failed String Count",
                    title="Block-wise Failure Strings"
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if all(c in filtered_df.columns for c in ["Plot", "Working String Count"]):
                plot_work = (
                    filtered_df.groupby("Plot", as_index=False)["Working String Count"]
                    .sum()
                    .sort_values("Working String Count", ascending=False)
                )
                fig = px.bar(
                    plot_work,
                    x="Plot",
                    y="Working String Count",
                    text="Working String Count",
                    title="Block-wise Working Strings"
                )
                st.plotly_chart(fig, use_container_width=True)

        if all(c in filtered_df.columns for c in ["Plot", "E-Daily(KWH)"]):
            plot_energy = (
                filtered_df.groupby("Plot", as_index=False)["E-Daily(KWH)"]
                .sum()
                .sort_values("E-Daily(KWH)", ascending=False)
            )
            fig = px.line(
                plot_energy,
                x="Plot",
                y="E-Daily(KWH)",
                markers=True,
                title="Energy by Plot"
            )
            st.plotly_chart(fig, use_container_width=True)

    # =====================================================
    # INVERTER ANALYSIS
    # =====================================================
    with tab3:
        if all(c in filtered_df.columns for c in ["String Inverter", "Failed String Count", "Inverter Status"]):
            top_fail = (
                filtered_df[
                    ["String Inverter", "Plot", "SACU", "Failed String Count", "Failure %", "Inverter Status"]
                ]
                .sort_values("Failed String Count", ascending=False)
                .head(20)
            )

            fig = px.bar(
                top_fail,
                x="String Inverter",
                y="Failed String Count",
                color="Inverter Status",
                hover_data=["Plot", "SACU", "Failure %"],
                title="Top 20 Inverters by Failed Strings"
            )
            st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)

        with col1:
            if all(c in filtered_df.columns for c in ["Active Power", "Failed String Count", "Plot", "String Inverter"]):
                scatter = px.scatter(
                    filtered_df,
                    x="Active Power",
                    y="Failed String Count",
                    color="Plot",
                    hover_data=["String Inverter", "SACU", "Failure %"],
                    title="Failed Strings vs Active Power"
                )
                st.plotly_chart(scatter, use_container_width=True)

        with col2:
            if all(c in filtered_df.columns for c in ["E-Daily(KWH)", "Failed String Count", "String Inverter"]):
                scatter2 = px.scatter(
                    filtered_df,
                    x="E-Daily(KWH)",
                    y="Failed String Count",
                    color="SACU" if "SACU" in filtered_df.columns else None,
                    hover_data=["String Inverter", "Plot", "Failure %"] if "Plot" in filtered_df.columns else ["String Inverter"],
                    title="Failed Strings vs E-Daily(KWH)"
                )
                st.plotly_chart(scatter2, use_container_width=True)

        existing_pv_cols = [c for c in PV_CURRENT_COLS if c in filtered_df.columns][:ACTUAL_STRINGS_PER_INVERTER]
        if existing_pv_cols and "String Inverter" in filtered_df.columns:
            inverter_list = filtered_df["String Inverter"].dropna().astype(str).unique().tolist()
            if inverter_list:
                selected_inv = st.selectbox("Select inverter for string heatmap", inverter_list)
                one_row = filtered_df[filtered_df["String Inverter"].astype(str) == selected_inv].head(1)

                if not one_row.empty:
                    current_values = [
                        float(one_row.iloc[0][col]) if pd.notna(one_row.iloc[0][col]) else 0
                        for col in existing_pv_cols
                    ]
                    status_values = [1 if v > STRING_WORKING_THRESHOLD else 0 for v in current_values]

                    heat_fig = px.imshow(
                        [status_values],
                        x=existing_pv_cols,
                        y=[selected_inv],
                        aspect="auto",
                        color_continuous_scale=["red", "green"],
                        title="String Health Heatmap (0=Failed, 1=Working)"
                    )
                    st.plotly_chart(heat_fig, use_container_width=True)

                    string_df = pd.DataFrame({
                        "String": existing_pv_cols,
                        "Current": current_values,
                        "Status": ["Working" if v > STRING_WORKING_THRESHOLD else "Failed" for v in current_values]
                    })
                    st.dataframe(string_df, use_container_width=True)

    # =====================================================
    # DATA / LOGS
    # =====================================================
    with tab4:
        st.subheader("Filtered Data")
        st.dataframe(filtered_df, use_container_width=True)

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                label="Download filtered CSV",
                data=filtered_df.to_csv(index=False).encode("utf-8"),
                file_name=f"{selected_sheet}_filtered.csv",
                mime="text/csv"
            )

        with col2:
            workbook_bytes = export_excel_bytes(processed_sheets)
            st.download_button(
                label="Download processed workbook",
                data=workbook_bytes,
                file_name=f"processed_{uploaded_file.name}",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        if logs:
            st.subheader("Processing Logs")
            st.json(logs)

else:
    st.info("Upload an Excel file to start processing and visualizing the SCADA data.")