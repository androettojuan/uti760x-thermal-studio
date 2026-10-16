; Instalador de Windows (Inno Setup 6). Empaqueta dist\ThermalStudio\ (salida de PyInstaller).
;   iscc /DVersion=0.4.0 packaging\instalador.iss
; Se instala por usuario, sin pedir permisos de administrador.

#ifndef Version
  #define Version "0.4.0"
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
; Preguntar el idioma al empezar, con el del sistema elegido de entrada
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

; El idioma que se elige al instalar queda como idioma del programa (seccion
; [Registry]); los codigos coinciden con los de thermal_studio/i18n.py.
[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
es.AccesoEscritorio=Crear un acceso directo en el escritorio
en.AccesoEscritorio=Create a desktop shortcut
pt.AccesoEscritorio=Criar um atalho na área de trabalho
es.Accesos=Accesos directos:
en.Accesos=Shortcuts:
pt.Accesos=Atalhos:
es.Desinstalar=Desinstalar Thermal Studio
en.Desinstalar=Uninstall Thermal Studio
pt.Desinstalar=Desinstalar o Thermal Studio
es.Abrir=Abrir Thermal Studio
en.Abrir=Open Thermal Studio
pt.Abrir=Abrir o Thermal Studio

[Tasks]
Name: "escritorio"; Description: "{cm:AccesoEscritorio}"; GroupDescription: "{cm:Accesos}"

[Files]
Source: "..\dist\ThermalStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Licencia del programa: se muestra en Ayuda > Acerca de
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Thermal Studio"; Filename: "{app}\ThermalStudio.exe"
Name: "{group}\{cm:Desinstalar}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Thermal Studio"; Filename: "{app}\ThermalStudio.exe"; Tasks: escritorio

[Run]
Filename: "{app}\ThermalStudio.exe"; Description: "{cm:Abrir}"; Flags: nowait postinstall skipifsilent

[Registry]
; Idioma del programa = el del instalador (se puede cambiar en Ver > Idioma)
Root: HKCU; Subkey: "Software\ThermalStudio\ThermalStudio"; ValueType: string; ValueName: "idioma"; ValueData: "{language}"
