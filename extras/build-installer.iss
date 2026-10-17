; Compile only an explicit whitelist stage produced by package_source.py.
#ifndef PackageDir
  #error Define PackageDir as the source staging directory; never package a working runtime.
#endif
#include AddBackslash(PackageDir) + "installer-defines.iss"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#APP_NAME}
AppVersion={#APP_VERSION}
AppPublisher={#APP_NAME}
AppPublisherURL={#APP_URL}
AppSupportURL={#APP_URL}
AppUpdatesURL={#APP_URL}
DefaultDirName={localappdata}\{#APP_NAME}
DefaultGroupName={#APP_NAME}
PrivilegesRequired=lowest
WizardStyle=modern
OutputBaseFilename={#APP_NAME}-{#APP_VERSION}-Source-Setup
Compression=lzma2/max
SolidCompression=yes
AllowNoIcons=yes

[Files]
Source: "{#PackageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Start"; Filename: "{app}\start.bat"; WorkingDir: "{app}"
Name: "{group}\Configure"; Filename: "{app}\配置API.bat"; WorkingDir: "{app}"
Name: "{group}\Stop owned services"; Filename: "{app}\Stop-All.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\install.bat"; Description: "Install native dependencies (network and build tools required)"; Flags: postinstall nowait skipifsilent shellexec
; Instance data is outside {app}; no recursive user-data deletion on uninstall.
