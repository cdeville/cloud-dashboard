import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add parent directory to path for shared_libs import
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared_libs import get_aws_profiles, get_aws_client

# Page config
st.set_page_config(
    page_title="Lambda Failures - AWS Dashboard",
    layout="wide"
)

st.title("Lambda Failures Dashboard")

# Fetch Lambda functions with failure metrics
@st.cache_data(ttl=300)
def get_failed_functions(region='us-east-2', profile=None, days=7):
    """Fetch Lambda functions that have failures in the specified time period"""
    lambda_client = get_aws_client('lambda', region, profile)
    cloudwatch = get_aws_client('cloudwatch', region, profile)
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    failed_functions = []
    
    try:
        # Get all Lambda functions
        paginator = lambda_client.get_paginator('list_functions')
        
        for page in paginator.paginate():
            for func in page['Functions']:
                function_name = func['FunctionName']
                
                # Get error metrics
                errors_response = cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Errors',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,  # 1 hour periods
                    Statistics=['Sum']
                )
                
                # Get invocation count
                invocations_response = cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Invocations',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                # Get throttles
                throttles_response = cloudwatch.get_metric_statistics(
                    Namespace='AWS/Lambda',
                    MetricName='Throttles',
                    Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
                    StartTime=start_time,
                    EndTime=end_time,
                    Period=3600,
                    Statistics=['Sum']
                )
                
                total_errors = sum(dp['Sum'] for dp in errors_response['Datapoints'])
                total_invocations = sum(dp['Sum'] for dp in invocations_response['Datapoints'])
                total_throttles = sum(dp['Sum'] for dp in throttles_response['Datapoints'])
                
                # Only include functions with errors
                if total_errors > 0:
                    error_rate = (total_errors / total_invocations * 100) if total_invocations > 0 else 0
                    
                    # Get the most recent error timestamp
                    if errors_response['Datapoints']:
                        sorted_errors = sorted(errors_response['Datapoints'], key=lambda x: x['Timestamp'], reverse=True)
                        last_error_time = sorted_errors[0]['Timestamp']
                    else:
                        last_error_time = None
                    
                    failed_functions.append({
                        'Function Name': function_name,
                        'Total Errors': int(total_errors),
                        'Total Invocations': int(total_invocations),
                        'Error Rate (%)': round(error_rate, 2),
                        'Throttles': int(total_throttles),
                        'Runtime': func.get('Runtime', 'Container'),
                        'Last Error': last_error_time.strftime('%Y-%m-%d %H:%M:%S UTC') if last_error_time else 'N/A',
                        'Timeout (s)': func['Timeout'],
                        'Memory (MB)': func['MemorySize']
                    })
    
    except Exception as e:
        st.error(f"Error fetching failed functions: {str(e)}")
        return pd.DataFrame()
    
    df = pd.DataFrame(failed_functions)
    if not df.empty:
        df = df.sort_values('Total Errors', ascending=False)
    return df

# Get error timeline for a specific function
@st.cache_data(ttl=300)
def get_error_timeline(function_name, region='us-east-2', profile=None, days=7):
    """Get error timeline for visualization"""
    cloudwatch = get_aws_client('cloudwatch', region, profile)
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Errors',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,  # 1 hour intervals
            Statistics=['Sum']
        )
        
        datapoints = response['Datapoints']
        if datapoints:
            df = pd.DataFrame(datapoints)
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df = df.sort_values('Timestamp')
            return df
        
    except Exception as e:
        st.error(f"Error fetching timeline: {str(e)}")
    
    return pd.DataFrame()

