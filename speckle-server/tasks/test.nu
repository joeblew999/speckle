#!/usr/bin/env nu
# Verify the Speckle stack works end-to-end. Exits non-zero on any failure.

# True if the external command exits 0 (missing/error → false).
def succeeds [c: closure]: nothing -> bool {
    (try { do $c | complete | get exit_code } catch { 1 }) == 0
}

# First regex capture group from a string, or "" if none.
def capture [text: string, re: string]: nothing -> string {
    let m = ($text | parse --regex $re)
    if ($m | is-empty) { "" } else { $m | get 0 | values | get 0 }
}

mut results = []

print "Infra:"
$results = ($results | append {name: "Postgres", ok: (succeeds { pg_ctl -D $env.PGDATA status })})
$results = ($results | append {name: "Redis", ok: (succeeds { redis-cli ping })})
$results = ($results | append {name: "MinIO", ok: (succeeds { curl -sf http://127.0.0.1:9000/minio/health/live })})

print ""
print "Services:"
let api = (try { curl -sf -H "Content-Type: application/json" -d '{"query":"{ serverInfo { version } }"}' http://127.0.0.1:3000/graphql } catch { "" })
$results = ($results | append {name: "API server", ok: ($api | str contains "version")})
$results = ($results | append {name: "Frontend", ok: (succeeds { curl -sf -o /dev/null http://127.0.0.1:8080 })})

print ""
print "Auth:"
let login_body = $"{\"email\":\"($env.SPECKLE_ADMIN_EMAIL)\",\"password\":\"($env.SPECKLE_ADMIN_PASSWORD)\"}"
let login = (try { curl -s -H "Content-Type: application/json" -d $login_body "http://127.0.0.1:3000/auth/local/login?challenge=test" } catch { "" })
let code = (capture $login 'access_code=(?P<c>[^&"]+)')

mut token = ""
if ($code | is-not-empty) {
    let tok_body = $"{\"appId\":\"spklwebapp\",\"appSecret\":\"spklwebapp\",\"accessCode\":\"($code)\",\"challenge\":\"test\"}"
    let tr = (try { curl -sf -H "Content-Type: application/json" -d $tok_body http://127.0.0.1:3000/auth/token } catch { "" })
    $token = (capture $tr '"token":"(?P<t>[^"]+)"')
}
$results = ($results | append {name: "Login", ok: ($token | is-not-empty)})

if ($token | is-not-empty) {
    let user = (try { curl -sf -H "Content-Type: application/json" -H $"Authorization: Bearer ($token)" -d '{"query":"{ activeUser { name role } }"}' http://127.0.0.1:3000/graphql } catch { "" })
    $results = ($results | append {name: "Admin role", ok: ($user | str contains "server:admin")})
}

for r in $results {
    if $r.ok { print $"  ($r.name)" } else { print $"  FAIL: ($r.name)" }
}

let passed = ($results | where ok | length)
let failed = ($results | where ok == false | length)
print ""
print "══════════════════════════════════════════════════"
if $failed == 0 {
    print $"  All ($passed) tests passed"
} else {
    print $"  ($passed) passed, ($failed) failed"
}
print "══════════════════════════════════════════════════"
exit (if $failed == 0 { 0 } else { 1 })
