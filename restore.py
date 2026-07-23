# restore.py
"""
Restore & TAT Analysis Module for PV SCADA Analytics
Tracks string failures, restoration times, and calculates TAT metrics
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib

# ==========================================
# CONFIGURATION
# ==========================================
WORKING_HOURS_START = 6  # 6 AM
WORKING_HOURS_END = 18   # 6 PM
WORKING_HOURS_PER_DAY = WORKING_HOURS_END - WORKING_HOURS_START

DATA_DIR = Path("data")
HISTORY_FILE = DATA_DIR / "string_history.json"
DATA_DIR.mkdir(exist_ok=True)

# ==========================================
# DATA MANAGEMENT
# ==========================================
def load_string_history():
    """Load string history data from JSON file"""
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
                # Ensure 'strings' key exists
                if "strings" not in data:
                    data["strings"] = {}
                if "last_updated" not in data:
                    data["last_updated"] = None
                return data
        except:
            return {"strings": {}, "last_updated": None}
    return {"strings": {}, "last_updated": None}

def save_string_history(history):
    """Save string history data to JSON file"""
    if "strings" not in history:
        history["strings"] = {}
    history["last_updated"] = datetime.now().isoformat()
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def init_history():
    """Initialize empty history if not exists"""
    if not HISTORY_FILE.exists():
        save_string_history({"strings": {}, "last_updated": None})

def update_string_history(df, date_str):
    """Update string history with current day's data"""
    if df is None or df.empty:
        return
    
    # Get current history with proper initialization
    history = load_string_history()
    
    # Ensure strings key exists
    if "strings" not in history:
        history["strings"] = {}
    
    # Find inverter column
    inverter_col = None
    df_columns_lower_map = {str(c).strip().lower(): c for c in df.columns}
    
    # Define INVERTER_ID_COLS here to avoid import issues
    INVERTER_ID_COLS = [
        "Inverter ID",
        "Inverter_ID",
        "Inverter",
        "ID",
        "Device Name",
        "String Inverter",
        "Inverters"
    ]
    
    for col in INVERTER_ID_COLS:
        if col in df.columns:
            inverter_col = col
            break
        elif col.strip().lower() in df_columns_lower_map:
            inverter_col = df_columns_lower_map[col.strip().lower()]
            break
    
    if not inverter_col:
        return
    
    # Get PV current columns
    pv_current_cols = []
    for col in df.columns:
        col_str = str(col).strip()
        if col_str.startswith("PV-I"):
            pv_current_cols.append(col)
    
    if not pv_current_cols:
        return
    
    # Process each inverter
    for _, row in df.iterrows():
        inverter_id = str(row[inverter_col])
        if inverter_id not in history["strings"]:
            history["strings"][inverter_id] = {}
        
        # Process each string
        for col in pv_current_cols:
            string_id = str(col)
            current_value = pd.to_numeric(row.get(col), errors="coerce")
            
            # Initialize string if not exists
            if string_id not in history["strings"][inverter_id]:
                history["strings"][inverter_id][string_id] = {
                    "status_history": [],
                    "current_status": "unknown",
                    "last_change": None
                }
            
            # Determine status
            if pd.notna(current_value) and current_value > 0.5:
                status = "working"
            else:
                status = "failed"
            
            # Update status history
            status_history = history["strings"][inverter_id][string_id]["status_history"]
            
            # Only add if status changed or it's a new day
            if not status_history or status_history[-1]["status"] != status:
                status_history.append({
                    "date": date_str,
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "status": status,
                    "value": float(current_value) if pd.notna(current_value) else 0
                })
                
                history["strings"][inverter_id][string_id]["current_status"] = status
                history["strings"][inverter_id][string_id]["last_change"] = datetime.now().isoformat()
    
    # Save history
    save_string_history(history)

