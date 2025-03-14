#!/bin/bash

# 配置文件路径
CONFIG_FILE="webapp_my_config.sav.json"

# 解析 JSON 配置文件获取凭据
TENANT_ID=$(jq -r '.[0].tenant_id' $CONFIG_FILE)
CLIENT_ID=$(jq -r '.[0].client_id' $CONFIG_FILE)
CLIENT_SECRET=$(jq -r '.[0].client_secret' $CONFIG_FILE)
SUBSCRIPTION_ID=$(jq -r '.[0].subscription_id' $CONFIG_FILE)

# Azure 中国世纪互联 OAuth 端点
AUTH_URL="https://login.partner.microsoftonline.cn/$TENANT_ID/oauth2/token"

# 获取 Access Token
ACCESS_TOKEN=$(curl -s -X POST $AUTH_URL \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=client_credentials" \
    -d "client_id=$CLIENT_ID" \
    -d "client_secret=$CLIENT_SECRET" \
    -d "resource=https://management.chinacloudapi.cn" | jq -r '.access_token')

# 检查是否成功获取 Access Token
if [[ -z "$ACCESS_TOKEN" || "$ACCESS_TOKEN" == "null" ]]; then
    echo "获取 Azure 访问令牌失败"
    exit 1
fi

# 发送 API 请求获取 App Service Plan (Serverfarms)
#API_URL="https://management.chinacloudapi.cn/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Web/serverfarms?api-version=2024-04-01"
#API_URL="https://management.chinacloudapi.cn/subscriptions/f5a4a74a-a0e1-49e4-bf09-13609f38b674/resourceGroups/az006aboitcdlpoc538538/providers/Microsoft.Web/sites/webgpt01cnlp006?api-version=2024-04-01"
API_URL="https://management.chinacloudapi.cn/subscriptions/f5a4a74a-a0e1-49e4-bf09-13609f38b674/resourceGroups/az006aboitcdlpoc538538/providers/Microsoft.Insights/metrics?api-version=2024-02-01&metricnames=CpuPercentage"


curl -X GET "$API_URL" \
     -H "Authorization: Bearer $ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     -s | jq .



#https://management.chinacloudapi.cn/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$resourceGroups_ID/providers/Microsoft.Web/sites/$WEB_APP_NAME?api-version=2024-04-01"