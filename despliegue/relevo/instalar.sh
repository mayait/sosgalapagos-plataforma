#!/bin/sh
# SOS Galápagos · instala el relevo de IERSE en una máquina que esté en Ecuador (Mac o Linux).
# © 2026 USFQ · SOS Galápagos · Julián Maya <jamaya@usfq.edu.ec>. Licencia Apache 2.0 (ver LICENSE y NOTICE): puede reutilizarse dando crédito.
#
# Uso:   sh instalar.sh            (pide la llave)
#        RELEVO_LLAVE=… sh instalar.sh
# Deja el programa en ~/.sosgalapagos-relevo, la llave en ~/.config/sosgalapagos/relevo.env (solo
# la puede leer este usuario) y lo programa cada 5 minutos. No necesita nada más que Python 3.
# Si en esta máquina corría el puente anterior (org.sosgalapagos.clima-puente), lo detiene: no lo borra.
set -eu
AQUI="$(cd "$(dirname "$0")" && pwd)"
DESTINO="$HOME/.sosgalapagos-relevo"
CONFIG="$HOME/.config/sosgalapagos/relevo.env"
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { echo "Hace falta Python 3 (en la Mac: xcode-select --install)"; exit 1; }

mkdir -p "$DESTINO" "$(dirname "$CONFIG")"
cp "$AQUI/relevo.py" "$AQUI/ca-intermedios.pem" "$DESTINO/"
if [ ! -f "$CONFIG" ] || [ -n "${RELEVO_LLAVE:-}" ]; then
  if [ -z "${RELEVO_LLAVE:-}" ]; then
    printf "Llave del relevo (CLIMA_RELEVO_LLAVE del servidor): "; stty -echo 2>/dev/null || true; read -r RELEVO_LLAVE; stty echo 2>/dev/null || true; echo
  fi
  umask 077
  printf 'RELEVO_SERVIDOR=%s\nRELEVO_LLAVE=%s\n' "${RELEVO_SERVIDOR:-https://sosgalapagos.org}" "$RELEVO_LLAVE" > "$CONFIG"
fi
chmod 600 "$CONFIG"

echo "Probando una vuelta…"
"$PY" "$DESTINO/relevo.py" || { echo "La prueba falló: revisa la llave y que esta máquina alcance a IERSE."; exit 1; }

if [ "$(uname)" = "Darwin" ]; then
  AGENTE="$HOME/Library/LaunchAgents/org.sosgalapagos.relevo.plist"
  mkdir -p "$(dirname "$AGENTE")"
  cat > "$AGENTE" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>org.sosgalapagos.relevo</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DESTINO/relevo.py</string></array>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DESTINO/relevo.log</string>
  <key>StandardErrorPath</key><string>$DESTINO/relevo.log</string>
</dict></plist>
PLIST
  launchctl bootout "gui/$(id -u)/org.sosgalapagos.relevo" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTE"
  # El puente anterior (enviaba por SSH a la base SQLite): se detiene y su archivo se guarda, no se borra.
  VIEJO="$HOME/Library/LaunchAgents/org.sosgalapagos.clima-puente.plist"
  if [ -f "$VIEJO" ]; then
    launchctl bootout "gui/$(id -u)/org.sosgalapagos.clima-puente" 2>/dev/null || true
    mv "$VIEJO" "$DESTINO/org.sosgalapagos.clima-puente.plist.archivado"
    echo "El puente anterior quedó detenido (su archivo está en $DESTINO)."
  fi
  echo "Listo: corre cada 5 minutos. Registro: $DESTINO/relevo.log"
else
  LINEA="*/5 * * * * $PY $DESTINO/relevo.py >> $DESTINO/relevo.log 2>&1"
  ( crontab -l 2>/dev/null | grep -v "sosgalapagos-relevo/relevo.py" ; echo "$LINEA" ) | crontab -
  echo "Listo: programado en cron cada 5 minutos. Registro: $DESTINO/relevo.log"
fi
