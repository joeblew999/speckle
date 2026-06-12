#!/usr/bin/env nu
# First-time Speckle server setup: clone, install, build, init infra.

print "══════════════════════════════════════════════════"
print "  Speckle Server — First Time Setup"
print "══════════════════════════════════════════════════"

let env_file = $"($env.SPECKLE_ROOT)/.env"
if not ($env_file | path exists) {
    print "Creating .env from .env.example..."
    cp $"($env.SPECKLE_ROOT)/.env.example" $env_file
}

mkdir $env.SPECKLE_LOGS

if ($env.SPECKLE_SRC | path exists) {
    print $"Already cloned. Checking out ($env.SPECKLE_VERSION)..."
    cd $env.SPECKLE_SRC
    git fetch --tags
    git checkout $env.SPECKLE_VERSION
} else {
    git clone --branch $env.SPECKLE_VERSION --depth 1 https://github.com/specklesystems/speckle-server.git $env.SPECKLE_SRC
}
print $"Speckle server @ ($env.SPECKLE_VERSION)"

cd $env.SPECKLE_SRC
corepack enable
yarn | tee { save --force $"($env.SPECKLE_LOGS)/install.log" } | ignore
yarn build:public | tee { save --append $"($env.SPECKLE_LOGS)/install.log" } | ignore

print ""
print "  Building for production..."
with-env { NODE_ENV: "production" } {
    yarn build | tee { save --force $"($env.SPECKLE_LOGS)/build.log" } | ignore
}

mkdir $env.SPECKLE_DATA
mkdir $env.MINIO_DATA
if not ($env.PGDATA | path exists) {
    print "Initializing Postgres..."
    initdb -D $env.PGDATA --username=speckle --auth=trust
    "port = 5432\n" | save --append $"($env.PGDATA)/postgresql.conf"
}

print ""
print "Setup complete! Run: mise run start"
