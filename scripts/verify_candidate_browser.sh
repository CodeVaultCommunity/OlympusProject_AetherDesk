#!/usr/bin/env bash
set -euo pipefail

# Run only inside a disposable Playwright image with /src and /candidate read-only.
test -f /candidate/web/dist/index.html
mkdir -p /work/web/tests
cp /src/web/package.json /src/web/pnpm-lock.yaml /src/web/pnpm-workspace.yaml \
  /src/web/playwright-candidate.config.ts /src/web/vite.config.ts /work/web/
cp -r /src/web/tests/candidate /work/web/tests/
mkdir -p /work/web/scripts
cp /src/web/scripts/probe_native_zoom.mjs /src/web/scripts/probe_tab_menu.mjs \
  /src/web/scripts/probe_screen_reader.mjs /work/web/scripts/
cd /work/web
if ! command -v pnpm >/dev/null 2>&1; then npm install --silent --global pnpm@11.25.0; fi
if [[ ! -d node_modules ]]; then pnpm install --frozen-lockfile; fi
pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort --outDir /candidate/web/dist >/tmp/aetherdesk-preview.log 2>&1 &
preview_pid=$!
trap 'kill "$preview_pid" 2>/dev/null || true' EXIT
for attempt in $(seq 1 100); do
  if curl --silent --fail http://127.0.0.1:4173/ >/dev/null; then break; fi
  if ! kill -0 "$preview_pid" 2>/dev/null; then cat /tmp/aetherdesk-preview.log; exit 1; fi
  sleep 0.2
done
curl --silent --fail http://127.0.0.1:4173/ >/dev/null
if [[ "${1:-}" == '--native-probe' ]]; then
  shift
  if ! command -v xdotool >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends xdotool >/tmp/aetherdesk-apt.log
  fi
  PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    xvfb-run -a -s '-screen 0 1920x1080x24' node scripts/probe_native_zoom.mjs "$@"
elif [[ "${1:-}" == '--tab-menu-probe' ]]; then
  shift
  PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    xvfb-run -a -s '-screen 0 1920x1080x24' node scripts/probe_tab_menu.mjs "$@"
elif [[ "${1:-}" == '--screen-reader-probe' ]]; then
  mkdir -p /tmp/runtime-orca
  chmod 700 /tmp/runtime-orca
  export XDG_RUNTIME_DIR=/tmp/runtime-orca
  PLAYWRIGHT_BROWSERS_PATH=/ms-playwright dbus-run-session -- \
    xvfb-run -a -s '-screen 0 1920x1080x24' bash -c '
      orca --debug-file=/evidence/w006-orca-firefox.log \
        >/evidence/w006-orca-stdout.log 2>&1 &
      reader_pid=$!
      sleep 3
      node scripts/probe_screen_reader.mjs
      result=$?
      kill "$reader_pid" 2>/dev/null || true
      wait "$reader_pid" 2>/dev/null || true
      exit "$result"
    '
else
  AETHERDESK_E2E_BASE_URL=http://127.0.0.1:4173 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright CI=true \
    pnpm exec playwright test --config playwright-candidate.config.ts "$@"
fi
