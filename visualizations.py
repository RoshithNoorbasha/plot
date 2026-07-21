# visualizations.py - Chart builder module
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import Optional, List, Dict

class ChartBuilder:
    def __init__(self):
        self.theme = {
            'light': {
                'background': 'white',
                'color': '#2c3e50',
                'gridcolor': '#e6e6e6'
            },
            'dark': {
                'background': '#1a1a1a',
                'color': '#e6e6e6',
                'gridcolor': '#404040'
            }
        }
    
    def _get_theme(self):
        """Get current theme settings"""
        # This should be passed from session state
        return self.theme['light']
    
    def create_bar_chart(self, df: pd.DataFrame, x: str, y: str, title: str, color: Optional[str] = None) -> go.Figure:
        """Create a bar chart"""
        fig = px.bar(
            df,
            x=x,
            y=y,
            title=title,
            color=color,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_layout(
            template='plotly_white',
            xaxis_title=x,
            yaxis_title=y,
            height=400,
            hovermode='x unified'
        )
        
        return fig
    
    def create_pie_chart(self, df: pd.DataFrame, names: str, values: str, title: str) -> go.Figure:
        """Create a pie chart"""
        fig = px.pie(
            df,
            names=names,
            values=values,
            title=title,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_layout(
            template='plotly_white',
            height=400,
            showlegend=True
        )
        
        fig.update_traces(textposition='inside', textinfo='percent+label')
        
        return fig
    
    def create_line_chart(self, df: pd.DataFrame, x: str, y: str, title: str, color: Optional[str] = None) -> go.Figure:
        """Create a line chart"""
        fig = px.line(
            df,
            x=x,
            y=y,
            title=title,
            color=color,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_layout(
            template='plotly_white',
            xaxis_title=x,
            yaxis_title=y,
            height=400,
            hovermode='x unified'
        )
        
        return fig
    
    def create_scatter_chart(self, df: pd.DataFrame, x: str, y: str, title: str, color: Optional[str] = None) -> go.Figure:
        """Create a scatter chart"""
        fig = px.scatter(
            df,
            x=x,
            y=y,
            title=title,
            color=color,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        
        fig.update_layout(
            template='plotly_white',
            xaxis_title=x,
            yaxis_title=y,
            height=400,
            hovermode='closest'
        )
        
        return fig
    
    def create_restoration_trend(self, df: pd.DataFrame) -> go.Figure:
        """Create restoration trend chart"""
        # Count status
        status_counts = df['Status'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Count']
        
        fig = px.bar(
            status_counts,
            x='Status',
            y='Count',
            title='String Restoration Status Distribution',
            color='Status',
            color_discrete_map={
                'Restored': '#10b981',
                'New Failure': '#ef4444',
                'No Change': '#f59e0b'
            }
        )
        
        fig.update_layout(
            template='plotly_white',
            height=400,
            showlegend=False
        )
        
        fig.update_traces(texttemplate='%{y}', textposition='outside')
        
        return fig
    
    def create_availability_gauge(self, value: float, title: str) -> go.Figure:
        """Create a gauge chart for availability"""
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=value,
            title={'text': title},
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "#667eea"},
                'steps': [
                    {'range': [0, 50], 'color': "#ef4444"},
                    {'range': [50, 80], 'color': "#f59e0b"},
                    {'range': [80, 100], 'color': "#10b981"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 85
                }
            }
        ))
        
        fig.update_layout(
            height=300,
            margin=dict(l=20, r=20, t=30, b=20)
        )
        
        return fig
    
    def create_heatmap(self, df: pd.DataFrame, x: str, y: str, values: str, title: str) -> go.Figure:
        """Create a heatmap"""
        pivot_df = df.pivot_table(index=y, columns=x, values=values, aggfunc='sum')
        
        fig = px.imshow(
            pivot_df,
            title=title,
            color_continuous_scale='RdYlGn',
            aspect='auto'
        )
        
        fig.update_layout(
            template='plotly_white',
            height=400,
            xaxis_title=x,
            yaxis_title=y
        )
        
        return fig