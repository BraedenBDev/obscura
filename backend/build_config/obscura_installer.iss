; Obscura - Inno Setup Installer Script
; Run with: iscc build_config\obscura_installer.iss

#define MyAppName "Obscura"
#define MyAppVersion "1.0"
#define MyAppPublisher "Obscura Team"
#define MyAppExeName "Obscura.exe"
#define MyAppDescription "Privacy Protection for Chrome - Detect and Anonymize PII"

[Setup]
AppId={{7E9A5F3D-4B2C-4E8A-9D1F-6A8C2B5E7D4F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=Obscura_Setup_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=
SetupIconFile=icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startupicon"; Description: "Start Obscura when Windows starts"; GroupDescription: "System Integration:"

[Files]
; Main application files from PyInstaller dist folder
Source: "..\dist\Obscura\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "{#MyAppDescription}"
; Desktop shortcut (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "{#MyAppDescription}"
; Startup shortcut (optional)
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
; Option to launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up config and log files on uninstall
Type: files; Name: "{app}\extension_config.json"
Type: files; Name: "{app}\sessions.json"
Type: files; Name: "{app}\launcher_debug.log"
Type: files; Name: "{app}\gui_debug.log"

[Code]
// Check if application is running before uninstall
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Try to kill the process if running
  Exec('taskkill.exe', '/F /IM "Obscura.exe"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
