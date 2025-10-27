# Build script for Windows releases
# This script builds the Windows executable and creates an MSI installer

param(
    [Parameter(Mandatory=$false)]
    [string]$Version = "0.1.0"
)

Write-Host "Building Todo App for Windows..." -ForegroundColor Green
Write-Host "Version: $Version" -ForegroundColor Cyan

# Clean previous builds
Write-Host "`nCleaning previous builds..." -ForegroundColor Yellow
cargo clean

# Build release binary
Write-Host "`nBuilding release binary..." -ForegroundColor Yellow
cargo build --release

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Build successful!" -ForegroundColor Green

# Create release directory
$releaseDir = "release-windows"
if (Test-Path $releaseDir) {
    Remove-Item -Recurse -Force $releaseDir
}
New-Item -ItemType Directory -Path $releaseDir | Out-Null

# Copy executable
Write-Host "`nCopying executable to release directory..." -ForegroundColor Yellow
Copy-Item "target\release\todo.exe" "$releaseDir\todo-windows-x64.exe"

# Create MSI installer using WiX
Write-Host "`nCreating MSI installer..." -ForegroundColor Yellow

# Check if WiX is installed
try {
    $wixInstalled = Get-Command wix -ErrorAction Stop
} catch {
    Write-Host "WiX not found. Installing WiX..." -ForegroundColor Yellow
    dotnet tool install --global wix
    dotnet tool update --global wix
    wix extension add WixToolset.UI.wixext
}

# Create WiX source file
$wxsContent = @"
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*" Name="Todo App" Language="1033" Version="$Version"
           Manufacturer="Todo App" UpgradeCode="12345678-1234-1234-1234-123456789012">
    <Package InstallerVersion="200" Compressed="yes" InstallScope="perMachine" />
    <MajorUpgrade DowngradeErrorMessage="A newer version is already installed." />
    <MediaTemplate EmbedCab="yes" />

    <Feature Id="ProductFeature" Title="Todo App" Level="1">
      <ComponentGroupRef Id="ProductComponents" />
    </Feature>

    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFiles64Folder">
        <Directory Id="INSTALLFOLDER" Name="TodoApp" />
      </Directory>
      <Directory Id="ProgramMenuFolder">
        <Directory Id="ApplicationProgramsFolder" Name="Todo App"/>
      </Directory>
    </Directory>

    <ComponentGroup Id="ProductComponents" Directory="INSTALLFOLDER">
      <Component Id="TodoExe" Guid="*">
        <File Id="TodoExeFile" Source="target\release\todo.exe" KeyPath="yes">
          <Shortcut Id="TodoStartMenuShortcut" Directory="ApplicationProgramsFolder"
                    Name="Todo App" WorkingDirectory="INSTALLFOLDER"
                    Icon="TodoIcon.exe" IconIndex="0" Advertise="yes" />
        </File>
      </Component>
    </ComponentGroup>

    <Icon Id="TodoIcon.exe" SourceFile="target\release\todo.exe" />
  </Product>
</Wix>
"@

$wxsContent | Out-File -FilePath "installer.wxs" -Encoding UTF8

# Build the installer
wix build installer.wxs -o "$releaseDir\todo-installer-$Version.msi"

if ($LASTEXITCODE -ne 0) {
    Write-Host "MSI creation failed!" -ForegroundColor Red
} else {
    Write-Host "MSI installer created successfully!" -ForegroundColor Green
}

# Clean up temporary files
Remove-Item "installer.wxs" -ErrorAction SilentlyContinue

Write-Host "`n================================" -ForegroundColor Cyan
Write-Host "Release files created in: $releaseDir" -ForegroundColor Green
Write-Host "  - todo-windows-x64.exe" -ForegroundColor White
Write-Host "  - todo-installer-$Version.msi" -ForegroundColor White
Write-Host "================================`n" -ForegroundColor Cyan
