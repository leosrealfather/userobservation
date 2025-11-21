"""
Streamlit dashboard for monitoring company conversation activity from Langfuse.
"""
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
from langfuse_client import (
    get_langfuse_client,
    fetch_traces_by_company,
    aggregate_company_conversations,
    get_time_range_filter
)

# Page configuration
st.set_page_config(
    page_title="Company Conversation Dashboard",
    page_icon="📊",
    layout="wide"
)

# Initialize session state for tracking last refresh
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# Title with refresh button inline
col_title, col_refresh = st.columns([5, 1])
with col_title:
    st.title("📊 Company Conversation Activity Dashboard")
with col_refresh:
    st.write("")  # Spacing
    st.write("")  # Spacing
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.cache_data.clear()
        st.session_state.last_refresh = datetime.now()
        st.rerun()

# Last updated info
st.caption(f"Last updated: {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")

# Sidebar for time period selection
st.sidebar.header("Time Period Filter")

time_period = st.sidebar.radio(
    "Select time period:",
    ["Today", "This Week", "This Month", "Custom Range"],
    index=0
)

custom_start = None
custom_end = None

if time_period == "Custom Range":
    col1, col2 = st.sidebar.columns(2)
    with col1:
        custom_start = st.date_input("Start date", value=datetime.now().date() - timedelta(days=7))
    with col2:
        custom_end = st.date_input("End date", value=datetime.now().date())
    
    # Convert to datetime
    custom_start = datetime.combine(custom_start, datetime.min.time())
    custom_end = datetime.combine(custom_end, datetime.max.time())

# Convert time period to lowercase with underscore for function
time_period_key = time_period.lower().replace(" ", "_")

# Get time range
start_time, end_time = get_time_range_filter(time_period_key, custom_start, custom_end)

# Display selected time range
st.sidebar.info(f"**Time Range:**\n{start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}")

# Initialize Langfuse client
client = get_langfuse_client()

if client is None:
    st.error("⚠️ Langfuse client not initialized. Please check your API credentials in `.streamlit/secrets.toml`")
    st.stop()

# Fetch data with loading indicator
with st.spinner("Fetching conversation data from Langfuse..."):
    traces = fetch_traces_by_company(
        _client=client,
        start_time=start_time,
        end_time=end_time
    )

# Aggregate data by company
if traces:
    df = aggregate_company_conversations(traces)
    
    # Store debug info for display at bottom
    if len(df) > 0:
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = []
        st.session_state.debug_info.append(f"Found {len(df)} companies after filtering test companies")
    
    # Display summary stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Companies", len(df))
    with col2:
        st.metric("Total Conversations", df['Number of Conversations'].sum() if len(df) > 0 else 0)
    with col3:
        st.metric("Total Tool Calls", df['Number of Tool Calls'].sum() if len(df) > 0 else 0)
    with col4:
        st.metric("Time Period", time_period)
    
    st.divider()
    
    # Display grouped bar chart with both metrics
    if len(df) > 0:
        st.subheader("Conversations and Tool Calls by Company")
        
        # Debug: Show how many companies are in the dataframe
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = []
        st.session_state.debug_info.append(f"Displaying {len(df)} companies in chart")
        
        # Sort by number of conversations (descending) - highest at top
        # Then by tool calls as secondary sort for ties
        df_sorted = df.sort_values(['Number of Conversations', 'Number of Tool Calls'], ascending=[False, False]).copy()
        
        # Scale down tool calls for better visualization (divide by a factor)
        # This makes the bars more comparable in size
        df_sorted['Tool Calls (Scaled)'] = df_sorted['Number of Tool Calls'] / max(
            df_sorted['Number of Tool Calls'].max() / df_sorted['Number of Conversations'].max() if df_sorted['Number of Conversations'].max() > 0 else 1,
            1
        )
        # If tool calls are much larger, scale them down proportionally
        if df_sorted['Number of Tool Calls'].max() > 0 and df_sorted['Number of Conversations'].max() > 0:
            scale_factor = df_sorted['Number of Conversations'].max() / df_sorted['Number of Tool Calls'].max()
            # Only scale if tool calls are significantly larger (more than 2x)
            if scale_factor < 0.5:
                df_sorted['Tool Calls (Scaled)'] = df_sorted['Number of Tool Calls'] * scale_factor * 0.8  # Scale down a bit more
            else:
                df_sorted['Tool Calls (Scaled)'] = df_sorted['Number of Tool Calls']
        else:
            df_sorted['Tool Calls (Scaled)'] = df_sorted['Number of Tool Calls']
        
        # Prepare data for grouped bar chart using plotly.graph_objects for more control
        import plotly.graph_objects as go
        
        companies_list = df_sorted['Company'].tolist()
        
        # Extract data for each metric
        conversations_data = df_sorted['Number of Conversations'].tolist()
        tool_calls_scaled = df_sorted['Tool Calls (Scaled)'].tolist()
        tool_calls_actual = df_sorted['Number of Tool Calls'].tolist()
        
        # Create traces manually to ensure all companies are included
        fig = go.Figure()
        
        # Add Conversations trace
        fig.add_trace(go.Bar(
            name='Conversations',
            x=conversations_data,
            y=companies_list,
            orientation='h',
            marker_color='#1f77b4',
            text=conversations_data,
            textposition='outside',
            texttemplate='%{text}'
        ))
        
        # Add Tool Calls trace
        fig.add_trace(go.Bar(
            name='Tool Calls',
            x=tool_calls_scaled,
            y=companies_list,
            orientation='h',
            marker_color='#2ca02c',
            text=tool_calls_actual,  # Show actual values, not scaled
            textposition='outside',
            texttemplate='%{text}'
        ))
        
        # Calculate height to ensure all companies are visible
        chart_height = max(400, len(df_sorted) * 50)
        
        fig.update_layout(
            barmode='group',
            height=chart_height,
            yaxis=dict(
                categoryorder='array',
                categoryarray=companies_list,
                autorange='reversed'  # Reverse so highest is at top
            ),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            margin=dict(l=20, r=20, t=40, b=20),
            xaxis_title="Count"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.divider()
        
        # Download button
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Download as CSV",
            data=csv,
            file_name=f"company_conversations_{time_period_key}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No conversations found for the selected time period.")
else:
    st.warning("⚠️ No data retrieved. Please check:")
    st.markdown("""
    - Langfuse API credentials are correct
    - There are traces in the selected time period
    - Traces have company_name in their metadata
    - Network connectivity to Langfuse
    """)

# Footer
st.divider()
st.caption("💡 Data is cached for 5 minutes to reduce API calls. Click 'Refresh Now' to update immediately.")

# Discrete debug info at the bottom
if 'debug_info' in st.session_state and st.session_state.debug_info:
    st.markdown("---")
    with st.expander("📊 Debug Information", expanded=False):
        for info in st.session_state.debug_info:
            st.caption(f"• {info}")
    # Clear debug info after displaying
    st.session_state.debug_info = []

