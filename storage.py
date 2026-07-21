# storage.py - Data storage module
import pandas as pd
import os
import json
from datetime import datetime
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)

class DataStorage:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.history_file = os.path.join(data_dir, "history.csv")
        self.audit_file = os.path.join(data_dir, "audit_log.json")
        
        # Create data directory if it doesn't exist
        os.makedirs(data_dir, exist_ok=True)
        
        # Initialize history file if it doesn't exist
        if not os.path.exists(self.history_file):
            pd.DataFrame(columns=[
                'Date', 'Time', 'Plot', 'Block', 'SACU', 'Inverter',
                'Working String Count', 'Failed String Count', 'Availability'
            ]).to_csv(self.history_file, index=False)
        
        # Initialize audit file if it doesn't exist
        if not os.path.exists(self.audit_file):
            with open(self.audit_file, 'w') as f:
                json.dump([], f)
    
    def save_to_history(self, processed_data: Dict, metadata: Dict) -> bool:
        """Save processed data to historical records"""
        try:
            # Get first sheet data
            sheet_name = list(processed_data.keys())[0]
            df = processed_data[sheet_name]
            
            # Prepare history records
            history_records = []
            current_date = datetime.now()
            
            for _, row in df.iterrows():
                record = {
                    'Date': current_date.strftime('%Y-%m-%d'),
                    'Time': current_date.strftime('%H:%M:%S'),
                    'Plot': row.get('Plot', 'Unknown'),
                    'Block': row.get('Block', 'Unknown'),
                    'SACU': row.get('SACU', 'Unknown'),
                    'Inverter': row.get('String Inverter', 'Unknown'),
                    'Working String Count': row.get('Working String Count', 0),
                    'Failed String Count': row.get('Failed String Count', 0),
                    'Availability': row.get('String Availability', 0)
                }
                history_records.append(record)
            
            # Append to history
            history_df = pd.DataFrame(history_records)
            if not history_df.empty:
                # Read existing history
                if os.path.exists(self.history_file):
                    existing_df = pd.read_csv(self.history_file)
                    updated_df = pd.concat([existing_df, history_df], ignore_index=True)
                else:
                    updated_df = history_df
                
                # Remove duplicates based on date and inverter
                updated_df = updated_df.drop_duplicates(subset=['Date', 'Inverter'], keep='last')
                
                # Save updated history
                updated_df.to_csv(self.history_file, index=False)
                logger.info(f"Saved {len(history_records)} records to history")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error saving to history: {e}")
            return False
    
    def load_history(self) -> Optional[pd.DataFrame]:
        """Load historical data"""
        try:
            if os.path.exists(self.history_file):
                df = pd.read_csv(self.history_file)
                if not df.empty:
                    # Convert date to datetime
                    df['Date'] = pd.to_datetime(df['Date'])
                    return df
            return None
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            return None
    
    def log_audit(self, user: str, action: str, details: Dict) -> bool:
        """Log user action for audit trail"""
        try:
            with open(self.audit_file, 'r') as f:
                logs = json.load(f)
            
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'user': user,
                'action': action,
                'details': details
            }
            
            logs.append(log_entry)
            
            # Keep only last 1000 logs
            if len(logs) > 1000:
                logs = logs[-1000:]
            
            with open(self.audit_file, 'w') as f:
                json.dump(logs, f, indent=2)
            
            return True
        except Exception as e:
            logger.error(f"Error logging audit: {e}")
            return False
    
    def get_audit_logs(self, limit: int = 100) -> List[Dict]:
        """Get audit logs"""
        try:
            if os.path.exists(self.audit_file):
                with open(self.audit_file, 'r') as f:
                    logs = json.load(f)
                return logs[-limit:]
            return []
        except Exception as e:
            logger.error(f"Error getting audit logs: {e}")
            return []
    
    def get_report_history(self) -> List[Dict]:
        """Get report generation history"""
        logs = self.get_audit_logs(limit=50)
        reports = [log for log in logs if log['action'] == 'generate_report']
        return [{
            'name': log['details'].get('report_type', 'Unknown'),
            'date': log['timestamp']
        } for log in reports]
    
    def clear_history(self) -> bool:
        """Clear all historical data"""
        try:
            if os.path.exists(self.history_file):
                os.remove(self.history_file)
                # Recreate empty history file
                pd.DataFrame(columns=[
                    'Date', 'Time', 'Plot', 'Block', 'SACU', 'Inverter',
                    'Working String Count', 'Failed String Count', 'Availability'
                ]).to_csv(self.history_file, index=False)
            return True
        except Exception as e:
            logger.error(f"Error clearing history: {e}")
            return False