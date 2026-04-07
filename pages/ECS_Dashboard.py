import streamlit as st
import pandas as pd
from datetime import datetime
import os
import sys
from pathlib import Path

# Add parent directory to path for shared_libs import
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared_libs import get_aws_profiles, get_aws_client

# Page config
st.set_page_config(
    page_title="ECS Dashboard - AWS Dashboard",
    layout="wide"
)

st.title("ECS Dashboard")

# Fetch ECS clusters
@st.cache_data(ttl=300)
def get_clusters(region='us-east-2', profile=None):
    """Fetch all ECS clusters"""
    client = get_aws_client('ecs', region, profile)
    clusters_data = []
    
    try:
        # List all clusters
        cluster_arns = client.list_clusters()['clusterArns']
        
        if not cluster_arns:
            return pd.DataFrame()
        
        # Describe clusters to get details
        clusters = client.describe_clusters(clusters=cluster_arns)['clusters']
        
        for cluster in clusters:
            clusters_data.append({
                'Cluster Name': cluster['clusterName'],
                'Status': cluster['status'],
                'Active Services': cluster['activeServicesCount'],
                'Running Tasks': cluster['runningTasksCount'],
                'Pending Tasks': cluster['pendingTasksCount']
            })
    except Exception as e:
        st.error(f"Error fetching clusters: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(clusters_data)

# Fetch ECS services for a cluster
@st.cache_data(ttl=300)
def get_services(cluster_name, region='us-east-2', profile=None):
    """Fetch all services in a cluster"""
    client = get_aws_client('ecs', region, profile)
    services_data = []
    
    try:
        # List all services in the cluster
        service_arns = client.list_services(cluster=cluster_name)['serviceArns']
        
        if not service_arns:
            return pd.DataFrame()
        
        # Describe services to get details
        services = client.describe_services(cluster=cluster_name, services=service_arns)['services']
        
        for service in services:
            # Get task definition details
            task_def = service['taskDefinition'].split('/')[-1]
            
            services_data.append({
                'Service Name': service['serviceName'],
                'Status': service['status'],
                'Desired Count': service['desiredCount'],
                'Running Count': service['runningCount'],
                'Pending Count': service['pendingCount'],
                'Task Definition': task_def,
                'Launch Type': service.get('launchType', 'N/A'),
                'Created': service['createdAt'].strftime('%Y-%m-%d %H:%M:%S UTC')
            })
    except Exception as e:
        st.error(f"Error fetching services: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(services_data)

# Fetch running tasks
@st.cache_data(ttl=300)
def get_tasks(cluster_name, region='us-east-2', profile=None):
    """Fetch all running tasks in a cluster"""
    client = get_aws_client('ecs', region, profile)
    tasks_data = []
    
    try:
        # List all tasks
        task_arns = client.list_tasks(cluster=cluster_name, desiredStatus='RUNNING')['taskArns']
        
        if not task_arns:
            return pd.DataFrame()
        
        # Describe tasks to get details
        tasks = client.describe_tasks(cluster=cluster_name, tasks=task_arns)['tasks']
        
        for task in tasks:
            # Get container info
            containers = task.get('containers', [])
            container_names = ', '.join([c['name'] for c in containers])
            
            tasks_data.append({
                'Task ID': task['taskArn'].split('/')[-1],
                'Task Definition': task['taskDefinitionArn'].split('/')[-1],
                'Status': task['lastStatus'],
                'Health': task.get('healthStatus', 'UNKNOWN'),
                'Containers': container_names,
                'Launch Type': task.get('launchType', 'N/A'),
                'Started': task.get('startedAt', 'N/A').strftime('%Y-%m-%d %H:%M:%S UTC') if task.get('startedAt') else 'N/A'
            })
    except Exception as e:
        st.error(f"Error fetching tasks: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(tasks_data)

# Fetch task definition details
@st.cache_data(ttl=300)
def get_task_definition_images(cluster_name, region='us-east-2', profile=None):
    """Fetch container images from task definitions with ECR metadata"""
    ecs_client = get_aws_client('ecs', region, profile)
    ecr_client = get_aws_client('ecr', region, profile)
    images_data = []
    
    def get_ecr_image_details(image_uri):
        """Parse ECR image URI and fetch image details"""
        try:
            # Check if this is an ECR image
            if '.dkr.ecr.' not in image_uri:
                return None
            
            # Parse: account.dkr.ecr.region.amazonaws.com/repository:tag
            parts = image_uri.split('/')
            if len(parts) < 2:
                return None
            
            repository = '/'.join(parts[1:]).split(':')[0].split('@')[0]
            
            # Get tag or digest
            if ':' in image_uri and '@' not in image_uri:
                tag = image_uri.split(':')[-1]
                image_id = {'imageTag': tag}
            elif '@' in image_uri:
                digest = image_uri.split('@')[-1]
                image_id = {'imageDigest': digest}
            else:
                image_id = {'imageTag': 'latest'}
            
            # Query ECR
            response = ecr_client.describe_images(
                repositoryName=repository,
                imageIds=[image_id]
            )
            
            if response['imageDetails']:
                return response['imageDetails'][0].get('imagePushedAt')
            
        except Exception:
            pass  # Image might be in different region/account
        
        return None
    
    try:
        # Get services
        service_arns = ecs_client.list_services(cluster=cluster_name)['serviceArns']
        
        if not service_arns:
            return pd.DataFrame()
        
        services = ecs_client.describe_services(cluster=cluster_name, services=service_arns)['services']
        
        # Get unique task definitions
        task_defs = set([service['taskDefinition'] for service in services])
        
        for task_def_arn in task_defs:
            task_def = ecs_client.describe_task_definition(taskDefinition=task_def_arn)['taskDefinition']
            
            for container in task_def['containerDefinitions']:
                image = container['image']
                pushed_at = get_ecr_image_details(image)
                
                images_data.append({
                    'Task Definition': task_def_arn.split('/')[-1],
                    'Container': container['name'],
                    'ECR Image': image,
                    'ECR Image Created At': pushed_at.strftime('%Y-%m-%d %H:%M:%S UTC') if pushed_at else 'N/A',
                    'CPU': container.get('cpu', 'N/A'),
                    'Memory': container.get('memory', 'N/A')
                })
    except Exception as e:
        st.error(f"Error fetching task definitions: {str(e)}")
        return pd.DataFrame()
    
    return pd.DataFrame(images_data)

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
st.header(f"ECS Resources in {region} ({profile})")

# Fetch clusters
clusters_df = get_clusters(region, profile)

if not clusters_df.empty:
    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Clusters", len(clusters_df))
    with col2:
        st.metric("Total Running Tasks", clusters_df['Running Tasks'].sum())
    with col3:
        st.metric("Total Active Services", clusters_df['Active Services'].sum())
    with col4:
        st.metric("Total Pending Tasks", clusters_df['Pending Tasks'].sum())
    
    # Clusters table
    st.subheader("Clusters Overview")
    st.dataframe(clusters_df, width='stretch', height=200)
    
    # Cluster selector for detailed view
    st.markdown("---")
    selected_cluster = st.selectbox(
        "Select a cluster for detailed view:",
        clusters_df['Cluster Name'].tolist()
    )
    
    if selected_cluster:
        st.subheader(f"Cluster: {selected_cluster}")
        
        # Services
        # col1, col2 = st.columns(2)
        
        # with col1:
        st.markdown("### Services")
        services_df = get_services(selected_cluster, region, profile)
        if not services_df.empty:
            st.dataframe(services_df, width='stretch', height=200)
            
            # Download services data
            csv = services_df.to_csv(index=False)
            st.download_button(
                label="Download Services CSV",
                data=csv,
                file_name=f"ecs_services_{selected_cluster}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No services found in this cluster.")
        
        # with col2:
        st.markdown("### Running Tasks")
        tasks_df = get_tasks(selected_cluster, region, profile)
        if not tasks_df.empty:
            st.dataframe(tasks_df, width='stretch', height=300)
            
            # Download tasks data
            csv = tasks_df.to_csv(index=False)
            st.download_button(
                label="Download Tasks CSV",
                data=csv,
                file_name=f"ecs_tasks_{selected_cluster}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No running tasks found in this cluster.")
        
        # Container Images
        st.markdown("### Container Images")
        images_df = get_task_definition_images(selected_cluster, region, profile)
        if not images_df.empty:
            st.dataframe(images_df, width='stretch', height=250)
            
            # Download images data
            csv = images_df.to_csv(index=False)
            st.download_button(
                label="Download Images CSV",
                data=csv,
                file_name=f"ecs_images_{selected_cluster}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No container images found.")

else:
    st.info("No ECS clusters found in this region.")
    st.markdown("""
    ### Troubleshooting
    
    Make sure your AWS credentials are configured and you have ECS clusters in the selected region.
    
    Required IAM permissions:
    - `ecs:ListClusters`
    - `ecs:DescribeClusters`
    - `ecs:ListServices`
    - `ecs:DescribeServices`
    - `ecs:ListTasks`
    - `ecs:DescribeTasks`
    - `ecs:DescribeTaskDefinition`
    - `ecr:DescribeImages`
    """)
