#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup-app-registration.sh
#
# Creates an Azure AD (Entra ID) app registration for the MAF OneDrive
# Browser demo, adds the required delegated Microsoft Graph permissions,
# generates a client secret, and prints the values needed for .env.
#
# Prerequisites:
#   - Azure CLI (`az`) installed and logged in (`az login`)
#
# Usage:
#   ./scripts/setup-app-registration.sh [APP_DISPLAY_NAME]
# ---------------------------------------------------------------------------
set -euo pipefail

APP_NAME="${1:-MAF OneDrive Browser}"
REDIRECT_URI="http://localhost:8000/auth/callback"
SECRET_DESCRIPTION="maf-onedrive-integration"
SECRET_YEARS=1

# Microsoft Graph well-known application ID
MS_GRAPH_APP_ID="00000003-0000-0000-c000-000000000000"

# Delegated permission IDs for Microsoft Graph
# https://learn.microsoft.com/en-us/graph/permissions-reference
USER_READ="e1fe6dd8-ba31-4d61-89e7-88639da4683d"           # User.Read
FILES_READ_ALL="df85f4d6-205c-4ac5-a5ea-6bf408dba283"      # Files.Read.All
SITES_READ_ALL="205e70e5-aba6-4c52-a976-6d2d46c48043"      # Sites.Read.All

echo "==> Creating app registration: ${APP_NAME}"

APP_JSON=$(az ad app create \
    --display-name "${APP_NAME}" \
    --web-redirect-uris "${REDIRECT_URI}" \
    --required-resource-accesses "[
        {
            \"resourceAppId\": \"${MS_GRAPH_APP_ID}\",
            \"resourceAccess\": [
                { \"id\": \"${USER_READ}\",      \"type\": \"Scope\" },
                { \"id\": \"${FILES_READ_ALL}\", \"type\": \"Scope\" },
                { \"id\": \"${SITES_READ_ALL}\", \"type\": \"Scope\" }
            ]
        }
    ]" \
    --output json)

APP_ID=$(echo "${APP_JSON}" | jq -r '.appId')
OBJECT_ID=$(echo "${APP_JSON}" | jq -r '.id')

echo "==> App registered (appId=${APP_ID})"

# Create a client secret
echo "==> Generating client secret (valid ${SECRET_YEARS} year(s))"

SECRET_JSON=$(az ad app credential reset \
    --id "${OBJECT_ID}" \
    --display-name "${SECRET_DESCRIPTION}" \
    --years "${SECRET_YEARS}" \
    --output json)

CLIENT_SECRET=$(echo "${SECRET_JSON}" | jq -r '.password')
TENANT_ID=$(echo "${SECRET_JSON}" | jq -r '.tenant')

echo ""
echo "============================================"
echo " App registration created successfully!"
echo "============================================"
echo ""
echo "APPLICATION_ID=${APP_ID}"
echo "APPLICATION_SECRET=${CLIENT_SECRET}"
echo "TENANT_ID=${TENANT_ID}"
echo ""
echo "Add these to your .env file, or run:"
echo ""
echo "  cat >> .env << EOF"
echo "  APPLICATION_ID=${APP_ID}"
echo "  APPLICATION_SECRET=${CLIENT_SECRET}"
echo "  TENANT_ID=${TENANT_ID}"
echo "  EOF"
echo ""