# ==========================================
# TAT & RESTORE CALCULATIONS
# ==========================================
def calculate_failure_to_restore_tat(history, inverter_id, string_id, date_start=None, date_end=None):
    """
    Calculate failure to restore TAT for a specific string
    """
    if "strings" not in history:
        return []
    
    if inverter_id not in history["strings"]:
        return []
    
    if string_id not in history["strings"][inverter_id]:
        return []
    
    status_history = history["strings"][inverter_id][string_id].get("status_history", [])
    
    if len(status_history) < 2:
        return []
    
    events = []
    last_failure_time = None
    
    for record in status_history:
        status = record.get("status", "")
        date = record.get("date", "")
        time_str = record.get("time", "00:00:00")
        
        try:
            event_time = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M:%S")
        except:
            try:
                event_time = datetime.strptime(f"{date} 00:00:00", "%Y-%m-%d")
            except:
                continue
        
        if status == "failed" and last_failure_time is None:
            last_failure_time = event_time
        
        elif status == "working" and last_failure_time is not None:
            # Calculate restoration time in working hours
            restore_time = event_time
            total_minutes = 0
            
            # Calculate only working hours (6 AM - 6 PM)
            current_time = last_failure_time
            while current_time < restore_time:
                if WORKING_HOURS_START <= current_time.hour < WORKING_HOURS_END:
                    total_minutes += 60
                current_time += timedelta(minutes=60)
            
            working_hours = total_minutes / 60
            
            events.append({
                "failure_date": last_failure_time.strftime("%Y-%m-%d %H:%M:%S"),
                "restore_date": restore_time.strftime("%Y-%m-%d %H:%M:%S"),
                "tat_working_hours": round(working_hours, 2),
                "tat_actual_hours": round((restore_time - last_failure_time).total_seconds() / 3600, 2),
                "status": "restored"
            })
            
            last_failure_time = None
    
    # If currently in failure state
    if last_failure_time is not None:
        events.append({
            "failure_date": last_failure_time.strftime("%Y-%m-%d %H:%M:%S"),
            "restore_date": "Not restored yet",
            "tat_working_hours": "Ongoing",
            "tat_actual_hours": "Ongoing",
            "status": "ongoing_failure"
        })
    
    return events

# ==========================================
# UI COMPONENTS
# ==========================================
def display_tat_dashboard(processed_dataframes, current_df):
    """Display the Restore & TAT Analysis Dashboard"""
    st.title("🔄 Restore & TAT Analysis")
    st.caption("Track string failures, restoration times, and Turn Around Time metrics")
    
    # Initialize history
    init_history()
    
    # Load history
    history = load_string_history()
    
    # Initialize or update history with current data
    if current_df is not None and not current_df.empty:
        current_date = datetime.now().strftime("%Y-%m-%d")
        update_string_history(current_df, current_date)
        history = load_string_history()
    
    # Tabs for different views
    tab_summary, tab_string_analysis, tab_tat_tracking, tab_working_hours = st.tabs([
        "📊 Summary Dashboard",
        "🔌 String Analysis",
        "⏱️ TAT Tracking",
        "⏰ Working Hours"
    ])
    
    with tab_summary:
        display_summary_dashboard(history, current_df)
    
    with tab_string_analysis:
        display_string_analysis(history, current_df)
    
    with tab_tat_tracking:
        display_tat_tracking(history, current_df)
    
    with tab_working_hours:
        display_working_hours_analysis(history, current_df)

