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
    
    Args:
        time_period: One of "today", "this_week", "this_month", "custom"
        custom_start: Start datetime for custom range
        custom_end: End datetime for custom range
    
    Returns:
        Tuple of (start_datetime, end_datetime)
    """
    now = datetime.now()
    
    if time_period == "today":
        # Last 24 hours instead of from midnight
        start = now - timedelta(hours=24)
        end = now
    elif time_period == "this_week":
        # Start of week (Monday)
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif time_period == "this_month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif time_period == "custom":
        if custom_start and custom_end:
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
                    if start_time.tzinfo is None:
                        api_params["fromTimestamp"] = start_time.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                    else:
                        start_utc = start_time.astimezone(timezone.utc).replace(tzinfo=None)
                        api_params["fromTimestamp"] = start_utc.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                if end_time:
                    if end_time.tzinfo is None:
                        api_params["toTimestamp"] = end_time.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                    else:
                        end_utc = end_time.astimezone(timezone.utc).replace(tzinfo=None)
                        api_params["toTimestamp"] = end_utc.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                
                response = requests.get(url, headers=headers, params=api_params, timeout=30)
                
                batch = []
                has_more = False
                
                if response.status_code == 200:
                    data = response.json()
                    # Handle paginated response
                    if isinstance(data, dict):
                        batch = data.get('data', [])
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
                    
                    traces.append({
                        'company_name': str(company_name),
                        'conversation_id': str(conversation_id) if conversation_id else f"trace_{trace_id}",
                        'trace_id': str(trace_id),
                        'timestamp': timestamp
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
    'tesla', 'pacarana', 'apple', 'prada', 'bruce'
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
    
    # Merge the two metrics
    aggregated = conversation_counts.merge(tool_call_counts, on='Company', how='outer').fillna(0)
    
    # Convert to integers
    aggregated['Number of Conversations'] = aggregated['Number of Conversations'].astype(int)
    aggregated['Number of Tool Calls'] = aggregated['Number of Tool Calls'].astype(int)
    
    # Sort by number of conversations (descending)
    aggregated = aggregated.sort_values('Number of Conversations', ascending=False)
    
    return aggregated

