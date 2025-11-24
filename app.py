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
    fetch_tool_calls_by_company,
    aggregate_tool_calls_by_name,
    fetch_conversation_outcomes,
    aggregate_conversation_outcomes,
    get_time_range_filter
)

# Page configuration
st.set_page_config(
    page_title="Agent Observability",
    page_icon="📊",
    layout="wide"
)

# Initialize session state for tracking last refresh
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# Title with refresh button inline
col_title, col_refresh = st.columns([5, 1])
with col_title:
    st.title("Agent Observability")
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
    ["Today", "This Week", "Last 7 Days", "This Month", "Custom Range"],
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

# Create tabs for different views
tab1, tab2, tab3 = st.tabs(["Company Overview", "Tool Call Breakdown", "True Agent Success/Failure"])

# Tab 1: Company Overview (existing dashboard)
with tab1:
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
            
            # Scale both conversations and tool calls proportionally to each other
            # Find the max value for each metric to determine chart scale
            max_conversations = df_sorted['Number of Conversations'].max() if len(df_sorted) > 0 else 1
            max_tool_calls = df_sorted['Number of Tool Calls'].max() if len(df_sorted) > 0 else 1
            chart_max = max(max_conversations, max_tool_calls)
            
            # Scale conversations proportionally (maintain relative sizes to each other)
            if max_conversations > 0:
                df_sorted['Conversations (Scaled)'] = df_sorted['Number of Conversations'] * (chart_max / max_conversations)
            else:
                df_sorted['Conversations (Scaled)'] = df_sorted['Number of Conversations']
            
            # Scale tool calls proportionally to EACH OTHER (not relative to conversations)
            # This ensures if one company has 20 and another has 14, the first is always longer
            if max_tool_calls > 0:
                # Scale all tool calls by the same factor to maintain their relative proportions
                scale_factor = chart_max / max_tool_calls
                df_sorted['Tool Calls (Scaled)'] = df_sorted['Number of Tool Calls'] * scale_factor
            else:
                df_sorted['Tool Calls (Scaled)'] = df_sorted['Number of Tool Calls']
            
            # Prepare data for grouped bar chart using plotly.graph_objects for more control
            import plotly.graph_objects as go
            
            companies_list = df_sorted['Company'].tolist()
            
            # Extract data for each metric
            conversations_data = df_sorted['Conversations (Scaled)'].tolist()
            tool_calls_scaled = df_sorted['Tool Calls (Scaled)'].tolist()
            tool_calls_actual = df_sorted['Number of Tool Calls'].tolist()
            conversations_actual = df_sorted['Number of Conversations'].tolist()  # For display text
            
            # Extract success/failure data
            success_counts = df_sorted['Success Count'].tolist() if 'Success Count' in df_sorted.columns else [0] * len(df_sorted)
            failure_counts = df_sorted['Failure Count'].tolist() if 'Failure Count' in df_sorted.columns else [0] * len(df_sorted)
            
            # Calculate scaled successful and failed tool calls
            tool_calls_successful_scaled = []
            tool_calls_failed_scaled = []
            for i, (total_scaled, total_actual, success_count, failure_count) in enumerate(zip(
                tool_calls_scaled, tool_calls_actual, success_counts, failure_counts
            )):
                if total_actual > 0:
                    # Calculate proportions
                    success_ratio = success_count / total_actual
                    failure_ratio = failure_count / total_actual
                    # Scale proportionally
                    tool_calls_successful_scaled.append(total_scaled * success_ratio)
                    tool_calls_failed_scaled.append(total_scaled * failure_ratio)
                else:
                    tool_calls_successful_scaled.append(0)
                    tool_calls_failed_scaled.append(0)
            
            # Create traces manually to ensure all companies are included
            fig = go.Figure()
            
            # Add Conversations trace (separate group)
            fig.add_trace(go.Bar(
                name='Conversations',
                x=conversations_data,
                y=companies_list,
                orientation='h',
                marker_color='#1f77b4',
                text=conversations_actual,  # Show actual values, not scaled
                textposition='outside',
                texttemplate='%{text}',
                offsetgroup='conversations'
            ))
            
            # Add Tool Calls base bar (like conversations) - shows total number outside
            # Calculate total tool calls from metadata (success + failure) for display
            total_tool_calls_from_metadata = [sc + fc for sc, fc in zip(success_counts, failure_counts)]
            # Use metadata total if available, otherwise fall back to trace count
            tool_calls_display = [metadata_total if metadata_total > 0 else actual 
                                 for metadata_total, actual in zip(total_tool_calls_from_metadata, tool_calls_actual)]
            
            fig.add_trace(go.Bar(
                name='Tool Calls',
                x=tool_calls_scaled,
                y=companies_list,
                orientation='h',
                marker_color='#2ca02c',
                text=tool_calls_display,  # Show total from metadata if available
                textposition='outside',
                texttemplate='%{text}',
                textfont=dict(color='black', size=11),  # Black color for the number
                hovertemplate='<b>%{y}</b><br>Total Tool Calls (traces): %{customdata}<br>Total Tool Calls (with metadata): %{text}<extra></extra>',
                customdata=tool_calls_actual,  # Show trace count in hover
                offsetgroup='tool_calls',
                opacity=0.3,  # Make it semi-transparent so stacked bars show through
                showlegend=False  # Hide from legend
            ))
            
            # Add Tool Calls - Successful portion (green, stacked on base)
            # Create custom hover text showing actual successful counts
            successful_hover = [f"Successful: {sc}" for sc in success_counts]
            fig.add_trace(go.Bar(
                name='Tool Calls (Successful)',
                x=tool_calls_successful_scaled,
                y=companies_list,
                orientation='h',
                marker_color='#2ca02c',  # Green
                opacity=0.9,
                hovertemplate='<b>%{y}</b><br>Successful Tool Calls: %{customdata}<extra></extra>',
                customdata=success_counts,
                showlegend=True,
                offsetgroup='tool_calls',
                base=[0] * len(companies_list)  # Start at x=0, will overlay on base bar
            ))
            
            # Add Tool Calls - Failed portion (red, stacked on top of successful)
            # Create custom hover text showing actual failed counts
            failed_hover = [f"Failed: {fc}" for fc in failure_counts]
            fig.add_trace(go.Bar(
                name='Tool Calls (Failed)',
                x=tool_calls_failed_scaled,
                y=companies_list,
                orientation='h',
                marker_color='#d62728',  # Red
                opacity=0.9,
                hovertemplate='<b>%{y}</b><br>Failed Tool Calls: %{customdata}<extra></extra>',
                customdata=failure_counts,
                showlegend=True,
                offsetgroup='tool_calls',
                base=tool_calls_successful_scaled  # Stack on top of successful
            ))
            
            # Calculate height and max x value for annotations
            chart_height = max(400, len(df_sorted) * 50)
            max_x_value = max(
                max(conversations_data) if conversations_data else 0,
                max(tool_calls_scaled) if tool_calls_scaled else 0
            )
            
            # Calculate success rates and create annotations
            annotations = []
            for i, (company, tool_calls_total, tool_calls_scaled_val, success_count, failure_count) in enumerate(zip(
                companies_list, tool_calls_actual, tool_calls_scaled, success_counts, failure_counts
            )):
                # Add annotation with total tool calls and success rate only
                # Calculate total tool calls with success/failure data
                # Use success_count + failure_count as the actual total (from metadata)
                # tool_calls_total is the number of traces, but success/failure counts are from within those traces
                total_with_data = success_count + failure_count
                
                if total_with_data > 0:
                    success_rate = (success_count / total_with_data * 100)
                    # Show the actual total from metadata (success + failure), not trace count
                    # If there's a discrepancy (traces without metadata), note it
                    if total_with_data < tool_calls_total:
                        # Some traces don't have metadata - show both
                        annotation_text = f"{total_with_data} ({success_rate:.1f}%)"
                    else:
                        annotation_text = f"{total_with_data} ({success_rate:.1f}%)"
                elif tool_calls_total > 0:
                    # If we have tool calls but no success/failure data, show trace count
                    annotation_text = f"{tool_calls_total} (N/A)"
                else:
                    annotation_text = "0 (N/A)"
                
                # Position annotation at a fixed position on the right side using paper coordinates
                # xref='paper' means 0-1 relative to plot area, so 0.95 = 95% from left (near right edge)
                annotations.append(
                    dict(
                        x=0.95,  # Fixed position at 95% from left (right side of plot)
                        y=company,
                        text=annotation_text,
                        showarrow=False,
                        xref='paper',  # Use paper coordinates (0-1) instead of data coordinates
                        yref='y',  # Still use y-axis for vertical alignment
                        font=dict(size=11, color='#333333', family='Arial Black'),  # Bolder font
                        align='left',
                        xanchor='left'
                    )
                )
            
            fig.update_layout(
                barmode='group',  # Group conversations with tool calls, stack successful/failed within tool calls
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
                margin=dict(l=20, r=200, t=40, b=20),  # Increased right margin for success rate percentages
                xaxis_title="Count",
                annotations=annotations
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
        - **Have there been any traces in the selected time period?** (Most likely cause)
        - Langfuse API credentials are correct
        - Traces have company_name in their metadata
        - Network connectivity to Langfuse
        """)
    
    # Footer for Tab 1
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

# Tab 2: Tool Call Breakdown
with tab2:
    # Fetch tool calls with loading indicator
    with st.spinner("Fetching tool call data from Langfuse..."):
        tool_calls = fetch_tool_calls_by_company(
            _client=client,
            start_time=start_time,
            end_time=end_time
        )
    
    if tool_calls:
        # Aggregate tool calls by company and tool name
        tool_calls_df = aggregate_tool_calls_by_name(tool_calls)
        
        if len(tool_calls_df) > 0:
            # Display summary stats
            total_tool_types = tool_calls_df['Tool Name'].nunique()
            total_tool_calls = tool_calls_df['Total Calls'].sum()
            total_successful = tool_calls_df['Successful'].sum()
            total_failed = tool_calls_df['Failed'].sum()
            overall_success_rate = (total_successful / total_tool_calls * 100) if total_tool_calls > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Tool Types", total_tool_types)
            with col2:
                st.metric("Total Tool Calls", total_tool_calls)
            with col3:
                st.metric("Overall Success Rate", f"{overall_success_rate:.1f}%")
            with col4:
                st.metric("Time Period", time_period)
            
            st.divider()
            
            # Group by company and display charts
            companies = tool_calls_df['Company'].unique()
            # Sort companies by total tool calls (descending)
            company_totals = tool_calls_df.groupby('Company')['Total Calls'].sum().sort_values(ascending=False)
            companies_sorted = company_totals.index.tolist()
            
            for company in companies_sorted:
                company_data = tool_calls_df[tool_calls_df['Company'] == company].copy()
                company_data = company_data.sort_values('Total Calls', ascending=False)
                
                st.subheader(company)
                
                # Prepare data for chart
                tool_names = company_data['Tool Name'].tolist()
                successful_counts = company_data['Successful'].tolist()
                failed_counts = company_data['Failed'].tolist()
                total_counts = company_data['Total Calls'].tolist()
                success_rates = company_data['Success Rate (%)'].tolist()
                
                # Create horizontal stacked bar chart
                import plotly.graph_objects as go
                
                fig = go.Figure()
                
                # Add successful portion (green, base layer)
                fig.add_trace(go.Bar(
                    name='Successful',
                    x=successful_counts,
                    y=tool_names,
                    orientation='h',
                    marker_color='#2ca02c',  # Green
                    opacity=0.9,
                    showlegend=True
                ))
                
                # Add failed portion (red, stacked on top)
                fig.add_trace(go.Bar(
                    name='Failed',
                    x=failed_counts,
                    y=tool_names,
                    orientation='h',
                    marker_color='#d62728',  # Red
                    opacity=0.9,
                    showlegend=True,
                    base=successful_counts  # Stack on top of successful
                ))
                
                # Add total number labels
                fig.add_trace(go.Bar(
                    name='',
                    x=total_counts,
                    y=tool_names,
                    orientation='h',
                    marker_color='rgba(0,0,0,0)',  # Transparent
                    text=[f"{total} ({rate:.1f}%)" for total, rate in zip(total_counts, success_rates)],
                    textposition='outside',
                    texttemplate='%{text}',
                    textfont=dict(color='black', size=10),
                    showlegend=False,
                    hoverinfo='skip'
                ))
                
                # Calculate height
                chart_height = max(300, len(tool_names) * 40)
                
                fig.update_layout(
                    barmode='stack',
                    height=chart_height,
                    yaxis=dict(
                        categoryorder='array',
                        categoryarray=tool_names,
                        autorange='reversed'
                    ),
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    margin=dict(l=20, r=200, t=40, b=20),
                    xaxis_title="Count"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                st.divider()
        else:
            st.info("No tool calls found for the selected time period.")
    else:
        st.warning("⚠️ No tool call data retrieved. Please check:")
        st.markdown("""
        - **Have there been any traces in the selected time period?** (Most likely cause)
        - Langfuse API credentials are correct
        - Tool calls have tool_name and success data in their metadata
        - Network connectivity to Langfuse
        """)

# Tab 3: Conversation Success/Failure
with tab3:
    # Fetch conversation outcomes with loading indicator
    try:
        with st.spinner("Fetching conversation outcomes from Langfuse (this may take a minute for large datasets)..."):
            conversations = fetch_conversation_outcomes(
                _client=client,
                start_time=start_time,
                end_time=end_time
            )
    except Exception as e:
        st.error(f"Error fetching conversation outcomes: {str(e)}")
        import traceback
        with st.expander("Error Details"):
            st.code(traceback.format_exc())
        conversations = []
    
    if conversations:
        # Create DataFrame from conversations
        conv_df = pd.DataFrame(conversations)
        
        # Sort: Failed first, then by timestamp (most recent first)
        conv_df['outcome_sort'] = conv_df['outcome'].map({'failed': 0, 'success': 1})
        conv_df = conv_df.sort_values(['outcome_sort', 'timestamp'], ascending=[True, False])
        
        # Select and prepare columns for display
        display_df = conv_df[['conversation_id', 'company_name', 'outcome', 'prompt_message', 'final_meta_tool', 'trace_id', 'timestamp']].copy()
        display_df.columns = ['Conversation ID', 'Company', 'Outcome', 'Prompt Message', 'Final Meta Tool', 'Trace ID', 'Timestamp']
        
        # Format outcome for display
        display_df['Outcome'] = display_df['Outcome'].str.capitalize()
        
        # Truncate prompt message (first 50 words)
        def truncate_message(msg):
            if pd.isna(msg) or not msg:
                return ''
            words = str(msg).split()
            if len(words) > 50:
                return ' '.join(words[:50]) + '...'
            return ' '.join(words)
        
        display_df['Prompt Message'] = display_df['Prompt Message'].apply(truncate_message)
        
        # Format timestamp
        def format_timestamp(ts):
            if isinstance(ts, datetime):
                return ts.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return str(ts)
            return str(ts)
        
        display_df['Timestamp'] = display_df['Timestamp'].apply(format_timestamp)
        
        # Color code: Darker red for failed, darker green for successful, with white text
        def color_outcome(val):
            if val == 'Failed':
                return 'background-color: #cc0000; color: white'  # Darker red
            return 'background-color: #006600; color: white'  # Darker green
        
        # Display table
        st.dataframe(
            display_df.style.applymap(color_outcome, subset=['Outcome']),
            use_container_width=True,
            hide_index=True,
            height=600
        )
        
        # Summary at bottom
        total = len(display_df)
        failed = len(display_df[display_df['Outcome'] == 'Failed'])
        success_rate = (total - failed) / total * 100 if total > 0 else 0
        st.caption(f"Total: {total} conversations | Failed: {failed} ({failed/total*100:.1f}%) | Success Rate: {success_rate:.1f}%" if total > 0 else "No conversations found")
    else:
        st.warning("⚠️ No conversation outcome data retrieved. Please check:")
        st.markdown("""
        - **Have there been any traces in the selected time period?** (Most likely cause)
        - Langfuse API credentials are correct
        - Traces have conversation_id and tool_call data with create_ meta tools
        - Network connectivity to Langfuse
        """)

