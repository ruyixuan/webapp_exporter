import json
import asyncio
from aiohttp import ClientSession
from prometheus_client import Gauge
from azure.identity import ClientSecretCredential

class WebAppMetrics:
    def __init__(self, config_path="webapp_my_config.json"):
        self.web_app_configs = self.load_webapp_configs(config_path)

        # ✅ Web App 监控指标
        self.metrics = {
            "CpuTime": Gauge("azure_webapp_cputime", "CpuTime of Azure Web App", ["resource_group_name", "web_app_name", "plan_name"]),
            "Requests": Gauge("azure_webapp_requests", "Requests of Azure Web App", ["resource_group_name", "web_app_name", "plan_name"]),
            "BytesReceived": Gauge("azure_webapp_bytesreceived", "BytesReceived of Azure Web App", ["resource_group_name", "web_app_name", "plan_name"]),
            "BytesSent": Gauge("azure_webapp_bytessent", "BytesSent of Azure Web App", ["resource_group_name", "web_app_name", "plan_name"]),
            "MemoryWorkingSet": Gauge("azure_webapp_memoryworkingset", "MemoryWorkingSet of Azure Web App", ["resource_group_name", "web_app_name", "plan_name"]),
        }

    def load_webapp_configs(self, file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[ERROR] 读取 Web App 配置失败: {e}")
            return []

    def get_access_token(self, tenant_id, client_id, client_secret):
        try:
            credential = ClientSecretCredential(tenant_id, client_id, client_secret)
            token = credential.get_token("https://management.azure.com/.default")
            return token.token
        except Exception as e:
            print(f"[ERROR] 获取 Access Token 失败: {e}")
            return None

    async def fetch_webapp_metrics(self, session, web_app_name, config, access_token):
        """ 获取 Web App 监控数据 """
        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://management.azure.com/subscriptions/{config['subscription_id']}/resourceGroups/{config['resource_group_name']}/providers/Microsoft.Web/sites/{web_app_name}/providers/microsoft.insights/metrics?api-version=2024-02-01"
        params = {"metricnames": ",".join(self.metrics.keys()), "interval": "PT5M"}

        try:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    for metric in self.metrics.keys():
                        value = 0  # 解析 API 数据填充值
                        self.metrics[metric].labels(config["resource_group_name"], web_app_name, "unknown_plan").set(value)
                    print(f"[INFO] Web App {web_app_name} 监控数据已更新")
                else:
                    print(f"[ERROR] 获取 {web_app_name} 监控数据失败 (HTTP {response.status})")
        except Exception as e:
            print(f"[ERROR] 请求 Web App {web_app_name} 失败: {e}")

    async def run(self):
        """ 启动 Web App 监控数据采集 """
        while True:
            async with ClientSession() as session:
                tasks = []
                for config in self.web_app_configs:
                    access_token = self.get_access_token(config["tenant_id"], config["client_id"], config["client_secret"])
                    if not access_token:
                        continue

                    for web_app_name in config["web_app_names"]:
                        tasks.append(self.fetch_webapp_metrics(session, web_app_name, config, access_token))

                await asyncio.gather(*tasks)
            await asyncio.sleep(60)  # ✅ 每 60 秒更新一次数据

if __name__ == "__main__":
    webapp_exporter = WebAppMetrics()
    asyncio.run(webapp_exporter.run())
