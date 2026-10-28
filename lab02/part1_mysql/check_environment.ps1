param([string]$CourseDir = 'D:\大数据采集与处理-学生实验环境')
$ErrorActionPreference = 'Stop'
$EvidenceDir = Join-Path $PSScriptRoot 'evidence'
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function Docker-Json([string[]]$Arguments) {
    $Raw = & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('docker failed: ' + ($Arguments -join ' ')) }
    return ($Raw | ConvertFrom-Json)
}

function Container-Summary($Container) {
    return [ordered]@{
        name = $Container.Name.TrimStart('/')
        image = $Container.Config.Image
        image_id = $Container.Image
        running = $Container.State.Running
        health = $Container.State.Health.Status
        started_at = $Container.State.StartedAt
        mounts = @($Container.Mounts | Select-Object Type, Name, Source, Destination, RW)
        published_ports = $Container.NetworkSettings.Ports
        networks = @($Container.NetworkSettings.Networks.PSObject.Properties.Name)
    }
}

$Workspace = @(Docker-Json @('inspect', 'smartpark-student-course-workspace-1'))[0]
$Mysql = @(Docker-Json @('inspect', 'smartpark-student-mysql-1'))[0]
$Version = Docker-Json @('version', '--format', '{{json .}}')
$Volume = @(Docker-Json @('volume', 'inspect', 'smartpark-student_l05-mysql-data'))[0]
$WorkspaceMount = @($Workspace.Mounts | Where-Object { $_.Destination -eq '/home/pwuser/workspace' })
$MysqlMount = @($Mysql.Mounts | Where-Object { $_.Destination -eq '/var/lib/mysql' })
$Bindings = @($Mysql.NetworkSettings.Ports.PSObject.Properties | Where-Object { $null -ne $_.Value })
$Jupyter = Invoke-WebRequest -Uri 'http://127.0.0.1:8888/api/status' -Headers @{ Authorization = 'token bigdata-course' } -TimeoutSec 10

# Check 是教学脚本提供的只读分支。保留真实失败，不修补脚本或替换镜像。
$HelperOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $CourseDir 'l05-mysql.ps1') -Action Check -CourseDir $CourseDir 2>&1
$HelperExitCode = $LASTEXITCODE
$Checks = [ordered]@{
    workspace_healthy = ($Workspace.State.Running -and $Workspace.State.Health.Status -eq 'healthy')
    mysql_healthy = ($Mysql.State.Running -and $Mysql.State.Health.Status -eq 'healthy')
    d_drive_workspace_bind = ($WorkspaceMount.Count -eq 1 -and $WorkspaceMount[0].Type -eq 'bind' -and $WorkspaceMount[0].Source -eq (Join-Path $CourseDir 'workspace') -and $WorkspaceMount[0].RW)
    l05_volume_in_use = ($MysqlMount.Count -eq 1 -and $MysqlMount[0].Type -eq 'volume' -and $MysqlMount[0].Name -eq 'smartpark-student_l05-mysql-data')
    mysql_no_host_port = ($Bindings.Count -eq 0)
    jupyter_api_200 = ($Jupyter.StatusCode -eq 200)
    shared_course_network = ($Workspace.NetworkSettings.Networks.PSObject.Properties.Name -contains 'smartpark-student_default' -and $Mysql.NetworkSettings.Networks.PSObject.Properties.Name -contains 'smartpark-student_default')
}
$Result = [ordered]@{
    checked_at = [DateTimeOffset]::Now.ToOffset([TimeSpan]::FromHours(8)).ToString('o')
    read_only = $true
    environment_ok = (@($Checks.Values | Where-Object { $_ -ne $true }).Count -eq 0)
    checks = $Checks
    docker_client_version = $Version.Client.Version
    docker_engine_version = $Version.Server.Version
    compose_version = (& docker compose version --short).Trim()
    workspace = Container-Summary $Workspace
    mysql = Container-Summary $Mysql
    volume = [ordered]@{ name = $Volume.Name; created_at = $Volume.CreatedAt; driver = $Volume.Driver; mountpoint = $Volume.Mountpoint }
    jupyter = [ordered]@{ url = 'http://127.0.0.1:8888/api/status'; status_code = $Jupyter.StatusCode }
    teaching_helper = [ordered]@{ action = 'Check'; exit_code = $HelperExitCode; output = @($HelperOutput | ForEach-Object { $_.ToString() }) }
    configured_by = '父聊天已配置；本次只读复用并核验，不重装、不重建、不改密码。'
}
$Json = $Result | ConvertTo-Json -Depth 12
$RunName = 'environment_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff') + '.json'
$RunPath = Join-Path $EvidenceDir $RunName
[IO.File]::WriteAllText($RunPath, $Json, [Text.UTF8Encoding]::new($false))
$LatestPath = Join-Path $EvidenceDir 'environment.json'
$TempPath = $LatestPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
[IO.File]::WriteAllText($TempPath, $Json, [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $TempPath -Destination $LatestPath -Force
$Json
if (-not $Result.environment_ok) { exit 1 }
