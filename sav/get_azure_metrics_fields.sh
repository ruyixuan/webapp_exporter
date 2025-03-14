#!/bin/bash

# Azure 认证信息（请替换为你的实际值）
TENANT_ID="03258f72-ee37-4bbb-b38d-6efdfc96cde6"
CLIENT_ID="c7172bf6-41d5-415d-bf1e-8dfc79b38663"
CLIENT_SECRET="Sf--R~0WK.f6764~vrPJ4B~S-6zxu6Squ3"
SUBSCRIPTION_ID="f5a4a74a-a0e1-49e4-bf09-13609f38b674"
RESOURCE_GROUP="az006aboitcdlpoc538538"
WEB_APP_NAME="webgpt01cnlp006"

# Azure API 端点（中国世纪互联版）
AZURE_CHINA_AUTH_URL="https://login.partner.microsoftonline.cn"
AZURE_CHINA_MANAGEMENT_URL="https://management.chinacloudapi.cn"
API_VERSION="2024-02-01"

# 获取 Azure 访问令牌
echo "🔑 获取 Azure 访问令牌..."
ACCESS_TOKEN=$(curl -s -X POST "$AZURE_CHINA_AUTH_URL/$TENANT_ID/oauth2/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET&resource=$AZURE_CHINA_MANAGEMENT_URL" | jq -r '.access_token')

# 检查是否成功获取 Token
if [[ -z "$ACCESS_TOKEN" || "$ACCESS_TOKEN" == "null" ]]; then
    echo "❌ 获取访问令牌失败，请检查 Azure 认证信息！"
    exit 1
fi
echo "✅ 访问令牌获取成功！"

# 构造 API URL
METRICS_URL="$AZURE_CHINA_MANAGEMENT_URL/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.Web/sites/$WEB_APP_NAME/providers/microsoft.insights/metrics?api-version=$API_VERSION"

# 发送 API 请求
echo "🌍 访问 Azure API 获取可用指标..."
response=$(curl -s -X GET "$METRICS_URL" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json")

# 检查 API 请求是否成功
if [[ -z "$response" || "$response" == "null" ]]; then
    echo "❌ API 请求失败，请检查网络或 Azure 访问权限！"
    exit 1
fi

# 提取所有可用的 metric 字段
echo "🔍 提取可用的指标字段..."
echo ""

# 解析 JSON，提取 metricNames
echo "$response" | jq -r '.value[].name.value' | while read -r metric; do
    echo "🟢 可用指标: $metric"
done

echo ""
echo "✅ 任务完成！"
