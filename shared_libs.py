"""Shared library functions for AWS Dashboard"""

import os
from pathlib import Path
import configparser
import streamlit as st
import boto3


@st.cache_resource
def get_aws_client(service_name, region='us-east-2', profile=None):
    """
    Initialize AWS client for any service
    
    Args:
        service_name: AWS service name (e.g., 'ec2', 'lambda', 'ecs', 'cloudwatch', 'logs', 'ecr')
        region: AWS region (default: 'us-east-2')
        profile: AWS profile name (optional)
    
    Returns:
        boto3 client for the specified service
    """
    if profile:
        session = boto3.Session(profile_name=profile)
        return session.client(service_name, region_name=region)
    return boto3.client(service_name, region_name=region)


@st.cache_data
def get_aws_profiles():
    """Get list of AWS profiles from credentials and config files"""
    profiles = set(['default'])
    
    # Check credentials file
    credentials_path = os.environ.get('AWS_SHARED_CREDENTIALS_FILE', str(Path.home() / '.aws' / 'credentials'))
    if Path(credentials_path).exists():
        try:
            config = configparser.ConfigParser()
            config.read(credentials_path)
            profiles.update(config.sections())
        except Exception:
            pass
    
    # Check config file for SSO profiles
    config_path = os.environ.get('AWS_CONFIG_FILE', str(Path.home() / '.aws' / 'config'))
    if Path(config_path).exists():
        try:
            config = configparser.ConfigParser()
            config.read(config_path)
            for section in config.sections():
                # Config file has sections like [profile name] or [default]
                if section.startswith('profile '):
                    profiles.add(section.replace('profile ', ''))
                elif section == 'default':
                    profiles.add('default')
        except Exception:
            pass
    
    return sorted(list(profiles))
