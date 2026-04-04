import streamlit as st
import boto3
import pandas as pd
from datetime import datetime, timedelta, timezone
import plotly.express as px
import os
import sys
from pathlib import Path

# Add parent directory to path for shared_libs import
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared_libs import get_aws_profiles

# Page config
st.set_page_config(
    page_title="Lambda Functions - AWS Dashboard",
    layout="wide"
)

st.title("Lambda Functions")

# Initialize AWS clients
@st.cache_resource
def get_lambda_client(region='us-east-2', profile=None):
    """Initialize AWS Lambda client (uses AWS_PROFILE from environment)"""
    if profile:
        session = boto3.Session(profile_name=profile)
        return session.client('lambda', region_name=region)
    return boto3.client('lambda', region_name=region)

@st.cache_resource
def get_cloudwatch_client(region='us-east-2', profile=None):
    """Initialize CloudWatch client"""
    if profile:
        session = boto3.Session(profile_name=profile)
        return session.client('cloudwatch', region_name=region)
    return boto3.client('cloudwatch', region_name=region)

# Fetch Lambda invocation metrics
@st.cache_data(ttl=300)
def get_function_metrics(function_name, region='us-east-2', profile=None):
    """Get last invocation metrics for a Lambda function"""
    cloudwatch = get_cloudwatch_client(region, profile)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=7)  # Look back 7 days
    
    try:
        # Get invocation count to check if function has been invoked
        invocations = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Invocations',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=3600,  # 1 hour periods
            Statistics=['Sum']
        )
        
        if not invocations['Datapoints']:
            return None, None, None
        
        # Sort by timestamp to get the most recent
        invocations['Datapoints'].sort(key=lambda x: x['Timestamp'], reverse=True)
        last_invocation_time = invocations['Datapoints'][0]['Timestamp']
        
        # Get errors in the same time window
        errors = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Errors',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=last_invocation_time - timedelta(hours=1),
            EndTime=last_invocation_time + timedelta(hours=1),
            Period=3600,
            Statistics=['Sum']
        )
        
        has_errors = any(dp['Sum'] > 0 for dp in errors['Datapoints'])
        status = 'Failed' if has_errors else 'Success'
        
        # Get average duration over 1 hour (3600 seconds) around the last invocation time (7 days lookback window)
        duration = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Duration',
            Dimensions=[{'Name': 'FunctionName', 'Value': function_name}],
            StartTime=last_invocation_time - timedelta(hours=1),
            EndTime=last_invocation_time + timedelta(hours=1),
            Period=3600,
            Statistics=['Average']
        )
        
        avg_duration = duration['Datapoints'][0]['Average'] if duration['Datapoints'] else None
        
        return last_invocation_time, status, avg_duration
    except Exception as e:
        return None, None, None

# Fetch Lambda functions
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_lambda_functions(region='us-east-2', profile=None):
    """Fetch all Lambda functions with invocation metrics"""
    client = get_lambda_client(region, profile)
    functions = []
    
    try:
        paginator = client.get_paginator('list_functions')
        for page in paginator.paginate():
            for func in page['Functions']:
                function_name = func['FunctionName']
                
                # Get invocation metrics
                last_invocation, status, duration = get_function_metrics(function_name, region, profile)
                
                functions.append({
                    'Name': function_name,
                    'Runtime': func.get('Runtime', 'Container'),
                    'Memory (MB)': func['MemorySize'],
                    'Timeout (s)': func['Timeout'],
                    'Last Modified': func['LastModified'],
                    'Last Invocation': last_invocation.strftime('%Y-%m-%d %H:%M:%S UTC') if last_invocation else 'Never',
                    'Status': status if status else 'N/A',
                    'Duration (ms)': f"{duration:.2f}" if duration else 'N/A'
                })
    except Exception as e:
        st.error(f"Error fetching Lambda functions: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(functions)

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

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# Main content
st.header(f"Lambda Functions in {region} ({profile})")

# Fetch data
df = get_lambda_functions(region, profile)

if not df.empty:
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Functions", len(df))
    with col2:
        st.metric("Total Memory (GB)", f"{df['Memory (MB)'].sum() / 1024:.2f}")
    with col3:
        st.metric("Avg Timeout (s)", f"{df['Timeout (s)'].mean():.1f}")
    with col4:
        unique_runtimes = df['Runtime'].nunique()
        st.metric("Runtimes", unique_runtimes)
    
    # Charts
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Functions by Runtime")
        runtime_counts = df['Runtime'].value_counts()
        fig = px.pie(values=runtime_counts.values, names=runtime_counts.index)
        st.plotly_chart(fig, width='stretch')
    
    with col2:
        st.subheader("Memory Distribution")
        fig = px.histogram(df, x='Memory (MB)', nbins=20)
        st.plotly_chart(fig, width='stretch')
    
    with col3:
        st.subheader("Lambda Function Status")
        fig = px.histogram(df, x='Status', nbins=20)
        st.plotly_chart(fig, width='stretch')
    
    # Data table
    st.subheader("Function Details")
    # Sort the dataframe by Status so that functions with "Failed" appear at the top
    # df = df.sort_values('Status', ascending=True)
    st.dataframe(
        df,
        width='stretch',
        height=500
    )
    
    # Download button
    csv = df.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"lambda_functions_{region}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.info("No Lambda functions found or unable to connect to AWS.")
    st.markdown("""
    ### Troubleshooting
    
    Make sure your AWS credentials are configured:
    - Environment variables: `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_PROFILE`
    - Or mount your `~/.aws` credentials directory
    
    Check that your IAM user/role has permissions for:
    - `lambda:ListFunctions`
    - `cloudwatch:GetMetricStatistics`
    """)
