import streamlit as st

# Page config
st.set_page_config(
    page_title="AWS Cloud Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("AWS Cloud Health Dashboard")

st.markdown("""
Welcome to the AWS Cloud Health Dashboard - a comprehensive monitoring tool for your AWS resources.

## Available Dashboards

Use the navigation on the left to access different dashboards:

### ECS Dashboard
Monitor your Amazon ECS clusters, services, and tasks:
- Cluster overview with status and capacity metrics
- Service health and deployment status
- Task monitoring and health status
- Container image tracking from task definitions
- Export data for offline analysis

### EC2 Dashboard
Monitor and analyze your Amazon EC2 instances:
- View all instances with key information (Name, ID, State, Type, IPs)
- Track IAM roles and security configurations
- Visualize distribution by state, type, and availability zone
- Filter and export instance data for analysis
- Monitor resource allocation across your infrastructure

### Lambda Failures
Track and troubleshoot Lambda function failures:
- Identify functions with errors over customizable time periods
- View error rates, throttles, and failure patterns
- Analyze error timelines with hourly granularity
- Search CloudWatch Logs for ERROR messages
- Export failure data and error logs for analysis

### Lambda Functions
Monitor and analyze your AWS Lambda functions across regions:
- View all Lambda functions with key metrics
- Track invocation history and status
- Analyze runtime distribution and memory usage
- Export data for further analysis

## Quick Start

1. Select a dashboard from the sidebar
2. **Choose your AWS profile** from the dropdown (auto-detected from `~/.aws/` files)
3. Choose your AWS region
4. View real-time data from your AWS account

## Configuration

This dashboard uses your AWS credentials configured via:
- AWS CLI profile (set via `AWS_PROFILE` environment variable)
- Mounted `~/.aws` directory for SSO authentication

## Features

- **Real-time monitoring** - Live data from AWS APIs
- **Multi-region support** - Switch between regions easily
- **Multi-profile support** - Switch between AWS accounts/profiles on the fly
- **Data export** - Download data as CSV for offline analysis
- **CloudWatch integration** - Invocation metrics and performance data
""")

st.markdown("---")

st.info("Select a dashboard from the sidebar to get started!")


