; Installateur Windows de Feuillet (Inno Setup 6.3 ou plus récent).
; Compilation : ISCC.exe installer\feuillet.iss  (après installer\build.ps1)
;
; Feuillet ne prend en charge que Windows 10 et Windows 11, en 64 bits.
; Deux contrôles :
;   1. MinVersion : Inno Setup refuse l'installation sous Windows 10 build 10240 ;
;      son message d'erreur est remplacé par le nôtre (section [Messages]).
;   2. InitializeSetup : contrôle explicite du numéro de build, message bilingue.
; L'application refait le même contrôle à chaque lancement.

#define AppName "Feuillet"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppExe "Feuillet.exe"

[Setup]
AppId={{3A893DE2-E5DE-4C57-AD28-1885F082B72A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Feuillet
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\dist\installer
OutputBaseFilename=Feuillet-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.10240
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\src\feuillet\resources\feuillet.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
french.WinVersionTooLowError=Feuillet nécessite Windows 10 ou Windows 11 (64 bits). Votre version de Windows n'est pas prise en charge.
english.WinVersionTooLowError=Feuillet requires Windows 10 or Windows 11 (64-bit). Your version of Windows is not supported.

[CustomMessages]
french.UnsupportedWindows=Feuillet nécessite Windows 10 ou Windows 11 (64 bits).%n%nVersion détectée : %1.%n%nL'installation va s'arrêter.
english.UnsupportedWindows=Feuillet requires Windows 10 or Windows 11 (64-bit).%n%nDetected version: %1.%n%nSetup will now exit.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Dossier produit par PyInstaller (mode « onedir »), Tesseract inclus.
Source: "..\dist\Feuillet\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  Version: TWindowsVersion;
  Detected: String;
begin
  GetWindowsVersionEx(Version);
  Detected := Format('%d.%d build %d', [Version.Major, Version.Minor, Version.Build]);
  // Windows 10 et 11 annoncent tous deux 10.0 ; Windows 11 commence au build 22000.
  if (Version.Major < 10) or ((Version.Major = 10) and (Version.Build < 10240)) or (not IsWin64) then
  begin
    SuppressibleMsgBox(FmtMessage(CustomMessage('UnsupportedWindows'), [Detected]),
      mbCriticalError, MB_OK, IDOK);
    Result := False;
  end
  else
    Result := True;
end;
