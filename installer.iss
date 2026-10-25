[Setup]
AppName=Seraphine
AppVersion=2.5
AppPublisher=Seraphine
DefaultDirName={autopf}\Seraphine
DefaultGroupName=Seraphine
UninstallDisplayIcon={app}\Seraphine.exe
UninstallDisplayName=Seraphine
OutputDir=installer_output
OutputBaseFilename=SeraphineSetup_2.5
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[Files]
Source: "dist\Seraphine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Seraphine"; Filename: "{app}\Seraphine.exe"
Name: "{group}\卸载 Seraphine"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Seraphine"; Filename: "{app}\Seraphine.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Seraphine.exe"; Description: "启动 Seraphine"; Flags: nowait postinstall skipifsilent
