# The live root account is confined to the disposable ISO session.
if [[ $(tty) == /dev/tty1 ]]; then
    /usr/local/bin/hafthios-session
fi
