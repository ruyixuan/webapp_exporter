import json
import time
import requests
import re
from prometheus_client import start_http_server, Gauge


# 获得Plan的监控指标，非静态配置


CONFIG_FILE = "webapp_my_config.json"
METRICS = {}

# Azure API versions
API_VERSION_serverfarms = "2024-04-01"
API_VERSION_insights = "2023-10-01"

# List of metrics to monitor
METRIC_NAMES = [
    "CpuPercentage", "MemoryPercentage", "DiskQueueLength", "HttpQueueLength",
    "BytesReceived", "BytesSent", "TcpSynSent", "TcpSynReceived",
    "TcpEstablished", "TcpFinWait1", "TcpFinWait2", "TcpClosing",
    "TcpCloseWait", "TcpLastAck", "TcpTimeWait", "SocketInboundAll",
    "SocketOutboundAll", "SocketOutboundEstablished", "SocketOutboundTimeWait", "SocketLoopback"
]

def load_config():
    """Load JSON configuration file"""
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def get_access_token(tenant_id, client_id, client_secret):
    """Retrieve Azure AD access token"""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "resource": "https://management.azure.com"
    }

    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()["access_token"]
    except requests.exceptions.RequestException as e:
        print(f"Failed to get access token: {e}")
        return None

def get_app_service_plans(access_token, subscription_id, resource_group_name):
    """Retrieve all App Service Plans under a given resource group"""
    url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Web/serverfarms?api-version={API_VERSION_serverfarms}"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        plans = response.json().get("value", [])
        return [plan["name"] for plan in plans]
    except requests.exceptions.RequestException as e:
        print(f"Failed to get App Service Plans: {e}")
        return []

def get_plan_metrics(access_token, subscription_id, resource_group_name, plan_name):
    """Retrieve metrics for a given App Service Plan"""
    metric_names = ",".join(METRIC_NAMES)
    url = (
        f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/"
        f"providers/Microsoft.Web/serverfarms/{plan_name}/providers/Microsoft.Insights/metrics?"
        f"api-version={API_VERSION_insights}&metricnames={metric_names}"
    )
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to get metrics for {plan_name}: {e}")
        return None

def sanitize_metric_name(name):
    """Replace invalid characters (- . / etc.) with _ to ensure Prometheus compatibility"""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)

def initialize_metrics(config):
    """Initialize Prometheus metrics"""
    for entry in config:
        resource_group_name = sanitize_metric_name(entry["resource_group_name"])
        tenant_id, client_id, client_secret, subscription_id = (
            entry["tenant_id"], entry["client_id"], entry["client_secret"], entry["subscription_id"]
        )

        # Retrieve access token
        access_token = get_access_token(tenant_id, client_id, client_secret)
        if not access_token:
            print(f"Unable to retrieve access token, skipping {resource_group_name}")
            continue

        # Retrieve App Service Plans
        plan_names = get_app_service_plans(access_token, subscription_id, entry["resource_group_name"])
        if not plan_names:
            print(f"No App Service Plans found, skipping {resource_group_name}")
            continue

        for plan_name in plan_names:
            sanitized_plan_name = sanitize_metric_name(plan_name)
            key = f"{resource_group_name}_{sanitized_plan_name}"

            for metric in METRIC_NAMES:
                metric_key = f"{key}_{metric.lower()}"
                METRICS[metric_key] = Gauge(
                    f"azure_plan_{metric_key}",
                    f"{metric} of {plan_name} in {entry['resource_group_name']}"
                )

def update_metrics(config):
    """Update Prometheus metrics"""
    for entry in config:
        tenant_id = entry["tenant_id"]
        client_id = entry["client_id"]
        client_secret = entry["client_secret"]
        subscription_id = entry["subscription_id"]
        resource_group_name = sanitize_metric_name(entry["resource_group_name"])

        access_token = get_access_token(tenant_id, client_id, client_secret)
        if not access_token:
            print(f"Unable to retrieve access token, skipping {resource_group_name}")
            continue

        plan_names = get_app_service_plans(access_token, subscription_id, entry["resource_group_name"])
        if not plan_names:
            print(f"No App Service Plans found, skipping {resource_group_name}")
            continue

        for plan_name in plan_names:
            sanitized_plan_name = sanitize_metric_name(plan_name)
            key = f"{resource_group_name}_{sanitized_plan_name}"
            metrics_data = get_plan_metrics(access_token, subscription_id, entry["resource_group_name"], plan_name)

            if not metrics_data:
                print(f"Unable to retrieve metrics for {plan_name}, skipping")
                continue  

            for metric in metrics_data["value"]:
                metric_name = metric["name"]["value"]
                metric_key = f"{key}_{metric_name.lower()}"

                for timeseries in metric["timeseries"]:
                    for data in timeseries["data"]:
                        if "average" in data and metric_key in METRICS:
                            METRICS[metric_key].set(data["average"])

if __name__ == "__main__":
    config = load_config()
    initialize_metrics(config)
    start_http_server(9202)
    print("Exporter started on port 9202")

    while True:
        update_metrics(config)
        time.sleep(60)
