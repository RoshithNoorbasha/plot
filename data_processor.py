# data_processor.py - Data processing module
import pandas as pd
import numpy as np
import re
import io
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SCADADataProcessor:
    def __init__(self):
        self.inverter_id_cols = ['Inverter ID', 'Inverter_ID', 'Inverter', 'ID', 'Device Name', 'String Inverter']
        self.pv_columns = [f'PV-I{i}' for i in range(1, 29)]  # PV-I1 to PV-I28
        self.max_rows_check = 100
        
    def process_file(self, uploaded_file) -> Tuple[Dict[str, pd.DataFrame], Dict]:
        """Process uploaded Excel file"""
        try:
            # Read Excel file
            excel_file = pd.ExcelFile(uploaded_file, engine='openpyxl')
            sheet_names = excel_file.sheet_names
            
            processed_dfs = {}
            metadata = {
                'file_name': uploaded_file.name,
                'processed_at': datetime.now().isoformat(),
                'sheets_processed': [],
                'total_rows': 0
            }
            
            for sheet_name in sheet_names:
                # Find header row
                header_row = self._find_header_row(excel_file, sheet_name)
                if header_row is None:
                    logger.warning(f"Could not find header in sheet: {sheet_name}")
                    continue
                
                # Read data
                df = pd.read_excel(
                    uploaded_file,
                    sheet_name=sheet_name,
                    skiprows=header_row,
                    header=0,
                    engine='openpyxl'
                )
                
                # Clean data
                df = self._clean_dataframe(df)
                
                # Process data
                df = self._process_dataframe(df)
                
                if df is not None and not df.empty:
                    processed_dfs[sheet_name] = df
                    metadata['sheets_processed'].append(sheet_name)
                    metadata['total_rows'] += len(df)
                    logger.info(f"Processed sheet: {sheet_name} with {len(df)} rows")
            
            return processed_dfs, metadata
            
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            raise
    
    def _find_header_row(self, excel_file, sheet_name: str) -> Optional[int]:
        """Find the row containing column headers"""
        try:
            # Read first few rows
            temp_df = pd.read_excel(
                excel_file,
                sheet_name=sheet_name,
                header=None,
                nrows=self.max_rows_check,
                engine='openpyxl'
            )
            
            for i, row in temp_df.iterrows():
                row_values = [str(val).strip() for val in row.dropna()]
                if any(col.lower() in [v.lower() for v in row_values] for col in self.inverter_id_cols):
                    return i
            
            return None
        except Exception as e:
            logger.error(f"Error finding header row: {e}")
            return None
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean the dataframe"""
        # Remove completely empty rows
        df = df.dropna(how='all')
        
        # Remove 'Unnamed' columns
        df = df.loc[:, ~df.columns.str.contains('^Unnamed:')]
        
        # Remove rows where all values are NaN or empty strings
        df = df[~df.astype(str).apply(lambda x: (x == '').all(), axis=1)]
        
        return df
    
    def _process_dataframe(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Process the dataframe - add computed columns"""
        try:
            # Find inverter ID column
            inverter_col = self._find_inverter_column(df)
            if inverter_col is None:
                logger.warning("No inverter column found")
                return None
            
            # Add computed columns
            df['Plot'] = df[inverter_col].apply(self._extract_plot)
            df['Block'] = df[inverter_col].apply(self._extract_block)
            df['SACU'] = df[inverter_col].apply(self._map_to_sacu)
            
            # Calculate working strings
            df['Working String Count'] = self._calculate_working_strings(df)
            df['Failed String Count'] = self._calculate_failed_strings(df)
            df['String Availability'] = df.apply(
                lambda row: self._calculate_availability(row['Working String Count'], row['Failed String Count']),
                axis=1
            )
            
            # Reorder columns
            cols = ['Plot', 'Block', 'SACU', 'Working String Count', 'Failed String Count', 'String Availability']
            cols.extend([col for col in df.columns if col not in cols])
            df = df[cols]
            
            return df
            
        except Exception as e:
            logger.error(f"Error processing dataframe: {e}")
            return None
    
    def _find_inverter_column(self, df: pd.DataFrame) -> Optional[str]:
        """Find the inverter ID column"""
        for col in self.inverter_id_cols:
            if col in df.columns:
                return col
            if col.lower() in [c.lower() for c in df.columns]:
                return [c for c in df.columns if c.lower() == col.lower()][0]
        return None
    
    def _extract_plot(self, inverter_id: str) -> str:
        """Extract plot from inverter ID"""
        if not isinstance(inverter_id, str):
            return 'Unknown'
        
        try:
            # Extract plot from pattern like P1-IB3-2.1-SI05
            parts = inverter_id.split('-')
            if parts and parts[0].startswith('P'):
                return parts[0]
        except:
            pass
        return 'Unknown'
    
    def _extract_block(self, inverter_id: str) -> str:
        """Extract block from inverter ID"""
        if not isinstance(inverter_id, str):
            return 'Unknown'
        
        try:
            # Extract block from pattern like P1-IB3-2.1-SI05
            parts = inverter_id.split('-')
            if len(parts) >= 2 and parts[1].startswith('IB'):
                return parts[1]
        except:
            pass
        return 'Unknown'
    
    def _map_to_sacu(self, inverter_id: str) -> str:
        """Map inverter to SACU based on naming convention"""
        if not isinstance(inverter_id, str):
            return 'Unknown'
        
        # Regex to capture the X.Y or X-Y part
        match = re.search(r'-(\d[\.\-]\d)-', inverter_id)
        if match:
            sacu_identifier = match.group(1)
            try:
                if '.' in sacu_identifier:
                    first_digit = int(sacu_identifier.split('.')[0])
                else:
                    first_digit = int(sacu_identifier.split('-')[0])
                
                if first_digit in [1, 2]:
                    return 'SACU-1'
                elif first_digit in [3, 4]:
                    return 'SACU-2'
            except:
                pass
        return 'Unknown SACU'
    
    def _calculate_working_strings(self, df: pd.DataFrame) -> pd.Series:
        """Calculate working string count"""
        existing_pv_cols = [col for col in self.pv_columns if col in df.columns]
        if not existing_pv_cols:
            return pd.Series([0] * len(df))
        
        # A string is working if value > 0.5
        return (df[existing_pv_cols] > 0.5).sum(axis=1)
    
    def _calculate_failed_strings(self, df: pd.DataFrame) -> pd.Series:
        """Calculate failed string count"""
        existing_pv_cols = [col for col in self.pv_columns if col in df.columns]
        if not existing_pv_cols:
            return pd.Series([0] * len(df))
        
        # A string is failed if value <= 0.5 and not NaN
        return (df[existing_pv_cols].notna() & (df[existing_pv_cols] <= 0.5)).sum(axis=1)
    
    def _calculate_availability(self, working: int, failed: int) -> float:
        """Calculate string availability percentage"""
        total = working + failed
        if total == 0:
            return 0.0
        return (working / total) * 100