def display_summary_dashboard(history, current_df):
    """Display summary dashboard with key metrics"""
    st.subheader("📊 Summary Dashboard")
    
    if "strings" not in history or not history["strings"]:
        st.info("No string history available. Please upload SCADA data first.")
        return
    
    # Calculate summary metrics
    total_inverters = len(history["strings"])
    total_strings = 0
    total_failures = 0
    total_restorations = 0
    
    all_failures = []
    
    for inverter_id, strings in history["strings"].items():
        for string_id, data in strings.items():
            total_strings += 1
            status_history = data.get("status_history", [])
            
            # Count failures and restorations
            for i in range(1, len(status_history)):
                if status_history[i].get("status") == "failed" and status_history[i-1].get("status") == "working":
                    total_failures += 1
                    all_failures.append({
                        "inverter": inverter_id,
                        "string": string_id,
                        "date": status_history[i].get("date", "")
                    })
                elif status_history[i].get("status") == "working" and status_history[i-1].get("status") == "failed":
                    total_restorations += 1
    
    # Display KPIs
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Inverters", total_inverters)
    col2.metric("Total Strings", total_strings)
    col3.metric("Total Failures", total_failures)
    col4.metric("Total Restorations", total_restorations)
    
    # Calculate current health
    if current_df is not None and not current_df.empty:
        total_active = current_df["Total Active Strings"].sum() if "Total Active Strings" in current_df.columns else 0
        working = current_df["Working String Count"].sum() if "Working String Count" in current_df.columns else 0
        availability = (working / total_active * 100) if total_active > 0 else 0
        col5.metric("Current Availability", f"{availability:.1f}%")
    
    st.markdown("---")
    
    # Failure trends chart
    if all_failures:
        df_failures = pd.DataFrame(all_failures)
        df_failures["date"] = pd.to_datetime(df_failures["date"], errors='coerce')
        daily_failures = df_failures.groupby(df_failures["date"].dt.date).size().reset_index(name="failures")
        
        fig = px.bar(daily_failures, x="date", y="failures",
                     title="📉 Daily Failure Count",
                     labels={"date": "Date", "failures": "Number of Failures"})
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    
    # Status distribution
    status_counts = {"working": 0, "failed": 0}
    if current_df is not None and not current_df.empty:
        status_counts["working"] = int(current_df["Working String Count"].sum()) if "Working String Count" in current_df.columns else 0
        status_counts["failed"] = int(current_df["Failed String Count"].sum()) if "Failed String Count" in current_df.columns else 0
    
    col1, col2 = st.columns([2, 1])
    with col1:
        if status_counts["working"] + status_counts["failed"] > 0:
            fig_status = go.Figure(data=[go.Pie(
                labels=["✅ Working", "❌ Failed"],
                values=[status_counts["working"], status_counts["failed"]],
                hole=0.5,
                marker_colors=["#10b981", "#ef4444"],
                textinfo="label+percent+value"
            )])
            fig_status.update_layout(title="Current String Status", height=350)
            st.plotly_chart(fig_status, use_container_width=True)

def display_string_analysis(history, current_df):
    """Display detailed string analysis"""
    st.subheader("🔌 String Analysis")
    
    if "strings" not in history or not history["strings"]:
        st.info("No string history available.")
        return
    
    # Get list of all strings
    all_strings = []
    for inverter_id, strings in history["strings"].items():
        for string_id in strings.keys():
            all_strings.append(f"{inverter_id}_{string_id}")
    
    if not all_strings:
        st.info("No strings found in history.")
        return
    
    # Filter controls
    col1, col2 = st.columns(2)
    with col1:
        selected_strings = st.multiselect("Select Strings", all_strings, default=all_strings[:5] if len(all_strings) > 5 else all_strings)
    
    with col2:
        date_range = st.date_input(
            "Date Range",
            value=(datetime.now() - timedelta(days=7), datetime.now()),
            max_value=datetime.now()
        )
    
    if not selected_strings:
        st.warning("Please select at least one string.")
        return
    
    # Analyze selected strings
    string_data = []
    for string_key in selected_strings:
        parts = string_key.split("_")
        if len(parts) == 2:
            inverter_id, string_id = parts
            events = calculate_failure_to_restore_tat(history, inverter_id, string_id)
            
            # Filter by date range
            filtered_events = []
            for event in events:
                try:
                    failure_date = datetime.strptime(event["failure_date"], "%Y-%m-%d %H:%M:%S")
                    if date_range[0] <= failure_date.date() <= date_range[1]:
                        filtered_events.append(event)
                except:
                    continue
            
            for event in filtered_events:
                string_data.append({
                    "Inverter": inverter_id,
                    "String": string_id,
                    "Failure Date": event["failure_date"],
                    "Restore Date": event["restore_date"],
                    "TAT (Working Hours)": event["tat_working_hours"],
                    "TAT (Actual Hours)": event["tat_actual_hours"],
                    "Status": event["status"]
                })
    
    if string_data:
        df_strings = pd.DataFrame(string_data)
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Events", len(df_strings))
        
        # Calculate average TAT safely
        tat_values = df_strings[df_strings['TAT (Working Hours)'] != 'Ongoing']['TAT (Working Hours)']
        if not tat_values.empty:
            col2.metric("Avg TAT (Working Hours)", f"{tat_values.mean():.1f}h")
        else:
            col2.metric("Avg TAT (Working Hours)", "N/A")
        
        col3.metric("Total Restorations", len(df_strings[df_strings["Status"] == "restored"]))
        col4.metric("Ongoing Failures", len(df_strings[df_strings["Status"] == "ongoing_failure"]))
        
        # Display table
        st.dataframe(df_strings, use_container_width=True)
        
        # Visualize TAT
        df_tat = df_strings[df_strings['TAT (Working Hours)'] != 'Ongoing'].copy()
        if not df_tat.empty:
            fig = px.bar(df_tat, x="String", y="TAT (Working Hours)", 
                        color="Inverter", 
                        title="📊 TAT by String (Working Hours)",
                        labels={"TAT (Working Hours)": "TAT (Hours)"})
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No events found for the selected strings in the date range.")

