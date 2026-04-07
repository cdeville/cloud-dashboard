import streamlit as st
import boto3
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
from pathlib import Path

# Add parent directory to path for shared_libs import
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared_libs import get_aws_profiles

# Page config
st.set_page_config(
    page_title="EC2 Dashboard - AWS Dashboard",
    layout="wide"
)

st.title("EC2 Dashboard")

# Initialize AWS client
@st.cache_resource
def get_ec2_client(region='us-east-2', profile=None):
    """Initialize AWS EC2 client"""
    if profile:
        session = boto3.Session(profile_name=profile)
        return session.client('ec2', region_name=region)
    return boto3.client('ec2', region_name=region)

# Fetch EC2 instances
@st.cache_data(ttl=300)
def get_ec2_instances(region='us-east-2', profile=None):
    """Fetch all EC2 instances with details"""
    client = get_ec2_client(region, profile)
    instances_data = []
    
    try:
        # Describe all instances
        response = client.describe_instances()
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                # Get Name tag if it exists
                name_tag = 'N/A'
                if 'Tags' in instance:
                    for tag in instance['Tags']:
                        if tag['Key'] == 'Name':
                            name_tag = tag['Value']
                            break
                
                # Get IAM Role
                iam_role = 'N/A'
                if 'IamInstanceProfile' in instance:
                    # Extract role name from ARN
                    iam_profile_arn = instance['IamInstanceProfile'].get('Arn', '')
                    if iam_profile_arn:
                        iam_role = iam_profile_arn.split('/')[-1]
                
                # Get Private IP
                private_ip = instance.get('PrivateIpAddress', 'N/A')
                
                # Get Public IP if exists
                public_ip = instance.get('PublicIpAddress', 'N/A')
                
                # Get Launch Time
                launch_time = instance.get('LaunchTime', None)
                launch_time_str = launch_time.strftime('%Y-%m-%d %H:%M:%S UTC') if launch_time else 'N/A'
                
                instances_data.append({
                    'Name': name_tag,
                    'Instance ID': instance['InstanceId'],
                    'Instance State': instance['State']['Name'],
                    'Instance Type': instance['InstanceType'],
                    'Private IP': private_ip,
                    'Public IP': public_ip,
                    'Availability Zone': instance['Placement']['AvailabilityZone'],
                    'IAM Role': iam_role,
                    'Platform': instance.get('Platform', 'Linux/Unix'),
                    'Launch Time': launch_time_str,
                    'VPC ID': instance.get('VpcId', 'N/A'),
                    'Subnet ID': instance.get('SubnetId', 'N/A')
                })
        
    except Exception as e:
        st.error(f"Error fetching EC2 instances: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(instances_data)

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
st.header(f"EC2 Instances in {region} ({profile})")

# Fetch data
df = get_ec2_instances(region, profile)

if not df.empty:
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Instances", len(df))
    with col2:
        running_count = len(df[df['Instance State'] == 'running'])
        st.metric("Running", running_count)
    with col3:
        stopped_count = len(df[df['Instance State'] == 'stopped'])
        st.metric("Stopped", stopped_count)
    with col4:
        unique_types = df['Instance Type'].nunique()
        st.metric("Instance Types", unique_types)
    
    # Charts
    st.subheader("Visualizations")
    
    # Row 1 - State and Type distribution
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Instances by State")
        state_counts = df['Instance State'].value_counts()
        # Color map for different states
        color_map = {
            'running': '#2ecc71',
            'stopped': '#e74c3c',
            'pending': '#f39c12',
            'stopping': '#e67e22',
            'terminated': '#95a5a6',
            'terminating': '#c0392b'
        }
        colors = [color_map.get(state, '#3498db') for state in state_counts.index]
        fig = px.pie(
            values=state_counts.values, 
            names=state_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("#### Instances by Type")
        type_counts = df['Instance Type'].value_counts().head(10)
        fig = px.bar(
            x=type_counts.index,
            y=type_counts.values,
            labels={'x': 'Instance Type', 'y': 'Count'}
        )
        fig.update_layout(showlegend=False, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    
    # Row 2 - AZ distribution and State Timeline
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Instances by Availability Zone")
        az_counts = df['Availability Zone'].value_counts()
        fig = px.bar(
            x=az_counts.index,
            y=az_counts.values,
            labels={'x': 'Availability Zone', 'y': 'Count'},
            color=az_counts.values,
            color_continuous_scale='viridis'
        )
        fig.update_layout(showlegend=False, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("#### Instances by Platform")
        platform_counts = df['Platform'].value_counts()
        fig = px.pie(
            values=platform_counts.values,
            names=platform_counts.index
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Data table
    st.subheader("Instance Details")
    
    # Add filter options
    col1, col2 = st.columns(2)
    with col1:
        state_filter = st.multiselect(
            "Filter by State",
            options=df['Instance State'].unique(),
            default=df['Instance State'].unique()
        )
    with col2:
        type_filter = st.multiselect(
            "Filter by Instance Type",
            options=sorted(df['Instance Type'].unique()),
            default=df['Instance Type'].unique()
        )
    
    # Apply filters
    filtered_df = df[
        (df['Instance State'].isin(state_filter)) &
        (df['Instance Type'].isin(type_filter))
    ]
    
    # Sort by State (running first) then by Name
    state_order = ['running', 'pending', 'stopping', 'stopped', 'terminated', 'terminating']
    filtered_df['State_Order'] = filtered_df['Instance State'].apply(
        lambda x: state_order.index(x) if x in state_order else 999
    )
    filtered_df = filtered_df.sort_values(['State_Order', 'Name']).drop('State_Order', axis=1)
    
    st.dataframe(
        filtered_df,
        use_container_width=True,
        height=500
    )
    
    # Download button
    csv = filtered_df.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"ec2_instances_{region}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.info("No EC2 instances found or unable to connect to AWS.")
    st.markdown("""
    ### Troubleshooting
    
    Make sure your AWS credentials are configured:
    - Environment variables: `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_PROFILE`
    - Or mount your `~/.aws` credentials directory
    
    Check that your IAM user/role has permissions for:
    - `ec2:DescribeInstances`
    """)
