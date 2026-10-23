; HeadMouse installer (Inno Setup 6.3+). Built by .github/workflows/windows.yml:
;   ISCC.exe /DAppVersion=1.0.0 installer\headmouse.iss
; Expects the PyInstaller output in dist\HeadMouse.
;
; - Installs for the current user only: no administrator rights needed.
; - Start-menu and desktop icons; uninstall from Settings > Apps.
; - Updating keeps the player's settings (headmouse_settings.toml).
; - Starts HeadMouse when finished, also in silent installs. Add /NOLAUNCH=1 to stop that.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F6A2C1E-5B7D-4E3A-9C21-7D4B1E0F9A63}
AppName=HeadMouse
AppVersion={#AppVersion}
AppVerName=HeadMouse {#AppVersion}
AppPublisher=HeadMouse
AppPublisherURL=https://github.com/nkkoran/Testing-Opentrack
DefaultDirName={localappdata}\Programs\HeadMouse
DefaultGroupName=HeadMouse
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=HeadMouse-Setup
SetupIconFile=..\headmouse.ico
UninstallDisplayIcon={app}\HeadMouse.exe
UninstallDisplayName=HeadMouse
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Close a running HeadMouse before updating it.
CloseApplications=force
RestartApplications=no

[Files]
Source: "..\dist\HeadMouse\*"; DestDir: "{app}"; Excludes: "headmouse_settings.toml,headmouse_error.log"; \
    Flags: recursesubdirs createallsubdirs ignoreversion
; Default settings only on first install, so updates keep the player's own settings.
Source: "..\headmouse_settings.toml"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\HeadMouse"; Filename: "{app}\HeadMouse.exe"; Comment: "Head control for games"
Name: "{autodesktop}\HeadMouse"; Filename: "{app}\HeadMouse.exe"; Comment: "Head control for games"

[Run]
Filename: "{app}\HeadMouse.exe"; Description: "Start HeadMouse now"; Flags: nowait postinstall; Check: ShouldLaunch

[UninstallDelete]
Type: files; Name: "{app}\headmouse_error.log"
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function ShouldLaunch: Boolean;
begin
  Result := ExpandConstant('{param:NOLAUNCH|0}') = '0';
end;