def display_tat_tracking(history, current_df):
    """Display TAT Tracking dashboard"""
    st.subheader("⏱️ TAT Tracking Dashboard")
    
    if "strings" not in history or not history["strings"]:
        st.info("No string history available.")
        return
    
    # Summary TAT metrics
    all_tats = []
    
    for inverter_id, strings in history["strings"].items():
        for string_id in strings.keys():
            events = calculate_failure_to_restore_tat(history, inverter_id, string_id)
            for event in events:
                if event["status"] == "restored" and event["tat_working_hours"] != "Ongoing":
                    all_tats.append({
                        "inverter": inverter_id,
                        "string": string_id,
                        "tat_hours": event["tat_working_hours"],
                        "failure_date": event["failure_date"],
                        "restore_date": event["restore_date"]
                    })
    
    if all_tats:
        df_tat = pd.DataFrame(all_tats)
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total TAT Events", len(df_tat))
        col2.metric("Average TAT", f"{df_tat['tat_hours'].mean():.1f} hours")
        col3.metric("Max TAT", f"{df_tat['tat_hours'].max():.1f} hours")
        
        st.markdown("---")
        
        # TAT Distribution
        col1, col2 = st.columns(2)
        
        with col1:
            # Histogram of TAT
            fig_hist = px.histogram(df_tat, x="tat_hours", nbins=20,
                                    title="TAT Distribution",
                                    labels={"tat_hours": "TAT (Hours)", "count": "Number of Events"})
            fig_hist.update_layout(height=350)
            st.plotly_chart(fig_hist, use_container_width=True)
        
        with col2:
            # Top 10 worst TAT
            worst_tat = df_tat.nlargest(10, "tat_hours")
            fig_worst = px.bar(worst_tat, x="string", y="tat_hours", 
                              color="inverter",
                              title="Top 10 Worst TAT",
                              labels={"tat_hours": "TAT (Hours)", "string": "String"})
            fig_worst.update_layout(height=350)
            st.plotly_chart(fig_worst, use_container_width=True)
        
        # Detailed TAT table
        st.subheader("📋 Detailed TAT Data")
        st.dataframe(df_tat.sort_values("tat_hours", ascending=False), use_container_width=True)
        
        # Export option
        csv = df_tat.to_csv(index=False)
        st.download_button(
            label="📥 Download TAT Data (CSV)",
            data=csv,
            file_name=f"tat_data_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No TAT events found.")

