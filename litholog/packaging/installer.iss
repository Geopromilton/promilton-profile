; Inno Setup script for LithoLog Studio (Windows installer).
;   iscc packaging\installer.iss      (after: pyinstaller packaging\litholog_studio.spec)
#define AppName "LithoLog Studio"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{8C4E1D52-5A0B-4E43-9B7C-4D2A1F0E7B11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=LithoLog (open source)
AppPublisherURL=https://github.com/Geopromilton/litholog
AppSupportURL=https://github.com/Geopromilton/litholog/issues
DefaultDirName={autopf}\LithoLog Studio
DefaultGroupName=LithoLog Studio
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=LithoLogStudio-Setup-{#AppVersion}
SetupIconFile=litholog.ico
UninstallDisplayIcon={app}\LithoLogStudio.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\LithoLogStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LithoLog Studio"; Filename: "{app}\LithoLogStudio.exe"
Name: "{group}\Uninstall LithoLog Studio"; Filename: "{uninstallexe}"
Name: "{autodesktop}\LithoLog Studio"; Filename: "{app}\LithoLogStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LithoLogStudio.exe"; Description: "Launch LithoLog Studio"; Flags: nowait postinstall skipifsilent
