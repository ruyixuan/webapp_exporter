import json
import asyncio
from aiohttp import ClientSession
from prometheus_client import start_http_server, Gauge
from azure.identity import ClientSecretCredential

class AzureWebAppExporter:
    def __init__(self, config_path="webapp_my_config.json", port=9200):
        self.web_app_configs = self.load_webapp_configs(config_path)
        self.port = port

        # Metric groups with different time intervals
        self.metric_groups = {
            "PT5M": [
                "CpuTime", "Requests", "BytesReceived", "BytesSent",
                "Http2xx", "Http3xx", "Http4xx", "Http5xx", 
                "MemoryWorkingSet", "AverageMemoryWorkingSet", 
                "AverageResponseTime", "HttpResponseTime", "IoReadBytesPerSecond",
                "IoWriteBytesPerSecond", "IoReadOperationsPerSecond", "IoWriteOperationsPerSecond", "HealthCheckStatus"
            ],
            "PT6H": ["FileSystemUsage"]  # FileSystemUsage uses a 6-hour interval
        }

        # Create Prometheus metrics
        self.metrics = {
            metric: Gauge(
                f"azure_webapp_{metric.lower()}",
                f"{metric} of Azure Web App",
                ["resource_group_name", "web_app_name"]
            )
            for interval, metrics in self.metric_groups.items()
            for metric in metrics
        }

    def load_webapp_configs(self, file_path):
        """ Load Web App configuration file """
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error: Failed to load configuration file - {e}")
            return []

    def get_access_token(self, tenant_id, client_id, client_secret):
        """ Obtain Azure API access token """
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

    async def get_azure_metrics(self, session, web_app_config, interval):
        """ Request Azure API to fetch monitoring data """
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
            url = f"https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}/providers/Microsoft.Web/sites/{web_app_name}/providers/microsoft.insights/metrics"
            params = {
                "api-version": "2024-02-01",
                "metricnames": ",".join(metric_names),
                "timespan": "PT24H" if interval == "PT6H" else "PT1H",
                "interval": interval
            }

            try:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"\nAPI Response for {web_app_name} ({interval} interval):\n{json.dumps(data, indent=4)}")
                        metrics[web_app_name] = {
                            metric: self.get_metric_value(metric, data) for metric in metric_names
                        }
                    else:
                        print(f"Error: Failed to fetch metrics for {web_app_name} (HTTP {response.status}) - {await response.text()}")
            except Exception as e:
                print(f"Error: API request failed for {web_app_name} - {e}")

            # Avoid Azure API rate limits
            await asyncio.sleep(1)

        return metrics

    def get_metric_value(self, metric_name, data):
        """ Parse Azure API response data """
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
            print(f"\nNo {metric_name} data found")
            return 0
        except Exception as e:
            print(f"Error: Failed to parse metric {metric_name} - {e}")
            return 0

    async def update_metrics(self):
        """ Periodically fetch Azure Web App monitoring data and update Prometheus """
        while True:
            async with ClientSession() as session:
                tasks = []
                for web_app_config in self.web_app_configs:
                    for interval in self.metric_groups.keys():
                        tasks.append(self.get_azure_metrics(session, web_app_config, interval))
                
                metrics_results = await asyncio.gather(*tasks)

                result_index = 0
                for web_app_config in self.web_app_configs:
                    resource_group_name = web_app_config["resource_group_name"]
                    for interval in self.metric_groups.keys():
                        metrics = metrics_results[result_index]
                        result_index += 1

                        for web_app_name, app_metrics in metrics.items():
                            for metric_name, value in app_metrics.items():
                                prometheus_metric = self.metrics.get(metric_name)
                                if prometheus_metric:
                                    prometheus_metric.labels(resource_group_name=resource_group_name, web_app_name=web_app_name).set(value)
                                    print(f"Updated {metric_name}: {value} (Web App: {web_app_name})")

            await asyncio.sleep(60)  # Update every 60 seconds

    def run(self):
        start_http_server(self.port)
        print(f"Exporter is running on port {self.port}")
        asyncio.run(self.update_metrics())

if __name__ == "__main__":
    exporter = AzureWebAppExporter()
    exporter.run()
