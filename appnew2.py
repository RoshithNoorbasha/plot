# app.py - Main entry point
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io
import os
import json
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path

# Import modules
from auth import AuthenticationManager, UserRole
from data_processor import SCADADataProcessor
from analytics import AnalyticsEngine
from visualizations import ChartBuilder
from storage import DataStorage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Solar SCADA Analytics Portal",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for enterprise look
def load_css():
    st.markdown("""
    <style>
        .main-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 1rem;
            border-radius: 10px;
            color: white;
            margin-bottom: 2rem;
        }
        .kpi-card {
            background: white;
            padding: 1.5rem;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
            margin-bottom: 1rem;
        }
        .kpi-value {
            font-size: 2rem;
            font-weight: bold;
            color: #2c3e50;
        }
        .kpi-label {
            font-size: 0.9rem;
            color: #7f8c8d;
            margin-top: 0.5rem;
        }
        .status-badge {
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
        }
        .status-success {
            background: #d4edda;
            color: #155724;
        }
        .status-danger {
            background: #f8d7da;
            color: #721c24;
        }
        .status-warning {
            background: #fff3cd;
            color: #856404;
        }
        .sidebar-content {
            padding: 1rem 0;
        }
        .metric-card {
            background: white;
            border-radius: 10px;
            padding: 1.25rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: transform 0.2s;
        }
        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.12);
        }
        .metric-title {
            font-size: 0.85rem;
            color: #6b7280;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .metric-value {
            font-size: 1.75rem;
            font-weight: 700;
            color: #1f2937;
            margin-top: 0.5rem;
        }
        .metric-change {
            font-size: 0.8rem;
            margin-top: 0.25rem;
        }
        .metric-change.positive { color: #10b981; }
        .metric-change.negative { color: #ef4444; }
        .metric-change.neutral { color: #6b7280; }
    </style>
    """, unsafe_allow_html=True)

# Initialize session state
def init_session_state():
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
    if 'processed_data' not in st.session_state:
        st.session_state.processed_data = None
    if 'historical_data' not in st.session_state:
        st.session_state.historical_data = None
    if 'current_file' not in st.session_state:
        st.session_state.current_file = None
    if 'filtered_data' not in st.session_state:
        st.session_state.filtered_data = None
    if 'analytics' not in st.session_state:
        st.session_state.analytics = None
    if 'theme' not in st.session_state:
        st.session_state.theme = 'light'