def display_working_hours_analysis(history, current_df):
    """Display working hours analysis"""
    st.subheader("⏰ Working Hours Analysis")
    st.caption(f"Working Hours: {WORKING_HOURS_START}:00 AM to {WORKING_HOURS_END}:00 PM")
    
    if "strings" not in history or not history["strings"]:
        st.info("No string history available.")
        return
    
    # Calculate working hours metrics
    string_metrics = []
    
    for inverter_id, strings in history["strings"].items():
        for string_id, data in strings.items():
            status_history = data.get("status_history", [])
            
            # Calculate hours for each status
            working_hours = 0
            failure_hours = 0
            
            for i in range(len(status_history) - 1):
                current = status_history[i]
                next_status = status_history[i + 1]
                
                try:
                    current_time = datetime.strptime(f"{current.get('date', '')} {current.get('time', '00:00:00')}", 
                                                    "%Y-%m-%d %H:%M:%S")
                    next_time = datetime.strptime(f"{next_status.get('date', '')} {next_status.get('time', '00:00:00')}", 
                                                 "%Y-%m-%d %H:%M:%S")
                    
                    # Calculate working hours (6 AM - 6 PM)
                    delta_hours = 0
                    temp_time = current_time
                    while temp_time < next_time:
                        if WORKING_HOURS_START <= temp_time.hour < WORKING_HOURS_END:
                            delta_hours += 1
                        temp_time += timedelta(hours=1)
                    
                    if current.get("status") == "working":
                        working_hours += delta_hours
                    else:
                        failure_hours += delta_hours
                        
                except:
                    continue
            
            # Current status duration
            if status_history:
                last_status = status_history[-1]
                try:
                    last_time = datetime.strptime(f"{last_status.get('date', '')} {last_status.get('time', '00:00:00')}", 
                                                 "%Y-%m-%d %H:%M:%S")
                    current_duration = (datetime.now() - last_time).total_seconds() / 3600
                    
                    if last_status.get("status") == "working":
                        working_hours += current_duration
                    else:
                        failure_hours += current_duration
                except:
                    pass
            
            string_metrics.append({
                "inverter": inverter_id,
                "string": string_id,
                "working_hours": round(working_hours, 1),
                "failure_hours": round(failure_hours, 1),
                "total_hours": round(working_hours + failure_hours, 1),
                "current_status": data.get("current_status", "unknown")
            })
    
    if string_metrics:
        df_metrics = pd.DataFrame(string_metrics)
        
        # Display KPIs
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Working Hours", f"{df_metrics['working_hours'].sum():.1f}h")
        col2.metric("Total Failure Hours", f"{df_metrics['failure_hours'].sum():.1f}h")
        col3.metric("Avg Working Hours/String", f"{df_metrics['working_hours'].mean():.1f}h")
        col4.metric("Avg Failure Hours/String", f"{df_metrics['failure_hours'].mean():.1f}h")
        
        st.markdown("---")
        
        # Working vs Failure hours chart
        df_long = df_metrics.melt(id_vars=["inverter", "string"], 
                                  value_vars=["working_hours", "failure_hours"],
                                  var_name="Status", value_name="Hours")
        df_long["Status"] = df_long["Status"].map({"working_hours": "✅ Working", "failure_hours": "❌ Failed"})
        
        fig = px.bar(df_long, x="string", y="Hours", color="Status",
                     title="Working vs Failure Hours by String",
                     barmode="stack",
                     color_discrete_map={"✅ Working": "#10b981", "❌ Failed": "#ef4444"})
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)
        
        # Detailed table
        st.subheader("📋 Detailed Hours Analysis")
        st.dataframe(df_metrics, use_container_width=True)
        
        # Export option
        csv = df_metrics.to_csv(index=False)
        st.download_button(
            label="📥 Download Hours Analysis (CSV)",
            data=csv,
            file_name=f"hours_analysis_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No metrics available.")

# ==========================================
# MAIN EXPORT FUNCTION
# ==========================================
def get_restore_tab(processed_dataframes, current_df):
    """Main function to display the Restore & TAT tab"""
    display_tat_dashboard(processed_dataframes, current_df)

# ==========================================
# INITIALIZATION
# ==========================================
# Initialize history on module load
init_history()
