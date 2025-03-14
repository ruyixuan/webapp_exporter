import json
import asyncio
from aiohttp import ClientSession
from prometheus_client import Gauge

class PlanMetrics:
    def __init__(self, config_path="webapp_my_config.json"):
        self.web_app_configs = self.load_webapp_configs(config_path)

        # ✅ Plan 监控指标
        self.plan_metric_groups = {
            "PT5M": [
                "CpuPercentage", "MemoryPercentage", "DiskQueueLength",
                "HttpQueueLength", "BytesReceived", "BytesSent"
            ]
        }

        # ✅ Plan 规格指标
        self.plan_static_metrics = {
            "cpu_cores": Gauge("azure_plan_cpu_cores", "CPU cores of Azure App Service Plan", ["resource_group_name", "plan_name"]),
            "memory_gb": Gauge("azure_plan_memory_gb", "Memory (GB) of Azure App Service Plan", ["resource_group_name", "plan_name"]),
            "disk_size_gb": Gauge("azure_plan_disk_size_gb", "Disk Size (GB) of Azure App Service Plan", ["resource_group_name", "plan_name"])
        }

    def load_webapp_configs(self, file_path):
        """ 加载 Web App Plan 配置 """
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ERROR] Failed to load configuration file - {e}")
            return []

    async def get_plan_specs(self, session, plan_name, config, access_token):
        """ 获取 Plan 规格信息 """
        url = f"https://management.azure.com/subscriptions/{config['subscription_id']}/resourceGroups/{config['resource_group_name']}/providers/Microsoft.Web/serverfarms/{plan_name}?api-version=2024-04-01"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    cpu_cores = 2  # 解析 API 数据
                    memory_gb = 4  # 解析 API 数据
                    disk_size_gb = 10  # 解析 API 数据

                    self.plan_static_metrics["cpu_cores"].labels(config["resource_group_name"], plan_name).set(cpu_cores)
                    self.plan_static_metrics["memory_gb"].labels(config["resource_group_name"], plan_name).set(memory_gb)
                    self.plan_static_metrics["disk_size_gb"].labels(config["resource_group_name"], plan_name).set(disk_size_gb)

        except Exception as e:
            print(f"[ERROR] 获取 Plan {plan_name} 规格失败: {e}")

    async def run(self):
        """ 启动 Plan 监控数据收集 """
        async with ClientSession() as session:
            tasks = []
            for web_app_config in self.web_app_configs:
                for plan_name in web_app_config["plan_names"]:
                    tasks.append(self.get_plan_specs(session, plan_name, web_app_config, "your_access_token"))

            await asyncio.gather(*tasks)
