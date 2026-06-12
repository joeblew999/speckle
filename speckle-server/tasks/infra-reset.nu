#!/usr/bin/env nu
# Stop everything and wipe all Speckle data. (Confirmation is in mise.)

do -i { pitchfork stop --all }
print "Wiping data..."
rm -rf $env.SPECKLE_DATA
print "Done. Run 'mise run setup' to start fresh."
