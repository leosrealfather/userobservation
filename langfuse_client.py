"""
Langfuse API client module for fetching ProjectManager agent conversation data.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
import base64
import os
import streamlit as st
from langfuse import Langfuse
import pandas as pd
import requests

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional


def get_langfuse_client() -> Optional[Langfuse]:
    """
    Initialize and return Langfuse client using Streamlit secrets or environment variables.
    
    Supports both:
    - Streamlit secrets.toml format: [langfuse] public_key, secret_key, host
    - Environment variables: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL
    
    Returns:
        Langfuse client instance or None if credentials are missing
    """
    try:
        public_key = None
        secret_key = None
        host = "https://cloud.langfuse.com"
        
        # Try Streamlit secrets first
        try:
            if "langfuse" in st.secrets:
                langfuse_config = st.secrets["langfuse"]
                public_key = langfuse_config.get("public_key")
                secret_key = langfuse_config.get("secret_key")
                host = langfuse_config.get("host", host)
        except Exception:
            pass  # Fall through to environment variables
        
        # Fall back to environment variables (works with .env files if python-dotenv is installed)
        if not public_key:
            public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        if not secret_key:
            secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        if host == "https://cloud.langfuse.com":  # Only override if still default
            host = os.getenv("LANGFUSE_BASE_URL", host)
        
        # Validate credentials
        if not public_key or not secret_key:
            st.error(
                "Langfuse credentials not found. Please configure either:\n"
                "- `.streamlit/secrets.toml` with [langfuse] section, or\n"
                "- Environment variables: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL"
            )
            return None
        
        client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host
        )
        return client
    except Exception as e:
        st.error(f"Failed to initialize Langfuse client: {str(e)}")
        return None


def get_time_range_filter(time_period: str, custom_start: Optional[datetime] = None, 
                          custom_end: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """
    Get start and end datetime for the selected time period.
    Returns timezone-aware datetimes in local timezone, which will be converted to UTC for API calls.
    
    Args:
        time_period: One of "today", "this_week", "this_month", "custom"
        custom_start: Start datetime for custom range
        custom_end: End datetime for custom range
    
    Returns:
        Tuple of (start_datetime, end_datetime) - timezone-aware in local timezone
    """
    # Get current time in local timezone (timezone-aware)
    # On Streamlit Cloud, the server runs in UTC, so we need to handle that case
    import time
    try:
        # Try to get the actual local timezone
        local_offset_seconds = time.timezone if (time.daylight == 0) else time.altzone
        local_offset = timedelta(seconds=-local_offset_seconds)
        local_tz = timezone(local_offset)
        now = datetime.now(local_tz)
        
        # If we're in UTC (offset is 0), we might be on a server in UTC
        # In that case, we should use UTC for calculations but this is fine
        # The data in Langfuse is stored in UTC anyway
    except Exception:
        # Fallback to UTC if timezone detection fails
        local_tz = timezone.utc
        now = datetime.now(timezone.utc)
    
    if time_period == "today":
        # Last 24 hours instead of from midnight
        # Add a small buffer to end time to ensure we capture recent data
        start = now - timedelta(hours=24)
        end = now + timedelta(minutes=1)  # Add 1 minute buffer to ensure we get recent data
    elif time_period == "this_week":
        # Start of week (Monday)
        # Always calculate in UTC for consistency across server timezones
        # This ensures the same week boundaries regardless of where the server is located
        now_utc = now.astimezone(timezone.utc) if now.tzinfo != timezone.utc else now
        days_since_monday = now_utc.weekday()
        start_utc = (now_utc - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        # Keep in UTC - will be converted to UTC again in API call, but this ensures consistency
        start = start_utc
        end = now_utc
    elif time_period == "last_7_days":
        # Last 7 days from now (rolling 7-day window)
        start = now - timedelta(days=7)
        end = now
    elif time_period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif time_period == "custom":
        if custom_start and custom_end:
            # Make custom datetimes timezone-aware if they're naive
            if custom_start.tzinfo is None:
                custom_start = custom_start.replace(tzinfo=local_tz)
            if custom_end.tzinfo is None:
                custom_end = custom_end.replace(tzinfo=local_tz)
            start = custom_start
            end = custom_end
        else:
            # Fallback to today if custom dates not provided
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
    else:
        # Default to today
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    
    return start, end


@st.cache_data(ttl=300)  # Cache for 5 minutes (auto-refresh interval)
def fetch_traces_by_company(
    _client: Langfuse,  # Underscore prefix tells Streamlit not to hash this parameter
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[Dict]:
    """
    Fetch traces from Langfuse filtered by time range.
    Extracts company and conversation information from trace metadata.
    
    Args:
        _client: Langfuse client instance (underscore prefix excludes from cache hashing)
        start_time: Start datetime for filtering
        end_time: End datetime for filtering
    
    Returns:
        List of trace dictionaries with company_name and conversation_id
    """
    if _client is None:
        return []
    
    try:
        traces = []
        page = 1
        page_size = 50
        max_pages = 100  # Increased limit to fetch more data
        
        # Build filter parameters for Langfuse API
        # Langfuse SDK uses different parameter names
        params = {
            "page": page,
            "limit": page_size,
        }
        
        # Add time filters if provided (convert to ISO format)
        if start_time:
            params["from_timestamp"] = start_time.isoformat()
        if end_time:
            params["to_timestamp"] = end_time.isoformat()
        
        # Use Langfuse REST API directly for more reliable access
        # Get credentials from environment or secrets
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
        
        # Fall back to Streamlit secrets if env vars not set
        if not public_key or not secret_key:
            try:
                langfuse_config = st.secrets.get("langfuse", {})
                public_key = public_key or langfuse_config.get("public_key", "")
                secret_key = secret_key or langfuse_config.get("secret_key", "")
                if host == "https://cloud.langfuse.com":
                    host = langfuse_config.get("host", host)
            except Exception:
                pass
        
        # Use REST API endpoint
        url = f"{host}/api/public/traces"
        
        # Langfuse uses Basic Auth with public_key:secret_key
        auth_string = f"{public_key}:{secret_key}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/json'
        }
        
        # Fetch traces using REST API with pagination
        while page <= max_pages:
            try:
                api_params = {
                    "page": page,
                    "limit": page_size,
                }
                
                # Add time filters (API uses camelCase: fromTimestamp, toTimestamp)
                # API expects ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ (UTC)
                if start_time:
                    # Convert to UTC (datetimes should now be timezone-aware from get_time_range_filter)
                    if start_time.tzinfo is None:
                        # Fallback: if somehow still naive, treat as UTC
                        start_utc = start_time.replace(tzinfo=timezone.utc)
                    else:
                        start_utc = start_time.astimezone(timezone.utc)
                    # Format as UTC (remove timezone info for strftime)
                    api_params["fromTimestamp"] = start_utc.replace(tzinfo=None).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                    # Debug: log the timestamp conversion
                    if 'debug_info' not in st.session_state:
                        st.session_state.debug_info = []
                    if page == 1:  # Only log once
                        st.session_state.debug_info.append(f"Original start_time: {start_time} (tz: {start_time.tzinfo})")
                        st.session_state.debug_info.append(f"Converted start_utc: {start_utc}, API param: {api_params['fromTimestamp']}")
                    
                if end_time:
                    # Convert to UTC (datetimes should now be timezone-aware from get_time_range_filter)
                    if end_time.tzinfo is None:
                        # Fallback: if somehow still naive, treat as UTC
                        end_utc = end_time.replace(tzinfo=timezone.utc)
                    else:
                        end_utc = end_time.astimezone(timezone.utc)
                    # Format as UTC (remove timezone info for strftime)
                    api_params["toTimestamp"] = end_utc.replace(tzinfo=None).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                    # Debug: log the timestamp conversion
                    if 'debug_info' not in st.session_state:
                        st.session_state.debug_info = []
                    if page == 1:  # Only log once
                        st.session_state.debug_info.append(f"Original end_time: {end_time} (tz: {end_time.tzinfo})")
                        st.session_state.debug_info.append(f"Converted end_utc: {end_utc}, API param: {api_params['toTimestamp']}")
                
                response = requests.get(url, headers=headers, params=api_params, timeout=30)
                
                batch = []
                has_more = False
                
                # Debug: log API response
                if 'debug_info' not in st.session_state:
                    st.session_state.debug_info = []
                if page == 1:  # Only log once
                    st.session_state.debug_info.append(f"API Request URL: {url}")
                    st.session_state.debug_info.append(f"API Request params: {api_params}")
                    st.session_state.debug_info.append(f"API Response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    # Handle paginated response
                    if isinstance(data, dict):
                        batch = data.get('data', [])
                        if page == 1:  # Debug: log response data
                            st.session_state.debug_info.append(f"API Response: {len(batch)} traces in batch, total pages: {data.get('meta', {}).get('totalPages', 'unknown')}")
                        # Check for pagination info
                        if 'meta' in data and 'page' in data['meta']:
                            current_page = data['meta'].get('page', page)
                            total_pages = data['meta'].get('totalPages', 1)
                            has_more = current_page < total_pages
                        else:
                            has_more = len(batch) >= page_size
                    else:
                        batch = data if isinstance(data, list) else []
                        has_more = len(batch) >= page_size
                elif response.status_code == 401:
                    st.error("Authentication failed. Please check your Langfuse API credentials.")
                    break
                elif response.status_code == 404:
                    st.warning("Traces endpoint not found. Please check your Langfuse host URL.")
                    break
                else:
                    st.warning(f"API request failed with status {response.status_code}: {response.text}")
                    break
                
                if not batch:
                    break
                
                # Extract company and conversation information from all traces
                for trace in batch:
                    # Handle both dict and object responses
                    if isinstance(trace, dict):
                        trace_metadata = trace.get('metadata', {}) or {}
                        trace_id = trace.get('id', '')
                        trace_timestamp = trace.get('timestamp') or trace.get('createdAt') or trace.get('created_at')
                        # Get conversation_id from metadata
                        conversation_id = (
                            trace_metadata.get('conversation_id') or
                            trace_metadata.get('conversationId') or
                            trace.get('session_id') or
                            trace.get('sessionId') or
                            None
                        )
                    else:
                        # Object attributes
                        trace_metadata = getattr(trace, 'metadata', {}) or {}
                        trace_id = getattr(trace, 'id', '')
                        trace_timestamp = getattr(trace, 'timestamp', None) or getattr(trace, 'createdAt', None) or getattr(trace, 'created_at', None)
                        if isinstance(trace_metadata, dict):
                            conversation_id = (
                                trace_metadata.get('conversation_id') or
                                trace_metadata.get('conversationId') or
                                getattr(trace, 'session_id', None) or
                                getattr(trace, 'sessionId', None) or
                                None
                            )
                        else:
                            conversation_id = (
                                getattr(trace_metadata, 'conversation_id', None) or
                                getattr(trace_metadata, 'conversationId', None) or
                                getattr(trace, 'session_id', None) or
                                getattr(trace, 'sessionId', None) or
                                None
                            )
                    
                    # Extract company name from metadata
                    if isinstance(trace_metadata, dict):
                        company_name = (
                            trace_metadata.get('company_name') or
                            trace_metadata.get('companyName') or
                            trace_metadata.get('company') or
                            'Unknown Company'
                        )
                    else:
                        company_name = (
                            getattr(trace_metadata, 'company_name', None) or
                            getattr(trace_metadata, 'companyName', None) or
                            getattr(trace_metadata, 'company', None) or
                            'Unknown Company'
                        )
                    
                    # Extract timestamp
                    timestamp = trace_timestamp or datetime.now()
                    if isinstance(timestamp, str):
                        try:
                            timestamp = timestamp.replace('Z', '+00:00')
                            timestamp = datetime.fromisoformat(timestamp)
                        except:
                            try:
                                timestamp = datetime.fromtimestamp(float(timestamp))
                            except:
                                timestamp = datetime.now()
                    
                    # Extract success/failure from metadata.tools
                    success_count = 0
                    failure_count = 0
                    if isinstance(trace_metadata, dict):
                        tools_data = trace_metadata.get('tools', {})
                        if isinstance(tools_data, dict):
                            success_count = tools_data.get('successful', 0) or 0
                            failure_count = tools_data.get('failed', 0) or 0
                    else:
                        try:
                            tools_data = getattr(trace_metadata, 'tools', None)
                            if tools_data:
                                if isinstance(tools_data, dict):
                                    success_count = tools_data.get('successful', 0) or 0
                                    failure_count = tools_data.get('failed', 0) or 0
                                else:
                                    success_count = getattr(tools_data, 'successful', 0) or 0
                                    failure_count = getattr(tools_data, 'failed', 0) or 0
                        except:
                            pass
                    
                    # Convert to integers
                    try:
                        success_count = int(success_count) if success_count else 0
                    except (ValueError, TypeError):
                        success_count = 0
                    try:
                        failure_count = int(failure_count) if failure_count else 0
                    except (ValueError, TypeError):
                        failure_count = 0
                    
                    traces.append({
                        'company_name': str(company_name),
                        'conversation_id': str(conversation_id) if conversation_id else f"trace_{trace_id}",
                        'trace_id': str(trace_id),
                        'timestamp': timestamp,
                        'success_count': success_count,
                        'failure_count': failure_count
                    })
                
                # Check if there are more pages
                if not has_more or len(batch) < page_size:
                    break
                
                page += 1
                
                # Safety check: prevent infinite loops
                if page > max_pages:
                    st.info(f"Reached maximum page limit ({max_pages}). Fetched {len(traces)} traces so far.")
                    break
                
            except requests.exceptions.RequestException as e:
                st.error(f"Network error fetching traces: {str(e)}")
                break
            except Exception as e:
                st.warning(f"Error fetching traces page {page}: {str(e)}")
                # Don't break on first error, try to continue
                if page == 1:
                    break  # Break if first page fails
                page += 1
                if page > max_pages:  # Safety limit
                    st.info(f"Reached maximum page limit ({max_pages}). Fetched {len(traces)} traces so far.")
                    break
        
        # Store debug info in session state for display at bottom
        if traces:
            unique_companies = set(t['company_name'] for t in traces)
            if 'debug_info' not in st.session_state:
                st.session_state.debug_info = []
            st.session_state.debug_info.append(f"Fetched {len(traces)} traces from {len(unique_companies)} unique companies (before filtering test companies)")
        
        return traces
        
    except Exception as e:
        st.error(f"Failed to fetch traces from Langfuse: {str(e)}")
        import traceback
        st.debug(traceback.format_exc())
        return []


# List of test companies to exclude
TEST_COMPANIES = {
    'startx', 'startxcommunity', 'invoicemate', 'leoadsai', 'test',
    'fibonacci101', 'fibonacci', 'fibonacci300', 'test-company', 'thisworks',
    'vandelayindustries', 'redbull', 'avery', 'averymagoriumswonderemporium',
    'holly', 'unknown company', 'finaltest', 'leotest',
    'tombroschinskydigitallic', 'tombroschinskydigitalllc', 'wawa', 'agoodcompany',
    'tesla', 'pacarana', 'apple', 'prada', 'bruce', 'intuit'
}


def aggregate_company_conversations(traces: List[Dict]) -> pd.DataFrame:
    """
    Aggregate trace data by company to show both conversation counts and tool call counts.
    Excludes test companies and counts unique conversations and total tool calls per company.
    
    Args:
        traces: List of trace dictionaries with company_name and conversation_id
    
    Returns:
        DataFrame with columns: Company, Number of Conversations, Number of Tool Calls
    """
    if not traces:
        return pd.DataFrame(columns=['Company', 'Number of Conversations', 'Number of Tool Calls'])
    
    # Convert to DataFrame
    df = pd.DataFrame(traces)
    
    # Filter out test companies (case-insensitive)
    df = df[~df['company_name'].str.lower().isin([c.lower() for c in TEST_COMPANIES])]
    
    if len(df) == 0:
        return pd.DataFrame(columns=['Company', 'Number of Conversations', 'Number of Tool Calls'])
    
    # Count unique conversations per company
    unique_conversations = df.groupby(['company_name', 'conversation_id']).size().reset_index(name='count')
    conversation_counts = unique_conversations.groupby('company_name').agg({
        'conversation_id': 'count'  # Count unique conversations
    }).reset_index()
    conversation_counts.columns = ['Company', 'Number of Conversations']
    
    # Count total tool calls (all traces/agentMeta occurrences) per company
    tool_call_counts = df.groupby('company_name').agg({
        'trace_id': 'count'  # Count all traces (tool calls)
    }).reset_index()
    tool_call_counts.columns = ['Company', 'Number of Tool Calls']
    
    # Aggregate success and failure counts per company
    if 'success_count' in df.columns and 'failure_count' in df.columns:
        success_failure_counts = df.groupby('company_name').agg({
            'success_count': 'sum',
            'failure_count': 'sum'
        }).reset_index()
        success_failure_counts.columns = ['Company', 'Success Count', 'Failure Count']
    else:
        # If no success/failure data, set to 0
        success_failure_counts = tool_call_counts[['Company']].copy()
        success_failure_counts['Success Count'] = 0
        success_failure_counts['Failure Count'] = 0
    
    # Merge all metrics
    aggregated = conversation_counts.merge(tool_call_counts, on='Company', how='outer')
    aggregated = aggregated.merge(success_failure_counts, on='Company', how='outer').fillna(0)
    
    # Convert to integers
    aggregated['Number of Conversations'] = aggregated['Number of Conversations'].astype(int)
    aggregated['Number of Tool Calls'] = aggregated['Number of Tool Calls'].astype(int)
    aggregated['Success Count'] = aggregated['Success Count'].astype(int)
    aggregated['Failure Count'] = aggregated['Failure Count'].astype(int)
    
    # Sort by number of conversations (descending)
    aggregated = aggregated.sort_values('Number of Conversations', ascending=False)
    
    return aggregated


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_tool_calls_by_company(
    _client: Langfuse,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> List[Dict]:
    """
    Fetch individual tool calls from Langfuse traces.
    Extracts tool_name and success status from trace output.tool_call.
    
    Args:
        _client: Langfuse client instance
        start_time: Start datetime for filtering
        end_time: End datetime for filtering
    
    Returns:
        List of tool call dictionaries with company_name, tool_name, success, timestamp
    """
    if _client is None:
        return []
    
    try:
        # First, fetch traces to get trace IDs and company info
        traces = fetch_traces_by_company(_client, start_time, end_time)
        if not traces:
            return []
        
        # Get credentials for API calls
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
        
        # Fall back to Streamlit secrets if env vars not set
        if not public_key or not secret_key:
            try:
                langfuse_config = st.secrets.get("langfuse", {})
                public_key = public_key or langfuse_config.get("public_key", "")
                secret_key = secret_key or langfuse_config.get("secret_key", "")
                if host == "https://cloud.langfuse.com":
                    host = langfuse_config.get("host", host)
            except Exception:
                pass
        
        if not public_key or not secret_key:
            return []
        
        # Setup authentication
        auth_string = f"{public_key}:{secret_key}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/json'
        }
        
        tool_calls = []
        
        # Fetch full trace details to extract tool_call from output
        for trace in traces:
            trace_id = trace.get('trace_id', '')
            company_name = trace.get('company_name', 'Unknown Company')
            trace_timestamp = trace.get('timestamp', datetime.now())
            
            if not trace_id:
                continue
            
            try:
                # Fetch full trace details
                url = f"{host}/api/public/traces/{trace_id}"
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    trace_data = response.json()
                    
                    # Extract tool_call from output
                    # Check various possible locations for output
                    output = (
                        trace_data.get('output') or
                        trace_data.get('outputs') or
                        (trace_data.get('observations', []) if isinstance(trace_data.get('observations'), list) else None)
                    )
                    
                    # Handle different output formats
                    tool_call_list = []
                    
                    if isinstance(output, dict):
                        # If output is a dict, look for tool_call field
                        tool_call = output.get('tool_call') or output.get('tool_calls')
                        if tool_call:
                            if isinstance(tool_call, list):
                                tool_call_list = tool_call
                            else:
                                tool_call_list = [tool_call]
                    elif isinstance(output, list):
                        # If output is a list, check each item for tool_call
                        for item in output:
                            if isinstance(item, dict):
                                tool_call = item.get('tool_call') or item.get('tool_calls')
                                if tool_call:
                                    if isinstance(tool_call, list):
                                        tool_call_list.extend(tool_call)
                                    else:
                                        tool_call_list.append(tool_call)
                    elif isinstance(output, str):
                        # If output is a string, try to parse as JSON
                        try:
                            import json
                            parsed_output = json.loads(output)
                            if isinstance(parsed_output, dict):
                                tool_call = parsed_output.get('tool_call') or parsed_output.get('tool_calls')
                                if tool_call:
                                    if isinstance(tool_call, list):
                                        tool_call_list = tool_call
                                    else:
                                        tool_call_list = [tool_call]
                        except:
                            pass
                    
                    # Also check if tool_call is directly in trace_data
                    if not tool_call_list:
                        tool_call = trace_data.get('tool_call') or trace_data.get('tool_calls')
                        if tool_call:
                            if isinstance(tool_call, list):
                                tool_call_list = tool_call
                            else:
                                tool_call_list = [tool_call]
                    
                    # Extract tool_name and success from each tool_call
                    for tool_call_item in tool_call_list:
                        if not isinstance(tool_call_item, dict):
                            continue
                        
                        # Extract tool_name
                        tool_name = (
                            tool_call_item.get('tool_name') or
                            tool_call_item.get('toolName') or
                            tool_call_item.get('name') or
                            'Unknown Tool'
                        )
                        
                        # Extract success status
                        success = tool_call_item.get('success')
                        if success is None:
                            # Default to True if not specified
                            success = True
                        else:
                            # Convert to boolean
                            success = bool(success)
                        
                        tool_calls.append({
                            'company_name': company_name,
                            'tool_name': str(tool_name),
                            'success': success,
                            'timestamp': trace_timestamp
                        })
                
                elif response.status_code == 404:
                    # Trace not found, skip
                    continue
                else:
                    # Skip this trace if we can't fetch it
                    continue
                    
            except requests.exceptions.RequestException:
                # Skip this trace if there's a network error
                continue
            except Exception as e:
                # Skip this trace on any other error
                if 'debug_info' not in st.session_state:
                    st.session_state.debug_info = []
                st.session_state.debug_info.append(f"Error processing trace {trace_id}: {str(e)}")
                continue
        
        # Debug: Log results
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = []
        if tool_calls:
            st.session_state.debug_info.append(f"Successfully fetched {len(tool_calls)} tool calls from trace output")
        else:
            st.session_state.debug_info.append("No tool calls found in trace output")
        
        return tool_calls
        
    except Exception as e:
        if 'debug_info' not in st.session_state:
            st.session_state.debug_info = []
        st.session_state.debug_info.append(f"Error fetching tool calls: {str(e)}")
        st.error(f"Failed to fetch tool calls from Langfuse: {str(e)}")
        import traceback
        st.debug(traceback.format_exc())
        return []


def aggregate_tool_calls_by_name(tool_calls: List[Dict]) -> pd.DataFrame:
    """
    Aggregate tool call data by company and tool name.
    Excludes test companies and calculates success rates.
    
    Args:
        tool_calls: List of tool call dictionaries with company_name, tool_name, success
    
    Returns:
        DataFrame with columns: Company, Tool Name, Total Calls, Successful, Failed, Success Rate (%)
    """
    if not tool_calls:
        return pd.DataFrame(columns=['Company', 'Tool Name', 'Total Calls', 'Successful', 'Failed', 'Success Rate (%)'])
    
    # Convert to DataFrame
    df = pd.DataFrame(tool_calls)
    
    # Filter out test companies (case-insensitive)
    df = df[~df['company_name'].str.lower().isin([c.lower() for c in TEST_COMPANIES])]
    
    if len(df) == 0:
        return pd.DataFrame(columns=['Company', 'Tool Name', 'Total Calls', 'Successful', 'Failed', 'Success Rate (%)'])
    
    # Group by company and tool name, count successes and failures
    aggregated = df.groupby(['company_name', 'tool_name']).agg({
        'success': ['count', 'sum']  # count = total, sum = successful (True = 1, False = 0)
    }).reset_index()
    
    # Flatten column names
    aggregated.columns = ['Company', 'Tool Name', 'Total Calls', 'Successful']
    
    # Calculate failed calls
    aggregated['Failed'] = aggregated['Total Calls'] - aggregated['Successful']
    
    # Calculate success rate
    aggregated['Success Rate (%)'] = (aggregated['Successful'] / aggregated['Total Calls'] * 100).round(1)
    
    # Convert to integers
    aggregated['Total Calls'] = aggregated['Total Calls'].astype(int)
    aggregated['Successful'] = aggregated['Successful'].astype(int)
    aggregated['Failed'] = aggregated['Failed'].astype(int)
    
    # Sort by company, then by total calls (descending)
    aggregated = aggregated.sort_values(['Company', 'Total Calls'], ascending=[True, False])
    
    return aggregated

