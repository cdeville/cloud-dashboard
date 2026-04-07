import os
import sys
from datetime import datetime
from pathlib import Path

from botocore.exceptions import ClientError
import pandas as pd
import plotly.express as px
import streamlit as st

# Add parent directory to path for shared_libs import
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared_libs import get_aws_profiles, get_aws_client

# Page config
st.set_page_config(
    page_title="S3 Dashboard - AWS Dashboard",
    layout="wide"
)

st.title("S3 Dashboard")


# Fetch S3 bucket details
@st.cache_data(ttl=300)
def get_s3_buckets(profile=None):
    """Fetch all S3 buckets with details"""
    # S3 is global, but we need a region for the client
    s3_client = get_aws_client('s3', region='us-east-1', profile=profile)
    buckets_data = []
    
    try:
        # List all buckets
        response = s3_client.list_buckets()
        
        for bucket in response['Buckets']:
            bucket_name = bucket['Name']
            creation_date = bucket['CreationDate']
            
            # Get bucket location
            try:
                location_response = s3_client.get_bucket_location(Bucket=bucket_name)
                region = location_response['LocationConstraint']
                # None means us-east-1
                if region is None:
                    region = 'us-east-1'
            except Exception:
                region = 'Unknown'
            
            # Get encryption status
            encryption_status = 'Not Encrypted'
            encryption_type = 'None'
            try:
                encryption = s3_client.get_bucket_encryption(Bucket=bucket_name)
                if 'ServerSideEncryptionConfiguration' in encryption:
                    rules = encryption['ServerSideEncryptionConfiguration'].get('Rules', [])
                    if rules:
                        rule = rules[0]
                        encryption_status = 'Encrypted'
                        if 'ApplyServerSideEncryptionByDefault' in rule:
                            sse_algo = rule['ApplyServerSideEncryptionByDefault'].get('SSEAlgorithm', 'Unknown')
                            encryption_type = sse_algo
            except ClientError as e:
                if e.response['Error']['Code'] == 'ServerSideEncryptionConfigurationNotFoundError':
                    encryption_status = 'Not Encrypted'
                else:
                    encryption_status = 'Unknown'
            except Exception:
                encryption_status = 'Unknown'
            
            # Get versioning status
            versioning_status = 'Disabled'
            try:
                versioning = s3_client.get_bucket_versioning(Bucket=bucket_name)
                versioning_status = versioning.get('Status', 'Disabled')
                if versioning_status == 'Enabled':
                    versioning_status = 'Enabled'
                else:
                    versioning_status = 'Disabled'
            except Exception:
                versioning_status = 'Unknown'
            
            # Get logging status
            logging_status = 'Disabled'
            logging_target = 'N/A'
            try:
                logging = s3_client.get_bucket_logging(Bucket=bucket_name)
                if 'LoggingEnabled' in logging:
                    logging_status = 'Enabled'
                    logging_target = logging['LoggingEnabled'].get('TargetBucket', 'N/A')
                else:
                    logging_status = 'Disabled'
            except Exception:
                logging_status = 'Unknown'
            
            # Get public access block settings
            public_access = 'Unknown'
            try:
                pub_access = s3_client.get_public_access_block(Bucket=bucket_name)
                config = pub_access['PublicAccessBlockConfiguration']
                if all([
                    config.get('BlockPublicAcls', False),
                    config.get('IgnorePublicAcls', False),
                    config.get('BlockPublicPolicy', False),
                    config.get('RestrictPublicBuckets', False)
                ]):
                    public_access = 'All Blocked'
                elif any([
                    config.get('BlockPublicAcls', False),
                    config.get('IgnorePublicAcls', False),
                    config.get('BlockPublicPolicy', False),
                    config.get('RestrictPublicBuckets', False)
                ]):
                    public_access = 'Partially Blocked'
                else:
                    public_access = 'Not Blocked'
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchPublicAccessBlockConfiguration':
                    public_access = 'Not Configured'
                else:
                    public_access = 'Unknown'
            except Exception:
                public_access = 'Unknown'
            
            buckets_data.append({
                'Bucket Name': bucket_name,
                'Region': region,
                'Encryption': encryption_status,
                'Encryption Type': encryption_type,
                'Versioning': versioning_status,
                'Logging': logging_status,
                'Logging Target': logging_target,
                'Public Access': public_access,
                'Created': creation_date.strftime('%Y-%m-%d %H:%M:%S UTC')
            })
        
    except Exception as e:
        st.error(f"Error fetching S3 buckets: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(buckets_data)


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

st.sidebar.info("ℹ️ S3 is a global service. All buckets across all regions will be displayed.")

if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

# Main content
st.header(f"S3 Buckets ({profile})")

# Fetch data
df = get_s3_buckets(profile)

if not df.empty:
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Buckets", len(df))
    with col2:
        encrypted_count = len(df[df['Encryption'] == 'Encrypted'])
        encryption_pct = (encrypted_count / len(df) * 100) if len(df) > 0 else 0
        st.metric("Encrypted", f"{encrypted_count} ({encryption_pct:.0f}%)")
    with col3:
        versioned_count = len(df[df['Versioning'] == 'Enabled'])
        st.metric("Versioning Enabled", versioned_count)
    with col4:
        blocked_count = len(df[df['Public Access'] == 'All Blocked'])
        st.metric("Public Access Blocked", blocked_count)
    
    # Charts
    st.subheader("Visualizations")
    
    # Row 1 - Encryption and Versioning
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Encryption Status")
        encryption_counts = df['Encryption'].value_counts()
        color_map = {
            'Encrypted': '#2ecc71',
            'Not Encrypted': '#e74c3c',
            'Unknown': '#95a5a6'
        }
        colors = [color_map.get(status, '#3498db') for status in encryption_counts.index]
        fig = px.pie(
            values=encryption_counts.values,
            names=encryption_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    with col2:
        st.markdown("#### Versioning Status")
        versioning_counts = df['Versioning'].value_counts()
        color_map_versioning = {
            'Enabled': '#2ecc71',
            'Disabled': '#e74c3c',
            'Unknown': '#95a5a6'
        }
        colors = [color_map_versioning.get(status, '#3498db') for status in versioning_counts.index]
        fig = px.pie(
            values=versioning_counts.values,
            names=versioning_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    # Row 2 - Public Access and Logging
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Public Access Block Status")
        public_counts = df['Public Access'].value_counts()
        color_map_public = {
            'All Blocked': '#2ecc71',
            'Partially Blocked': '#f39c12',
            'Not Blocked': '#e74c3c',
            'Not Configured': '#e67e22',
            'Unknown': '#95a5a6'
        }
        colors = [color_map_public.get(status, '#3498db') for status in public_counts.index]
        fig = px.pie(
            values=public_counts.values,
            names=public_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    with col2:
        st.markdown("#### Logging Status")
        logging_counts = df['Logging'].value_counts()
        color_map_logging = {
            'Enabled': '#2ecc71',
            'Disabled': '#e74c3c',
            'Unknown': '#95a5a6'
        }
        colors = [color_map_logging.get(status, '#3498db') for status in logging_counts.index]
        fig = px.pie(
            values=logging_counts.values,
            names=logging_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    # Row 3 - Region distribution and Encryption Type
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Buckets by Region")
        region_counts = df['Region'].value_counts()
        fig = px.bar(
            x=region_counts.index,
            y=region_counts.values,
            labels={'x': 'Region', 'y': 'Count'},
            color=region_counts.values,
            color_continuous_scale='viridis'
        )
        fig.update_layout(showlegend=False, xaxis_tickangle=-45)
        st.plotly_chart(fig, width='stretch')
    
    with col2:
        st.markdown("#### Encryption Type Distribution")
        # Filter only encrypted buckets
        encrypted_df = df[df['Encryption'] == 'Encrypted']
        if not encrypted_df.empty:
            enc_type_counts = encrypted_df['Encryption Type'].value_counts()
            fig = px.bar(
                x=enc_type_counts.index,
                y=enc_type_counts.values,
                labels={'x': 'Encryption Type', 'y': 'Count'}
            )
            fig.update_layout(showlegend=False, xaxis_tickangle=-45)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No encrypted buckets to display")
    
    # Security Summary
    st.subheader("Security Summary")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        unencrypted = len(df[df['Encryption'] == 'Not Encrypted'])
        if unencrypted > 0:
            st.warning(f"⚠️ {unencrypted} bucket(s) without encryption")
        else:
            st.success("✅ All buckets are encrypted")
    
    with col2:
        no_versioning = len(df[df['Versioning'] == 'Disabled'])
        if no_versioning > 0:
            st.info(f"ℹ️ {no_versioning} bucket(s) without versioning")
        else:
            st.success("✅ All buckets have versioning enabled")
    
    with col3:
        not_blocked = len(df[df['Public Access'].isin(['Not Blocked', 'Not Configured', 'Partially Blocked'])])
        if not_blocked > 0:
            st.warning(f"⚠️ {not_blocked} bucket(s) with public access not fully blocked")
        else:
            st.success("✅ All buckets have public access fully blocked")
    
    # Data table
    st.subheader("Bucket Details")
    
    # Add filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        encryption_filter = st.multiselect(
            "Filter by Encryption",
            options=df['Encryption'].unique(),
            default=df['Encryption'].unique()
        )
    with col2:
        versioning_filter = st.multiselect(
            "Filter by Versioning",
            options=df['Versioning'].unique(),
            default=df['Versioning'].unique()
        )
    with col3:
        region_filter = st.multiselect(
            "Filter by Region",
            options=sorted(df['Region'].unique()),
            default=df['Region'].unique()
        )
    
    # Apply filters
    filtered_df = df[
        (df['Encryption'].isin(encryption_filter)) &
        (df['Versioning'].isin(versioning_filter)) &
        (df['Region'].isin(region_filter))
    ]
    
    # Sort by Bucket Name
    filtered_df = filtered_df.sort_values('Bucket Name')
    
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
        file_name=f"s3_buckets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.info("No S3 buckets found or unable to connect to AWS.")
    st.markdown("""
    ### Troubleshooting
    
    Make sure your AWS credentials are configured:
    - Environment variables: `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_PROFILE`
    - Or mount your `~/.aws` credentials directory
    
    Check that your IAM user/role has permissions for:
    - `s3:ListAllMyBuckets`
    - `s3:GetBucketLocation`
    - `s3:GetEncryptionConfiguration`
    - `s3:GetBucketVersioning`
    - `s3:GetBucketLogging`
    - `s3:GetBucketPublicAccessBlock`
    """)
