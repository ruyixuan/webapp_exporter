import json
import asyncio
from aiohttp import ClientSession
from prometheus_client import start_http_server, Gauge
from azure.identity import ClientSecretCredential

class AzureWebAppExporter:
    def __init__(self, config_path="webapp_my_config.json", port=9200):
        self.web_app_configs = self.load_webapp_configs(config_path)
        self.port = port

        # Web App 监控指标
        self.metric_groups = {
            "PT5M": [
                "CpuTime", "Requests", "BytesReceived", "BytesSent",
                "Http2xx", "Http3xx", "Http4xx", "Http5xx",
                "MemoryWorkingSet", "AverageMemoryWorkingSet",
                "AverageResponseTime", "HttpResponseTime",
                "IoReadBytesPerSecond", "IoWriteBytesPerSecond",
                "IoReadOperationsPerSecond", "IoWriteOperationsPerSecond",
                "HealthCheckStatus"
            ],
            "PT6H": ["FileSystemUsage"]
        }

        # Prometheus 指标
        self.metrics = {
            metric: Gauge(
                f"azure_webapp_{metric.lower()}",
                f"{metric} of Azure Web App",
                ["resource_group_name", "web_app_name", "plan_name"]
            )
            for interval, metrics in self.metric_groups.items()
            for metric in metrics
        }

    def load_webapp_configs(self, file_path):
        """ 加载 Web App 配置 """
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error: Failed to load configuration file - {e}")
            return []

    def get_access_token(self, tenant_id, client_id, client_secret):
        """ 获取 Azure API 访问 Token """
        try:
            credential = ClientSecretCredential(
                tenant_id, client_id, client_secret,
                authority="https://login.microsoftonline.com"
            )
            token = credential.get_token("https://management.azure.com/.default")
            return token.token
        except Exception as e:
            print(f"Error: Failed to get access token - {e}")
            return None

    async def get_webapp_plan_name(self, session, web_app_name, config, access_token):
        """ 获取 Web App 归属的 Plan 名称 """
        url = f"https://management.azure.com/subscriptions/{config['subscription_id']}/resourceGroups/{config['resource_group_name']}/providers/Microsoft.Web/sites/{web_app_name}?api-version=2024-04-01"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    server_farm_id = data.get("properties", {}).get("serverFarmId", None)
                    if server_farm_id:
                        plan_name = server_farm_id.split("/")[-1]
                        print(f"[INFO] Web App {web_app_name} 属于 Plan: {plan_name}")
                        return plan_name
                print(f"[WARNING] 未能获取 {web_app_name} 的 Plan 名称")
        except Exception as e:
            print(f"[ERROR] 获取 {web_app_name} Plan 失败: {e}")

        return "unknown_plan"

    def get_metric_value(self, metric_name, data):
        """ 解析 Azure API 返回的监控数据，获取最新的指标值 """
        try:
            for item in data.get("value", []):
                if item["name"]["value"].lower() == metric_name.lower():
                    timeseries_data = item.get("timeseries", [])
                    if timeseries_data:
                        values = timeseries_data[0].get("data", [])
                        if values:
                            latest_value = values[-1].get(
                                "total",
                                values[-1].get("average", values[-1].get("maximum", values[-1].get("sum", 0)))
                            )
                            timestamp = values[-1].get("timeStamp", "Unknown Time")
                            print(f"\n{metric_name}: {latest_value} (Timestamp: {timestamp})")
                            return latest_value
            print(f"\n[WARNING] No {metric_name} data found")
            return 0
        except Exception as e:
            print(f"[ERROR] 解析指标 {metric_name} 失败: {e}")
            return 0

    async def get_azure_metrics(self, session, web_app_config, interval):
        """ 获取 Web App 监控数据 """
        tenant_id, client_id, client_secret = (
            web_app_config["tenant_id"],
            web_app_config["client_id"],
            web_app_config["client_secret"]
        )
        subscription_id, resource_group_name, web_app_names = (
            web_app_config["subscription_id"],
            web_app_config["resource_group_name"],
            web_app_config["web_app_names"]
        )

        access_token = self.get_access_token(tenant_id, client_id, client_secret)
        if not access_token:
            return {}

        headers = {"Authorization": f"Bearer {access_token}"}
        metric_names = self.metric_groups[interval]
        metrics = {}

        for web_app_name in web_app_names:
            plan_name = await self.get_webapp_plan_name(session, web_app_name, web_app_config, access_token)

            url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Web/sites/{web_app_name}/providers/microsoft.insights/metrics"
            params = {
                "api-version": "2024-02-01",
                "metricnames": ",".join(metric_names),
                "timespan": "PT24H" if interval == "PT6H" else "PT1H",
                "interval": interval,
                "metricnamespace": "Microsoft.Web/sites"
            }

            try:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        metrics[web_app_name] = {
                            metric: self.get_metric_value(metric, data) for metric in metric_names
                        }
                        for metric_name, value in metrics[web_app_name].items():
                            prometheus_metric = self.metrics.get(metric_name)
                            if prometheus_metric:
                                prometheus_metric.labels(
                                    resource_group_name=resource_group_name,
                                    web_app_name=web_app_name,
                                    plan_name=plan_name
                                ).set(value)
                                print(f"[Web App] {web_app_name} (Plan: {plan_name}) → {metric_name}: {value}")
                    else:
                        print(f"[ERROR] 获取 {web_app_name} 监控数据失败 (HTTP {response.status}) - {await response.text()}")
            except Exception as e:
                print(f"[ERROR] API 请求失败 {web_app_name}: {e}")

            await asyncio.sleep(1)

    async def update_metrics(self):
        """ 定期采集 Web App 监控数据并更新 Prometheus """
        while True:
            async with ClientSession() as session:
                tasks = []
                for web_app_config in self.web_app_configs:
                    for interval in self.metric_groups.keys():
                        tasks.append(self.get_azure_metrics(session, web_app_config, interval))

                await asyncio.gather(*tasks)

            await asyncio.sleep(60)  # ✅ 每 60 秒更新一次数据

    def run(self):
        start_http_server(self.port)
        print(f"Exporter is running on port {self.port}")
        asyncio.run(self.update_metrics())  # ✅ 现在 `update_metrics()` 已经定义

if __name__ == "__main__":
    exporter = AzureWebAppExporter()
    exporter.run()
