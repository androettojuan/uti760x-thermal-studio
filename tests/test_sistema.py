"""Tests de la deteccion de WiFi sin IP (la camara a veces no da direccion)."""
from thermal_studio.ui.sistema import _wifi_sin_ip_en_ipconfig

ETHERNET = "Adaptador de Ethernet Ethernet:\r\n\r\n   Dirección IPv4. . . : 192.168.6.18\r\n\r\n"


def test_wifi_con_ip_169_254():
    salida = ETHERNET + ("Adaptador de LAN inalámbrica Wi-Fi:\r\n\r\n"
                         "   Dirección IPv4 de configuración automática: 169.254.81.250\r\n"
                         "   Puerta de enlace predeterminada . . . . . : 192.168.32.1\r\n")
    assert _wifi_sin_ip_en_ipconfig(salida)


def test_wifi_con_ip_de_la_camara():
    salida = ETHERNET + ("Adaptador de LAN inalámbrica Wi-Fi:\r\n\r\n"
                         "   Dirección IPv4. . . . . . . . . . . . . . : 192.168.32.91\r\n")
    assert not _wifi_sin_ip_en_ipconfig(salida)


def test_wifi_desconectado_o_en_ingles():
    assert not _wifi_sin_ip_en_ipconfig(
        "Adaptador de LAN inalámbrica Wi-Fi:\r\n\r\n   Estado de los medios. . : medios "
        "desconectados\r\n")
    assert _wifi_sin_ip_en_ipconfig(
        "Wireless LAN adapter Wi-Fi:\r\n\r\n   Autoconfiguration IPv4 Address. . : 169.254.1.2\r\n")
