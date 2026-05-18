param(
    [string]$VaultPath = "D:\OB\ranran",
    [string]$Token = "mftgOTW3V3D4RKPHR7zgH50NVHnYRSyDXf1k5yXp",
    [string]$ApiBase = "https://api.flowus.cn/v1",
    [string]$BotWorkspaceId = "da8468df-9b6e-4fb5-a9f6-0cd8a336bf70",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$headers = @{ "Authorization" = "Bearer $Token"; "Content-Type" = "application/json" }

function Invoke-FlowUs {
    param($Method, $Path, $Body)
    $url = "$ApiBase$Path"
    $params = @{ Method = $Method; Uri = $url; Headers = $headers }
    if ($Body) { $params["Body"] = ($Body | ConvertTo-Json -Depth 10) }
    try {
        $r = Invoke-WebRequest @params -ErrorAction Stop
        return ($r.Content | ConvertFrom-Json)
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        $msg = if ($_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { $_.Exception.Message }
        Write-Warning "API Error [$status] $Path"
        return $null
    }
}

function Convert-MdToBlocks {
    param([string]$Content)
    $blocks = @()
    $lines = $Content -split "`n"
    $i = 0
    while ($i -lt $lines.Length) {
        $line = $lines[$i]
        if ($i -eq 0 -and $line.Trim() -eq '---') {
            $i++
            while ($i -lt $lines.Length -and $lines[$i].Trim() -ne '---') { $i++ }
            $i++
            continue
        }
        $trimmed = $line.TrimEnd("`r")
        if ($trimmed -match '^#{1,6}\s') {
            $level = ($matches[0].Length - 1).ToString()
            $text = $trimmed -replace '^#+\s+', ''
            $blocks += @{ type = "heading_$level"; data = @{ rich_text = @(@{ type = "text"; text = @{ content = $text } }) } }
        } elseif ($trimmed -match '^```(\w*)') {
            $lang = $matches[1]
            $codeLines = @(); $i++
            while ($i -lt $lines.Length -and $lines[$i].Trim() -ne '```') {
                $codeLines += $lines[$i].TrimEnd("`r"); $i++
            }
            $blocks += @{ type = "code"; data = @{ rich_text = @(@{ type = "text"; text = @{ content = $codeLines -join "`n" } }); language = if ($lang) { $lang } else { "plain text" } } }
        } elseif ($trimmed -match '^>\s') {
            $blocks += @{ type = "quote"; data = @{ rich_text = @(@{ type = "text"; text = @{ content = $trimmed -replace '^>\s+', '' } }) } }
        } elseif ($trimmed -match '^-{3,}$') {
            $blocks += @{ type = "divider"; data = @{} }
        } elseif ($trimmed -match '^\*\s(.*)') {
            $blocks += @{ type = "bulleted_list_item"; data = @{ rich_text = @(@{ type = "text"; text = @{ content = $matches[1] } }) } }
        } elseif ($trimmed -match '^\d+[\.\)\s]\s+(.*)') {
            $blocks += @{ type = "numbered_list_item"; data = @{ rich_text = @(@{ type = "text"; text = @{ content = $matches[1] } }) } }
        } elseif ($trimmed -match '^- \[( |x)\]\s+(.*)') {
            $blocks += @{ type = "to_do"; data = @{ rich_text = @(@{ type = "text"; text = @{ content = $matches[2] } }); checked = ($matches[1] -eq 'x') } }
        } elseif ($trimmed -ne '') {
            $blocks += @{ type = "paragraph"; data = @{ rich_text = @(@{ type = "text"; text = @{ content = $trimmed } }) } }
        }
        $i++
    }
    return $blocks
}

Write-Host "=== Obsidian to FlowUs Sync ===" -ForegroundColor Cyan

$rootPageId = $null

# Create parent folder called "Obsidian Sync"
$folderName = "Obsidian Sync"
$folderBody = @{
    parent = @{ page_id = $BotWorkspaceId; type = "page_id" }
    icon = @{ type = "emoji"; emoji = " " }
    properties = @{ title = @{ type = "title"; title = @(@{ type = "text"; text = @{ content = $folderName } }) } }
}

if ($DryRun) {
    Write-Host "[DRY RUN] Would create folder: $folderName (under workspace)"
    $rootPageId = "dry-run-id"
} else {
    $folderResult = Invoke-FlowUs -Method Post -Path "/v1/pages" -Body $folderBody
    if ($folderResult -and $folderResult.id) {
        $rootPageId = $folderResult.id
        Write-Host "Folder created: $folderName ($rootPageId)" -ForegroundColor Green
        Write-Host "URL: https://flowus.cn/docs/$rootPageId" -ForegroundColor Cyan
    } else {
        Write-Host "Folder creation failed, using workspace root" -ForegroundColor Yellow
        $rootPageId = $BotWorkspaceId
    }
}

$files = Get-ChildItem -LiteralPath $VaultPath -Recurse -Filter "*.md" | Where-Object {
    $skipDirs = @('\.agents', '\.obsidian', '\.claude', '\.smart-env', '\.git', 'copilot', 'node_modules')
    $skip = $false
    foreach ($d in $skipDirs) { if ($_.FullName -match [regex]::Escape($d)) { $skip = $true; break } }
    -not $skip -and $_.Length -gt 0
}

Write-Host "Found $($files.Count) markdown files" -ForegroundColor Cyan
$total = $files.Count; $current = 0; $success = 0

foreach ($file in $files) {
    $current++
    $title = [System.IO.Path]::GetFileNameWithoutExtension($file.Name)
    $content = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { Write-Warning "[$current/$total] Cannot read: $($file.Name)"; continue }
    Write-Host "[$current/$total] $title"

    if ($DryRun) { Write-Host "  [DRY RUN] Would create page"; continue }

    $pageBody = @{
        parent = @{ page_id = $rootPageId; type = "page_id" }
        icon = @{ type = "emoji"; emoji = " " }
        properties = @{ title = @{ type = "title"; title = @(@{ type = "text"; text = @{ content = $title } }) } }
    }
    $page = Invoke-FlowUs -Method Post -Path "/v1/pages" -Body $pageBody
    if (-not $page) { Write-Warning "  Failed to create page"; continue }

    $blocks = Convert-MdToBlocks -Content $content
    if ($blocks.Count -gt 0) {
        for ($b = 0; $b -lt $blocks.Count; $b += 100) {
            $end = [Math]::Min($b + 99, $blocks.Count - 1)
            $batch = $blocks[$b..$end]
            $blockBody = @{ children = @($batch) }
            Invoke-FlowUs -Method Patch -Path "/v1/blocks/$($page.id)/children" -Body $blockBody | Out-Null
        }
    }
    Write-Host "  OK" -ForegroundColor Green
    $success++
    Start-Sleep -Milliseconds 100
}

Write-Host "`n=== Sync Complete ===" -ForegroundColor Cyan
Write-Host "Success: $success / $total" -ForegroundColor Green
if ($rootPageId -and $rootPageId -ne $BotWorkspaceId) {
    Write-Host "View in FlowUs: https://flowus.cn/docs/$rootPageId" -ForegroundColor Cyan
}
