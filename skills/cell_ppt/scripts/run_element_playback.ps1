#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Manifest
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$manifestPath = (Resolve-Path -LiteralPath $Manifest).Path
$plan = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
$copy = (Resolve-Path -LiteralPath $plan.copy).Path
$hash = [System.Security.Cryptography.SHA256]::Create()
$stream = [IO.File]::OpenRead($copy)
try { $digest = [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '') }
finally { $stream.Dispose(); $hash.Dispose() }
if ([IO.Path]::GetDirectoryName($copy) -ne [IO.Path]::GetDirectoryName($manifestPath) -or
    $copy -eq $plan.source -or $digest -ne $plan.copy_sha256) {
    throw 'Playback copy or its hash does not match the manifest.'
}
$queue = @{}
foreach ($page in $plan.targets.PSObject.Properties) {
    $queue[$page.Name] = [System.Collections.Generic.Queue[int]]::new()
    foreach ($shapeId in $page.Value) { $queue[$page.Name].Enqueue([int]$shapeId) }
}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class CellPptWindow {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr window);

    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr window, int command);
}
'@

function Wait-ForPlaybackForeground($Deck) {
    $Deck.Windows.Item(1).Activate()
    $name = [IO.Path]::GetFileNameWithoutExtension($Deck.Name)
    $titlePattern = '^' + [regex]::Escape($name) + '(?:\.pptx)?(?: - |$)'
    $handle = [IntPtr]::Zero
    for ($attempt = 0; $attempt -lt 20 -and $handle -eq [IntPtr]::Zero; $attempt++) {
        foreach ($process in [Diagnostics.Process]::GetProcessesByName('POWERPNT')) {
            if ($process.MainWindowTitle -match $titlePattern) {
                $handle = $process.MainWindowHandle
                break
            }
        }
        if ($handle -eq [IntPtr]::Zero) { Start-Sleep -Milliseconds 100 }
    }
    if ($handle -eq [IntPtr]::Zero) { throw 'Could not identify the playback window.' }
    if ([CellPptWindow]::IsIconic($handle)) { [void][CellPptWindow]::ShowWindowAsync($handle, 9) }
    if ([CellPptWindow]::GetForegroundWindow() -ne $handle) {
        [void][CellPptWindow]::SetForegroundWindow($handle)
        Write-Output 'ELEMENT_PLAYBACK_WAITING_FOR_FOREGROUND'
    }
    while ($Deck.Windows.Count -gt 0) {
        if ([CellPptWindow]::GetForegroundWindow() -eq $handle) {
            Start-Sleep -Milliseconds 300
            if ([CellPptWindow]::GetForegroundWindow() -eq $handle) {
                Write-Output 'ELEMENT_PLAYBACK_FOREGROUND_READY'
                return
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw 'The playback window closed before becoming foreground.'
}

$mutex = [System.Threading.Mutex]::new($false, 'Local\CellPptElementPlayback')
$locked = $false
try {
    try { $locked = $mutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'A PowerPoint element playback session is already running.' }
    $app = New-Object -ComObject PowerPoint.Application
    $app.Visible = -1
    # Open the isolated copy in the normal editing window.
    $deck = $app.Presentations.Open($copy, 0, 0, -1)
    Write-Output 'ELEMENT_PLAYBACK_EDITOR_OPEN'
    Wait-ForPlaybackForeground $deck
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $loadedPage = ''
    $shapes = @{}
    for ($index = 1; $index -le $deck.Slides.Count; $index++) {
        if ($queue.ContainsKey([string]$deck.Slides.Item($index).SlideID)) {
            $deck.Windows.Item(1).View.GotoSlide($index)
            break
        }
    }
    while ($queue.Count -gt 0) {
        try { if ($deck.Windows.Count -eq 0) { break } }
        catch { break }
        try {
            $window = $app.ActiveWindow
            $slide = if ($window -and $window.Presentation.FullName -eq $copy) { $window.View.Slide } else { $null }
            $pageId = if ($slide) { [string]$slide.SlideID } else { '' }
        } catch { $pageId = '' }
        if (-not $queue.ContainsKey($pageId)) {
            Start-Sleep -Milliseconds 120
            continue
        }
        if ($loadedPage -ne $pageId) {
            Write-Output "ELEMENT_PLAYBACK_PAGE_BEGIN|$($slide.SlideIndex)|$($clock.ElapsedMilliseconds)"
            $shapes = @{}
            for ($i = 1; $i -le $slide.Shapes.Count; $i++) {
                $shape = $slide.Shapes.Item($i)
                $shapes[[int]$shape.Id] = $shape
            }
            $loadedPage = $pageId
        }
        $shapeId = $queue[$pageId].Dequeue()
        if ($shapes.ContainsKey($shapeId)) { $shapes[$shapeId].Visible = -1 }
        else { throw "Preview element is missing on slide $pageId." }
        Start-Sleep -Milliseconds 200
        if ($queue[$pageId].Count -ne 0) { continue }

        $queue.Remove($pageId)
        $pageIndex = $slide.SlideIndex
        Write-Output "ELEMENT_PLAYBACK_PAGE_DONE|$pageIndex|$($clock.ElapsedMilliseconds)"
        if ($queue.Count -eq 0) { break }

        # A manual page change during the interval takes precedence.
        $window = $app.ActiveWindow
        if (-not $window -or $window.Presentation.FullName -ne $copy) { continue }
        try { $selectedPageId = [string]$window.View.Slide.SlideID }
        catch { continue }
        if ($selectedPageId -ne $pageId) { continue }

        for ($step = 1; $step -lt $deck.Slides.Count; $step++) {
            $next = ($pageIndex + $step - 1) % $deck.Slides.Count + 1
            $nextSlide = $deck.Slides.Item($next)
            if ($queue.ContainsKey([string]$nextSlide.SlideID)) {
                $window.View.GotoSlide($next)
                break
            }
        }
    }
    if ($queue.Count -gt 0) { throw 'The preview window closed before output finished.' }
    Write-Output 'ELEMENT_PLAYBACK_WORKER_FINISHED'
} catch {
    Write-Output "ELEMENT_PLAYBACK_ERROR|$($_.InvocationInfo.ScriptLineNumber)|$($_.Exception.Message)"
    throw
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
