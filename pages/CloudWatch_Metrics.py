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
    page_title="CloudWatch Metrics - AWS Dashboard",
    layout="wide"
)

st.title("CloudWatch Metrics Dashboard")


# Fetch CloudWatch Alarms
@st.cache_data(ttl=300)
def get_cloudwatch_alarms(region='us-east-2', profile=None):
    """Fetch all CloudWatch alarms with details"""
    cw_client = get_aws_client('cloudwatch', region, profile)
    alarms_data = []
    
    try:
        # Describe all metric alarms
        paginator = cw_client.get_paginator('describe_alarms')
        
        for page in paginator.paginate():
            for alarm in page.get('MetricAlarms', []):
                alarm_name = alarm['AlarmName']
                
                # Get state and reason
                state_value = alarm.get('StateValue', 'UNKNOWN')
                state_reason = alarm.get('StateReason', 'N/A')
                state_updated_timestamp = alarm.get('StateUpdatedTimestamp')
                
                # Convert to local time
                if state_updated_timestamp:
                    local_time = state_updated_timestamp.astimezone()
                    state_updated = local_time.strftime('%Y-%m-%d %H:%M:%S %Z')
                else:
                    state_updated = 'N/A'
                
                # Get metric information
                metric_name = alarm.get('MetricName', 'N/A')
                namespace = alarm.get('Namespace', 'N/A')
                
                # Get dimensions
                dimensions = alarm.get('Dimensions', [])
                dim_str = ', '.join([f"{d['Name']}={d['Value']}" for d in dimensions])
                if not dim_str:
                    dim_str = 'N/A'
                
                # Get condition/threshold
                comparison_operator = alarm.get('ComparisonOperator', 'N/A')
                threshold = alarm.get('Threshold', 'N/A')
                statistic = alarm.get('Statistic', alarm.get('ExtendedStatistic', 'N/A'))
                period = alarm.get('Period', 0)
                evaluation_periods = alarm.get('EvaluationPeriods', 0)
                
                # Format condition
                condition = f"{statistic} {comparison_operator} {threshold} for {evaluation_periods} period(s) of {period}s"
                
                # Get actions
                alarm_actions = alarm.get('AlarmActions', [])
                ok_actions = alarm.get('OKActions', [])
                insufficient_data_actions = alarm.get('InsufficientDataActions', [])
                
                # Format actions
                all_actions = []
                if alarm_actions:
                    all_actions.append(f"ALARM: {', '.join([a.split(':')[-1] for a in alarm_actions])}")
                if ok_actions:
                    all_actions.append(f"OK: {', '.join([a.split(':')[-1] for a in ok_actions])}")
                if insufficient_data_actions:
                    all_actions.append(f"INSUFFICIENT_DATA: {', '.join([a.split(':')[-1] for a in insufficient_data_actions])}")
                
                actions_str = ' | '.join(all_actions) if all_actions else 'No Actions'
                
                # Get actions enabled status
                actions_enabled = 'Yes' if alarm.get('ActionsEnabled', False) else 'No'
                
                # Get datapoints to alarm
                datapoints_to_alarm = alarm.get('DatapointsToAlarm', evaluation_periods)
                
                # Get treat missing data
                treat_missing = alarm.get('TreatMissingData', 'notBreaching')
                
                alarms_data.append({
                    'Alarm Name': alarm_name,
                    'State': state_value,
                    'State Reason': state_reason,
                    'Last State Update': state_updated,
                    'Metric': metric_name,
                    'Namespace': namespace,
                    'Dimensions': dim_str,
                    'Condition': condition,
                    'Threshold': str(threshold),
                    'Actions': actions_str,
                    'Actions Enabled': actions_enabled,
                    'Datapoints to Alarm': f"{datapoints_to_alarm}/{evaluation_periods}",
                    'Treat Missing Data': treat_missing,
                    'Period (seconds)': str(period)
                })
        
        # Also get composite alarms
        for page in paginator.paginate(AlarmTypes=['CompositeAlarm']):
            for alarm in page.get('CompositeAlarms', []):
                alarm_name = alarm['AlarmName']
                
                # Get state
                state_value = alarm.get('StateValue', 'UNKNOWN')
                state_reason = alarm.get('StateReason', 'N/A')
                state_updated_timestamp = alarm.get('StateUpdatedTimestamp')
                
                # Convert to local time
                if state_updated_timestamp:
                    local_time = state_updated_timestamp.astimezone()
                    state_updated = local_time.strftime('%Y-%m-%d %H:%M:%S %Z')
                else:
                    state_updated = 'N/A'
                
                # Get alarm rule
                alarm_rule = alarm.get('AlarmRule', 'N/A')
                
                # Get actions
                alarm_actions = alarm.get('AlarmActions', [])
                ok_actions = alarm.get('OKActions', [])
                insufficient_data_actions = alarm.get('InsufficientDataActions', [])
                
                # Format actions
                all_actions = []
                if alarm_actions:
                    all_actions.append(f"ALARM: {', '.join([a.split(':')[-1] for a in alarm_actions])}")
                if ok_actions:
                    all_actions.append(f"OK: {', '.join([a.split(':')[-1] for a in ok_actions])}")
                if insufficient_data_actions:
                    all_actions.append(f"INSUFFICIENT_DATA: {', '.join([a.split(':')[-1] for a in insufficient_data_actions])}")
                
                actions_str = ' | '.join(all_actions) if all_actions else 'No Actions'
                
                # Get actions enabled status
                actions_enabled = 'Yes' if alarm.get('ActionsEnabled', False) else 'No'
                
                alarms_data.append({
                    'Alarm Name': alarm_name,
                    'State': state_value,
                    'State Reason': state_reason,
                    'Last State Update': state_updated,
                    'Metric': 'Composite',
                    'Namespace': 'Composite',
                    'Dimensions': 'N/A',
                    'Condition': alarm_rule,
                    'Threshold': 'N/A',
                    'Actions': actions_str,
                    'Actions Enabled': actions_enabled,
                    'Datapoints to Alarm': 'N/A',
                    'Treat Missing Data': 'N/A',
                    'Period (seconds)': 'N/A'
                })
        
    except Exception as e:
        st.error(f"Error fetching CloudWatch alarms: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(alarms_data)


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
st.header(f"CloudWatch Alarms in {region} ({profile})")

# Fetch data
df = get_cloudwatch_alarms(region, profile)

if not df.empty:
    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Alarms", len(df))
    with col2:
        alarm_count = len(df[df['State'] == 'ALARM'])
        st.metric("In ALARM", alarm_count)
    with col3:
        ok_count = len(df[df['State'] == 'OK'])
        st.metric("OK", ok_count)
    with col4:
        insufficient_count = len(df[df['State'] == 'INSUFFICIENT_DATA'])
        st.metric("Insufficient Data", insufficient_count)
    
    # Charts
    st.subheader("Visualizations")
    
    # Row 1 - State, Namespace, and Actions Status
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("#### Alarm State Distribution")
        state_counts = df['State'].value_counts()
        color_map = {
            'OK': '#2ecc71',
            'ALARM': '#e74c3c',
            'INSUFFICIENT_DATA': '#f39c12',
            'UNKNOWN': '#95a5a6'
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
        st.markdown("#### Top 10 Namespaces")
        namespace_counts = df['Namespace'].value_counts().head(10)
        fig = px.bar(
            x=namespace_counts.index,
            y=namespace_counts.values,
            labels={'x': 'Namespace', 'y': 'Count'},
            color=namespace_counts.values,
            color_continuous_scale='viridis'
        )
        fig.update_layout(showlegend=False, xaxis_tickangle=-45)
        st.plotly_chart(fig, width='stretch')
    
    with col3:
        st.markdown("#### Actions Enabled Status")
        actions_counts = df['Actions Enabled'].value_counts()
        color_map_actions = {
            'Yes': '#2ecc71',
            'No': '#e74c3c'
        }
        colors = [color_map_actions.get(status, '#3498db') for status in actions_counts.index]
        fig = px.pie(
            values=actions_counts.values,
            names=actions_counts.index,
            color_discrete_sequence=colors
        )
        fig.update_layout(showlegend=True)
        st.plotly_chart(fig, width='stretch')
    
    # Alert Summary
    st.subheader("Alert Summary")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        alarm_state = len(df[df['State'] == 'ALARM'])
        if alarm_state > 0:
            st.error(f"🚨 {alarm_state} alarm(s) in ALARM state")
        else:
            st.success("✅ No alarms in ALARM state")
    
    with col2:
        insufficient = len(df[df['State'] == 'INSUFFICIENT_DATA'])
        if insufficient > 0:
            st.warning(f"⚠️ {insufficient} alarm(s) with insufficient data")
        else:
            st.success("✅ No alarms with insufficient data")
    
    with col3:
        no_actions = len(df[df['Actions Enabled'] == 'No'])
        if no_actions > 0:
            st.warning(f"⚠️ {no_actions} alarm(s) with actions disabled")
        else:
            st.success("✅ All alarms have actions enabled")
    
    # Data table
    st.subheader("Alarm Details")
    
    # Add filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        state_filter = st.multiselect(
            "Filter by State",
            options=df['State'].unique(),
            default=df['State'].unique()
        )
    with col2:
        namespace_filter = st.multiselect(
            "Filter by Namespace",
            options=sorted(df['Namespace'].unique()),
            default=df['Namespace'].unique()
        )
    with col3:
        actions_filter = st.multiselect(
            "Filter by Actions Enabled",
            options=df['Actions Enabled'].unique(),
            default=df['Actions Enabled'].unique()
        )
    
    # Apply filters
    filtered_df = df[
        (df['State'].isin(state_filter)) &
        (df['Namespace'].isin(namespace_filter)) &
        (df['Actions Enabled'].isin(actions_filter))
    ]
    
    # Sort by State (ALARM first) then by Alarm Name
    state_order = ['ALARM', 'INSUFFICIENT_DATA', 'OK', 'UNKNOWN']
    filtered_df['State_Order'] = filtered_df['State'].apply(
        lambda x: state_order.index(x) if x in state_order else 999
    )
    filtered_df = filtered_df.sort_values(['State_Order', 'Alarm Name']).drop('State_Order', axis=1)
    
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
        file_name=f"cloudwatch_alarms_{region}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.info("No CloudWatch alarms found or unable to connect to AWS.")
    st.markdown("""
    ### Troubleshooting
    
    Make sure your AWS credentials are configured:
    - Environment variables: `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE`, `AWS_PROFILE`
    - Or mount your `~/.aws` credentials directory
    
    Check that your IAM user/role has permissions for:
    - `cloudwatch:DescribeAlarms`
    """)
