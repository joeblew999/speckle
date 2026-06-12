#!/usr/bin/env nu
# Create the admin account if it doesn't exist yet (idempotent).

let body = $"{\"email\":\"($env.SPECKLE_ADMIN_EMAIL)\",\"password\":\"($env.SPECKLE_ADMIN_PASSWORD)\",\"name\":\"($env.SPECKLE_ADMIN_NAME)\"}"

let resp = (
    try {
        curl -sf -H "Content-Type: application/json" -d $body "http://127.0.0.1:3000/auth/local/register?challenge=auto-setup"
    } catch { "" }
)

if ($resp | str contains "access_code") {
    print $"  Admin account created: ($env.SPECKLE_ADMIN_EMAIL)"
} else {
    print $"  Admin account already exists: ($env.SPECKLE_ADMIN_EMAIL)"
}
