; Instalador de Windows (Inno Setup 6). Empaqueta dist\ThermalStudio\ (salida de PyInstaller).
;   iscc /DVersion=0.1.3 packaging\instalador.iss
; Se instala por usuario, sin pedir permisos de administrador.

#ifndef Version
  #define Version "0.1.3"
#endif

[Setup]
AppId={{6B0E4C1E-3F2A-4D7B-9C61-7A2B5D8E1F40}
AppName=Thermal Studio
AppVersion={#Version}
AppVerName=Thermal Studio {#Version}
AppPublisher=Juan Manuel Androetto
AppPublisherURL=https://github.com/androettojuan/uti760x-thermal-studio
DefaultDirName={autopf}\Thermal Studio
DefaultGroupName=Thermal Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=ThermalStudio-{#Version}-instalador
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\ThermalStudio.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\ThermalStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Thermal Studio"; Filename: "{app}\ThermalStudio.exe"
Name: "{group}\Desinstalar Thermal Studio"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Thermal Studio"; Filename: "{app}\ThermalStudio.exe"; Tasks: escritorio

[Run]
Filename: "{app}\ThermalStudio.exe"; Description: "Abrir Thermal Studio"; Flags: nowait postinstall skipifsilent
