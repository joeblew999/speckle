#!/usr/bin/env nu
# Start the whole stack via pitchfork (infra + API + frontend + admin).

mkdir $env.SPECKLE_LOGS

if not ($"($env.SPECKLE_ROOT)/.env" | path exists) {
    print "ERROR: .env not found. Run 'mise run setup' first."
    exit 1
}

let built = (
    ($"($env.SPECKLE_SRC)/packages/server/dist/index.js" | path exists) or
    ($"($env.SPECKLE_SRC)/packages/server/bin/www" | path exists)
)
if not $built {
    print "ERROR: Server not built. Run 'mise run setup' first."
    exit 1
}

pitchfork start -l
mise run admin:ensure

print ""
print "══════════════════════════════════════════════════"
print "  Speckle Server running (pitchfork)"
print "  Web UI:    http://127.0.0.1:8080"
print "  API:       http://127.0.0.1:3000"
print "  GraphQL:   http://127.0.0.1:3000/graphql"
print "  MinIO:     http://127.0.0.1:9001"
print "  Status:    mise run status"
print "  Logs:      pitchfork logs -t"
print "  Stop:      mise run stop"
print "══════════════════════════════════════════════════"
