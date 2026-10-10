[Setup]
AppId=Guangzhu.Desktop
AppName=光筑
AppVersion=0.2.0
AppPublisher=验形工坊
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\guangzhu
DisableProgramGroupPage=yes
DisableDirPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Output}
OutputBaseFilename=guangzhu-setup
SetupIconFile={#Stage}\desktop\web\assets\guangzhu.ico
UninstallDisplayIcon={app}\光筑.exe
UninstallDisplayName=光筑
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
ShowLanguageDialog=no
[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
[InstallDelete]
; 升级时先清掉上一版的程序和插件，避免旧文件残留（例如两份插件快照）；用户的设计记录、缓存和 key 不在这些目录里。
Type: filesandordirs; Name: "{app}\plugins"
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\desktop"
Type: filesandordirs; Name: "{app}\data\demo"
Type: filesandordirs; Name: "{app}\data\roofs"
Type: filesandordirs; Name: "{app}\data\catalog"
Type: filesandordirs; Name: "{app}\data\showcase"
[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userdesktop}\光筑"; Filename: "{app}\光筑.exe"; WorkingDir: "{app}"; AppUserModelID: "Guangzhu.Desktop"
Name: "{userprograms}\光筑"; Filename: "{app}\光筑.exe"; WorkingDir: "{app}"; AppUserModelID: "Guangzhu.Desktop"
[Run]
Filename: "{app}\光筑.exe"; Description: "打开光筑"; Flags: postinstall nowait skipifsilent
[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\desktop"
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\data\cache"
[Code]
function GetFileAttributes(Path: String): LongWord;
  external 'GetFileAttributesW@kernel32.dll stdcall';
function RealTree(Path: String): Boolean;
var
  Entry: TFindRec;
begin
  Result := False;
  if (GetFileAttributes(Path) and $400) <> 0 then Exit;
  if not FindFirst(AddBackslash(Path) + '*', Entry) then begin
    Result := not DirExists(Path);
    Exit;
  end;
  Result := True;
  try
    repeat
      if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
        if (Entry.Attributes and $400) <> 0 then Result := False;
        if ((Entry.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0) and Result then
          Result := RealTree(AddBackslash(Path) + Entry.Name);
      end;
    until (not Result) or (not FindNext(Entry));
  finally
    FindClose(Entry);
  end;
end;
procedure DeleteOwned(Path: String);
var
  Parent, Previous: String;
begin
  Parent := Path;
  repeat
    if (GetFileAttributes(Parent) and $400) <> 0 then Exit;
    Previous := Parent;
    Parent := ExtractFileDir(Parent);
  until (Parent = Previous) or (Parent = '');
  if DirExists(Path) and RealTree(Path) then DelTree(Path, True, True, True);
end;
{ 装完立刻配置光筑自带的 AGH、设计工具和插件，打开软件时就不用再配置。 }
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then Exit;
  WizardForm.StatusLabel.Caption := '正在配置光筑自带的 AGH 和设计工具，大约需要 1 分钟……';
  WizardForm.ProgressGauge.Style := npbstMarquee;
  try
    if not Exec(ExpandConstant('{app}\runtime\python\python.exe'), '-X utf8 -B -m guangzhu.setup install',
        ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      SuppressibleMsgBox('光筑已经装好，但自动配置这一步没有完成。打开光筑时会自动再试一次。' + #13#10 +
        '如果仍然不行，请把这个文件发给我们：' + #13#10 + ExpandConstant('{localappdata}\guangzhu\setup\actions.jsonl'),
        mbInformation, MB_OK, IDOK);
  finally
    WizardForm.ProgressGauge.Style := npbstNormal;
  end;
end;
procedure CurUninstallStepChanged(Step: TUninstallStep);
begin
  if (Step = usUninstall) and not UninstallSilent then
    if MsgBox('要不要同时删除光筑的设计记录、项目、你画的屋顶和光筑自带 AGH 的数据（包括保存的 key）？选"否"会保留。', mbConfirmation,
      MB_YESNO or MB_DEFBUTTON2) = IDYES then begin
      DeleteOwned(ExpandConstant('{app}\projects'));
      DeleteOwned(ExpandConstant('{app}\runs'));
      DeleteOwned(ExpandConstant('{app}\data\my-roofs'));
      DeleteOwned(ExpandConstant('{localappdata}\guangzhu\agh'));
    end;
end;
