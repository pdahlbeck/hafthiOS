if [[ -f "$HOME/.config/hafthios/environment" ]]; then
    source "$HOME/.config/hafthios/environment"
fi
# Autostart only on the live welcome TTY, never inside a terminal window.
if [[ $(tty) == /dev/tty1 && -z ${HAFTHIOS_SESSION_STARTED:-} ]]; then
    export HAFTHIOS_SESSION_STARTED=1
    /usr/local/bin/hafthios-session
fi
