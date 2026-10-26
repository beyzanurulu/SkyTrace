#!/bin/sh
# Start the bundled Ollama server, wait until it answers, then run the command.
set -e
ollama serve >/tmp/ollama.log 2>&1 &
i=0
until ollama list >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -gt 60 ]; then
        echo "ollama did not start:" >&2
        cat /tmp/ollama.log >&2
        exit 1
    fi
    sleep 1
done
exec "$@"
