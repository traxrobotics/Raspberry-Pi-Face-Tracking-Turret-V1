# Printed parts

Three parts make the pan and tilt stack. Everything is small, flat-ish and
prints without a heated chamber.

| Part | Carries | Files |
|---|---|---|
| `base` | the pan servo | `base.3mf`, `base.step` |
| `turret-arm` | rides the pan servo, holds the tilt servo | `turret-arm.3mf`, `turret-arm.step` |
| `camera-attachment` | the ArduCAM Mini 2MP Plus on the tilt servo | `camera-attachment.3mf`, `camera-attachment.step` |

You do not need these. The README lists "any SG90 bracket works", and that is
still true. These are here if you would rather print the exact thing in the
photos than buy a bracket.

## The base has no floor

This is deliberate, and it is the one thing worth knowing before you print.

Leaving the bottom open means you can reach the servo and the wiring while you
are working, instead of assembling blind through a hole. It also means the
turret bolts straight onto another robot's deck and uses that as its floor,
rather than carrying a redundant bottom plate of its own.

If you want it to stand on a desk by itself, print any flat plate wider than
the base and screw it on, or weigh the base down. It is not tippy, but it is
not bolted to anything either.

## Which file to use

**`.3mf` to print.** Load it straight into your slicer. These carry their units
(millimetres), so nothing arrives at 25× scale the way a bare STL sometimes does.

**`.step` to change.** STEP is solid geometry rather than a mesh, so you can open
it in Fusion, FreeCAD, Onshape or SolidWorks and actually edit it — widen the
servo pocket, move a screw hole, fit the base to your own robot. Editing a 3MF
means pushing triangles around, which you do not want to do.

There are no STL files here on purpose. 3MF does everything STL does and carries
units as well, and every current slicer reads it.

## Print settings

Standard PLA settings are fine:

| Setting | Value |
|---|---|
| Material | PLA |
| Layer height | 0.2 mm |
| Infill | 20% |
| Supports | where your slicer asks for them |

**Use PETG for the support interface if you have a multi-material setup.** PETG
does not bond well to PLA, so PETG supports snap off a PLA part cleanly and
leave a much better surface than PLA-on-PLA, which fuses and tears. This needs
an AMS, an MMU or a manual filament swap at the right layer — if you have a
single-extruder printer, just use normal PLA supports and clean them up.

Nothing here is under real load. The servos are the weak point long before the
plastic is, so there is no reason to reach for a tougher material unless the
turret is living somewhere hot.

## Assembly

Two SG90 servos and the camera, in the order in the table above: pan servo into
the base, arm onto the pan servo's horn, tilt servo into the arm, camera
attachment onto the tilt servo's horn.

Wiring is in [`../docs/wiring.md`](../docs/wiring.md). Read the 3.3 V warning at
the top of that file before you plug the camera in.