# Main application class
class SolarSCADAApp:
    def __init__(self):
        self.auth_manager = AuthenticationManager()
        self.data_processor = SCADADataProcessor()
        self.analytics_engine = AnalyticsEngine()
        self.chart_builder = ChartBuilder()
        self.storage = DataStorage()
        
    def run(self):
        load_css()
        init_session_state()
        
        # Authentication
        if not st.session_state.authenticated:
            self.show_login()
            return
        
        # Main app
        self.show_main_app()
    
    def show_login(self):
        st.markdown("""
        <div style="text-align: center; padding: 3rem;">
            <h1 style="color: #667eea;">☀️ Solar SCADA Analytics</h1>
            <p style="color: #6b7280;">Enterprise Data Processing Portal</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.container():
                st.markdown("### Sign In")
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                
                if st.button("Login", use_container_width=True):
                    user = self.auth_manager.authenticate(username, password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user = user
                        st.session_state.user_login_time = datetime.now()
                        logger.info(f"User {username} logged in successfully")
                        st.rerun()
                    else:
                        st.error("Invalid credentials. Please try again.")
    
    def show_main_app(self):
        # Sidebar
        with st.sidebar:
            st.image("https://via.placeholder.com/200x60/667eea/ffffff?text=SOLAR+SCADA", use_column_width=True)
            st.markdown("---")
            
            # User info
            st.markdown(f"""
            **Welcome, {st.session_state.user['username']}**  
            Role: {st.session_state.user['role']}  
            Login: {st.session_state.user_login_time.strftime('%H:%M:%S')}
            """)
            st.markdown("---")
            
            # Navigation
            menu_items = self.get_menu_items()
            selected_page = st.radio("Navigation", menu_items, index=0)
            st.markdown("---")
            
            # Theme toggle
            theme = st.toggle("Dark Mode", value=st.session_state.theme == 'dark')
            st.session_state.theme = 'dark' if theme else 'light'
            
            # Logout
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state.authenticated = False
                st.session_state.user = None
                st.rerun()
        
        # Main content
        if selected_page == "Dashboard":
            self.show_dashboard()
        elif selected_page == "Upload & Process":
            self.show_upload()
        elif selected_page == "Data Preview":
            self.show_data_preview()
        elif selected_page == "String Performance":
            self.show_string_performance()
        elif selected_page == "Restoration Dashboard":
            self.show_restoration()
        elif selected_page == "Historical Trends":
            self.show_historical_trends()
        elif selected_page == "Reports":
            self.show_reports()
        elif selected_page == "Administration" and st.session_state.user['role'] in ['admin']:
            self.show_administration()
        elif selected_page == "Logs" and st.session_state.user['role'] in ['admin']:
            self.show_logs()
    
    def get_menu_items(self):
        base_items = [
            "Dashboard",
            "Upload & Process",
            "Data Preview",
            "String Performance",
            "Restoration Dashboard",
            "Historical Trends",
            "Reports"
        ]
        if st.session_state.user['role'] in ['admin']:
            base_items.extend(["Administration", "Logs"])
        return base_items
    
    def show_dashboard(self):
        st.markdown('<div class="main-header"><h1>📊 Dashboard Overview</h1></div>', unsafe_allow_html=True)
        
        if not st.session_state.processed_data:
            st.info("📁 No data loaded. Please upload and process a SCADA report first.")
            return
        
        # Get the first sheet data
        sheet_name = list(st.session_state.processed_data.keys())[0]
        df = st.session_state.processed_data[sheet_name]
        
        # Calculate KPIs
        total_inverters = len(df)
        total_plots = df['Plot'].nunique()
        total_sacus = df['SACU'].nunique()
        
        working_strings = df['Working String Count'].sum()
        total_possible = working_strings  # Will be calculated based on config
        
        failed_strings = df['Failed String Count'].sum() if 'Failed String Count' in df.columns else 0
        
        # KPI Cards
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            self.metric_card("🌳 Total Plots", total_plots, "")
        with col2:
            self.metric_card("📦 Total SACUs", total_sacus, "")
        with col3:
            self.metric_card("🔌 Total Inverters", total_inverters, "")
        with col4:
            self.metric_card("⚡ Working Strings", f"{working_strings:,.0f}", "")
        
        col5, col6, col7, col8 = st.columns(4)
        with col5:
            self.metric_card("❌ Failed Strings", f"{failed_strings:,.0f}", "")
        with col6:
            availability = (working_strings / (working_strings + failed_strings) * 100) if (working_strings + failed_strings) > 0 else 100
            self.metric_card("📈 String Availability", f"{availability:.1f}%", "")
        with col7:
            self.metric_card("🔄 Restored Strings", "0", "")  # Calculate from history
        with col8:
            self.metric_card("🏭 Plant Availability", f"{availability:.1f}%", "")
        
        st.markdown("---")
        
        # Charts
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Plot-wise Performance")
            plot_data = df.groupby('Plot')['Working String Count'].sum().reset_index()
            fig = self.chart_builder.create_bar_chart(plot_data, 'Plot', 'Working String Count', 'Plot-wise Working Strings')
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("📊 SACU-wise Performance")
            sacu_data = df.groupby('SACU')['Working String Count'].sum().reset_index()
            fig = self.chart_builder.create_pie_chart(sacu_data, 'SACU', 'Working String Count', 'SACU-wise Distribution')
            st.plotly_chart(fig, use_container_width=True)
    
    def metric_card(self, title, value, change):
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-title">{title}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-change neutral">{change}</div>
        </div>
        """, unsafe_allow_html=True)
    
    def show_upload(self):
        st.markdown('<div class="main-header"><h1>📤 Upload & Process SCADA Report</h1></div>', unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader(
            "Choose Excel file",
            type=['xlsx', 'xls'],
            help="Upload daily SCADA report in Excel format"
        )
        
        if uploaded_file:
            col1, col2 = st.columns([1, 3])
            with col1:
                st.info(f"📄 {uploaded_file.name}")
                st.write(f"Size: {uploaded_file.size / 1024:.1f} KB")
            
            if st.button("🔄 Process File", use_container_width=True, type="primary"):
                with st.spinner("Processing file..."):
                    try:
                        # Process the file
                        processed_data, metadata = self.data_processor.process_file(uploaded_file)
                        
                        if processed_data:
                            st.session_state.processed_data = processed_data
                            st.session_state.current_file = uploaded_file.name
                            st.session_state.data_loaded = True
                            
                            # Save to history
                            self.storage.save_to_history(processed_data, metadata)
                            
                            st.success("✅ File processed successfully!")
                            
                            # Show summary
                            sheet_name = list(processed_data.keys())[0]
                            df = processed_data[sheet_name]
                            st.write(f"Processed {len(df)} rows from sheet: {sheet_name}")
                            
                            # Preview
                            with st.expander("Preview Processed Data"):
                                st.dataframe(df.head(10))
                        else:
                            st.error("❌ No data could be processed. Please check the file format.")
                            
                    except Exception as e:
                        st.error(f"❌ Error processing file: {str(e)}")
                        logger.error(f"Error processing file: {e}")
    
    def show_data_preview(self):
        st.markdown('<div class="main-header"><h1>🔍 Data Preview</h1></div>', unsafe_allow_html=True)
        
        if not st.session_state.processed_data:
            st.info("📁 No data loaded. Please upload a file first.")
            return
        
        # Get data
        sheet_name = list(st.session_state.processed_data.keys())[0]
        df = st.session_state.processed_data[sheet_name].copy()
        
        # Filters
        with st.expander("🔎 Filters", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                plots = ['All'] + sorted(df['Plot'].unique().tolist())
                selected_plot = st.selectbox("Plot", plots)
            with col2:
                blocks = ['All'] + sorted(df['Block'].unique().tolist()) if 'Block' in df.columns else ['All']
                selected_block = st.selectbox("Block", blocks)
            with col3:
                sacus = ['All'] + sorted(df['SACU'].unique().tolist())
                selected_sacu = st.selectbox("SACU", sacus)
            with col4:
                search = st.text_input("Search Inverter", placeholder="Enter inverter ID...")
        
        # Apply filters
        filtered_df = df.copy()
        if selected_plot != 'All':
            filtered_df = filtered_df[filtered_df['Plot'] == selected_plot]
        if selected_block != 'All':
            filtered_df = filtered_df[filtered_df['Block'] == selected_block]
        if selected_sacu != 'All':
            filtered_df = filtered_df[filtered_df['SACU'] == selected_sacu]
        if search:
            filtered_df = filtered_df[filtered_df['String Inverter'].str.contains(search, case=False, na=False)]
        
        st.session_state.filtered_data = filtered_df
        
        # Data table
        st.subheader(f"📊 Data Preview ({len(filtered_df)} rows)")
        
        # Use AgGrid for large datasets
        from st_aggrid import AgGrid, GridOptionsBuilder
        
        gb = GridOptionsBuilder.from_dataframe(filtered_df)
        gb.configure_default_column(groupable=True, value=True, enableRowGroup=True, aggFunc='sum')
        gb.configure_grid_options(domLayout='normal')
        gb.configure_pagination(paginationAutoPageSize=True)
        
        grid_response = AgGrid(
            filtered_df,
            gridOptions=gb.build(),
            height=400,
            width='100%'
        )
        
        # Export button
        if st.button("📥 Download Filtered Data"):
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"filtered_data_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    
    def show_string_performance(self):
        st.markdown('<div class="main-header"><h1>⚡ String Performance Dashboard</h1></div>', unsafe_allow_html=True)
        
        if not st.session_state.processed_data:
            st.info("📁 No data loaded. Please upload a file first.")
            return
        
        # Get data
        sheet_name = list(st.session_state.processed_data.keys())[0]
        df = st.session_state.processed_data[sheet_name].copy()
        
        # Summary metrics
        total_working = df['Working String Count'].sum()
        total_failed = df['Failed String Count'].sum() if 'Failed String Count' in df.columns else 0
        availability = (total_working / (total_working + total_failed) * 100) if (total_working + total_failed) > 0 else 100
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            self.metric_card("✅ Working Strings", f"{total_working:,.0f}", "")
        with col2:
            self.metric_card("❌ Failed Strings", f"{total_failed:,.0f}", "")
        with col3:
            self.metric_card("📈 Availability", f"{availability:.1f}%", "")
        with col4:
            self.metric_card("🔌 Total Strings", f"{(total_working + total_failed):,.0f}", "")
        
        st.markdown("---")
        
        # Charts
        col1, col2 = st.columns(2)
        with col1:
            # Plot-wise failures
            plot_failures = df.groupby('Plot')['Failed String Count'].sum().reset_index() if 'Failed String Count' in df.columns else pd.DataFrame()
            if not plot_failures.empty:
                fig = self.chart_builder.create_bar_chart(plot_failures, 'Plot', 'Failed String Count', 'Plot-wise Failures')
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # SACU-wise failures
            sacu_failures = df.groupby('SACU')['Failed String Count'].sum().reset_index() if 'Failed String Count' in df.columns else pd.DataFrame()
            if not sacu_failures.empty:
                fig = self.chart_builder.create_pie_chart(sacu_failures, 'SACU', 'Failed String Count', 'SACU-wise Failures')
                st.plotly_chart(fig, use_container_width=True)
    
    def show_restoration(self):
        st.markdown('<div class="main-header"><h1>🔄 Restoration Dashboard</h1></div>', unsafe_allow_html=True)
        
        if not st.session_state.processed_data or not st.session_state.historical_data:
            st.info("📁 Need historical data for comparison. Please process multiple files.")
            return
        
        # Compare with yesterday's data
        restoration_data = self.analytics_engine.calculate_restoration(
            st.session_state.processed_data,
            st.session_state.historical_data
        )
        
        if restoration_data is not None:
            # Display restoration metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                restored = len(restoration_data[restoration_data['Status'] == 'Restored'])
                self.metric_card("✅ Restored Strings", restored, "")
            with col2:
                new_failures = len(restoration_data[restoration_data['Status'] == 'New Failure'])
                self.metric_card("❌ New Failures", new_failures, "")
            with col3:
                unchanged = len(restoration_data[restoration_data['Status'] == 'No Change'])
                self.metric_card("➖ Unchanged", unchanged, "")
            
            st.markdown("---")
            
            # Restoration table
            st.subheader("📊 String Restoration Status")
            
            # Color coding
            def color_status(row):
                if row['Status'] == 'Restored':
                    return ['background-color: #d4edda'] * len(row)
                elif row['Status'] == 'New Failure':
                    return ['background-color: #f8d7da'] * len(row)
                else:
                    return ['background-color: #fff3cd'] * len(row)
            
            styled_df = restoration_data.style.apply(color_status, axis=1)
            st.dataframe(styled_df, use_container_width=True)
            
            # Restoration trend chart
            fig = self.chart_builder.create_restoration_trend(restoration_data)
            st.plotly_chart(fig, use_container_width=True)
    
    def show_historical_trends(self):
        st.markdown('<div class="main-header"><h1>📈 Historical Trends</h1></div>', unsafe_allow_html=True)
        
        if not st.session_state.historical_data:
            st.info("📊 No historical data available. Process multiple files to build history.")
            return
        
        # Load historical data
        history_df = st.session_state.historical_data
        
        # Filters
        with st.expander("🔎 Filter History", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                dates = ['All'] + sorted(history_df['Date'].unique().tolist())
                selected_date = st.selectbox("Date", dates)
            with col2:
                plots = ['All'] + sorted(history_df['Plot'].unique().tolist())
                selected_plot = st.selectbox("Plot", plots)
            with col3:
                sacus = ['All'] + sorted(history_df['SACU'].unique().tolist())
                selected_sacu = st.selectbox("SACU", sacus)
            with col4:
                inverters = ['All'] + sorted(history_df['Inverter'].unique().tolist())
                selected_inverter = st.selectbox("Inverter", inverters)
        
        # Apply filters
        filtered_history = history_df.copy()
        if selected_date != 'All':
            filtered_history = filtered_history[filtered_history['Date'] == selected_date]
        if selected_plot != 'All':
            filtered_history = filtered_history[filtered_history['Plot'] == selected_plot]
        if selected_sacu != 'All':
            filtered_history = filtered_history[filtered_history['SACU'] == selected_sacu]
        if selected_inverter != 'All':
            filtered_history = filtered_history[filtered_history['Inverter'] == selected_inverter]
        
        # Display historical data
        st.subheader(f"📊 Historical Data ({len(filtered_history)} records)")
        st.dataframe(filtered_history, use_container_width=True)
        
        # Historical trends chart
        st.subheader("📈 Working String Trends Over Time")
        
        # Group by date and plot
        trend_data = filtered_history.groupby(['Date', 'Plot'])['Working String Count'].sum().reset_index()
        fig = self.chart_builder.create_line_chart(
            trend_data, 
            'Date', 
            'Working String Count', 
            'Historical Working String Trends',
            color='Plot'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    def show_reports(self):
        st.markdown('<div class="main-header"><h1>📄 Reports</h1></div>', unsafe_allow_html=True)
        
        if not st.session_state.processed_data:
            st.info("📁 No data available. Process a file first.")
            return
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Available Reports")
            
            report_types = [
                "Processed Excel",
                "Historical CSV",
                "Failure Report",
                "Restoration Report",
                "Filtered Report"
            ]
            
            selected_report = st.selectbox("Select Report Type", report_types)
            
            if st.button("📥 Generate Report", use_container_width=True):
                with st.spinner(f"Generating {selected_report}..."):
                    report_data = self.generate_report(selected_report)
                    if report_data:
                        st.download_button(
                            label=f"Download {selected_report}",
                            data=report_data['content'],
                            file_name=report_data['filename'],
                            mime=report_data['mime_type']
                        )
        
        with col2:
            st.subheader("📋 Report History")
            reports = self.storage.get_report_history()
            if reports:
                for report in reports[-10:]:
                    st.write(f"• {report['name']} - {report['date']}")
            else:
                st.info("No reports generated yet.")
    
    def generate_report(self, report_type):
        if report_type == "Processed Excel":
            # Generate processed Excel file
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                for sheet_name, df in st.session_state.processed_data.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            output.seek(0)
            return {
                'content': output.getvalue(),
                'filename': f"processed_report_{datetime.now().strftime('%Y%m%d')}.xlsx",
                'mime_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
        elif report_type == "Historical CSV":
            if st.session_state.historical_data is not None:
                csv = st.session_state.historical_data.to_csv(index=False)
                return {
                    'content': csv,
                    'filename': f"historical_data_{datetime.now().strftime('%Y%m%d')}.csv",
                    'mime_type': 'text/csv'
                }
        elif report_type == "Filtered Report":
            if st.session_state.filtered_data is not None:
                csv = st.session_state.filtered_data.to_csv(index=False)
                return {
                    'content': csv,
                    'filename': f"filtered_report_{datetime.now().strftime('%Y%m%d')}.csv",
                    'mime_type': 'text/csv'
                }
        return None
    
    def show_administration(self):
        st.markdown('<div class="main-header"><h1>⚙️ Administration</h1></div>', unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["User Management", "System Settings", "Data Management"])
        
        with tab1:
            st.subheader("👥 User Management")
            users = self.auth_manager.get_all_users()
            if users:
                user_df = pd.DataFrame(users)
                st.dataframe(user_df, use_container_width=True)
            
            # Add user form
            with st.expander("Add New User"):
                col1, col2 = st.columns(2)
                with col1:
                    new_username = st.text_input("Username")
                    new_password = st.text_input("Password", type="password")
                with col2:
                    new_role = st.selectbox("Role", ['admin', 'engineer', 'viewer'])
                
                if st.button("Add User"):
                    if self.auth_manager.add_user(new_username, new_password, new_role):
                        st.success(f"User {new_username} added successfully!")
                        st.rerun()
                    else:
                        st.error("User already exists or invalid input.")
        
        with tab2:
            st.subheader("⚙️ System Settings")
            
            # Plant configuration
            st.write("Plant Configuration")
            total_strings = st.number_input("Total Strings per Inverter", min_value=1, max_value=40, value=28)
            working_strings = st.number_input("Working Strings", min_value=1, max_value=40, value=19)
            
            if st.button("Save Settings"):
                st.success("Settings saved successfully!")
                # Save to config file or database
        
        with tab3:
            st.subheader("💾 Data Management")
            
            if st.button("🗑️ Clear All Data"):
                if st.checkbox("I confirm I want to clear all data"):
                    st.session_state.processed_data = None
                    st.session_state.historical_data = None
                    st.session_state.filtered_data = None
                    st.success("All data cleared!")
    
    def show_logs(self):
        st.markdown('<div class="main-header"><h1>📋 Audit Logs</h1></div>', unsafe_allow_html=True)
        
        logs = self.storage.get_audit_logs()
        if logs:
            log_df = pd.DataFrame(logs)
            st.dataframe(log_df, use_container_width=True)
            
            # Export logs
            if st.button("📥 Export Logs"):
                csv = log_df.to_csv(index=False)
                st.download_button(
                    label="Download Logs CSV",
                    data=csv,
                    file_name=f"audit_logs_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        else:
            st.info("No logs available.")

# Run the application
if __name__ == "__main__":
    app = SolarSCADAApp()
    app.run()