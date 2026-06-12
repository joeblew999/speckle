#!/usr/bin/env nu
# Daemon status + health checks.

pitchfork list
print ""
print "Health checks:"

def health [name: string, c: closure] {
    let ok = ((try { do $c | complete | get exit_code } catch { 1 }) == 0)
    let mark = (if $ok { "✓" } else { "✗" })
    print $"  ($name | fill --width 10)($mark)"
}

health "Postgres" { pg_isready -U speckle }
health "Redis" { redis-cli ping }
health "MinIO" { curl -sf http://127.0.0.1:9000/minio/health/live }
health "API" { curl -sf http://127.0.0.1:3000/graphql }
health "Frontend" { curl -sf -o /dev/null http://127.0.0.1:8080 }
