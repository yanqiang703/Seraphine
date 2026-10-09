[Setup]
AppName=Seraphine
AppVersion=2.0
AppPublisher=Seraphine
DefaultDirName={autopf}\Seraphine
DefaultGroupName=Seraphine
UninstallDisplayIcon={app}\Seraphine.exe
UninstallDisplayName=Seraphine
OutputDir=installer_output
OutputBaseFilename=SeraphineSetup_2.0
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
DisableProgramGroupPage=yes
PrivilegesRequired=admin

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenu"; Description: "创建开始菜单快捷方式"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\Seraphine\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Seraphine"; Filename: "{app}\Seraphine.exe"; IconFilename: "{app}\Seraphine.exe"; Tasks: startmenu
Name: "{group}\卸载 Seraphine"; Filename: "{uninstallexe}"; Tasks: startmenu
Name: "{commondesktop}\Seraphine"; Filename: "{app}\Seraphine.exe"; IconFilename: "{app}\Seraphine.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Seraphine.exe"; Description: "立即启动 Seraphine"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    begin
      // 安装完成后额外提示
    end;
end;
