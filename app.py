import io
import re
import json
import os
import hashlib
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime
from pathlib import Path
import streamlit as st
import plotly.io as pio
# ==========================================
# 1. PAGE CONFIGURATION & STYLING
# ==========================================
st.set_page_config(
    page_title="PV String Analytics",
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
    /* Heat map header colors */
    .string-header-high { background-color: #10b981; color: white; }
    .string-header-medium { background-color: #f59e0b; color: white; }
    .string-header-low { background-color: #ef4444; color: white; }
    .string-header-verylow { background-color: #7f1d1d; color: white; }
    .stDataFrame thead th {
        background-color: #1e293b;
        color: white;
        font-weight: 600;
    }
    .user-badge-admin {
        background-color: #8b5cf6;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.7rem;
        font-weight: 600;
    }
    .user-badge-engineer {
        background-color: #3b82f6;
        color: white;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.7rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. CONFIGURATION
# ==========================================
DEFAULT_TOTAL_ACTIVE_STRINGS = 19
WORKING_CURRENT_THRESHOLD = 0.5
PV_CURRENT_COLUMNS = [f"PV-I{i}" for i in range(1, 29)]
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
EXCEL_FILES_DIR = DATA_DIR / "excel_files"
EXCEL_FILES_DIR.mkdir(exist_ok=True)

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

# ==========================================
# 3. USER MANAGEMENT
# ==========================================
def load_users():
    """Load users from JSON file"""
    if USERS_FILE.exists():
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    """Save users to JSON file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

# def init_default_users():
#     """Initialize default users if no users exist"""
#     users = load_users()x
#     if not users:
#         default_users = {
#             "admin": {
#                 "password": hashlib.sha256("admin123".encode()).hexdigest(),
#                 "role": "admin",
#                 "assigned_plots": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"],
#                 "created_at": datetime.now().isoformat()
#             },
#             "engineer1": {
#                 "password": hashlib.sha256("eng123".encode()).hexdigest(),
#                 "role": "engineer",
#                 "assigned_plots": ["P1", "P2", "P3"],
#                 "created_at": datetime.now().isoformat()
#             },
#             "engineer2": {
#                 "password": hashlib.sha256("eng456".encode()).hexdigest(),
#                 "role": "engineer",
#                 "assigned_plots": ["P4", "P5", "P6"],
#                 "created_at": datetime.now().isoformat()
#             }
#         }
#         save_users(default_users)
#         return default_users
#     return users

def authenticate_user(username, password):
    """Authenticate user with password"""
    users = load_users()
    if username in users:
        hashed_pwd = hashlib.sha256(password.encode()).hexdigest()
        if users[username]["password"] == hashed_pwd:
            return users[username]
    return None

def get_current_user():
    """Get current user from session state"""
    if "user" in st.session_state:
        return st.session_state.user
    return None

# ==========================================
# 4. EXCEL FILE MANAGEMENT (Backend Storage)
# ==========================================
# def save_excel_file(file_bytes, filename):
#     """Save uploaded Excel file to backend storage"""
#     # Generate unique filename with timestamp
#     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#     file_hash = hashlib.md5(file_bytes).hexdigest()[:8]
#     stored_filename = f"{timestamp}_{file_hash}_{filename}"
#     file_path = EXCEL_FILES_DIR / stored_filename
    
#     # Save file
#     with open(file_path, 'wb') as f:
#         f.write(file_bytes)
    
#     # Store metadata
#     metadata_file = EXCEL_FILES_DIR / "metadata.json"
#     metadata = {}
#     if metadata_file.exists():
#         with open(metadata_file, 'r') as f:
#             metadata = json.load(f)
    
#     metadata[stored_filename] = {
#         "original_filename": filename,
#         "timestamp": timestamp,
#         "file_hash": file_hash,
#         "file_size": len(file_bytes)
#     }
    
#     with open(metadata_file, 'w') as f:
#         json.dump(metadata, f, indent=2)
    
#     # Update session state
#     st.session_state.current_file = stored_filename
#     return stored_filename
def save_excel_file(file_bytes, filename):
    metadata_file = EXCEL_FILES_DIR / "metadata.json"
    file_hash = hashlib.md5(file_bytes).hexdigest()
    ext = Path(filename).suffix or ".xlsx"
    stored_filename = f"{file_hash}{ext}"
    filepath = EXCEL_FILES_DIR / stored_filename

    metadata = {}
    if metadata_file.exists():
        with open(metadata_file, "r") as f:
            metadata = json.load(f)

    for existing_name, info in metadata.items():
        if info.get("filehash") == file_hash:
            st.session_state.current_file = existing_name
            return existing_name

    if not filepath.exists():
        with open(filepath, "wb") as f:
            f.write(file_bytes)

    metadata[stored_filename] = {
        "originalfilename": filename,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filehash": file_hash,
        "filesize": len(file_bytes)
    }

    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    st.session_state.current_file = stored_filename
    return stored_filename

def get_latest_excel_file():
    """Get the most recent Excel file"""
    metadata_file = EXCEL_FILES_DIR / "metadata.json"
    if not metadata_file.exists():
        return None
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    if not metadata:
        return None
    
    # Get latest file by timestamp
    latest_file = max(metadata.items(), key=lambda x: x[1]["timestamp"])
    return latest_file[0]

def load_excel_from_backend(filename):
    """Load Excel file from backend storage"""
    file_path = EXCEL_FILES_DIR / filename
    if file_path.exists():
        with open(file_path, 'rb') as f:
            return f.read()
    return None

# ==========================================
# 5. HELPERS
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

def get_pv_string_columns(df):
    """Get all PV string voltage and current columns"""
    pv_voltage_cols = []
    pv_current_cols = []
    
    for col in df.columns:
        col_str = str(col).strip()
        if col_str.startswith("PV-I"):
            pv_current_cols.append(col)
        elif col_str.startswith("PV") and col_str != "PV" and not col_str.startswith("PV-I"):
            # Try to parse as PV voltage
            try:
                num = int(col_str[2:])
                if 1 <= num <= 28:
                    pv_voltage_cols.append(col)
            except:
                pass
    
    return pv_voltage_cols, pv_current_cols

def get_string_health_color(value):
    """Get color for string health based on current value"""
    if pd.isna(value):
        return "#64748b"  # Gray
    if value > 5.0:
        return "#10b981"  # Green - Excellent
    elif value > 3.0:
        return "#34d399"  # Light Green - Good
    elif value > 1.5:
        return "#fbbf24"  # Yellow - Fair
    elif value > 0.5:
        return "#f59e0b"  # Orange - Poor
    else:
        return "#ef4444"  # Red - Critical

def get_column_header_color(value):
    """Get color for column header based on working percentage"""
    if pd.isna(value):
        return "#64748b"
    if value >= 80:
        return "#10b981"  # Green
    elif value >= 60:
        return "#f59e0b"  # Yellow
    elif value >= 40:
        return "#f97316"  # Orange
    else:
        return "#ef4444"  # Red

# ==========================================
# 6. PARSER
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

        df_columns_lower_map = {str(c).strip().lower(): c for c in df.columns}
        actual_inverter_col = None

        for col in INVERTER_ID_COLS:
            if col in df.columns:
                actual_inverter_col = col
                break
            elif col.strip().lower() in df_columns_lower_map:
                actual_inverter_col = df_columns_lower_map[col.strip().lower()]
                break

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
# 7. UI - User Management
# ==========================================
def user_management_ui():
    """Admin interface for user management"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("👥 User Management")
    
    users = load_users()
    current_user = get_current_user()
    
    if current_user and current_user["role"] == "admin":
        with st.sidebar.expander("Manage Users"):
            st.write("### Create New User")
            new_username = st.text_input("Username", key="new_user")
            new_password = st.text_input("Password", type="password", key="new_pass")
            new_role = st.selectbox("Role", ["engineer", "admin"], key="new_role")
            
            if st.button("Create User", key="create_user_btn"):
                if new_username and new_password:
                    if new_username in users:
                        st.error("Username already exists!")
                    else:
                        users[new_username] = {
                            "password": hashlib.sha256(new_password.encode()).hexdigest(),
                            "role": new_role,
                            "assigned_plots": ["P1", "P2", "P3"] if new_role == "engineer" else ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"],
                            "created_at": datetime.now().isoformat()
                        }
                        save_users(users)
                        st.success(f"User {new_username} created!")
                        st.rerun()
            
            st.write("### Existing Users")
            for username, user_data in users.items():
                if username != current_user.get("username"):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.write(f"**{username}** ({user_data['role']})")
                    with col2:
                        if st.button(f"Delete", key=f"del_{username}"):
                            del users[username]
                            save_users(users)
                            st.rerun()
                    with col3:
                        if user_data["role"] == "engineer":
                            if st.button(f"Assign Plots", key=f"assign_{username}"):
                                st.session_state.assign_user = username
                                st.rerun()
            
            # Plot assignment interface
            if "assign_user" in st.session_state:
                username = st.session_state.assign_user
                user_data = users.get(username)
                if user_data:
                    st.write(f"### Assign Plots for {username}")
                    available_plots = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"]
                    assigned = user_data.get("assigned_plots", [])
                    
                    selected_plots = st.multiselect(
                        f"Select plots for {username}",
                        options=available_plots,
                        default=assigned
                    )
                    
                    if st.button("Save Assignments"):
                        users[username]["assigned_plots"] = selected_plots
                        save_users(users)
                        st.success(f"Plots assigned for {username}")
                        del st.session_state.assign_user
                        st.rerun()
                    
                    if st.button("Cancel"):
                        del st.session_state.assign_user
                        st.rerun()
    else:
        st.sidebar.info("Admin access required for user management")

# ==========================================
# 8. UI - Main Tabs
# ==========================================

# ==========================================
# 8. UI - Main Tabs (UPDATED)
# ==========================================
def create_pv_string_tab(df):
    """Create the inverter-wise PV string details tab"""
    st.subheader("🔌 Inverter-wise PV String Details")
    st.caption("Color-coded headers show string health status")
    
    # Find the actual inverter column
    inverter_col = None
    df_columns_lower_map = {str(c).strip().lower(): c for c in df.columns}
    
    for col in INVERTER_ID_COLS:
        if col in df.columns:
            inverter_col = col
            break
        elif col.strip().lower() in df_columns_lower_map:
            inverter_col = df_columns_lower_map[col.strip().lower()]
            break
    
    if not inverter_col:
        st.warning("No inverter ID column found in the dataset")
        return
    
    # Get PV string columns
    pv_voltage_cols, pv_current_cols = get_pv_string_columns(df)
    
    if not pv_voltage_cols and not pv_current_cols:
        st.warning("No PV string data columns found in the dataset")
        return
    
    # Filter controls
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        available_plots = sorted(df["Plot"].unique())
        selected_plot = st.selectbox("Filter by Plot", ["All"] + available_plots, key="pv_plot_filter")
    
    with col2:
        filtered_by_plot = df if selected_plot == "All" else df[df["Plot"] == selected_plot]
        available_blocks = sorted(filtered_by_plot["Block"].unique())
        selected_block = st.selectbox("Filter by Block", ["All"] + available_blocks, key="pv_block_filter")
    
    with col3:
        filtered_by_block = filtered_by_plot if selected_block == "All" else filtered_by_plot[filtered_by_plot["Block"] == selected_block]
        available_sacus = sorted(filtered_by_block["SACU"].unique())
        selected_sacu = st.selectbox("Filter by SACU", ["All"] + available_sacus, key="pv_sacu_filter")
    
    with col4:
        filtered_by_sacu = filtered_by_block if selected_sacu == "All" else filtered_by_block[filtered_by_block["SACU"] == selected_sacu]
        available_inverters = sorted(filtered_by_sacu[inverter_col].unique())
        selected_inverter = st.selectbox("Filter by Inverter", ["All"] + available_inverters, key="pv_inverter_filter")
    
    with col5:
        show_voltage = st.checkbox("Show Voltage", value=False, key="show_voltage")
        show_current = st.checkbox("Show Current", value=True, key="show_current")
    
    # Filter data
    filtered_df = df.copy()
    if selected_plot != "All":
        filtered_df = filtered_df[filtered_df["Plot"] == selected_plot]
    if selected_block != "All":
        filtered_df = filtered_df[filtered_df["Block"] == selected_block]
    if selected_sacu != "All":
        filtered_df = filtered_df[filtered_df["SACU"] == selected_sacu]
    if selected_inverter != "All":
        filtered_df = filtered_df[filtered_df[inverter_col] == selected_inverter]
    
    if filtered_df.empty:
        st.warning("No data available for the selected filters")
        return
    
    # Calculate summary metrics for each inverter using existing calculations
    summary_metrics = []
    for idx, row in filtered_df.iterrows():
        inverter_id = row[inverter_col]
        plot = row.get("Plot", "")
        block = row.get("Block", "")
        sacu = row.get("SACU", "")
        
        # Use pre-calculated metrics if available
        if "Total Active Strings" in row and "Working String Count" in row:
            total_strings = int(row["Total Active Strings"]) if pd.notna(row["Total Active Strings"]) else 0
            working_strings = int(row["Working String Count"]) if pd.notna(row["Working String Count"]) else 0
            failed_strings = int(row["Failed String Count"]) if pd.notna(row["Failed String Count"]) else 0
            availability = row["Availability (%)"] if pd.notna(row["Availability (%)"]) else 0
        else:
            # Fallback: Calculate manually
            total_strings = 0
            working_strings = 0
            failed_strings = 0
            
            for col in pv_current_cols:
                if col in row and pd.notna(row[col]):
                    total_strings += 1
                    if row[col] > WORKING_CURRENT_THRESHOLD:
                        working_strings += 1
                    else:
                        failed_strings += 1
            
            availability = (working_strings / total_strings * 100) if total_strings > 0 else 0
        
        # Get additional metrics if available
        grid = row.get("Grid", "")
        e_daily = row.get("E-Daily(KWH)", "")
        active_power = row.get("Active Power", "")
        reactive_power = row.get("Reactive Power", "")
        
        # Get PV voltages summary
        voltage_values = []
        for col in pv_voltage_cols:
            if col in row and pd.notna(row[col]):
                voltage_values.append(row[col])
        
        avg_voltage = sum(voltage_values) / len(voltage_values) if voltage_values else 0
        min_voltage = min(voltage_values) if voltage_values else 0
        max_voltage = max(voltage_values) if voltage_values else 0
        
        # Get PV current summary
        current_values = []
        for col in pv_current_cols:
            if col in row and pd.notna(row[col]):
                current_values.append(row[col])
        
        avg_current = sum(current_values) / len(current_values) if current_values else 0
        
        # Calculate string health status
        health_status = "Excellent" if availability >= 90 else "Good" if availability >= 70 else "Fair" if availability >= 50 else "Poor"
        
        summary_metrics.append({
            "Inverter ID": inverter_id,
            "Plot": plot,
            "Block": block,
            "SACU": sacu,
            "Total Strings": total_strings,
            "Working Strings": working_strings,
            "Failed Strings": failed_strings,
            "Availability (%)": round(availability, 2),
            "Health Status": health_status,
            "Avg PV Voltage (V)": round(avg_voltage, 1),
            "Avg PV Current (A)": round(avg_current, 2),
            "Grid": grid,
            "E-Daily (KWH)": e_daily,
            "Active Power (KW)": active_power,
            "Reactive Power (KVAR)": reactive_power
        })
    
    summary_df = pd.DataFrame(summary_metrics)
    
    # Display summary cards
    st.markdown("### 📊 Inverter Summary")
    
    # Show total metrics
    total_inverters = len(summary_df)
    total_working = summary_df["Working Strings"].sum()
    total_strings_all = summary_df["Total Strings"].sum()
    total_failed = summary_df["Failed Strings"].sum()
    overall_availability = (total_working / total_strings_all * 100) if total_strings_all > 0 else 0
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Inverters", total_inverters)
    col2.metric("Total Strings", total_strings_all)
    col3.metric("Working Strings", total_working)
    col4.metric("Failed Strings", total_failed)
    col5.metric("Overall Availability", f"{overall_availability:.1f}%")
    
    st.markdown("---")
    
    # Display summary table with color coding
    st.subheader("📋 Inverter-wise Summary")
    
    # Color code the summary table
    def color_availability(val):
        if isinstance(val, (int, float)):
            if val >= 90:
                return 'background-color: #10b981; color: white; font-weight: bold'
            elif val >= 70:
                return 'background-color: #34d399; color: white; font-weight: bold'
            elif val >= 50:
                return 'background-color: #fbbf24; color: black; font-weight: bold'
            elif val >= 30:
                return 'background-color: #f59e0b; color: white; font-weight: bold'
            else:
                return 'background-color: #ef4444; color: white; font-weight: bold'
        return ''
    
    def color_health_status(val):
        if val == "Excellent":
            return 'background-color: #10b981; color: white; font-weight: bold'
        elif val == "Good":
            return 'background-color: #34d399; color: white; font-weight: bold'
        elif val == "Fair":
            return 'background-color: #fbbf24; color: black; font-weight: bold'
        elif val == "Poor":
            return 'background-color: #ef4444; color: white; font-weight: bold'
        return ''
    
    def color_failed_strings(val):
        if isinstance(val, (int, float)):
            if val == 0:
                return 'background-color: #10b981; color: white; font-weight: bold'
            elif val <= 2:
                return 'background-color: #fbbf24; color: black; font-weight: bold'
            elif val <= 5:
                return 'background-color: #f59e0b; color: white; font-weight: bold'
            else:
                return 'background-color: #ef4444; color: white; font-weight: bold'
        return ''
    
    # Apply styling to summary table
    styled_summary = summary_df.style.map(color_availability, subset=['Availability (%)'])
    styled_summary = styled_summary.map(color_health_status, subset=['Health Status'])
    styled_summary = styled_summary.map(color_failed_strings, subset=['Failed Strings'])
    
    # Format numeric columns
    styled_summary = styled_summary.format({
        'Availability (%)': '{:.1f}%',
        'Avg PV Voltage (V)': '{:.1f}',
        'Avg PV Current (A)': '{:.2f}'
    })
    
    st.dataframe(styled_summary, use_container_width=True)
    
    st.markdown("---")
    
    # Display detailed PV string data
    st.subheader("🔌 Detailed PV String Data")
    st.caption("Green = Good (>5A), Yellow = Fair (1.5-5A), Orange = Poor (0.5-1.5A), Red = Critical (<0.5A)")
    
    # Prepare display dataframe for detailed view
    display_cols = [inverter_col, "Plot", "Block", "SACU"]
    
    # Add pre-calculated metrics if available
    if "Total Active Strings" in filtered_df.columns:
        display_cols.append("Total Active Strings")
    if "Working String Count" in filtered_df.columns:
        display_cols.append("Working String Count")
    if "Failed String Count" in filtered_df.columns:
        display_cols.append("Failed String Count")
    if "Availability (%)" in filtered_df.columns:
        display_cols.append("Availability (%)")
    if "Failure Percentage (%)" in filtered_df.columns:
        display_cols.append("Failure Percentage (%)")
    
    # Add additional useful columns if available
    additional_cols = ["Grid", "E-Daily(KWH)", "Active Power", "Reactive Power", "VAB", "VBC", "VCA", "IA", "IB", "IC"]
    for col in additional_cols:
        if col in filtered_df.columns:
            display_cols.append(col)
    
    # Add PV columns based on selection
    pv_columns_to_show = []
    if show_voltage:
        pv_columns_to_show.extend(sorted(pv_voltage_cols))
    if show_current:
        pv_columns_to_show.extend(sorted(pv_current_cols))
    
    display_cols.extend(pv_columns_to_show)
    
    # Create display dataframe
    display_df = filtered_df[display_cols].copy()
    
    # Rename columns for better display
    rename_map = {inverter_col: "Inverter ID"}
    if "E-Daily(KWH)" in display_df.columns:
        rename_map["E-Daily(KWH)"] = "Energy (KWh)"
    if "Active Power" in display_df.columns:
        rename_map["Active Power"] = "Active Power (KW)"
    if "Reactive Power" in display_df.columns:
        rename_map["Reactive Power"] = "Reactive Power (KVAR)"
    if "Total Active Strings" in display_df.columns:
        rename_map["Total Active Strings"] = "Total Strings"
    if "Working String Count" in display_df.columns:
        rename_map["Working String Count"] = "Working"
    if "Failed String Count" in display_df.columns:
        rename_map["Failed String Count"] = "Failed"
    if "Failure Percentage (%)" in display_df.columns:
        rename_map["Failure Percentage (%)"] = "Failure %"
    if "VAB" in display_df.columns:
        rename_map["VAB"] = "VAB (V)"
    if "VBC" in display_df.columns:
        rename_map["VBC"] = "VBC (V)"
    if "VCA" in display_df.columns:
        rename_map["VCA"] = "VCA (V)"
    if "IA" in display_df.columns:
        rename_map["IA"] = "IA (A)"
    if "IB" in display_df.columns:
        rename_map["IB"] = "IB (A)"
    if "IC" in display_df.columns:
        rename_map["IC"] = "IC (A)"
    
    display_df = display_df.rename(columns=rename_map)
    
    # Update pv columns list for styling
    pv_current_cols_display = []
    pv_voltage_cols_display = []
    
    for col in pv_current_cols:
        if col in display_df.columns:
            pv_current_cols_display.append(col)
    
    for col in pv_voltage_cols:
        if col in display_df.columns:
            pv_voltage_cols_display.append(col)
    
    # Add color coding to headers and cells
    def apply_detailed_styling(df_display):
        styled = df_display.style
        
        # Color code PV column headers based on data health
        for col in pv_columns_to_show:
            if col in df_display.columns:
                # Calculate percentage of strings working for this column
                non_null = df_display[col].notna().sum()
                if non_null > 0:
                    working_count = (df_display[col] > WORKING_CURRENT_THRESHOLD).sum()
                    working_pct = (working_count / non_null) * 100
                    color = get_column_header_color(working_pct)
                    styled = styled.set_table_styles(
                        [{'selector': f'th.col{df_display.columns.get_loc(col)}',
                          'props': [('background-color', color), ('color', 'white'), ('font-weight', 'bold')]}],
                        overwrite=False
                    )
        
        # Color code cell values for PV current columns
        for col in pv_current_cols_display:
            if col in df_display.columns:
                styled = styled.map(
                    lambda x: f'background-color: {get_string_health_color(x)}; color: white; font-weight: bold;' 
                    if pd.notna(x) and isinstance(x, (int, float)) else '',
                    subset=[col]
                )
        
        # Color code Availability column
        if "Availability (%)" in df_display.columns:
            styled = styled.map(color_availability, subset=['Availability (%)'])
        
        # Color code Failed strings column
        if "Failed" in df_display.columns:
            styled = styled.map(color_failed_strings, subset=['Failed'])
        
        # Add column width styling
        styled = styled.set_table_styles([
            {'selector': 'thead th', 'props': [('position', 'sticky'), ('top', '0'), ('z-index', '999')]},
            {'selector': 'td', 'props': [('padding', '2px 4px'), ('font-size', '12px')]},
            {'selector': 'th', 'props': [('padding', '4px 8px'), ('font-size', '11px')]}
        ], overwrite=False)
        
        return styled
    
    # Display the styled dataframe
    if not display_df.empty:
        try:
            styled_df = apply_detailed_styling(display_df)
            st.dataframe(styled_df, use_container_width=True, height=400)
        except Exception as e:
            # Fallback to unstyled dataframe if styling fails
            st.warning(f"Styling error: {str(e)}. Showing unstyled data.")
            st.dataframe(display_df, use_container_width=True, height=400)
        
        # Individual inverter view
        st.markdown("---")
        st.subheader("🔍 Individual Inverter Analysis")
        
        # Let user select a specific inverter for detailed view
        inverter_list = sorted(filtered_df[inverter_col].unique())
        selected_single_inverter = st.selectbox("Select Inverter for Detailed View", inverter_list, key="single_inverter_view")
        
        if selected_single_inverter:
            inverter_data = filtered_df[filtered_df[inverter_col] == selected_single_inverter].iloc[0]
            
            # Display inverter details in columns
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Inverter", inverter_data[inverter_col])
            with col2:
                st.metric("Plot", inverter_data.get("Plot", "N/A"))
            with col3:
                st.metric("Block", inverter_data.get("Block", "N/A"))
            with col4:
                st.metric("SACU", inverter_data.get("SACU", "N/A"))
            with col5:
                # Use pre-calculated availability if available
                if "Availability (%)" in inverter_data and pd.notna(inverter_data["Availability (%)"]):
                    availability = inverter_data["Availability (%)"]
                else:
                    # Calculate manually
                    working = 0
                    total = 0
                    for col in pv_current_cols:
                        if col in inverter_data and pd.notna(inverter_data[col]):
                            total += 1
                            if inverter_data[col] > WORKING_CURRENT_THRESHOLD:
                                working += 1
                    availability = (working / total * 100) if total > 0 else 0
                st.metric("Availability", f"{availability:.1f}%")
            with col6:
                # Show string status
                if "Failed String Count" in inverter_data and pd.notna(inverter_data["Failed String Count"]):
                    failed = int(inverter_data["Failed String Count"])
                    st.metric("Failed Strings", failed)
            
            # Show string status visualization
            st.markdown("#### PV String Status")
            
            # Create columns for each string
            cols_per_row = 8
            for i in range(0, len(pv_current_cols), cols_per_row):
                string_cols = st.columns(cols_per_row)
                for idx, col in enumerate(pv_current_cols[i:i+cols_per_row]):
                    if col in inverter_data:
                        value = inverter_data[col]
                        if pd.notna(value):
                            status = "Working" if value > WORKING_CURRENT_THRESHOLD else "Failed"
                            color = "#10b981" if value > WORKING_CURRENT_THRESHOLD else "#ef4444"
                            with string_cols[idx]:
                                st.markdown(f"""
                                <div style='background-color: {color}; padding: 8px; border-radius: 5px; text-align: center; color: white; margin: 2px;'>
                                    <div style='font-size: 10px;'>{col}</div>
                                    <div style='font-size: 14px; font-weight: bold;'>{value:.1f}A</div>
                                    <div style='font-size: 9px;'>{status}</div>
                                </div>
                                """, unsafe_allow_html=True)
            
            # Additional inverter metrics if available
            st.markdown("#### Additional Metrics")
            metric_cols = st.columns(4)
            
            additional_metrics = [
                ("Grid", "Grid"),
                ("E-Daily(KWH)", "Energy (KWh)"),
                ("Active Power", "Active Power (KW)"),
                ("Reactive Power", "Reactive Power (KVAR)")
            ]
            
            for idx, (col, label) in enumerate(additional_metrics):
                if col in inverter_data and pd.notna(inverter_data[col]):
                    with metric_cols[idx]:
                        st.metric(label, f"{inverter_data[col]:.2f}" if isinstance(inverter_data[col], (int, float)) else inverter_data[col])
            
            # Show voltage summary
            if pv_voltage_cols:
                st.markdown("#### PV Voltage Summary")
                voltage_values = []
                for col in pv_voltage_cols:
                    if col in inverter_data and pd.notna(inverter_data[col]):
                        voltage_values.append(inverter_data[col])
                
                if voltage_values:
                    vol_cols = st.columns(4)
                    vol_cols[0].metric("Average Voltage", f"{sum(voltage_values)/len(voltage_values):.1f}V")
                    vol_cols[1].metric("Min Voltage", f"{min(voltage_values):.1f}V")
                    vol_cols[2].metric("Max Voltage", f"{max(voltage_values):.1f}V")
                    vol_cols[3].metric("Voltage Differential", f"{max(voltage_values)-min(voltage_values):.1f}V")
            
            # Show grid metrics if available
            if "VAB" in inverter_data and "VBC" in inverter_data and "VCA" in inverter_data:
                st.markdown("#### Grid Voltage")
                grid_cols = st.columns(3)
                grid_cols[0].metric("VAB", f"{inverter_data['VAB']:.1f}V" if pd.notna(inverter_data['VAB']) else "N/A")
                grid_cols[1].metric("VBC", f"{inverter_data['VBC']:.1f}V" if pd.notna(inverter_data['VBC']) else "N/A")
                grid_cols[2].metric("VCA", f"{inverter_data['VCA']:.1f}V" if pd.notna(inverter_data['VCA']) else "N/A")
            
            if "IA" in inverter_data and "IB" in inverter_data and "IC" in inverter_data:
                st.markdown("#### Grid Current")
                grid_cols = st.columns(3)
                grid_cols[0].metric("IA", f"{inverter_data['IA']:.1f}A" if pd.notna(inverter_data['IA']) else "N/A")
                grid_cols[1].metric("IB", f"{inverter_data['IB']:.1f}A" if pd.notna(inverter_data['IB']) else "N/A")
                grid_cols[2].metric("IC", f"{inverter_data['IC']:.1f}A" if pd.notna(inverter_data['IC']) else "N/A")
    else:
        st.info("No PV string data available for the selected filters")

# def main_dashboard_tab(df):
#     """Main dashboard tab"""
#     st.title("Solar PV String Availability Dashboard")
#     st.caption(f"Inverters: {len(df)}")
    
#     # Find the actual inverter column for display
#     inverter_col = None
#     df_columns_lower_map = {str(c).strip().lower(): c for c in df.columns}
    
#     for col in INVERTER_ID_COLS:
#         if col in df.columns:
#             inverter_col = col
#             break
#         elif col.strip().lower() in df_columns_lower_map:
#             inverter_col = df_columns_lower_map[col.strip().lower()]
#             break
    
#     # KPIs
#     kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    
#     total_inverters = df[inverter_col].nunique() if inverter_col and inverter_col in df.columns else 0
#     total_strings = int(df["Total Active Strings"].sum()) if "Total Active Strings" in df.columns else 0
#     working_strings = int(df["Working String Count"].sum()) if "Working String Count" in df.columns else 0
#     failed_strings = int(df["Failed String Count"].sum()) if "Failed String Count" in df.columns else 0
#     overall_availability = round((working_strings / total_strings) * 100, 2) if total_strings > 0 else 0.0
    
#     kpi1.metric("Total Inverters", f"{total_inverters:,}")
#     kpi2.metric("Total Active Strings", f"{total_strings:,}")
#     kpi3.metric("Working Strings", f"{working_strings:,}")
#     kpi4.metric("Failed Strings", f"{failed_strings:,}")
#     kpi5.metric("Availability", f"{overall_availability:.2f}%")
    
#     st.markdown("---")
    
#     col1, col2 = st.columns(2)
    
#     with col1:
#         st.subheader("Block-wise Strings")
#         if not df.empty:
#             block_summary = df.groupby("Block", as_index=False).agg(
#                 Total_Active_Strings=("Total Active Strings", "sum"),
#                 Working_String_Count=("Working String Count", "sum"),
#                 Failed_String_Count=("Failed String Count", "sum")
#             )
#             fig_bar = px.bar(
#                 block_summary,
#                 x="Block",
#                 y=["Working_String_Count", "Failed_String_Count"],
#                 barmode="stack",
#                 color_discrete_map={
#                     "Working_String_Count": "#10b981",
#                     "Failed_String_Count": "#ef4444"
#                 }
#             )
#             fig_bar.update_layout(height=400)
#             st.plotly_chart(fig_bar, use_container_width=True)
#         else:
#             st.warning("No records available for the selected filters.")
    
#     with col2:
#         st.subheader("String Health")
#         fig_pie = go.Figure(data=[go.Pie(
#             labels=["Working Strings", "Failed Strings"],
#             values=[working_strings, failed_strings],
#             hole=0.55,
#             marker_colors=["#10b981", "#ef4444"]
#         )])
#         fig_pie.update_layout(height=400)
#         st.plotly_chart(fig_pie, use_container_width=True)
    
#     st.markdown("---")
#     st.subheader("Block Summary")
    
#     if not df.empty:
#         block_table = df.groupby("Block", as_index=False).agg(
#             Total_Inverters=(inverter_col if inverter_col else df.columns[0], "nunique"),
#             Total_Active_Strings=("Total Active Strings", "sum"),
#             Total_Working_Strings=("Working String Count", "sum"),
#             Total_Failed_Strings=("Failed String Count", "sum")
#         )
#         block_table["Availability (%)"] = (
#             (block_table["Total_Working_Strings"] / block_table["Total_Active_Strings"]) * 100
#         ).fillna(0).round(2)
#         block_table["Failure Percentage (%)"] = (
#             (block_table["Total_Failed_Strings"] / block_table["Total_Active_Strings"]) * 100
#         ).fillna(0).round(2)
        
#         st.dataframe(block_table, use_container_width=True)
#     else:
#         st.warning("No block summary available.")
@st.cache_data(ttl=300)  # Cache for 5 minutes
def calculate_plot_summary(df, inverter_col):
    """Calculate plot-wise summary with caching"""
    if df.empty:
        return pd.DataFrame()
    
    plot_summary = df.groupby("Plot", as_index=False).agg(
        Total_Inverters=(inverter_col if inverter_col else df.columns[0], "nunique"),
        Total_Active_Strings=("Total Active Strings", "sum"),
        Total_Working_Strings=("Working String Count", "sum"),
        Total_Failed_Strings=("Failed String Count", "sum")
    )
    
    plot_summary["Availability (%)"] = (
        (plot_summary["Total_Working_Strings"] / plot_summary["Total_Active_Strings"]) * 100
    ).fillna(0).round(2)
    
    plot_summary["Failure Percentage (%)"] = (
        (plot_summary["Total_Failed_Strings"] / plot_summary["Total_Active_Strings"]) * 100
    ).fillna(0).round(2)
    
    plot_summary["Health Status"] = plot_summary["Availability (%)"].apply(
        lambda x: "🟢 Excellent" if x >= 90 else "🟡 Good" if x >= 70 else "🟠 Fair" if x >= 50 else "🔴 Poor"
    )
    
    # Add Block count per plot
    block_count = df.groupby("Plot")["Block"].nunique().reset_index(name="Total_Blocks")
    plot_summary = plot_summary.merge(block_count, on="Plot", how="left")
    
    return plot_summary

@st.cache_data(ttl=300)
def create_plot_charts(plot_summary):
    """Create all charts with caching - Plot wise"""
    charts = {}
    
    # 1. Stacked Bar Chart - Working vs Failed by Plot
    fig_bar = px.bar(
        plot_summary,
        x="Plot",
        y=["Total_Working_Strings", "Total_Failed_Strings"],
        barmode="stack",
        title="📊 Plot-wise String Status",
        labels={
            "value": "Number of Strings",
            "Plot": "Plot",
            "variable": "Status"
        },
        color_discrete_map={
            "Total_Working_Strings": "#10b981",
            "Total_Failed_Strings": "#ef4444"
        },
        text_auto=True
    )
    fig_bar.update_layout(
        height=450,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12)
    )
    fig_bar.update_traces(
        textfont_size=12,
        textposition="inside",
        insidetextanchor="middle"
    )
    # Format y-axis to show full numbers without k - Fixed: update_yaxes
    fig_bar.update_yaxes(
        tickformat=",.0f",
        tickprefix="",
        ticksuffix=""
    )
    charts["bar"] = fig_bar
    
    # 2. Horizontal Bar Chart - Availability by Plot
    plot_summary_sorted = plot_summary.sort_values("Availability (%)", ascending=True)
    
    fig_avail = px.bar(
        plot_summary_sorted,
        x="Availability (%)",
        y="Plot",
        orientation="h",
        title="📈 Plot-wise Availability (%)",
        labels={
            "Availability (%)": "Availability (%)",
            "Plot": "Plot"
        },
        color="Availability (%)",
        color_continuous_scale=[
            [0, "#ef4444"],
            [0.3, "#f59e0b"],
            [0.5, "#fbbf24"],
            [0.7, "#34d399"],
            [1, "#10b981"]
        ],
        range_color=[0, 100],
        text_auto=".1f"
    )
    fig_avail.update_layout(
        height=400,
        hovermode="y unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
        coloraxis_showscale=False,
        xaxis=dict(range=[0, 105])
    )
    fig_avail.update_traces(
        textposition="outside",
        textfont_size=12
    )
    charts["availability"] = fig_avail
    
    # 3. Donut Chart - Overall Health
    total_working = plot_summary["Total_Working_Strings"].sum()
    total_failed = plot_summary["Total_Failed_Strings"].sum()
    
    fig_donut = go.Figure(data=[go.Pie(
        labels=["✅ Working Strings", "❌ Failed Strings"],
        values=[total_working, total_failed],
        hole=0.6,
        marker_colors=["#10b981", "#ef4444"],
        textinfo="label+percent",
        textposition="auto",
        pull=[0.05, 0]
    )])
    fig_donut.update_layout(
        height=400,
        title="🎯 Overall String Health",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
        annotations=[dict(
            text=f"<b>{total_working + total_failed:,}</b><br>Total Strings",
            x=0.5, y=0.5,
            font_size=16,
            showarrow=False
        )]
    )
    charts["donut"] = fig_donut
    
    # 4. Scatter Plot - Inverters vs Strings by Plot
    fig_scatter = px.scatter(
        plot_summary,
        x="Total_Inverters",
        y="Total_Active_Strings",
        size="Total_Active_Strings",
        color="Availability (%)",
        text="Plot",
        title="📍 Plot Distribution: Inverters vs Strings",
        labels={
            "Total_Inverters": "Number of Inverters",
            "Total_Active_Strings": "Total Strings",
            "Availability (%)": "Availability"
        },
        color_continuous_scale=[
            [0, "#ef4444"],
            [0.3, "#f59e0b"],
            [0.5, "#fbbf24"],
            [0.7, "#34d399"],
            [1, "#10b981"]
        ],
        range_color=[0, 100],
        size_max=60
    )
    fig_scatter.update_traces(
        textposition="top center",
        marker=dict(line=dict(width=1, color='white'))
    )
    fig_scatter.update_layout(
        height=400,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
        hovermode="closest"
    )
    # Format axes to show full numbers without k - Fixed: update_xaxes and update_yaxes
    fig_scatter.update_xaxes(
        tickformat=",.0f",
        tickprefix="",
        ticksuffix=""
    )
    fig_scatter.update_yaxes(
        tickformat=",.0f",
        tickprefix="",
        ticksuffix=""
    )
    charts["scatter"] = fig_scatter
    
    # 5. Treemap - Plot Distribution
    fig_treemap = px.treemap(
        plot_summary,
        path=["Plot"],
        values="Total_Active_Strings",
        color="Availability (%)",
        color_continuous_scale=[
            [0, "#ef4444"],
            [0.3, "#f59e0b"],
            [0.5, "#fbbf24"],
            [0.7, "#34d399"],
            [1, "#10b981"]
        ],
        range_color=[0, 100],
        title="🎨 String Distribution by Plot",
        hover_data={
            "Total_Active_Strings": True,
            "Total_Working_Strings": True,
            "Total_Failed_Strings": True,
            "Total_Inverters": True,
            "Total_Blocks": True,
            "Availability (%)": ":.1f%"
        }
    )
    fig_treemap.update_traces(
        textinfo="label+value",
        textfont_size=14,
        marker=dict(cornerradius=4),
        hovertemplate='<b>%{label}</b><br>' +
                      'Total Strings: %{value:,.0f}<br>' +
                      'Availability: %{color:,.1f}%<extra></extra>'
    )
    fig_treemap.update_layout(
        height=400,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
        coloraxis_showscale=False
    )
    charts["treemap"] = fig_treemap
    
    return charts

def display_plot_metrics(plot_summary):
    """Display plot-wise metric cards"""
    st.subheader("📊 Plot-wise Performance Overview")
    
    # Create metric cards for each plot
    cols = st.columns(min(4, len(plot_summary)))
    
    for idx, (_, row) in enumerate(plot_summary.iterrows()):
        if idx >= 4:
            break
        
        col_idx = idx % 4
        with cols[col_idx]:
            # Determine color based on availability
            avail = row["Availability (%)"]
            if avail >= 90:
                status_color = "#10b981"
                status_icon = "🟢"
                status_text = "Excellent"
            elif avail >= 70:
                status_color = "#34d399"
                status_icon = "🟡"
                status_text = "Good"
            elif avail >= 50:
                status_color = "#fbbf24"
                status_icon = "🟠"
                status_text = "Fair"
            else:
                status_color = "#ef4444"
                status_icon = "🔴"
                status_text = "Poor"
            
            st.markdown(f"""
            <div style='background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border: 2px solid {status_color}; border-radius: 12px; padding: 15px; margin: 5px 0;'>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <h3 style='margin: 0; color: #f1f5f9;'>{row['Plot']}</h3>
                    <span style='font-size: 24px;'>{status_icon}</span>
                </div>
                <div style='margin-top: 8px;'>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #94a3b8; font-size: 12px;'>Status</span>
                        <span style='color: {status_color}; font-weight: bold; font-size: 14px;'>{status_text}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-top: 4px;'>
                        <span style='color: #94a3b8; font-size: 12px;'>Inverters</span>
                        <span style='color: #f1f5f9; font-weight: bold;'>{int(row['Total_Inverters']):,}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #94a3b8; font-size: 12px;'>Total Strings</span>
                        <span style='color: #f1f5f9; font-weight: bold;'>{int(row['Total_Active_Strings']):,}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between;'>
                        <span style='color: #94a3b8; font-size: 12px;'>✅ Working</span>
                        <span style='color: #10b981; font-weight: bold;'>{int(row['Total_Working_Strings']):,}</span>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-bottom: 8px;'>
                        <span style='color: #94a3b8; font-size: 12px;'>❌ Failed</span>
                        <span style='color: #ef4444; font-weight: bold;'>{int(row['Total_Failed_Strings']):,}</span>
                    </div>
                    <div style='background-color: #1e293b; height: 8px; border-radius: 4px; overflow: hidden;'>
                        <div style='background: linear-gradient(90deg, {status_color}, {status_color}88); width: {avail}%; height: 100%;'></div>
                    </div>
                    <div style='display: flex; justify-content: space-between; margin-top: 4px;'>
                        <span style='color: #94a3b8; font-size: 11px;'>Availability</span>
                        <span style='color: {status_color}; font-weight: bold; font-size: 16px;'>{avail:.1f}%</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

def main_dashboard_tab(df):
    """Main dashboard tab with Plot-wise visualizations"""
    st.title("☀️ PV String Performance Dashboard")
    
    # Find the actual inverter column for display
    inverter_col = None
    df_columns_lower_map = {str(c).strip().lower(): c for c in df.columns}
    
    for col in INVERTER_ID_COLS:
        if col in df.columns:
            inverter_col = col
            break
        elif col.strip().lower() in df_columns_lower_map:
            inverter_col = df_columns_lower_map[col.strip().lower()]
            break
    
    # Calculate metrics using cached function - Plot wise
    plot_summary = calculate_plot_summary(df, inverter_col)
    
    # KPIs
    st.markdown("### 0 Key Performance Indicators")
    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    
    total_inverters = df[inverter_col].nunique() if inverter_col and inverter_col in df.columns else 0
    total_strings = int(df["Total Active Strings"].sum()) if "Total Active Strings" in df.columns else 0
    working_strings = int(df["Working String Count"].sum()) if "Working String Count" in df.columns else 0
    failed_strings = int(df["Failed String Count"].sum()) if "Failed String Count" in df.columns else 0
    overall_availability = round((working_strings / total_strings) * 100, 2) if total_strings > 0 else 0.0
    num_plots = plot_summary["Plot"].nunique() if not plot_summary.empty else 0
    
    kpi1.metric("🏗️ Total Plots", f"{num_plots:,}")
    kpi2.metric("🔌 Total Inverters", f"{total_inverters:,}")
    kpi3.metric("📊 Total Strings", f"{total_strings:,}")
    kpi4.metric("✅ Working", f"{working_strings:,}")
    kpi5.metric("❌ Failed", f"{failed_strings:,}")
    kpi6.metric("📈 Availability", f"{overall_availability:.1f}%")
    
    st.markdown("---")
    
    # Display plot metrics cards
    if not plot_summary.empty:
        display_plot_metrics(plot_summary)
        st.markdown("---")
    
    # Charts Section
    st.subheader("Plot-wise Visualization Dashboard")
    st.caption("Understanding your PV plant performance at a glance")
    
    # Create charts with caching
    charts = create_plot_charts(plot_summary)
    
    # Row 1: Stacked Bar Chart and Donut Chart
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.plotly_chart(charts["bar"], use_container_width=True, key="plot_bar")
    
    with col2:
        st.plotly_chart(charts["donut"], use_container_width=True, key="overall_donut")
    
    # Row 2: Availability Chart and Treemap
    col1, col2 = st.columns(2)
    
    with col1:
        st.plotly_chart(charts["availability"], use_container_width=True, key="avail_bar")
    
    with col2:
        st.plotly_chart(charts["treemap"], use_container_width=True, key="plot_treemap")
    
    # Row 3: Scatter Plot
    st.plotly_chart(charts["scatter"], use_container_width=True, key="plot_scatter")
    
    st.markdown("---")
    
    # Plot Summary Table with enhanced styling
    st.subheader("Detailed Plot Summary")
    
    if not plot_summary.empty:
        # Prepare display dataframe
        display_plot_df = plot_summary.copy()
        
        # Reorder columns for better readability
        display_plot_df = display_plot_df[[
            "Plot", "Total_Blocks", "Total_Inverters", 
            "Total_Active_Strings", "Total_Working_Strings", "Total_Failed_Strings",
            "Availability (%)", "Failure Percentage (%)", "Health Status"
        ]]
        
        # Style the dataframe
        def color_health_status(val):
            if "Excellent" in str(val):
                return 'background-color: #10b981; color: white; font-weight: bold; border-radius: 4px;'
            elif "Good" in str(val):
                return 'background-color: #34d399; color: white; font-weight: bold; border-radius: 4px;'
            elif "Fair" in str(val):
                return 'background-color: #fbbf24; color: black; font-weight: bold; border-radius: 4px;'
            elif "Poor" in str(val):
                return 'background-color: #ef4444; color: white; font-weight: bold; border-radius: 4px;'
            return ''
        
        styled_plot_df = display_plot_df.style.map(color_health_status, subset=['Health Status'])
        
        # Format numeric columns with commas
        styled_plot_df = styled_plot_df.format({
            'Total_Active_Strings': '{:,.0f}',
            'Total_Working_Strings': '{:,.0f}',
            'Total_Failed_Strings': '{:,.0f}',
            'Total_Inverters': '{:,.0f}',
            'Total_Blocks': '{:,.0f}',
            'Availability (%)': '{:.1f}%',
            'Failure Percentage (%)': '{:.1f}%'
        })
        
        # Add bar visualization for availability
        def availability_bar(val):
            if isinstance(val, (int, float)):
                color = "#10b981" if val >= 90 else "#34d399" if val >= 70 else "#fbbf24" if val >= 50 else "#ef4444"
                return f'background: linear-gradient(90deg, {color} {val}%, transparent {val}%); font-weight: bold; padding: 4px 8px; border-radius: 4px;'
            return ''
        
        styled_plot_df = styled_plot_df.map(availability_bar, subset=['Availability (%)'])
        
        st.dataframe(
            styled_plot_df,
            use_container_width=True,
            column_config={
                "Plot": "📍 Plot",
                "Total_Blocks": "🏗️ Blocks",
                "Total_Inverters": "🔌 Inverters",
                "Total_Active_Strings": "📊 Total Strings",
                "Total_Working_Strings": "✅ Working",
                "Total_Failed_Strings": "❌ Failed",
                "Availability (%)": "📈 Availability",
                "Failure Percentage (%)": "⚠️ Failure %",
                "Health Status": "💚 Health"
            }
        )
        
        # Export buttons
        col1, col2 = st.columns(2)
        
        with col1:
            csv = plot_summary.to_csv(index=False)
            st.download_button(
                label="📥 Download Plot Summary (CSV)",
                data=csv,
                file_name=f"plot_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Summary insights
            best_plot = plot_summary.loc[plot_summary["Availability (%)"].idxmax()]
            worst_plot = plot_summary.loc[plot_summary["Availability (%)"].idxmin()]
            
            st.info(f"""
            **💡 Insights:**
            - Best performing plot: **{best_plot['Plot']}** ({best_plot['Availability (%)']:.1f}% availability)
            - Needs attention: **{worst_plot['Plot']}** ({worst_plot['Availability (%)']:.1f}% availability)
            - Total working strings: **{working_strings:,}** out of **{total_strings:,}**
            
            """)
    else:
        st.warning("No plot summary available.")
# ==========================================
# 9. MAIN APP (UPDATED)
# ==========================================
def main():
    # Initialize default users
    # init_default_users()
    
    # Check authentication
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    # Login UI
    if not st.session_state.authenticated:
        st.title("☀️ PV String Analytics")
        st.markdown("### Login to access the dashboard")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            if st.button("Login", use_container_width=True):
                user_data = authenticate_user(username, password)
                if user_data:
                    st.session_state.user = {
                        "username": username,
                        "role": user_data["role"],
                        "aPssigned_plots": user_data.get("assigned_plots", [])
                    }
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Invalid username or password")
        
        st.markdown("---")
        st.caption("Default users:  ")
        return
    
    # Get current user
    current_user = get_current_user()
    if not current_user:
        st.error("User not found")
        return
    
    # Sidebar
    st.sidebar.title("⚡ PV SCADA Control")
    
    # User info
    role_badge = "👑 Admin" if current_user["role"] == "admin" else "🔧 Engineer"
    st.sidebar.markdown(f"**User:** {current_user['username']} ({role_badge})")
    
    # Logout
    if st.sidebar.button("🚪 Logout"):
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # File upload section
    st.sidebar.subheader("📁 File Management")
    
    # Check if file exists in backend
    if "current_file" not in st.session_state:
        latest_file = get_latest_excel_file()
        if latest_file:
            st.session_state.current_file = latest_file
    
    # Show current file info
    if "current_file" in st.session_state:
        metadata_file = EXCEL_FILES_DIR / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            if st.session_state.current_file in metadata:
                st.sidebar.info(f"📄 Current file: {metadata[st.session_state.current_file]['originalfilename']}\n📅 {metadata[st.session_state.current_file]['timestamp']}")
    
    # File upload
    uploaded_file = st.sidebar.file_uploader("Upload new SCADA Report (.xlsx)", type=["xlsx"])
    if uploaded_file:
        file_bytes = uploaded_file.getvalue()
        stored_filename = save_excel_file(file_bytes, uploaded_file.name)
        st.sidebar.success(f"✅ File uploaded: {uploaded_file.name}")
        st.rerun()
    
    # Load data from backend
    if "current_file" not in st.session_state:
        st.info("No SCADA file available. Please upload one.")
        return
    
    file_bytes = load_excel_from_backend(st.session_state.current_file)
    if not file_bytes:
        st.error("Could not load file from backend storage")
        return
    
    # Process data
    processed_dataframes = process_scada_excel_bytes(file_bytes)
    
    if not processed_dataframes:
        st.error("No valid sheets or inverter columns were identified in the uploaded workbook.")
        return
    
    # Apply user permissions
    if current_user["role"] == "engineer":
        allowed_plots = current_user.get("assigned_plots", [])
        if allowed_plots:
            st.sidebar.markdown("---")
            st.sidebar.subheader("🔒 Assigned Plots")
            st.sidebar.write(", ".join(allowed_plots))
    
    # Sheet selection
    sheet_selection = st.sidebar.selectbox("Select Sheet", list(processed_dataframes.keys()))
    df_selected = processed_dataframes[sheet_selection].copy()
    
    # Apply plot filter based on user role
    if current_user["role"] == "engineer":
        allowed_plots = current_user.get("assigned_plots", [])
        if allowed_plots:
            df_selected = df_selected[df_selected["Plot"].isin(allowed_plots)]
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")
    
    # Filters
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
    
    # User management (Admin only)
    if current_user["role"] == "admin":
        user_management_ui()
    
    # Find inverter column for display
    inverter_col = None
    df_columns_lower_map = {str(c).strip().lower(): c for c in filtered_df.columns}
    
    for col in INVERTER_ID_COLS:
        if col in filtered_df.columns:
            inverter_col = col
            break
        elif col.strip().lower() in df_columns_lower_map:
            inverter_col = df_columns_lower_map[col.strip().lower()]
            break
    
    # Main content with tabs
    tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🔌 PV String Details", "📋 Data Table"])
    
    with tab1:
        if not filtered_df.empty:
            main_dashboard_tab(filtered_df)
        else:
            st.warning("No data available with current filters and permissions")
    
    with tab2:
        if not filtered_df.empty:
            create_pv_string_tab(filtered_df)
        else:
            st.warning("No data available for PV string analysis")
    
    with tab3:
        st.subheader("Inverter Data Table")
        if not filtered_df.empty:
            # Rename inverter column for display
            display_df = filtered_df.copy()
            if inverter_col and inverter_col != "Inverter ID":
                display_df = display_df.rename(columns={inverter_col: "Inverter ID"})
            
            st.dataframe(
                display_df,
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
            
            # Download button
            download_bytes = create_excel_download({sheet_selection: filtered_df})
            st.download_button(
                label="📥 Download Filtered Excel",
                data=download_bytes,
                file_name=f"processed_{sheet_selection}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.info("No data available")

if __name__ == "__main__":
    main()