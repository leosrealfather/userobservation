# ProjectManager Usage Dashboard

A Streamlit dashboard that monitors customer usage of the ProjectManager agent by pulling conversation data from Langfuse.

## Features

- **Real-time monitoring**: View which customers are actively using the ProjectManager agent
- **Time period filters**: Filter by Today, This Week, This Month, or Custom Range
- **Auto-refresh**: Automatically refreshes every 5 minutes
- **Clean UI**: Simple, functional interface optimized for internal tooling
- **Export data**: Download customer activity data as CSV

## Setup

### Prerequisites

- Python 3.11+
- Langfuse account with API credentials
- Streamlit

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd userobservation
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure Langfuse API credentials:
```bash
# Copy the example secrets file
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Edit .streamlit/secrets.toml with your actual credentials
```

The `secrets.toml` file should look like:
```toml
[langfuse]
public_key = "your-langfuse-public-key"
secret_key = "your-langfuse-secret-key"
host = "https://cloud.langfuse.com"  # or your self-hosted URL
```

### Running Locally

```bash
streamlit run app.py
```

The dashboard will be available at `http://localhost:8501`

## Deployment

### Docker

Build the Docker image:
```bash
docker build -t projectmanager-dashboard .
```

Run the container:
```bash
docker run -p 8501:8501 \
  -v $(pwd)/.streamlit/secrets.toml:/app/.streamlit/secrets.toml \
  projectmanager-dashboard
```

### AWS Amplify

The included `Dockerfile` is configured for deployment to AWS Amplify. Ensure your Langfuse credentials are configured as environment variables or secrets in your Amplify deployment settings.

## Project Structure

```
userobservation/
├── app.py                      # Main Streamlit application
├── langfuse_client.py          # Langfuse API client and data fetching logic
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration for deployment
├── .streamlit/
│   └── secrets.toml.example   # Example secrets configuration
├── .gitignore
└── README.md
```

## Usage

1. Select a time period from the sidebar (Today, This Week, This Month, or Custom Range)
2. View the customer activity table showing:
   - Customer/User name
   - Number of conversations
   - Last active timestamp
3. Data is automatically sorted by number of conversations (descending)
4. Click "Refresh Now" to manually update the data
5. Use "Download as CSV" to export the current view

## Configuration

### Agent Name

By default, the dashboard filters for traces with agent name "ProjectManager". To change this, modify the `agent_name` parameter in `app.py`:

```python
traces = fetch_projectmanager_traces(
    client=client,
    agent_name="YourAgentName",  # Change here
    start_time=start_time,
    end_time=end_time
)
```

### Auto-refresh Interval

The dashboard auto-refreshes every 5 minutes (300 seconds). To change this, modify the `refresh_interval` in `app.py`:

```python
refresh_interval = 300  # Change to desired seconds
```

## Error Handling

The dashboard includes error handling for:
- Missing or invalid Langfuse API credentials
- Network connectivity issues
- API rate limits (uses caching to minimize requests)
- Missing or malformed data

## Development

### Adding New Metrics

The code is structured modularly to make it easy to add new metrics:

1. Add data extraction logic in `langfuse_client.py`
2. Update the aggregation function to include new metrics
3. Add new columns to the dashboard table in `app.py`

## License

Internal tooling - for company use only.
