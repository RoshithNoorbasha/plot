# analytics.py - Analytics engine module
import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class AnalyticsEngine:
    def __init__(self):
        pass
    
    def calculate_kpis(self, df: pd.DataFrame) -> Dict:
        """Calculate key performance indicators"""
        if df is None or df.empty:
            return {}
        
        kpis = {
            'total_inverters': len(df),
            'total_plots': df['Plot'].nunique(),
            'total_blocks': df['Block'].nunique() if 'Block' in df.columns else 0,
            'total_sacus': df['SACU'].nunique(),
            'total_working_strings': df['Working String Count'].sum(),
            'total_failed_strings': df['Failed String Count'].sum(),
            'avg_availability': df['String Availability'].mean(),
            'plant_availability': self._calculate_plant_availability(df)
        }
        
        return kpis
    
    def _calculate_plant_availability(self, df: pd.DataFrame) -> float:
        """Calculate plant availability"""
        total_working = df['Working String Count'].sum()
        total_failed = df['Failed String Count'].sum()
        total = total_working + total_failed
        if total == 0:
            return 0.0
        return (total_working / total) * 100
    
    def calculate_restoration(self, current_data: Dict, historical_data: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Calculate restoration metrics by comparing with yesterday's data"""
        try:
            # Get current data
            current_sheet = list(current_data.keys())[0]
            current_df = current_data[current_sheet]
            
            # Get yesterday's data
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            yesterday_data = historical_data[historical_data['Date'] == yesterday]
            
            if yesterday_data.empty:
                logger.info("No data for yesterday")
                return None
            
            # Merge and compare
            comparison = pd.merge(
                current_df[['Plot', 'Block', 'SACU', 'String Inverter', 'Working String Count']],
                yesterday_data[['Plot', 'Block', 'SACU', 'Inverter', 'Working String Count']],
                left_on=['Plot', 'Block', 'SACU', 'String Inverter'],
                right_on=['Plot', 'Block', 'SACU', 'Inverter'],
                suffixes=('_today', '_yesterday'),
                how='outer'
            )
            
            # Calculate difference
            comparison['Difference'] = comparison['Working String Count_today'] - comparison['Working String Count_yesterday']
            comparison['Status'] = comparison['Difference'].apply(
                lambda x: 'Restored' if x > 0 else ('New Failure' if x < 0 else 'No Change')
            )
            
            # Rename columns
            comparison = comparison.rename(columns={
                'Working String Count_today': 'Today',
                'Working String Count_yesterday': 'Yesterday'
            })
            
            return comparison
            
        except Exception as e:
            logger.error(f"Error calculating restoration: {e}")
            return None
    
    def calculate_failure_analysis(self, df: pd.DataFrame) -> Dict:
        """Analyze failures across different dimensions"""
        if df is None or df.empty:
            return {}
        
        analysis = {
            'plot_wise': df.groupby('Plot')['Failed String Count'].sum().to_dict(),
            'block_wise': df.groupby('Block')['Failed String Count'].sum().to_dict() if 'Block' in df.columns else {},
            'sacu_wise': df.groupby('SACU')['Failed String Count'].sum().to_dict(),
            'inverter_wise': df.groupby('String Inverter')['Failed String Count'].sum().to_dict()
        }
        
        return analysis
    
    def calculate_trends(self, historical_data: pd.DataFrame) -> Dict:
        """Calculate trends from historical data"""
        if historical_data is None or historical_data.empty:
            return {}
        
        # Group by date
        daily_trends = historical_data.groupby('Date').agg({
            'Working String Count': 'sum',
            'Failed String Count': 'sum',
            'String Availability': 'mean'
        }).reset_index()
        
        # Calculate moving averages
        daily_trends['Working_MA_7'] = daily_trends['Working String Count'].rolling(window=7).mean()
        daily_trends['Availability_MA_7'] = daily_trends['String Availability'].rolling(window=7).mean()
        
        return {
            'daily_trends': daily_trends,
            'plot_trends': historical_data.groupby(['Date', 'Plot'])['Working String Count'].sum().reset_index(),
            'sacu_trends': historical_data.groupby(['Date', 'SACU'])['Working String Count'].sum().reset_index()
        }