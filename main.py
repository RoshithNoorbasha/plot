import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import io

st.set_page_config(
    page_title="Utility-Scale Solar String Dashboard - Plot 1",
    layout="wide",
    initial_sidebar_state="expanded"
)

WORK_START = time(6, 0)
WORK_END = time(18, 0)
FILE_PATH = "strings_data_file.xlsx"
OUTPUT_PATH = "String_Master_Plot1_Updated.xlsx"

st.markdown("""
    <style>
    .main {
        background: linear-gradient(180deg, #f6f9fc 0%, #eef4f9 100%);
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    .stMetric {
        background: white;
        border-radius: 16px;
        padding: 14px;
        box-shadow: 0 4px 18px rgba(0,0,0,0.06);
        border: 1px solid #e7edf3;
    }
    h1, h2, h3 {
        color: #16324f;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data
def load_data(filepath=FILE_PATH):
    try:
        df = pd.read_excel(filepath, sheet_name="String_Master")
        for col in ["Failure Date & Time", "Restored Date & Time"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    except FileNotFoundError:
        st.error(f"File not found: {filepath}")
        return pd.DataFrame()

def save_data(df, output_path=OUTPUT_PATH):
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="String_Master", index=False)

def calculate_working_hours(start_dt, end_dt, work_start=WORK_START, work_end=WORK_END):
    if pd.isna(start_dt) or pd.isna(end_dt) or end_dt <= start_dt:
        return 0.0

    total_seconds = 0
    current_day = start_dt.date()
    last_day = end_dt.date()

    while current_day <= last_day:
        day_start = datetime.combine(current_day, work_start)
        day_end = datetime.combine(current_day, work_end)

        effective_start = max(start_dt, day_start)
        effective_end = min(end_dt, day_end)

        if effective_end > effective_start:
            total_seconds += (effective_end - effective_start).total_seconds()

        current_day += timedelta(days=1)

    return round(total_seconds / 3600, 2)

def derive_status(row):
    failure_dt = row.get("Failure Date & Time", pd.NaT)
    restored_dt = row.get("Restored Date & Time", pd.NaT)

    if pd.isna(failure_dt) and pd.isna(restored_dt):
        return ""
    elif pd.notna(failure_dt) and pd.isna(restored_dt):
        return "OPEN"
    elif pd.notna(failure_dt) and pd.notna(restored_dt):
        return "CLOSED"
    return ""

def enrich_fault_metrics(df):
    df = df.copy()
    now = datetime.now()

    df["Failure Date & Time"] = pd.to_datetime(df["Failure Date & Time"], errors="coerce")
    df["Restored Date & Time"] = pd.to_datetime(df["Restored Date & Time"], errors="coerce")

    df["Status"] = df.apply(derive_status, axis=1)

    df["Turn Around Time"] = df.apply(
        lambda row: calculate_working_hours(
            row["Failure Date & Time"], row["Restored Date & Time"]
        ) if row["Status"] == "CLOSED" else 0.0,
        axis=1
    )

    df["Present Failure Hours"] = df.apply(
        lambda row: calculate_working_hours(row["Failure Date & Time"], now)
        if row["Status"] == "OPEN" and pd.notna(row["Failure Date & Time"]) else 0.0,
        axis=1
    )

    df["Current Loss Hours"] = df.apply(
        lambda row: row["Present Failure Hours"] if row["Status"] == "OPEN"
        else row["Turn Around Time"] if row["Status"] == "CLOSED"
        else 0.0,
        axis=1
    )

    return df

def get_download_excel_bytes(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="String_Master", index=False)
    buffer.seek(0)
    return buffer

def get_options(df, col):
    if col not in df.columns:
        return []
    return sorted([x for x in df[col].dropna().astype(str).unique().tolist() if str(x).strip() != ""])

df_master = load_data()

if not df_master.empty:
    if "Serial Number" not in df_master.columns:
        df_master["Serial Number"] = None

    df_master = enrich_fault_metrics(df_master)

    st.sidebar.header("Plant Hierarchy Filter")

    blocks = ["All"] + get_options(df_master, "Block")
    selected_block = st.sidebar.selectbox("Select Block", blocks)

    df_filtered = df_master if selected_block == "All" else df_master[df_master["Block"].astype(str) == selected_block]

    sacus = ["All"] + get_options(df_filtered, "SACU")
    selected_sacu = st.sidebar.selectbox("Select SACU", sacus)
    if selected_sacu != "All":
        df_filtered = df_filtered[df_filtered["SACU"].astype(str) == selected_sacu]

    inverters = ["All"] + get_options(df_filtered, "Inverter ID")
    selected_inverter = st.sidebar.selectbox("Select Inverter", inverters)
    if selected_inverter != "All":
        df_filtered = df_filtered[df_filtered["Inverter ID"].astype(str) == selected_inverter]

    selected_status = st.sidebar.selectbox("Fault Status", ["All", "OPEN", "CLOSED", ""])
    if selected_status != "All":
        df_filtered = df_filtered[df_filtered["Status"] == selected_status]

    st.title("Utility-Scale Solar String Monitoring Dashboard")
    st.caption("Business-hour fault analytics | Working hours: 6:00 AM to 6:00 PM")

    total_strings = len(df_filtered)
    open_faults = len(df_filtered[df_filtered["Status"] == "OPEN"])
    closed_faults = len(df_filtered[df_filtered["Status"] == "CLOSED"])
    availability = ((total_strings - open_faults) / total_strings * 100) if total_strings else 0
    avg_tat = df_filtered.loc[df_filtered["Status"] == "CLOSED", "Turn Around Time"].mean()
    avg_open_age = df_filtered.loc[df_filtered["Status"] == "OPEN", "Present Failure Hours"].mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Availability", f"{availability:.2f}%")
    c2.metric("Open Faults", open_faults)
    c3.metric("Closed Faults", closed_faults)
    c4.metric("Avg TAT", f"{0 if pd.isna(avg_tat) else avg_tat:.2f} hrs")
    c5.metric("Avg Open Age", f"{0 if pd.isna(avg_open_age) else avg_open_age:.2f} hrs")

    tab1, tab2, tab3 = st.tabs([
        "Fault Analytics",
        "Failure / Rectified Entry",
        "Live Fault Editor"
    ])

    with tab1:
        st.subheader("Open Faults by Block")
        fault_counts = (
            df_filtered[df_filtered["Status"] == "OPEN"]
            .groupby("Block")["String No"]
            .count()
            .reset_index(name="Open Faults")
        )

        if not fault_counts.empty:
            st.bar_chart(fault_counts.set_index("Block"))
        else:
            st.success("No active open faults in current filter.")

        st.subheader("Fault Details")
        st.dataframe(
            df_filtered[[
                "Plot", "Block", "SACU", "Inverter ID", "String No",
                "Failure Date & Time", "Restored Date & Time",
                "Present Failure Hours", "Remarks", "Status"
            ]].sort_values(by="Present Failure Hours", ascending=False),
            use_container_width=True
        )

    with tab2:
        st.subheader("Failure / Rectified Entry")

        action_mode = st.radio(
            "Select Action",
            ["New Failure", "Rectified / Restoration"],
            horizontal=True
        )

        if action_mode == "New Failure":
            plot_options = get_options(df_master, "Plot")
            plot_val = st.selectbox("Plot", plot_options)

            df_plot = df_master[df_master["Plot"].astype(str) == str(plot_val)]
            block_val = st.selectbox("Block", get_options(df_plot, "Block"))

            df_block = df_plot[df_plot["Block"].astype(str) == str(block_val)]
            sacu_val = st.selectbox("SACU", get_options(df_block, "SACU"))

            df_sacu = df_block[df_block["SACU"].astype(str) == str(sacu_val)]
            inverter_val = st.selectbox("Inverter ID", get_options(df_sacu, "Inverter ID"))

            df_inverter = df_sacu[df_sacu["Inverter ID"].astype(str) == str(inverter_val)]
            string_options = get_options(df_inverter, "String No")
            string_val = st.selectbox("String No", string_options)

            matched_row = df_inverter[df_inverter["String No"].astype(str) == str(string_val)].head(1)

            existing_serial = ""
            if not matched_row.empty and "Serial Number" in matched_row.columns:
                existing_serial = str(matched_row.iloc[0]["Serial Number"]) if pd.notna(matched_row.iloc[0]["Serial Number"]) else ""

            if existing_serial.strip() == "":
                serial_number = st.text_input("Serial Number (Optional)", key="new_serial")
            else:
                st.text_input("Serial Number", value=existing_serial, disabled=True)
                serial_number = existing_serial

            remarks_val = st.text_area("Failure Remarks", key="new_remarks")

            c1, c2 = st.columns(2)
            with c1:
                failure_date = st.date_input("Failure Date", value=datetime.now().date(), key="failure_date")
            with c2:
                failure_time = st.time_input("Failure Time", value=datetime.now().time().replace(second=0, microsecond=0), key="failure_time")

            if st.button("Save Failure Entry", type="primary"):
                failure_dt = datetime.combine(failure_date, failure_time)

                duplicate_open = df_master[
                    (df_master["Plot"].astype(str) == str(plot_val)) &
                    (df_master["Block"].astype(str) == str(block_val)) &
                    (df_master["SACU"].astype(str) == str(sacu_val)) &
                    (df_master["Inverter ID"].astype(str) == str(inverter_val)) &
                    (df_master["String No"].astype(str) == str(string_val)) &
                    (df_master["Status"] == "OPEN")
                ]

                if not duplicate_open.empty:
                    st.warning("An open fault already exists for this string.")
                else:
                    new_row = {col: None for col in df_master.columns}
                    new_row.update({
                        "Plot": plot_val,
                        "Block": block_val,
                        "SACU": sacu_val,
                        "Inverter ID": inverter_val,
                        "String No": string_val,
                        "Serial Number": serial_number if str(serial_number).strip() != "" else None,
                        "Remarks": remarks_val,
                        "Failure Date & Time": failure_dt,
                        "Restored Date & Time": pd.NaT
                    })

                    df_master = pd.concat([df_master, pd.DataFrame([new_row])], ignore_index=True)
                    df_master = enrich_fault_metrics(df_master)
                    save_data(df_master)

                    st.success("New failure entry added successfully.")
                    st.download_button(
                        "Download Updated Excel",
                        data=get_download_excel_bytes(df_master),
                        file_name="String_Master_Plot1_Updated.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    st.rerun()

        else:
            open_df = df_master[df_master["Status"] == "OPEN"].copy()

            if open_df.empty:
                st.success("No open faults available for rectification.")
            else:
                open_df["Fault Key"] = open_df.apply(
                    lambda r: f"{r['Plot']} | {r['Block']} | {r['SACU']} | {r['Inverter ID']} | {r['String No']} | {r['Failure Date & Time']}",
                    axis=1
                )

                selected_fault_key = st.selectbox("Select Open Fault", open_df["Fault Key"].tolist())
                selected_row = open_df[open_df["Fault Key"] == selected_fault_key].iloc[0]

                st.info(
                    f"Failure Time: {selected_row['Failure Date & Time']} | "
                    f"Current Age: {selected_row['Present Failure Hours']:.2f} hrs"
                )

                c1, c2 = st.columns(2)
                with c1:
                    restore_date = st.date_input("Rectified Date", value=datetime.now().date(), key="restore_date")
                with c2:
                    restore_time = st.time_input("Rectified Time", value=datetime.now().time().replace(second=0, microsecond=0), key="restore_time")

                rectified_remarks = st.text_area("Rectification Remarks", key="restore_remarks")

                if st.button("Save Rectified Entry"):
                    restored_dt = datetime.combine(restore_date, restore_time)

                    if restored_dt <= selected_row["Failure Date & Time"]:
                        st.error("Rectified Date & Time must be greater than Failure Date & Time.")
                    else:
                        mask = (
                            (df_master["Plot"].astype(str) == str(selected_row["Plot"])) &
                            (df_master["Block"].astype(str) == str(selected_row["Block"])) &
                            (df_master["SACU"].astype(str) == str(selected_row["SACU"])) &
                            (df_master["Inverter ID"].astype(str) == str(selected_row["Inverter ID"])) &
                            (df_master["String No"].astype(str) == str(selected_row["String No"])) &
                            (df_master["Failure Date & Time"] == selected_row["Failure Date & Time"])
                        )

                        df_master.loc[mask, "Restored Date & Time"] = restored_dt

                        old_remarks = df_master.loc[mask, "Remarks"].fillna("").astype(str)
                        df_master.loc[mask, "Remarks"] = (
                            old_remarks + 
                            old_remarks.apply(lambda x: " | " if x.strip() else "") +
                            f"Rectified: {rectified_remarks}"
                        )

                        df_master = enrich_fault_metrics(df_master)
                        save_data(df_master)

                        st.success("Fault rectified successfully.")
                        st.download_button(
                            "Download Updated Excel",
                            data=get_download_excel_bytes(df_master),
                            file_name="String_Master_Plot1_Updated.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        st.rerun()

    with tab3:
        st.subheader("Operator Fault Logging & Verification")

        edit_columns = [
            "Plot", "Block", "SACU", "Inverter ID", "String No", "Serial Number",
            "Remarks", "Failure Date & Time", "Restored Date & Time",
            "Turn Around Time", "Present Failure Hours", "Current Loss Hours", "Status"
        ]

        available_edit_columns = [col for col in edit_columns if col in df_filtered.columns]

        edited_df = st.data_editor(
            df_filtered[available_edit_columns],
            disabled=[
                col for col in [
                    "Plot", "Block", "SACU", "Inverter ID", "String No",
                    "Turn Around Time", "Present Failure Hours", "Current Loss Hours", "Status"
                ] if col in available_edit_columns
            ],
            use_container_width=True,
            num_rows="dynamic"
        )

        if st.button("Save Updates & Recalculate"):
            edited_df["Failure Date & Time"] = pd.to_datetime(edited_df["Failure Date & Time"], errors="coerce")
            edited_df["Restored Date & Time"] = pd.to_datetime(edited_df["Restored Date & Time"], errors="coerce")

            edited_df = enrich_fault_metrics(edited_df)

            key_cols = ["Plot", "Block", "SACU", "Inverter ID", "String No", "Failure Date & Time"]
            key_cols = [col for col in key_cols if col in df_master.columns]

            df_master_idx = df_master.set_index(key_cols)
            edited_df_idx = edited_df.set_index(key_cols)

            df_master_idx.update(edited_df_idx)
            df_master = df_master_idx.reset_index()

            save_data(df_master)

            st.success("Master database updated successfully.")
            st.download_button(
                "Download Updated Excel",
                data=get_download_excel_bytes(df_master),
                file_name="String_Master_Plot1_Updated.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.rerun()