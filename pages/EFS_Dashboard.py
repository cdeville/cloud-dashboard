import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Add parent directory to path for shared_libs import
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared_libs import get_aws_profiles, get_aws_client

# Page config
st.set_page_config(
    page_title="EFS Dashboard - AWS Dashboard",
    layout="wide"
)

st.title("EFS Dashboard")


# Fetch EFS file systems
@st.cache_data(ttl=300)
def get_efs_file_systems(region='us-east-2', profile=None):
    """Fetch all EFS file systems with details"""
    efs_client = get_aws_client('efs', region, profile)
    file_systems_data = []
    
    try:
        # Describe all file systems
        response = efs_client.describe_file_systems()
        
        for fs in response['FileSystems']:
            file_system_id = fs['FileSystemId']
            
            # Get name from tags
            name = 'N/A'
            if 'Tags' in fs:
                for tag in fs['Tags']:
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break
            
            # Get size in GB
            size_bytes = fs['SizeInBytes']['Value']
            size_gb = size_bytes / (1024**3)
            
            # Get encryption status
            encrypted = fs.get('Encrypted', False)
            encryption_status = 'Encrypted' if encrypted else 'Not Encrypted'
            
            # Get lifecycle state
            lifecycle_state = fs.get('LifeCycleState', 'N/A')
            
            # Get creation time
            creation_time = fs.get('CreationTime')
            creation_time_str = creation_time.strftime('%Y-%m-%d %H:%M:%S UTC') if creation_time else 'N/A'
            
            # Get performance mode
            performance_mode = fs.get('PerformanceMode', 'N/A')
            
            # Get throughput mode
            throughput_mode = fs.get('ThroughputMode', 'N/A')
            
            # Get number of mount targets (indicates AZ count)
            mount_targets = efs_client.describe_mount_targets(FileSystemId=file_system_id)
            num_mount_targets = len(mount_targets.get('MountTargets', []))
            
            # Get availability zones
            availability_zones = []
            for mt in mount_targets.get('MountTargets', []):
                az = mt.get('AvailabilityZoneName', 'N/A')
                if az not in availability_zones:
                    availability_zones.append(az)
            az_list = ', '.join(availability_zones) if availability_zones else 'N/A'
            
            # Get replication configuration
            replication_status = 'None'
            replication_destination = 'N/A'
            replication_overwrite_protection = 'N/A'
            try:
                replication_config = efs_client.describe_replication_configurations(
                    FileSystemId=file_system_id
                )
                replications = replication_config.get('Replications', [])
                if replications:
                    replication_status = 'Enabled'
                    destinations = []
                    for repl in replications:
                        for dest in repl.get('Destinations', []):
                            dest_fs_id = dest.get('FileSystemId', 'N/A')
                            dest_region = dest.get('Region', 'N/A')
                            destinations.append(f"{dest_fs_id} ({dest_region})")
                            # Get overwrite protection status
                            replication_overwrite_protection = dest.get('Status', 'N/A')
                    replication_destination = ', '.join(destinations) if destinations else 'N/A'
            except Exception:
                # Replication might not be configured
                pass
            
            file_systems_data.append({
                'Name': name,
                'File System ID': file_system_id,
                'State': lifecycle_state,
                'Encryption': encryption_status,
                'Size (GB)': f"{size_gb:.2f}",
                'Mount Targets': num_mount_targets,
                'Availability Zones': az_list,
                'Performance Mode': performance_mode,
                'Throughput Mode': throughput_mode,
                'Replication': replication_status,
                'Replication Destination': replication_destination,
                'Overwrite Protection': replication_overwrite_protection,
                'Created': creation_time_str
            })
        
    except Exception as e:
        st.error(f"Error fetching EFS file systems: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(file_systems_data)


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
st.header(f"EFS File Systems in {region} ({profile})")

# Fetch data
df = get_efs_file_systems(region, profile)

if not df.empty:
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total File Systems", len(df))
    with col2:
        encrypted_count = len(df[df['Encryption'] == 'Encrypted'])
        st.metric("Encrypted", encrypted_count)
    with col3:
        available_count = len(df[df['State'] == 'available'])
        st.metric("Available", available_count)
    with col4:
        # Calculate total size
        total_size = sum([float(size) for size in df['Size (GB)']])
        st.metric("Total Size (GB)", f"{total_size:.2f}")
    
    # Charts
    st.subheader("Visualizations")
    
    # Row 1 - State, Encryption, and Replication
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### File Systems by State")
        state_counts = df['State'].value_counts()
        color_map = {
            'available': '#2ecc71',
            'creating': '#f39c12',
            'deleting': '#e74c3c',
            'deleted': '#95a5a6',
            'error': '#c0392b'
        }
        colors = [color_map.get(state, '#3498db') for state in state_counts.index]
        fig = px.pie(
            values=state_counts.values,
            names=state_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    with col2:
        st.markdown("#### Encryption Status")
        encryption_counts = df['Encryption'].value_counts()
        color_map_encryption = {
            'Encrypted': '#2ecc71',
            'Not Encrypted': '#e74c3c'
        }
        colors = [color_map_encryption.get(status, '#3498db') for status in encryption_counts.index]
        fig = px.pie(
            values=encryption_counts.values,
            names=encryption_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    with col3:
        st.markdown("#### Replication Status")
        repl_counts = df['Replication'].value_counts()
        color_map_repl = {
            'Enabled': '#2ecc71',
            'None': '#95a5a6'
        }
        colors = [color_map_repl.get(status, '#3498db') for status in repl_counts.index]
        fig = px.pie(
            values=repl_counts.values,
            names=repl_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    # Security Summary
    st.subheader("Security Summary")
    col1, col2 = st.columns(2)
    
    with col1:
        unencrypted = len(df[df['Encryption'] == 'Not Encrypted'])
        if unencrypted > 0:
            st.warning(f"⚠️ {unencrypted} file system(s) without encryption")
        else:
            st.success("✅ All file systems are encrypted")
    
    with col2:
        no_replication = len(df[df['Replication'] == 'None'])
        if no_replication > 0:
            st.info(f"ℹ️ {no_replication} file system(s) without replication")
        else:
            st.success("✅ All file systems have replication enabled")
    
    # Data table
    st.subheader("File System Details")
    
    # Add filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        state_filter = st.multiselect(
            "Filter by State",
            options=df['State'].unique(),
            default=df['State'].unique()
        )
    with col2:
        encryption_filter = st.multiselect(
            "Filter by Encryption",
            options=df['Encryption'].unique(),
            default=df['Encryption'].unique()
        )
    with col3:
        replication_filter = st.multiselect(
            "Filter by Replication",
            options=df['Replication'].unique(),
            default=df['Replication'].unique()
        )
    
    # Apply filters
    filtered_df = df[
        (df['State'].isin(state_filter)) &
        (df['Encryption'].isin(encryption_filter)) &
        (df['Replication'].isin(replication_filter))
    ]
    
    # Sort by Name
    filtered_df = filtered_df.sort_values('Name')
    
    st.dataframe(
        filtered_df,
        width='stretch',
        height=500
    )
    
    # Download button
    csv = filtered_df.to_csv(index=False)
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"efs_file_systems_{region}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.info("No EFS file systems found or unable to connect to AWS.")
    st.markdown("""
    ### Troubleshooting
    
    Make sure your AWS credentials are configured:
    - Environment variables: `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_PROFILE`
    - Or mount your `~/.aws` credentials directory
    
    Check that your IAM user/role has permissions for:
    - `elasticfilesystem:DescribeFileSystems`
    - `elasticfilesystem:DescribeMountTargets`
    - `elasticfilesystem:DescribeReplicationConfigurations`
    """)
