# BrowserBot Stdio Tool Installation Script for execute_nobuycart_com
# Run this script to view the configuration block for Claude Desktop.

$configSnippet = @'
{
  "mcpServers": {
    "execute_nobuycart_com": {
      "command": "C:\\Users\\hp\\OneDrive\\Desktop\\BrowserBot\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\hp\\OneDrive\\Desktop\\BrowserBot\\packages\\execute_nobuycart_com\\server.py"
      ],
      "env": {
        "BROWSERBOT_HEADLESS": "true"
      }
    }
  }
}
'@

$claudeConfigDir = "$env:APPDATA\Claude"
$claudeConfigFile = "$claudeConfigDir\claude_desktop_config.json"

Write-Host "============================================================"
Write-Host "Installing BrowserBot Stdio Tool: execute_nobuycart_com"
Write-Host "============================================================"
Write-Host ""
Write-Host "To install manually, add the following snippet to your Claude config:"
Write-Host "Location: $claudeConfigFile"
Write-Host ""
Write-Host $configSnippet
Write-Host ""

# Create Claude config directory if missing
if (-not (Test-Path $claudeConfigDir)) {
    New-Item -ItemType Directory -Path $claudeConfigDir | Out-Null
}

Write-Host "Installation files prepared successfully."
