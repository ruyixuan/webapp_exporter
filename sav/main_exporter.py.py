import asyncio
import subprocess
from prometheus_client import start_http_server

class MainExporter:
    def __init__(self, port=9200):
        self.port = port

    async def run(self):
        """ 启动 Web App 和 Plan 指标采集 """
        webapp_process = subprocess.Popen(["python", "webapp_metrics.py"])
        plan_process = subprocess.Popen(["python", "plan_metrics.py"])

        try:
            await asyncio.gather(
                asyncio.create_task(self.monitor_subprocess(webapp_process, "WebApp Metrics")),
                asyncio.create_task(self.monitor_subprocess(plan_process, "Plan Metrics"))
            )
        except KeyboardInterrupt:
            webapp_process.terminate()
            plan_process.terminate()
            print("\n[INFO] 终止 Exporter")

    async def monitor_subprocess(self, process, name):
        """ 监控子进程是否正常运行 """
        while True:
            if process.poll() is not None:
                print(f"[ERROR] {name} 进程终止，重启中...")
                process = subprocess.Popen(["python", f"{name.lower().replace(' ', '_')}.py"])
            await asyncio.sleep(10)

    def start(self):
        """ 启动 Prometheus Exporter """
        start_http_server(self.port)
        print(f"Exporter is running on port {self.port}")
        asyncio.run(self.run())

if __name__ == "__main__":
    exporter = MainExporter()
    exporter.start()
