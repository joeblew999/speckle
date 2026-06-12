#!/usr/bin/env nu
# Build all Speckle packages for production.

mkdir $env.SPECKLE_LOGS
cd $env.SPECKLE_SRC
print "Building Speckle server (production)..."
with-env { NODE_ENV: "production" } {
    yarn build | tee { save --force $"($env.SPECKLE_LOGS)/build.log" } | ignore
}
print ""
print "Build complete."
