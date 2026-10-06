#!/bin/sh
# Render every printable part to ../stl  (needs OpenSCAD >= 2021.01)
# usage: sh export.sh            (from the scad/ folder)
cd "$(dirname "$0")"
mkdir -p ../stl
for p in holder_bottom holder_top lid_bottom lid_top \
         holder_bottom_a holder_bottom_b holder_top_a holder_top_b \
         lid_bottom_a lid_bottom_b lid_top_a lid_top_b; do
  echo "rendering $p"
  openscad -q -o "../stl/$p.stl" -D "part=\"$p\"" cellholder.scad &
done
wait
