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
    page_title="RDS Dashboard - AWS Dashboard",
    layout="wide"
)

st.title("RDS Dashboard")


# Fetch RDS Instances and Aurora Clusters
@st.cache_data(ttl=300)
def get_rds_databases(region='us-east-2', profile=None):
    """Fetch all RDS instances and Aurora clusters with details"""
    rds_client = get_aws_client('rds', region, profile)
    databases_data = []
    
    try:
        # Get Aurora Clusters
        clusters_response = rds_client.describe_db_clusters()
        for cluster in clusters_response.get('DBClusters', []):
            cluster_id = cluster['DBClusterIdentifier']
            
            # Get backup retention
            backup_retention = cluster.get('BackupRetentionPeriod', 0)
            backup_status = 'Enabled' if backup_retention > 0 else 'Disabled'
            
            # Get encryption status
            encrypted = cluster.get('StorageEncrypted', False)
            encryption_status = 'Encrypted' if encrypted else 'Not Encrypted'
            
            # Get availability zones
            availability_zones = ', '.join(cluster.get('AvailabilityZones', []))
            
            # Get Multi-AZ status
            multi_az = 'Yes' if cluster.get('MultiAZ', False) else 'No'
            
            # Get capacity/instance information
            instance_info = 'N/A'
            # Check for Serverless v2 scaling configuration
            if 'ServerlessV2ScalingConfiguration' in cluster:
                scaling = cluster['ServerlessV2ScalingConfiguration']
                min_capacity = scaling.get('MinCapacity', 'N/A')
                max_capacity = scaling.get('MaxCapacity', 'N/A')
                instance_info = f"Serverless v2 ({min_capacity}-{max_capacity} ACU)"
            # Check for Serverless v1 capacity
            elif 'Capacity' in cluster:
                capacity = cluster.get('Capacity')
                instance_info = f"Serverless v1 ({capacity} ACU)"
            # Get cluster members' instance classes
            elif 'DBClusterMembers' in cluster and cluster['DBClusterMembers']:
                member_classes = set()
                for member in cluster['DBClusterMembers']:
                    # Get member instance details
                    member_id = member.get('DBInstanceIdentifier')
                    if member_id:
                        try:
                            member_details = rds_client.describe_db_instances(
                                DBInstanceIdentifier=member_id
                            )
                            if member_details['DBInstances']:
                                member_class = member_details['DBInstances'][0].get('DBInstanceClass', '')
                                if member_class:
                                    member_classes.add(member_class)
                        except Exception:
                            pass
                if member_classes:
                    instance_info = ', '.join(sorted(member_classes))
            
            databases_data.append({
                'Name': cluster_id,
                'Type': 'Aurora Cluster',
                'Engine': cluster.get('Engine', 'N/A'),
                'Engine Version': cluster.get('EngineVersion', 'N/A'),
                'Status': cluster.get('Status', 'N/A'),
                'Endpoint': cluster.get('Endpoint', 'N/A'),
                'Port': str(cluster.get('Port', 'N/A')),
                'Multi-AZ': multi_az,
                'Availability Zones': availability_zones,
                'Encryption': encryption_status,
                'Backup Retention (days)': str(backup_retention),
                'Backup Status': backup_status,
                'Parameter Group': cluster.get('DBClusterParameterGroup', 'N/A'),
                'Storage Type': 'Aurora',
                'Allocated Storage (GB)': 'Auto-scaled',
                'Instance Class': instance_info,
                'Created': str(cluster.get('ClusterCreateTime', 'N/A'))
            })
        
        # Get RDS Instances
        instances_response = rds_client.describe_db_instances()
        for instance in instances_response.get('DBInstances', []):
            instance_id = instance['DBInstanceIdentifier']
            
            # Skip Aurora instances (they're part of clusters)
            if instance.get('DBClusterIdentifier'):
                continue
            
            # Get backup retention
            backup_retention = instance.get('BackupRetentionPeriod', 0)
            backup_status = 'Enabled' if backup_retention > 0 else 'Disabled'
            
            # Get encryption status
            encrypted = instance.get('StorageEncrypted', False)
            encryption_status = 'Encrypted' if encrypted else 'Not Encrypted'
            
            # Get availability zone
            availability_zone = instance.get('AvailabilityZone', 'N/A')
            
            # Get Multi-AZ status
            multi_az = 'Yes' if instance.get('MultiAZ', False) else 'No'
            
            # Get endpoint
            endpoint_info = instance.get('Endpoint', {})
            endpoint = endpoint_info.get('Address', 'N/A')
            port = endpoint_info.get('Port', 'N/A')
            
            # Get storage info
            allocated_storage = instance.get('AllocatedStorage', 0)
            storage_type = instance.get('StorageType', 'N/A')
            
            # Get parameter and option groups
            db_param_groups = instance.get('DBParameterGroups', [])
            param_group = db_param_groups[0].get('DBParameterGroupName', 'N/A') if db_param_groups else 'N/A'
            
            option_groups = instance.get('OptionGroupMemberships', [])
            option_group = option_groups[0].get('OptionGroupName', 'N/A') if option_groups else 'N/A'
            
            # Get instance class
            instance_class = instance.get('DBInstanceClass', 'N/A')
            
            # Get creation time
            creation_time = instance.get('InstanceCreateTime')
            creation_time_str = creation_time.strftime('%Y-%m-%d %H:%M:%S UTC') if creation_time else 'N/A'
            
            databases_data.append({
                'Name': instance_id,
                'Type': 'RDS Instance',
                'Engine': instance.get('Engine', 'N/A'),
                'Engine Version': instance.get('EngineVersion', 'N/A'),
                'Status': instance.get('DBInstanceStatus', 'N/A'),
                'Endpoint': endpoint,
                'Port': str(port),
                'Multi-AZ': multi_az,
                'Availability Zones': availability_zone,
                'Encryption': encryption_status,
                'Backup Retention (days)': str(backup_retention),
                'Backup Status': backup_status,
                'Parameter Group': param_group,
                'Option Group': option_group,
                'Storage Type': storage_type,
                'Allocated Storage (GB)': str(allocated_storage),
                'Instance Class': instance_class,
                'Created': creation_time_str
            })
        
    except Exception as e:
        st.error(f"Error fetching RDS databases: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(databases_data)


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
st.header(f"RDS Databases in {region} ({profile})")

# Fetch data
df = get_rds_databases(region, profile)

if not df.empty:
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Databases", len(df))
    with col2:
        encrypted_count = len(df[df['Encryption'] == 'Encrypted'])
        st.metric("Encrypted", encrypted_count)
    with col3:
        multi_az_count = len(df[df['Multi-AZ'] == 'Yes'])
        st.metric("Multi-AZ", multi_az_count)
    with col4:
        backup_enabled = len(df[df['Backup Status'] == 'Enabled'])
        st.metric("Backups Enabled", backup_enabled)
    
    # Charts
    st.subheader("Visualizations")
    
    # Row 1 - Status, Encryption, and Backup
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### Database Status")
        status_counts = df['Status'].value_counts()
        color_map = {
            'available': '#2ecc71',
            'backing-up': '#3498db',
            'creating': '#f39c12',
            'deleting': '#e74c3c',
            'failed': '#c0392b',
            'stopped': '#95a5a6',
            'stopping': '#e67e22',
            'starting': '#f39c12'
        }
        colors = [color_map.get(status, '#3498db') for status in status_counts.index]
        fig = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    with col2:
        st.markdown("#### Encryption Status")
        encryption_counts = df['Encryption'].value_counts()
        color_map_enc = {
            'Encrypted': '#2ecc71',
            'Not Encrypted': '#e74c3c'
        }
        colors = [color_map_enc.get(status, '#3498db') for status in encryption_counts.index]
        fig = px.pie(
            values=encryption_counts.values,
            names=encryption_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    with col3:
        st.markdown("#### Backup Status")
        backup_counts = df['Backup Status'].value_counts()
        color_map_backup = {
            'Enabled': '#2ecc71',
            'Disabled': '#e74c3c'
        }
        colors = [color_map_backup.get(status, '#3498db') for status in backup_counts.index]
        fig = px.pie(
            values=backup_counts.values,
            names=backup_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    # Row 2 - Engine Distribution and Multi-AZ
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Database Engine Distribution")
        engine_counts = df['Engine'].value_counts()
        fig = px.bar(
            x=engine_counts.index,
            y=engine_counts.values,
            labels={'x': 'Engine', 'y': 'Count'},
            color=engine_counts.values,
            color_continuous_scale='viridis'
        )
        fig.update_layout(showlegend=False, xaxis_tickangle=-45)
        st.plotly_chart(fig, width='stretch')
    
    with col2:
        st.markdown("#### Multi-AZ Distribution")
        multi_az_counts = df['Multi-AZ'].value_counts()
        color_map_az = {
            'Yes': '#2ecc71',
            'No': '#95a5a6'
        }
        colors = [color_map_az.get(status, '#3498db') for status in multi_az_counts.index]
        fig = px.pie(
            values=multi_az_counts.values,
            names=multi_az_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    # Security & Reliability Summary
    st.subheader("Security & Reliability Summary")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        unencrypted = len(df[df['Encryption'] == 'Not Encrypted'])
        if unencrypted > 0:
            st.warning(f"⚠️ {unencrypted} database(s) without encryption")
        else:
            st.success("✅ All databases are encrypted")
    
    with col2:
        no_backup = len(df[df['Backup Status'] == 'Disabled'])
        if no_backup > 0:
            st.warning(f"⚠️ {no_backup} database(s) without backups")
        else:
            st.success("✅ All databases have backups enabled")
    
    with col3:
        no_multi_az = len(df[df['Multi-AZ'] == 'No'])
        if no_multi_az > 0:
            st.info(f"ℹ️ {no_multi_az} database(s) without Multi-AZ")
        else:
            st.success("✅ All databases have Multi-AZ enabled")
    
    # Data table
    st.subheader("Database Details")
    
    # Add filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        type_filter = st.multiselect(
            "Filter by Type",
            options=df['Type'].unique(),
            default=df['Type'].unique()
        )
    with col2:
        engine_filter = st.multiselect(
            "Filter by Engine",
            options=sorted(df['Engine'].unique()),
            default=df['Engine'].unique()
        )
    with col3:
        status_filter = st.multiselect(
            "Filter by Status",
            options=df['Status'].unique(),
            default=df['Status'].unique()
        )
    
    # Apply filters
    filtered_df = df[
        (df['Type'].isin(type_filter)) &
        (df['Engine'].isin(engine_filter)) &
        (df['Status'].isin(status_filter))
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
        file_name=f"rds_databases_{region}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.info("No RDS databases found or unable to connect to AWS.")
    st.markdown("""
    ### Troubleshooting
    
    Make sure your AWS credentials are configured:
    - Environment variables: `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_PROFILE`
    - Or mount your `~/.aws` credentials directory
    
    Check that your IAM user/role has permissions for:
    - `rds:DescribeDBClusters`
    - `rds:DescribeDBInstances`
    """)
