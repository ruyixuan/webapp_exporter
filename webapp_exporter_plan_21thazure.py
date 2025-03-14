import json
import requests
import os
from flask import Flask, Response
from prometheus_client import CollectorRegistry, Gauge, generate_latest

# 读取配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "webapp_config.json")

# Prometheus 指标
registry = CollectorRegistry()
web_app_sku_metric = Gauge(
    "azure_webapp_plan_sku",
    "Web App SKU (定价层)",
    ["web_app_name", "resource_group_name", "subscription_id", "sku", "plan_name"],
    registry=registry
)
web_app_instance_count_metric = Gauge(
    "azure_webapp_plan_instance_count",
    "Web App 计算实例个数",
    ["web_app_name", "resource_group_name", "subscription_id", "plan_name"],
    registry=registry
)
web_app_cpu_metric = Gauge(
    "azure_webapp_plan_cpu_cores",
    "Web App 计算的 CPU 核心数",
    ["web_app_name", "resource_group_name", "subscription_id", "plan_name"],
    registry=registry
)
web_app_memory_metric = Gauge(
    "azure_webapp_plan_memory_gb",
    "Web App 计算的内存（GB）",
    ["web_app_name", "resource_group_name", "subscription_id", "plan_name"],
    registry=registry
)
web_app_storage_metric = Gauge(
    "azure_webapp_plan_storage_gb",
    "Web App 存储空间（GB）",
    ["web_app_name", "resource_group_name", "subscription_id", "plan_name"],
    registry=registry
)

# 预定义 Azure SKU 规格
SKU_CONFIG = {
    "F1": {"cpu": 1, "memory": 1, "storage": 1},
    "D1": {"cpu": 1, "memory": 1.75, "storage": 10},
    "B1": {"cpu": 1, "memory": 1.75, "storage": 10},
    "B2": {"cpu": 2, "memory": 3.5, "storage": 10},
    "B3": {"cpu": 4, "memory": 7, "storage": 10},
    "S1": {"cpu": 1, "memory": 1.75, "storage": 50},
    "S2": {"cpu": 2, "memory": 3.5, "storage": 50},
    "S3": {"cpu": 4, "memory": 7, "storage": 50},
    "P1V2": {"cpu": 1, "memory": 3.5, "storage": 250},
    "P2V2": {"cpu": 2, "memory": 7, "storage": 250},
    "P3V2": {"cpu": 4, "memory": 14, "storage": 250}
}

# 获取 Azure 访问令牌
def get_access_token(tenant_id, client_id, client_secret):
    url = f"https://login.partner.microsoftonline.cn/{tenant_id}/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "resource": "https://management.chinacloudapi.cn/"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(url, data=payload, headers=headers)
    response.raise_for_status()
    return response.json().get("access_token")

# 获取 Web App 绑定的 Plan ID
def get_web_app_info(subscription_id, resource_group_name, web_app, token):
    url = f"https://management.chinacloudapi.cn/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Web/sites/{web_app}?api-version=2024-04-01"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        properties = data.get("properties", {})

        # 获取 Server Farm ID
        plan_id = properties.get("serverFarmId", "Unknown")

        # 获取 计算实例个数
        instance_count = properties.get("siteConfig", {}).get("numberOfWorkers", 1)

        return plan_id, instance_count
    else:
        print(f"Error fetching Web App {web_app}: {response.status_code}, {response.text}")
        return "Unknown", 1

# 通过 Plan ID 获取 SKU（CPU、内存、存储）
def get_plan_metrics(subscription_id, plan_id, token):
    if plan_id == "Unknown":
        return "Unknown", "Unknown", 0, 0, 0

    plan_name = plan_id.split("/")[-1]  # 解析 Plan 名称
    resource_group_name = plan_id.split("/")[4]  # 解析 Resource Group Name

    url = f"https://management.chinacloudapi.cn/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Web/serverfarms/{plan_name}?api-version=2024-04-01"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        sku_name = data.get("sku", {}).get("name", "Unknown").upper()

        # 获取 CPU、内存、存储空间
        config = SKU_CONFIG.get(sku_name, {"cpu": 0, "memory": 0, "storage": 0})

        return plan_name, sku_name, config["cpu"], config["memory"], config["storage"]
    else:
        print(f"Error fetching Plan {plan_name}: {response.status_code}, {response.text}")
        return "Unknown", "Unknown", 0, 0, 0

# Flask 应用
app = Flask(__name__)

@app.route("/metrics")
def metrics():
    config = json.load(open(CONFIG_FILE, "r", encoding="utf-8"))

    for entry in config:
        tenant_id = entry["tenant_id"]
        client_id = entry["client_id"]
        client_secret = entry["client_secret"]
        subscription_id = entry["subscription_id"]
        resource_group_name = entry["resource_group_name"]  # 统一使用 resource_group_name
        web_apps = entry["web_app_names"]

        try:
            token = get_access_token(tenant_id, client_id, client_secret)

            for web_app in web_apps:
                plan_id, instance_count = get_web_app_info(subscription_id, resource_group_name, web_app, token)
                plan_name, sku, cpu, memory_gb, storage_gb = get_plan_metrics(subscription_id, plan_id, token)

                web_app_sku_metric.labels(web_app, resource_group_name, subscription_id, sku, plan_name).set(1)
                web_app_instance_count_metric.labels(web_app, resource_group_name, subscription_id, plan_name).set(instance_count)
                web_app_cpu_metric.labels(web_app, resource_group_name, subscription_id, plan_name).set(cpu)
                web_app_memory_metric.labels(web_app, resource_group_name, subscription_id, plan_name).set(memory_gb)
                web_app_storage_metric.labels(web_app, resource_group_name, subscription_id, plan_name).set(storage_gb)

        except Exception as e:
            print(f"Error processing subscription {subscription_id}: {str(e)}")

    return Response(generate_latest(registry), mimetype="text/plain")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9201)
