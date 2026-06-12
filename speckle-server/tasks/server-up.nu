#!/usr/bin/env nu
# Dev mode: server + frontend (yarn dev:minimal).

mkdir $env.SPECKLE_LOGS
cd $env.SPECKLE_SRC
yarn dev:minimal | tee { save --force $"($env.SPECKLE_LOGS)/server-dev.log" } | ignore
