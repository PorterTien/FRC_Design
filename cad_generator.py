import math

class ReactorCAD:
    """
    Parametric CAD generator for the optimized DFD configuration.
    """

    def generate_model(self, specs: dict, filename="optimized_dfd.step"):
        try:
            import cadquery as cq
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "cadquery is not installed. Install cadquery/OCP or run without CAD."
            ) from exc

        r = specs.get("r", 1.0)
        L = specs.get("L", 6.0)
        shield_thickness = specs.get("shield_thickness", 0.2)
        radiator_area = specs.get("radiator_area", 50.0)
        propellant_mass = specs.get("propellant_mass", 1000.0)

        vessel = (
            cq.Workplane("XY")
            .cylinder(L, r, centered=(True, True, True))
            .faces(">Z")
            .workplane()
            .hole(r * 0.7)
        )

        # Magnets as rings around the vessel
        magnet_thickness = 0.1 + 0.01 * specs.get("B", 10.0)
        magnets = cq.Workplane("XY")
        for z in [-L * 0.3, 0.0, L * 0.3]:
            ring = (
                cq.Workplane("XY")
                .workplane(offset=z)
                .circle(r * 1.05 + magnet_thickness)
                .circle(r * 1.05)
                .extrude(magnet_thickness)
            )
            magnets = magnets.union(ring)

        # Shielding shell
        shield = (
            cq.Workplane("XY")
            .cylinder(L * 1.02, r + shield_thickness)
            .cut(cq.Workplane("XY").cylinder(L * 1.02, r * 1.05))
        )

        # Radiator wings
        wing_width = 2 * r
        wing_length = max(radiator_area / max(wing_width, 1e-6), r)
        wing_thickness = 0.05
        radiator = (
            cq.Workplane("YZ")
            .box(wing_thickness, wing_width, wing_length)
            .translate((r + shield_thickness + wing_thickness, 0, 0))
        )
        radiator2 = radiator.mirror("YZ")

        # Propellant tanks (spherical)
        rho_prop = 70.0
        tank_volume = propellant_mass / rho_prop
        tank_radius = (3 * tank_volume / (4 * math.pi)) ** (1 / 3)
        tank1 = cq.Workplane("XY").sphere(tank_radius).translate((0, 0, L * 0.8))
        tank2 = cq.Workplane("XY").sphere(tank_radius).translate((0, 0, -L * 0.8))

        # Magnetic nozzle cone (lofted profile for cadquery compatibility)
        nozzle = (
            cq.Workplane("XY")
            .circle(r)
            .workplane(offset=L * 0.4)
            .circle(r * 2.5)
            .loft(ruled=True)
            .translate((0, 0, -L * 0.7))
        )

        assembly = vessel.union(magnets).union(shield).union(radiator).union(radiator2)
        assembly = assembly.union(tank1).union(tank2).union(nozzle)

        cq.exporters.export(assembly, filename)
        return filename