# Search CloudWatch Logs for ERROR messages
@st.cache_data(ttl=300)
def search_error_logs(function_name, region='us-east-2', profile=None, days=7, max_results=50):
    """Search CloudWatch Logs for ERROR messages"""
    logs_client = get_aws_client('logs', region, profile)
    
    log_group_name = f"/aws/lambda/{function_name}"
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)
    
    error_logs = []
    
    try:
        # Check if log group exists
        try:
            logs_client.describe_log_groups(logGroupNamePrefix=log_group_name, limit=1)
        except Exception:
            return pd.DataFrame({'Message': ['Log group not found']})
        
        # Search for ERROR in logs
        response = logs_client.filter_log_events(
            logGroupName=log_group_name,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern='ERROR',
            limit=max_results
        )
        
        for event in response['events']:
            error_logs.append({
                'Timestamp': datetime.fromtimestamp(event['timestamp'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'Log Stream': event['logStreamName'],
                'Message': event['message']
            })
        
        # Continue pagination if needed
        while 'nextToken' in response and len(error_logs) < max_results:
            response = logs_client.filter_log_events(
                logGroupName=log_group_name,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                filterPattern='ERROR',
                limit=max_results - len(error_logs),
                nextToken=response['nextToken']
            )
            
            for event in response['events']:
                error_logs.append({
                    'Timestamp': datetime.fromtimestamp(event['timestamp'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                    'Log Stream': event['logStreamName'],
                    'Message': event['message']
                })
    
    except Exception as e:
        st.error(f"Error searching logs: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(error_logs)

# Sidebar
st.sidebar.header("Settings")

# Get available profiles
available_profiles = get_aws_profiles()
current_profile = os.environ.get('AWS_PROFILE', 'default')

# Set default index
default_profile_index = 0
if current_profile in available_profiles:
    default_profile_index = available_profiles.index(current_profile)

profile = st.sidebar.selectbox(
    "AWS Profile",
    available_profiles,
    index=default_profile_index
)

region = st.sidebar.selectbox(
    "AWS Region",
    ["us-east-1", "us-east-2", "us-west-2"],
    index=1
)

days = st.sidebar.slider(
    "Time Range (days)",
    min_value=1,
    max_value=14,
    value=7
)

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# Main content
st.header(f"Lambda Failures in {region} ({profile}) - Last {days} days")

# Fetch failed functions
df = get_failed_functions(region, profile, days)

if not df.empty:
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Functions with Errors", len(df))
    with col2:
        st.metric("Total Errors", int(df['Total Errors'].sum()))
    with col3:
        st.metric("Avg Error Rate", f"{df['Error Rate (%)'].mean():.2f}%")
    with col4:
        st.metric("Total Throttles", int(df['Throttles'].sum()))
    
    # Charts
    st.subheader("Top 10 Functions by Error Count")

    # Bar chart of top functions
    top_10 = df.head(10)
    fig = px.bar(
        top_10,
        x='Function Name',
        y='Total Errors',
        title='Top 10 Functions by Total Errors',
        hover_data=['Function Name', 'Total Errors'],
        color='Error Rate (%)',
        color_continuous_scale='Reds'
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, width='stretch')
    
    # Failed functions table
    st.subheader("Functions with Failures")
    st.dataframe(
        df,
        width='stretch',
        height=300
    )
    
    # Download button
    csv = df.to_csv(index=False)
    st.download_button(
        label="Download Failed Functions CSV",
        data=csv,
        file_name=f"lambda_failures_{region}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
    
    # Function details section
    st.markdown("---")
    st.subheader("Function Error Analysis")
    
    selected_function = st.selectbox(
        "Select a function to view detailed errors:",
        df['Function Name'].tolist()
    )
    
    if selected_function:
        # Error timeline
        st.markdown(f"### Error Timeline: {selected_function}")
        timeline_df = get_error_timeline(selected_function, region, profile, days)
        
        if not timeline_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=timeline_df['Timestamp'],
                y=timeline_df['Sum'],
                mode='lines+markers',
                name='Errors',
                line=dict(color='red', width=2),
                marker=dict(size=8)
            ))
            fig.update_layout(
                title=f'Error Timeline (Hourly)',
                xaxis_title='Time',
                yaxis_title='Error Count',
                hovermode='x unified'
            )
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No timeline data available")
        
        # Error logs
        st.markdown(f"### Recent ERROR Logs: {selected_function}")
        max_logs = st.slider("Max log entries to retrieve", 10, 200, 50)
        
        with st.spinner("Searching CloudWatch Logs for ERROR messages..."):
            logs_df = search_error_logs(selected_function, region, profile, days, max_logs)
        
        if not logs_df.empty and 'Message' in logs_df.columns:
            st.info(f"Found {len(logs_df)} log entries containing 'ERROR'")
            
            # Show logs in expandable sections
            for idx, row in logs_df.iterrows():
                with st.expander(f"{row['Timestamp']} - {row.get('Log Stream', 'N/A')}"):
                    st.code(row['Message'], language='text')
            
            # Download logs
            csv_logs = logs_df.to_csv(index=False)
            st.download_button(
                label="Download Error Logs CSV",
                data=csv_logs,
                file_name=f"lambda_error_logs_{selected_function}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No ERROR messages found in CloudWatch Logs for this function in the selected time range.")

else:
    st.success("No Lambda functions with errors found in the selected time range!")
    st.markdown("""
    ### What this means
    
    - All Lambda functions are executing successfully
    - No functions have reported errors in the last {} days
    - This is a healthy state for your Lambda infrastructure
    
    ### Tips
    
    - Consider expanding the time range to see historical failures
    - Check individual Lambda dashboards for performance metrics
    - Ensure CloudWatch alarms are configured for critical functions
    """.format(days))

# Help section
with st.expander("About This Dashboard"):
    st.markdown("""
    ### Lambda Failures Dashboard
    
    This dashboard helps you monitor and troubleshoot Lambda function failures:
    
    **Features:**
    - View all functions with errors in the selected time range
    - Analyze error rates and patterns
    - Visualize error timelines
    - Search CloudWatch Logs for ERROR messages
    - Download detailed reports
    
    **Metrics Explained:**
    - **Total Errors**: Number of failed invocations
    - **Error Rate**: Percentage of invocations that failed
    - **Throttles**: Number of invocations rejected due to concurrency limits
    
    **Required IAM Permissions:**
    - `lambda:ListFunctions`
    - `cloudwatch:GetMetricStatistics`
    - `logs:DescribeLogGroups`
    - `logs:FilterLogEvents`
    """)
