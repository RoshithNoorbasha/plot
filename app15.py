import io
import re
from pathlib import Path
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# ==========================================
# 1. PAGE CONFIGURATION & STYLING
# ==========================================
st.set_page_config(
    page_title="PV SCADA Analytics",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
    .stMetric {
        background-color: #0f172a;
        border: 1px solid #1e293b;
        padding: 1rem;
        border-radius: 0.75rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.7rem;
        font-weight: 700;
        color: #38bdf8;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. CONFIGURATION
# ==========================================
DEFAULT_TOTAL_ACTIVE_STRINGS = 19
WORKING_CURRENT_THRESHOLD = 0.5
PV_CURRENT_COLUMNS = [f"PV-I{i}" for i in range(1, 29)]

ACTIVE_STRING_OVERRIDES = {
    "P2": {
        "IB1": 18,
        "IB3": 17,
        "IB4": 18,
        "IB5": 18,
    },
    "P6": {
        "IB1": 18,
        "IB2": 18,
        "IB3": 18,
        "IB5": 18,
        "IB6": 18,
        "IB7": 18,
    }
}

INVERTER_ID_COLS = [
    "Inverter ID",
    "Inverter_ID",
    "Inverter",
    "ID",
    "Device Name",
    "String Inverter",
    "Inverters"
]

MANUAL_SCADA_COLUMNS = [
    "String Inverter",
    "MBUS",
    "Grid",
    "E-Daily(KWH)",
    "Active Power",
    "Reactive Power",
    "PV1", "PV2", "PV3", "PV4", "PV5", "PV6", "PV7", "PV8", "PV9", "PV10",
    "PV11", "PV12", "PV13", "PV14", "PV15", "PV16", "PV17", "PV18", "PV19", "PV20",
    "PV21", "PV22", "PV23", "PV24", "PV25", "PV26", "PV27", "PV28",
    "PV-I1", "PV-I2", "PV-I3", "PV-I4", "PV-I5", "PV-I6", "PV-I7", "PV-I8", "PV-I9", "PV-I10",
    "PV-I11", "PV-I12", "PV-I13", "PV-I14", "PV-I15", "PV-I16", "PV-I17", "PV-I18", "PV-I19", "PV-I20",
    "PV-I21", "PV-I22", "PV-I23", "PV-I24", "PV-I25", "PV-I26", "PV-I27", "PV-I28",
    "VAB", "VBC", "VCA", "IA", "IB", "IC"
]

BASE_STORAGE_DIR = Path("storage")
UPLOADS_DIR = BASE_STORAGE_DIR / "uploads"
PROCESSED_CSV_DIR = BASE_STORAGE_DIR / "processed_csv"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_CSV_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 3. LOGIN
# ==========================================
def init_auth_state():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False


def login_screen():
    st.title("🔐 PV SCADA Login")
    st.write("Please login to continue.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_btn = st.form_submit_button("Login")

    if login_btn:
        app_username = st.secrets["app_auth"]["username"]
        app_password = st.secrets["app_auth"]["password"]

        if username == app_username and password == app_password:
            st.session_state.authenticated = True
            st.session_state.logged_user = username
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Invalid username or password")


def logout():
    st.session_state.authenticated = False
    st.session_state.logged_user = None
    st.rerun()


init_auth_state()

if not st.session_state.authenticated:
    login_screen()
    st.stop()


# ==========================================
# 4. HELPERS
# ==========================================
def normalize_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip().upper()


def clean_manual_columns(col_list):
    cleaned = []
    for col in col_list:
        col = str(col).strip()
        if col and col.lower() != "nan":
            cleaned.append(col)
    return cleaned


def extract_plot(inverter_id_str):
    if isinstance(inverter_id_str, str):
        parts = inverter_id_str.split("-")
        if len(parts) > 0:
            return parts[0].strip()
    return "Unknown Plot"


def extract_block(inverter_id_str):
    if isinstance(inverter_id_str, str):
        parts = inverter_id_str.split("-")
        if len(parts) > 1:
            return parts[1].strip()
    return "Unknown Block"


def map_inverter_to_sacu(inverter_id_str):
    if not isinstance(inverter_id_str, str):
        return "Invalid Inverter ID"

    match = re.search(r'-(\d[\.\-]\d)-', inverter_id_str)
    if match:
        sacu_identifier = match.group(1)
        try:
            if "." in sacu_identifier:
                first_digit_str = sacu_identifier.split(".")[0]
            else:
                first_digit_str = sacu_identifier.split("-")[0]

            first_digit = int(first_digit_str)

            if first_digit in [1, 2]:
                return "SACU-1"
            elif first_digit in [3, 4]:
                return "SACU-2"
        except ValueError:
            pass

    return "Unknown SACU"


def get_total_active_strings(plot, block):
    plot_key = normalize_text(plot)
    block_key = normalize_text(block)

    if plot_key in ACTIVE_STRING_OVERRIDES and block_key in ACTIVE_STRING_OVERRIDES[plot_key]:
        return ACTIVE_STRING_OVERRIDES[plot_key][block_key]

    return DEFAULT_TOTAL_ACTIVE_STRINGS


def get_available_pv_columns(df):
    normalized_map = {str(col).strip().upper(): col for col in df.columns}
    available_columns = []

    for col in PV_CURRENT_COLUMNS:
        if col.upper() in normalized_map:
            available_columns.append(normalized_map[col.upper()])

    return available_columns


def calculate_working_string_count(row, pv_columns):
    count = 0
    for col in pv_columns:
        value = pd.to_numeric(row.get(col), errors="coerce")
        if pd.notna(value) and value > WORKING_CURRENT_THRESHOLD:
            count += 1
    return count


def apply_string_metrics(df, plot_col="Plot", block_col="Block"):
    pv_columns = get_available_pv_columns(df)

    df["Total Active Strings"] = df.apply(
        lambda row: get_total_active_strings(row.get(plot_col), row.get(block_col)),
        axis=1
    )

    if pv_columns:
        df["Working String Count"] = df.apply(
            lambda row: calculate_working_string_count(row, pv_columns),
            axis=1
        )
    else:
        df["Working String Count"] = 0

    df["Failed String Count"] = (
        df["Total Active Strings"] - df["Working String Count"]
    ).clip(lower=0)

    df["Availability (%)"] = (
        (df["Working String Count"] / df["Total Active Strings"]) * 100
    ).fillna(0).round(2)

    df["Failure Percentage (%)"] = (
        (df["Failed String Count"] / df["Total Active Strings"]) * 100
    ).fillna(0).round(2)

    return df


def find_header_row_index(file_stream, sheet_name, possible_header_columns, max_rows_to_check=100):
    file_stream.seek(0)
    temp_df = pd.read_excel(
        file_stream,
        sheet_name=sheet_name,
        header=None,
        nrows=max_rows_to_check,
        engine="openpyxl"
    )

    possible_headers_lower = [str(col).strip().lower() for col in possible_header_columns]

    for i, row in temp_df.iterrows():
        row_values = [str(val).strip() for val in row.dropna()]
        row_values_lower = [v.lower() for v in row_values]

        if any(col in row_values_lower for col in possible_headers_lower):
            return i

    return None


def assign_manual_headers(df, manual_headers):
    manual_headers = clean_manual_columns(manual_headers)

    if len(df.columns) >= len(manual_headers):
        df = df.iloc[:, :len(manual_headers)].copy()
        df.columns = manual_headers
    else:
        df.columns = manual_headers[:len(df.columns)]

    return df


def read_sheet_with_fallback(file_stream, sheet_name):
    header_row_index = find_header_row_index(file_stream, sheet_name, INVERTER_ID_COLS)

    file_stream.seek(0)
    if header_row_index is not None:
        df = pd.read_excel(
            file_stream,
            sheet_name=sheet_name,
            skiprows=header_row_index,
            header=0,
            engine="openpyxl"
        )
    else:
        df = pd.read_excel(
            file_stream,
            sheet_name=sheet_name,
            header=None,
            engine="openpyxl"
        )
        df = assign_manual_headers(df, MANUAL_SCADA_COLUMNS)

    return df


def detect_inverter_column(df):
    df_columns_lower_map = {str(c).strip().lower(): c for c in df.columns}

    for col in INVERTER_ID_COLS:
        if col in df.columns:
            return col
        elif col.strip().lower() in df_columns_lower_map:
            return df_columns_lower_map[col.strip().lower()]

    return None


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", str(text)).strip("_")


def save_uploaded_excel(file_name, file_bytes):
    latest_path = UPLOADS_DIR / "latest_uploaded_scada.xlsx"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = UPLOADS_DIR / f"{safe_name(Path(file_name).stem)}_{timestamp}.xlsx"

    latest_path.write_bytes(file_bytes)
    archive_path.write_bytes(file_bytes)

    info_path = UPLOADS_DIR / "latest_upload_info.txt"
    info_path.write_text(
        f"Original File: {file_name}\nSaved At: {timestamp}\n",
        encoding="utf-8"
    )


def save_processed_csvs(dataframes_dict):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for sheet_name, df in dataframes_dict.items():
        clean_sheet_name = safe_name(sheet_name)

        latest_csv = PROCESSED_CSV_DIR / f"{clean_sheet_name}_latest.csv"
        archive_csv = PROCESSED_CSV_DIR / f"{clean_sheet_name}_{timestamp}.csv"

        df.to_csv(latest_csv, index=False)
        df.to_csv(archive_csv, index=False)

    info_path = PROCESSED_CSV_DIR / "latest_processed_info.txt"
    info_path.write_text(
        f"Processed At: {timestamp}\nSheets: {', '.join(dataframes_dict.keys())}",
        encoding="utf-8"
    )


# ==========================================
# 5. PARSER
# ==========================================
@st.cache_data(show_spinner="Processing SCADA workbook...", ttl=3600)
def process_scada_excel_bytes(file_bytes):
    file_stream = io.BytesIO(file_bytes)
    excel_file = pd.ExcelFile(file_stream, engine="openpyxl")
    processed_dfs = {}

    for sheet_name in excel_file.sheet_names:
        try:
            df = read_sheet_with_fallback(file_stream, sheet_name)
        except Exception:
            continue

        df.dropna(how="all", inplace=True)
        df = df.loc[:, ~df.columns.astype(str).str.contains("^Unnamed:", case=False, regex=True)]
        df = df.loc[:, ~df.columns.duplicated()].copy()

        actual_inverter_col = detect_inverter_column(df)

        if not actual_inverter_col:
            continue

        df["Plot"] = df[actual_inverter_col].apply(extract_plot)
        df["Block"] = df[actual_inverter_col].apply(extract_block)
        df["SACU"] = df[actual_inverter_col].apply(map_inverter_to_sacu)

        df = apply_string_metrics(df, plot_col="Plot", block_col="Block")

        preferred_columns = [
            "Plot",
            "Block",
            actual_inverter_col,
            "SACU",
            "Total Active Strings",
            "Working String Count",
            "Failed String Count",
            "Availability (%)",
            "Failure Percentage (%)"
        ]
        remaining_cols = [c for c in df.columns if c not in preferred_columns]
        final_columns = [c for c in preferred_columns if c in df.columns] + remaining_cols
        df = df[final_columns]

        processed_dfs[sheet_name] = df

    return processed_dfs


def create_excel_download(dataframes_dict):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, df in dataframes_dict.items():
            safe_sheet_name = str(sheet_name)[:31]
            df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
    buffer.seek(0)
    return buffer.getvalue()


# ==========================================
# 6. SIDEBAR
# ==========================================
st.sidebar.title("⚡ PV SCADA Control")
st.sidebar.success(f"Logged in as: {st.session_state.get('logged_user', 'User')}")
if st.sidebar.button("Logout"):
    logout()

uploaded_file = st.sidebar.file_uploader("Upload SCADA Report (.xlsx)", type=["xlsx"])


# ==========================================
# 7. MAIN FLOW
# ==========================================
if not uploaded_file:
    st.info("Upload your SCADA Excel workbook from the sidebar.")
    st.stop()

uploaded_bytes = uploaded_file.getvalue()

save_uploaded_excel(uploaded_file.name, uploaded_bytes)

processed_dataframes = process_scada_excel_bytes(uploaded_bytes)

if processed_dataframes:
    save_processed_csvs(processed_dataframes)

if not processed_dataframes:
    st.error("No valid sheets or inverter columns were identified in the uploaded workbook.")
    st.stop()


sheet_selection = st.sidebar.selectbox("Select Sheet", list(processed_dataframes.keys()))
df_selected = processed_dataframes[sheet_selection].copy()
actual_inverter_col = detect_inverter_column(df_selected)

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")

plots = ["All"] + sorted([p for p in df_selected["Plot"].dropna().unique()])
selected_plot = st.sidebar.selectbox("Plot", plots)

filtered_df = df_selected.copy()
if selected_plot != "All":
    filtered_df = filtered_df[filtered_df["Plot"] == selected_plot]

blocks = ["All"] + sorted([b for b in filtered_df["Block"].dropna().unique()])
selected_block = st.sidebar.selectbox("Block", blocks)
if selected_block != "All":
    filtered_df = filtered_df[filtered_df["Block"] == selected_block]

sacus = ["All"] + sorted([s for s in filtered_df["SACU"].dropna().unique()])
selected_sacu = st.sidebar.selectbox("SACU", sacus)
if selected_sacu != "All":
    filtered_df = filtered_df[filtered_df["SACU"] == selected_sacu]


# ==========================================
# 8. DASHBOARD
# ==========================================
st.title("Solar PV String Availability Dashboard")
st.caption(f"Sheet: {sheet_selection} | Filtered inverters: {len(filtered_df)}")

kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

total_inverters = filtered_df[actual_inverter_col].nunique() if actual_inverter_col and not filtered_df.empty else 0
total_strings = int(filtered_df["Total Active Strings"].sum()) if "Total Active Strings" in filtered_df.columns else 0
working_strings = int(filtered_df["Working String Count"].sum()) if "Working String Count" in filtered_df.columns else 0
failed_strings = int(filtered_df["Failed String Count"].sum()) if "Failed String Count" in filtered_df.columns else 0
overall_availability = round((working_strings / total_strings) * 100, 2) if total_strings > 0 else 0.0

kpi1.metric("Total Inverters", f"{total_inverters:,}")
kpi2.metric("Total Active Strings", f"{total_strings:,}")
kpi3.metric("Working Strings", f"{working_strings:,}")
kpi4.metric("Failed Strings", f"{failed_strings:,}")
kpi5.metric("Availability", f"{overall_availability:.2f}%")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Block-wise Strings")
    if not filtered_df.empty:
        block_summary = filtered_df.groupby("Block", as_index=False).agg(
            Total_Active_Strings=("Total Active Strings", "sum"),
            Working_String_Count=("Working String Count", "sum"),
            Failed_String_Count=("Failed String Count", "sum")
        )

        fig_bar = px.bar(
            block_summary,
            x="Block",
            y=["Working_String_Count", "Failed_String_Count"],
            barmode="stack",
            color_discrete_map={
                "Working_String_Count": "#10b981",
                "Failed_String_Count": "#ef4444"
            }
        )
        fig_bar.update_layout(height=400)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.warning("No records available for the selected filters.")

with col2:
    st.subheader("String Health")
    fig_pie = go.Figure(data=[go.Pie(
        labels=["Working Strings", "Failed Strings"],
        values=[working_strings, failed_strings],
        hole=0.55,
        marker_colors=["#10b981", "#ef4444"]
    )])
    fig_pie.update_layout(height=400)
    st.plotly_chart(fig_pie, use_container_width=True)

st.markdown("---")
st.subheader("Block Summary")

if not filtered_df.empty and actual_inverter_col:
    block_table = filtered_df.groupby("Block", as_index=False).agg(
        Total_Inverters=(actual_inverter_col, "nunique"),
        Total_Active_Strings=("Total Active Strings", "sum"),
        Total_Working_Strings=("Working String Count", "sum"),
        Total_Failed_Strings=("Failed String Count", "sum")
    )

    block_table["Availability (%)"] = (
        (block_table["Total_Working_Strings"] / block_table["Total_Active_Strings"]) * 100
    ).fillna(0).round(2)

    block_table["Failure Percentage (%)"] = (
        (block_table["Total_Failed_Strings"] / block_table["Total_Active_Strings"]) * 100
    ).fillna(0).round(2)

    st.dataframe(block_table, use_container_width=True)
else:
    st.warning("No block summary available.")

st.markdown("---")
st.subheader("Inverter Data")

st.dataframe(
    filtered_df,
    use_container_width=True,
    column_config={
        "Availability (%)": st.column_config.ProgressColumn(
            "Availability (%)",
            min_value=0,
            max_value=100,
            format="%.2f%%"
        ),
        "Failure Percentage (%)": st.column_config.NumberColumn(
            "Failure Percentage (%)",
            format="%.2f%%"
        )
    }
)

download_bytes = create_excel_download({sheet_selection: filtered_df})
st.download_button(
    label="📥 Download Filtered Excel",
    data=download_bytes,
    file_name=f"processed_{sheet_selection}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)