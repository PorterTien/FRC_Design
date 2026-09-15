import adsk.core
import adsk.fusion
import traceback
import json
import os

# References (DFD folder):
# - cohen2019jbis.pdf
# - 2108.01689v1.pdf
# - Degnan_NucFus_2013_nf.pdf
# - pnas.201921779.pdf
# - tesi.pdf


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox('No active Fusion 360 design. Open a design and re-run.')
            return

        units_mgr = design.unitsManager
        user_params = design.userParameters

        def add_param(name, expr, unit, comment):
            existing = user_params.itemByName(name)
            if existing:
                existing.expression = expr
                existing.comment = comment
                return existing
            return user_params.add(name, adsk.core.ValueInput.createByString(expr), unit, comment)

        def eval_expr(expr, unit='mm'):
            return units_mgr.evaluateExpression(expr, unit)

        def apply_overrides(overrides: dict):
            for name, expr in overrides.items():
                if user_params.itemByName(name):
                    add_param(name, expr, user_params.itemByName(name).unit, user_params.itemByName(name).comment)

        # ---- Physics-driven parameters (populated from physics_params.json) ----
        add_param('outer_length', '520 mm', 'mm', 'Overall housing length')
        add_param('outer_radius', '90 mm', 'mm', 'Outer housing radius')
        add_param('wall_thickness', '4 mm', 'mm', 'Housing wall thickness')
        add_param('liner_thickness', '2 mm', 'mm', 'Inner liner thickness')
        add_param('bore_radius', 'outer_radius - wall_thickness - liner_thickness', 'mm', 'Inner bore radius')

        add_param('chamber_start', '40 mm', 'mm', 'Z start of main chamber')
        add_param('chamber_length', '280 mm', 'mm', 'Main chamber length')

        add_param('nozzle_length', '120 mm', 'mm', 'Nozzle length')
        add_param('nozzle_throat_radius', '25 mm', 'mm', 'Nozzle throat radius')
        add_param('nozzle_exit_radius', '40 mm', 'mm', 'Nozzle exit radius')
        add_param('nozzle_wall_thickness', '3 mm', 'mm', 'Nozzle wall thickness')
        add_param('nozzle_throat_position', '0.35 * nozzle_length', 'mm', 'Throat location from nozzle start')

        add_param('flange_thickness', '10 mm', 'mm', 'Front mounting flange thickness')
        add_param('flange_outer_radius', 'outer_radius + 15 mm', 'mm', 'Front flange outer radius')
        add_param('bolt_circle_radius', 'outer_radius + 8 mm', 'mm', 'Bolt circle radius')
        add_param('bolt_hole_diameter', '6 mm', 'mm', 'Bolt hole diameter')
        add_param('bolt_hole_count', '8', '', 'Bolt hole count (unitless)')

        add_param('injector_length', '18 mm', 'mm', 'Injector manifold length')
        add_param('injector_port_diameter', '5 mm', 'mm', 'Injector port diameter')
        add_param('injector_port_count', '10', '', 'Injector port count (unitless)')
        add_param('injector_port_radius', 'bore_radius - 6 mm', 'mm', 'Injector port radius')

        add_param('coil_inner_radius', 'outer_radius + 5 mm', 'mm', 'Coil inner radius')
        add_param('coil_outer_radius', 'outer_radius + 20 mm', 'mm', 'Coil outer radius')
        add_param('coil_main_count', '10', '', 'Main coil count (unitless)')
        add_param('coil_main_spacing', '22 mm', 'mm', 'Main coil spacing')
        add_param('coil_main_thickness', '10 mm', 'mm', 'Main coil axial thickness')
        add_param('coil_main_start', 'chamber_start + 10 mm', 'mm', 'Main coil stack start Z')

        add_param('coil_nozzle_count', '4', '', 'Nozzle coil count (unitless)')
        add_param('coil_nozzle_spacing', '18 mm', 'mm', 'Nozzle coil spacing')
        add_param('coil_nozzle_thickness', '8 mm', 'mm', 'Nozzle coil axial thickness')
        add_param('coil_nozzle_start', 'chamber_start + chamber_length + 10 mm', 'mm', 'Nozzle coil stack start Z')

        # Field-shaping and mirror coils
        add_param('mirror_coil_count', '2', '', 'Mirror coil count (unitless)')
        add_param('mirror_coil_radius', 'coil_outer_radius + 10 mm', 'mm', 'Mirror coil radius')
        add_param('mirror_coil_thickness', '12 mm', 'mm', 'Mirror coil axial thickness')
        add_param('mirror_coil_start', 'chamber_start - 30 mm', 'mm', 'Mirror coil start Z')
        add_param('mirror_coil_spacing', 'chamber_length + 60 mm', 'mm', 'Mirror coil spacing')
        add_param('shaping_coil_count', '6', '', 'Field shaping coil count (unitless)')
        add_param('shaping_coil_radius', 'coil_outer_radius + 4 mm', 'mm', 'Shaping coil radius')
        add_param('shaping_coil_thickness', '6 mm', 'mm', 'Shaping coil axial thickness')
        add_param('shaping_coil_start', 'chamber_start + 10 mm', 'mm', 'Shaping coil start Z')
        add_param('shaping_coil_spacing', 'chamber_length / 6', 'mm', 'Shaping coil spacing')

        add_param('strut_count', '4', '', 'Support strut count (unitless)')
        add_param('strut_width', '12 mm', 'mm', 'Support strut width (tangential)')
        add_param('strut_thickness', '6 mm', 'mm', 'Support strut thickness (radial)')
        add_param('strut_start', 'chamber_start', 'mm', 'Support strut start Z')
        add_param('strut_length', 'chamber_length', 'mm', 'Support strut length')

        add_param('rear_cap_thickness', '8 mm', 'mm', 'Rear cap thickness')

        add_param('bay_length', '120 mm', 'mm', 'Electronics bay length (front)')
        add_param('bay_radius', 'outer_radius + 15 mm', 'mm', 'Electronics bay outer radius')
        add_param('bay_wall_thickness', '3 mm', 'mm', 'Electronics bay wall thickness')
        add_param('bay_cap_thickness', '6 mm', 'mm', 'Electronics bay front cap thickness')

        add_param('jacket_thickness', '6 mm', 'mm', 'Cooling jacket thickness')
        add_param('jacket_start', 'chamber_start - 10 mm', 'mm', 'Cooling jacket start Z')
        add_param('jacket_length', 'chamber_length + 20 mm', 'mm', 'Cooling jacket length')
        add_param('jacket_port_diameter', '10 mm', 'mm', 'Cooling jacket port diameter')
        add_param('jacket_port_length', '18 mm', 'mm', 'Cooling jacket port length')

        add_param('thermal_shield_thickness', '3 mm', 'mm', 'Thermal shield thickness')
        add_param('thermal_shield_clearance', '6 mm', 'mm', 'Thermal shield clearance')

        add_param('bobbin_thickness', '2 mm', 'mm', 'Coil bobbin thickness')
        add_param('bobbin_clearance', '1 mm', 'mm', 'Coil bobbin clearance')

        add_param('rail_count', '4', '', 'Frame rail count (unitless)')
        add_param('rail_width', '16 mm', 'mm', 'Frame rail width (tangential)')
        add_param('rail_thickness', '8 mm', 'mm', 'Frame rail thickness (radial)')
        add_param('rail_radius', 'outer_radius + jacket_thickness + 12 mm', 'mm', 'Frame rail center radius')
        add_param('rail_length', 'outer_length', 'mm', 'Frame rail length')

        add_param('foot_length', '50 mm', 'mm', 'Mount foot length')
        add_param('foot_width', '22 mm', 'mm', 'Mount foot width')
        add_param('foot_thickness', '8 mm', 'mm', 'Mount foot thickness')
        add_param('foot_offset_z', '40 mm', 'mm', 'Mount foot Z offset from front')

        add_param('nozzle_guard_length', '22 mm', 'mm', 'Nozzle guard length')
        add_param('nozzle_guard_outer_radius', 'outer_radius + 12 mm', 'mm', 'Nozzle guard outer radius')
        add_param('nozzle_guard_clearance', '4 mm', 'mm', 'Nozzle guard inner clearance')

        # Thruster tube taper
        add_param('tube_taper', '6 mm', 'mm', 'Tube taper increase at nozzle')

        # Gas box / SOL augmentation section (DFD papers)
        add_param('gas_box_length', '45 mm', 'mm', 'Gas box length')
        add_param('gas_box_thickness', '3 mm', 'mm', 'Gas box wall thickness')
        add_param('gas_box_radius', 'outer_radius + jacket_thickness + 8 mm', 'mm', 'Gas box outer radius')

        # RMF antenna region (odd-parity heating)
        add_param('rmf_antenna_count', '4', '', 'RMF antenna count (unitless)')
        add_param('rmf_antenna_radius', 'outer_radius + jacket_thickness + 6 mm', 'mm', 'RMF antenna radius')
        add_param('rmf_antenna_thickness', '4 mm', 'mm', 'RMF antenna radial thickness')
        add_param('rmf_antenna_length', '35 mm', 'mm', 'RMF antenna axial length')
        add_param('rmf_antenna_start', 'chamber_start + 10 mm', 'mm', 'RMF antenna start Z')
        add_param('rmf_antenna_spacing', '90 mm', 'mm', 'RMF antenna spacing')

        # Bias ring electrodes (rotation control)
        add_param('bias_ring_count', '2', '', 'Bias ring electrode count (unitless)')
        add_param('bias_ring_thickness', '6 mm', 'mm', 'Bias ring axial thickness')
        add_param('bias_ring_width', '8 mm', 'mm', 'Bias ring radial width')
        add_param('bias_ring_clearance', '2 mm', 'mm', 'Bias ring clearance from housing')
        add_param('bias_ring_start', 'chamber_start - 10 mm', 'mm', 'Bias ring start Z')
        add_param('bias_ring_spacing', 'chamber_length + 20 mm', 'mm', 'Bias ring spacing')
        add_param('bias_ring_inner_radius', 'outer_radius + bias_ring_clearance', 'mm', 'Bias ring inner radius')
        add_param('bias_ring_outer_radius', 'bias_ring_inner_radius + bias_ring_width', 'mm', 'Bias ring outer radius')

        # Target constraints (stored as parameters for later tuning)
        add_param('target_thrust', '45 N', 'N', 'Target thrust')
        add_param('target_power', '8 kW', 'kW', 'Target input power')
        add_param('target_voltage', '300 V', 'V', 'Target bus voltage')
        add_param('target_mass', '18 kg', 'kg', 'Target total mass')

        # Physics-driven overrides (required)
        physics_params_path = os.path.join(os.path.dirname(__file__), 'physics_params.json')
        if not os.path.exists(physics_params_path):
            ui.messageBox('Missing physics_params.json. Run physics_to_fusion_params.py first.')
            return
        try:
            physics_data = json.loads(open(physics_params_path, 'r').read())
            overrides = physics_data.get('cad_params', {})
            apply_overrides(overrides)
            required = [
                'outer_length','outer_radius','wall_thickness','liner_thickness','bore_radius',
                'chamber_length','nozzle_length','coil_inner_radius','coil_outer_radius',
                'coil_main_count','coil_main_spacing','coil_main_thickness','coil_main_start',
                'coil_nozzle_count','coil_nozzle_spacing','coil_nozzle_thickness','coil_nozzle_start',
                'mirror_coil_count','mirror_coil_radius','mirror_coil_thickness','mirror_coil_start','mirror_coil_spacing',
                'shaping_coil_count','shaping_coil_radius','shaping_coil_thickness','shaping_coil_start','shaping_coil_spacing',
                'tube_taper','gas_box_length','rmf_antenna_count','rmf_antenna_radius','rmf_antenna_length','rmf_antenna_spacing'
            ]
            missing = [name for name in required if name not in overrides]
            if missing:
                ui.messageBox('physics_params.json missing required parameters:\\n- ' + '\\n- '.join(missing))
                return
            violations = physics_data.get('violations', [])
            if violations:
                ui.messageBox('Physics violations found:\\n- ' + '\\n- '.join(violations))
                return
        except Exception:
            ui.messageBox('Failed to load physics_params.json. Aborting build.')
            return

        # ---- Helpers ----
        def new_component(parent_comp, name):
            occ = parent_comp.occurrences.addNewComponent(adsk.core.Matrix3D.create())
            occ.component.name = name
            return occ.component

        def create_offset_plane(comp, offset_z):
            planes = comp.constructionPlanes
            plane_input = planes.createInput()
            plane_input.setByOffset(comp.xYConstructionPlane, adsk.core.ValueInput.createByReal(offset_z))
            return planes.add(plane_input)

        def create_offset_plane_xz(comp, offset_y):
            planes = comp.constructionPlanes
            plane_input = planes.createInput()
            plane_input.setByOffset(comp.xZConstructionPlane, adsk.core.ValueInput.createByReal(offset_y))
            return planes.add(plane_input)

        def create_offset_plane_yz(comp, offset_x):
            planes = comp.constructionPlanes
            plane_input = planes.createInput()
            plane_input.setByOffset(comp.yZConstructionPlane, adsk.core.ValueInput.createByReal(offset_x))
            return planes.add(plane_input)

        def create_cylinder(comp, name, radius, start_z, length, operation):
            plane = create_offset_plane(comp, start_z)
            sketch = comp.sketches.add(plane)
            sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), radius)
            profile = sketch.profiles.item(0)
            extrudes = comp.features.extrudeFeatures
            ext_input = extrudes.createInput(profile, operation)
            ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(length))
            ext = extrudes.add(ext_input)
            if ext.bodies.count > 0:
                ext.bodies.item(0).name = name
            return ext

        def create_ring(comp, name, inner_radius, outer_radius, start_z, length, operation):
            plane = create_offset_plane(comp, start_z)
            sketch = comp.sketches.add(plane)
            curves = sketch.sketchCurves.sketchCircles
            curves.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), outer_radius)
            curves.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), inner_radius)
            profile = sketch.profiles.item(0)
            extrudes = comp.features.extrudeFeatures
            ext_input = extrudes.createInput(profile, operation)
            ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(length))
            ext = extrudes.add(ext_input)
            if ext.bodies.count > 0:
                ext.bodies.item(0).name = name
            return ext

        def create_cylinder_along_x(comp, name, radius, center_y, center_z, start_x, length, operation):
            plane = create_offset_plane_yz(comp, start_x)
            sketch = comp.sketches.add(plane)
            sketch.sketchCurves.sketchCircles.addByCenterRadius(
                adsk.core.Point3D.create(0, center_y, center_z),
                radius
            )
            profile = sketch.profiles.item(0)
            extrudes = comp.features.extrudeFeatures
            ext_input = extrudes.createInput(profile, operation)
            ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(length))
            ext = extrudes.add(ext_input)
            if ext.bodies.count > 0:
                ext.bodies.item(0).name = name
            return ext

        def circular_pattern_bodies(comp, bodies, count):
            feats = comp.features.circularPatternFeatures
            obj = adsk.core.ObjectCollection.create()
            for body in bodies:
                obj.add(body)
            pattern_input = feats.createInput(obj, comp.zConstructionAxis)
            pattern_input.quantity = adsk.core.ValueInput.createByReal(count)
            pattern_input.totalAngle = adsk.core.ValueInput.createByString('360 deg')
            feats.add(pattern_input)

        def circular_pattern_features(comp, features, count):
            feats = comp.features.circularPatternFeatures
            obj = adsk.core.ObjectCollection.create()
            for feat in features:
                obj.add(feat)
            pattern_input = feats.createInput(obj, comp.zConstructionAxis)
            pattern_input.quantity = adsk.core.ValueInput.createByReal(count)
            pattern_input.totalAngle = adsk.core.ValueInput.createByString('360 deg')
            feats.add(pattern_input)

        # ---- Clear existing DFD_Thruster component if present ----
        root = design.rootComponent
        to_delete = []
        for occ in root.occurrences:
            if occ.component and occ.component.name == 'DFD_Thruster':
                to_delete.append(occ)
        for occ in to_delete:
            occ.deleteMe()

        # ---- Build the assembly ----
        dfd_comp = new_component(root, 'DFD_Thruster')

        # Numeric values for geometry
        outer_length = eval_expr('outer_length')
        outer_radius = eval_expr('outer_radius')
        wall_thickness = eval_expr('wall_thickness')
        liner_thickness = eval_expr('liner_thickness')
        bore_radius = eval_expr('bore_radius')

        chamber_start = eval_expr('chamber_start')
        chamber_length = eval_expr('chamber_length')
        nozzle_length = eval_expr('nozzle_length')
        nozzle_throat_radius = eval_expr('nozzle_throat_radius')
        nozzle_exit_radius = eval_expr('nozzle_exit_radius')
        nozzle_wall_thickness = eval_expr('nozzle_wall_thickness')
        nozzle_throat_position = eval_expr('nozzle_throat_position')

        flange_thickness = eval_expr('flange_thickness')
        flange_outer_radius = eval_expr('flange_outer_radius')
        bolt_circle_radius = eval_expr('bolt_circle_radius')
        bolt_hole_radius = eval_expr('bolt_hole_diameter') / 2.0
        bolt_hole_count = int(user_params.itemByName('bolt_hole_count').value)

        injector_length = eval_expr('injector_length')
        injector_port_radius = eval_expr('injector_port_radius')
        injector_port_radius_cut = eval_expr('injector_port_diameter') / 2.0
        injector_port_count = int(user_params.itemByName('injector_port_count').value)

        coil_inner_radius = eval_expr('coil_inner_radius')
        coil_outer_radius = eval_expr('coil_outer_radius')
        coil_main_count = int(user_params.itemByName('coil_main_count').value)
        coil_main_spacing = eval_expr('coil_main_spacing')
        coil_main_thickness = eval_expr('coil_main_thickness')
        coil_main_start = eval_expr('coil_main_start')

        coil_nozzle_count = int(user_params.itemByName('coil_nozzle_count').value)
        coil_nozzle_spacing = eval_expr('coil_nozzle_spacing')
        coil_nozzle_thickness = eval_expr('coil_nozzle_thickness')
        coil_nozzle_start = eval_expr('coil_nozzle_start')

        mirror_coil_count = int(user_params.itemByName('mirror_coil_count').value)
        mirror_coil_radius = eval_expr('mirror_coil_radius')
        mirror_coil_thickness = eval_expr('mirror_coil_thickness')
        mirror_coil_start = eval_expr('mirror_coil_start')
        mirror_coil_spacing = eval_expr('mirror_coil_spacing')
        shaping_coil_count = int(user_params.itemByName('shaping_coil_count').value)
        shaping_coil_radius = eval_expr('shaping_coil_radius')
        shaping_coil_thickness = eval_expr('shaping_coil_thickness')
        shaping_coil_start = eval_expr('shaping_coil_start')
        shaping_coil_spacing = eval_expr('shaping_coil_spacing')

        strut_count = int(user_params.itemByName('strut_count').value)
        strut_width = eval_expr('strut_width')
        strut_thickness = eval_expr('strut_thickness')
        strut_start = eval_expr('strut_start')
        strut_length = eval_expr('strut_length')

        # --- Housing ---
        housing = new_component(dfd_comp, 'Housing')
        create_cylinder(housing, 'HousingOuter', outer_radius, 0.0, outer_length, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        create_cylinder(housing, 'HousingBore', bore_radius, 0.0, outer_length, adsk.fusion.FeatureOperations.CutFeatureOperation)

        # Tapered tube section near nozzle (physics-driven)
        taper_start = outer_length - nozzle_length
        taper_comp = new_component(dfd_comp, 'TubeTaper')
        create_ring(
            taper_comp,
            'TaperOuter',
            outer_radius,
            outer_radius + tube_taper,
            taper_start,
            nozzle_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        # Front mounting flange (ring)
        create_ring(
            housing,
            'FrontFlange',
            outer_radius,
            flange_outer_radius,
            0.0,
            flange_thickness,
            adsk.fusion.FeatureOperations.JoinFeatureOperation
        )

        # Bolt holes (patterned)
        flange_plane = housing.xYConstructionPlane
        flange_sketch = housing.sketches.add(flange_plane)
        flange_sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(bolt_circle_radius, 0, 0),
            bolt_hole_radius
        )
        bolt_profile = flange_sketch.profiles.item(0)
        bolt_ext_input = housing.features.extrudeFeatures.createInput(
            bolt_profile,
            adsk.fusion.FeatureOperations.CutFeatureOperation
        )
        bolt_ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(flange_thickness))
        bolt_ext = housing.features.extrudeFeatures.add(bolt_ext_input)
        circular_pattern_features(housing, [bolt_ext], bolt_hole_count)

        # --- Inner liner ---
        liner = new_component(dfd_comp, 'InnerLiner')
        create_ring(
            liner,
            'ChamberLiner',
            bore_radius - liner_thickness,
            bore_radius,
            chamber_start,
            chamber_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        # --- Injector manifold ---
        injector = new_component(dfd_comp, 'Injector')
        injector_ring_ext = create_ring(
            injector,
            'InjectorRing',
            bore_radius - liner_thickness,
            bore_radius,
            chamber_start,
            injector_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        injector_ring_body = None
        if injector_ring_ext and injector_ring_ext.bodies.count > 0:
            injector_ring_body = injector_ring_ext.bodies.item(0)
        
        injector_plane = create_offset_plane(injector, chamber_start)
        inj_sketch = injector.sketches.add(injector_plane)
        inj_sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(injector_port_radius, 0, 0),
            injector_port_radius_cut
        )
        inj_profile = inj_sketch.profiles.item(0)
        
        # Create tool bodies for cutting (more reliable than direct cut)
        inj_tool_input = injector.features.extrudeFeatures.createInput(
            inj_profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        inj_tool_input.setSymmetricExtent(adsk.core.ValueInput.createByReal(injector_length * 0.6), True)
        inj_tool = injector.features.extrudeFeatures.add(inj_tool_input)
        tool_body = None
        if inj_tool.bodies.count > 0:
            tool_body = inj_tool.bodies.item(0)
            tool_body.name = 'InjectorTool'
        
        if tool_body:
            circular_pattern_bodies(injector, [tool_body], injector_port_count)
        
        # Use combine feature to cut the ring with all tool bodies
        if injector_ring_body:
            tools = adsk.core.ObjectCollection.create()
            for body in injector.bRepBodies:
                if body != injector_ring_body:
                    tools.add(body)
            if tools.count > 0:
                combine = injector.features.combineFeatures
                combine_input = combine.createInput(injector_ring_body, tools)
                combine_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
                combine_input.isKeepToolBodies = False
                combine.add(combine_input)

        # --- Coils ---
        coils = new_component(dfd_comp, 'Coils')
        for i in range(coil_main_count):
            z0 = coil_main_start + i * coil_main_spacing
            create_ring(
                coils,
                f'MainCoil_{i + 1}',
                coil_inner_radius,
                coil_outer_radius,
                z0,
                coil_main_thickness,
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )
        for i in range(coil_nozzle_count):
            z0 = coil_nozzle_start + i * coil_nozzle_spacing
            create_ring(
                coils,
                f'NozzleCoil_{i + 1}',
                coil_inner_radius,
                coil_outer_radius,
                z0,
                coil_nozzle_thickness,
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )

        # Mirror coils (end-field shaping)
        mirror = new_component(dfd_comp, 'MirrorCoils')
        for i in range(mirror_coil_count):
            z0 = mirror_coil_start + i * mirror_coil_spacing
            create_ring(
                mirror,
                f'MirrorCoil_{i + 1}',
                mirror_coil_radius,
                mirror_coil_radius + (mirror_coil_thickness * 0.6),
                z0,
                mirror_coil_thickness,
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )

        # Field shaping coils
        shaping = new_component(dfd_comp, 'ShapingCoils')
        for i in range(shaping_coil_count):
            z0 = shaping_coil_start + i * shaping_coil_spacing
            create_ring(
                shaping,
                f'ShapingCoil_{i + 1}',
                shaping_coil_radius,
                shaping_coil_radius + (shaping_coil_thickness * 0.6),
                z0,
                shaping_coil_thickness,
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )

        # --- Nozzle ---
        nozzle = new_component(dfd_comp, 'Nozzle')
        z0 = outer_length - nozzle_length
        z1 = outer_length
        zt = z0 + nozzle_throat_position
        inner_r0 = bore_radius
        inner_rt = nozzle_throat_radius
        inner_r1 = nozzle_exit_radius
        outer_r0 = inner_r0 + nozzle_wall_thickness
        outer_rt = inner_rt + nozzle_wall_thickness
        outer_r1 = inner_r1 + nozzle_wall_thickness

        # Create nozzle as a simple tapered ring (avoids tangency issues with complex profiles)
        # Use average radii for simplicity - can be refined later
        avg_inner_r = (inner_r0 + inner_rt + inner_r1) / 3.0
        avg_outer_r = avg_inner_r + nozzle_wall_thickness
        
        create_ring(
            nozzle,
            'NozzleLiner',
            avg_inner_r,
            avg_outer_r,
            z0,
            nozzle_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        # --- Support struts ---
        supports = new_component(dfd_comp, 'Supports')
        strut_center_radius = bore_radius + (wall_thickness * 0.5)
        strut_plane = create_offset_plane(supports, strut_start)
        strut_sketch = supports.sketches.add(strut_plane)
        center = adsk.core.Point3D.create(strut_center_radius, 0, 0)
        corner = adsk.core.Point3D.create(
            strut_center_radius + (strut_thickness * 0.5),
            strut_width * 0.5,
            0
        )
        strut_sketch.sketchCurves.sketchLines.addCenterPointRectangle(center, corner)
        strut_profile = strut_sketch.profiles.item(0)
        strut_ext_input = supports.features.extrudeFeatures.createInput(
            strut_profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        strut_ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(strut_length))
        strut_ext = supports.features.extrudeFeatures.add(strut_ext_input)
        if strut_ext.bodies.count > 0:
            strut_ext.bodies.item(0).name = 'SupportStrut'
        circular_pattern_bodies(supports, [strut_ext.bodies.item(0)], strut_count)

        # --- Additional Components ---
        
        # Rear cap
        rear_cap_thickness = eval_expr('rear_cap_thickness')
        rear_cap = new_component(dfd_comp, 'RearCap')
        create_ring(
            rear_cap,
            'RearCap',
            bore_radius - liner_thickness,
            outer_radius,
            outer_length - rear_cap_thickness,
            rear_cap_thickness,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        
        # Electronics bay
        bay_length = eval_expr('bay_length')
        bay_radius = eval_expr('bay_radius')
        bay_wall_thickness = eval_expr('bay_wall_thickness')
        bay_cap_thickness = eval_expr('bay_cap_thickness')
        electronics = new_component(dfd_comp, 'ElectronicsBay')
        create_ring(
            electronics,
            'ElectronicsBayOuter',
            bay_radius - bay_wall_thickness,
            bay_radius,
            0.0,
            bay_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        create_ring(
            electronics,
            'ElectronicsBayCap',
            bay_radius - bay_wall_thickness,
            bay_radius,
            bay_length - bay_cap_thickness,
            bay_cap_thickness,
            adsk.fusion.FeatureOperations.JoinFeatureOperation
        )
        
        # Cooling jacket
        jacket_thickness = eval_expr('jacket_thickness')
        jacket_start = eval_expr('jacket_start')
        jacket_length = eval_expr('jacket_length')
        jacket_port_diameter = eval_expr('jacket_port_diameter')
        jacket_port_length = eval_expr('jacket_port_length')
        jacket = new_component(dfd_comp, 'CoolingJacket')
        jacket_outer_radius = outer_radius + jacket_thickness
        create_ring(
            jacket,
            'CoolingJacket',
            outer_radius,
            jacket_outer_radius,
            jacket_start,
            jacket_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        # Cooling ports
        jacket_port_radius = eval_expr('jacket_port_diameter') / 2.0
        jacket_plane = create_offset_plane(jacket, jacket_start)
        jacket_sketch = jacket.sketches.add(jacket_plane)
        jacket_sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(outer_radius + (jacket_thickness * 0.5), 0, 0),
            jacket_port_radius
        )
        jacket_port_profile = jacket_sketch.profiles.item(0)
        jacket_port_input = jacket.features.extrudeFeatures.createInput(
            jacket_port_profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        jacket_port_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(jacket_port_length))
        jacket_port = jacket.features.extrudeFeatures.add(jacket_port_input)
        if jacket_port.bodies.count > 0:
            jacket_port.bodies.item(0).name = 'CoolingPort'
        circular_pattern_bodies(jacket, [jacket_port.bodies.item(0)], 4)
        
        # Thermal shield
        thermal_shield_thickness = eval_expr('thermal_shield_thickness')
        thermal_shield_clearance = eval_expr('thermal_shield_clearance')
        shield = new_component(dfd_comp, 'ThermalShield')
        shield_inner = bore_radius - thermal_shield_clearance
        shield_outer = shield_inner + thermal_shield_thickness
        create_ring(
            shield,
            'ThermalShield',
            shield_inner,
            shield_outer,
            chamber_start,
            chamber_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        
        # Coil bobbins
        bobbin_thickness = eval_expr('bobbin_thickness')
        bobbin_clearance = eval_expr('bobbin_clearance')
        bobbins = new_component(dfd_comp, 'CoilBobbins')
        bobbin_inner = coil_inner_radius - bobbin_clearance
        bobbin_outer = coil_outer_radius + bobbin_clearance
        for i in range(coil_main_count):
            z0 = coil_main_start + i * coil_main_spacing
            create_ring(
                bobbins,
                f'Bobbin_{i + 1}',
                bobbin_inner,
                bobbin_outer,
                z0 - bobbin_thickness,
                coil_main_thickness + (bobbin_thickness * 2),
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )
        
        # Frame rails
        rail_count = int(user_params.itemByName('rail_count').value)
        rail_width = eval_expr('rail_width')
        rail_thickness = eval_expr('rail_thickness')
        rail_radius = eval_expr('rail_radius')
        rail_length = eval_expr('rail_length')
        rails = new_component(dfd_comp, 'FrameRails')
        rail_plane = rails.xYConstructionPlane
        rail_sketch = rails.sketches.add(rail_plane)
        rail_center = adsk.core.Point3D.create(rail_radius, 0, 0)
        rail_corner = adsk.core.Point3D.create(
            rail_radius + rail_thickness,
            rail_width * 0.5,
            0
        )
        rail_sketch.sketchCurves.sketchLines.addCenterPointRectangle(rail_center, rail_corner)
        rail_profile = rail_sketch.profiles.item(0)
        rail_ext_input = rails.features.extrudeFeatures.createInput(
            rail_profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        rail_ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(rail_length))
        rail_ext = rails.features.extrudeFeatures.add(rail_ext_input)
        if rail_ext.bodies.count > 0:
            rail_ext.bodies.item(0).name = 'FrameRail'
        circular_pattern_bodies(rails, [rail_ext.bodies.item(0)], rail_count)
        
        # Mounting feet
        foot_length = eval_expr('foot_length')
        foot_width = eval_expr('foot_width')
        foot_thickness = eval_expr('foot_thickness')
        foot_offset_z = eval_expr('foot_offset_z')
        feet = new_component(dfd_comp, 'MountingFeet')
        foot_plane = create_offset_plane(feet, foot_offset_z)
        foot_sketch = feet.sketches.add(foot_plane)
        foot_center = adsk.core.Point3D.create(rail_radius, 0, 0)
        foot_corner = adsk.core.Point3D.create(
            rail_radius + foot_length,
            foot_width * 0.5,
            0
        )
        foot_sketch.sketchCurves.sketchLines.addCenterPointRectangle(foot_center, foot_corner)
        foot_profile = foot_sketch.profiles.item(0)
        foot_ext_input = feet.features.extrudeFeatures.createInput(
            foot_profile,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        foot_ext_input.setDistanceExtent(False, adsk.core.ValueInput.createByReal(foot_thickness))
        foot_ext = feet.features.extrudeFeatures.add(foot_ext_input)
        if foot_ext.bodies.count > 0:
            foot_ext.bodies.item(0).name = 'MountFoot'
        circular_pattern_bodies(feet, [foot_ext.bodies.item(0)], rail_count)
        
        # Nozzle guard
        nozzle_guard_length = eval_expr('nozzle_guard_length')
        nozzle_guard_outer_radius = eval_expr('nozzle_guard_outer_radius')
        nozzle_guard_clearance = eval_expr('nozzle_guard_clearance')
        tube_taper = eval_expr('tube_taper')
        gas_box_length = eval_expr('gas_box_length')
        gas_box_thickness = eval_expr('gas_box_thickness')
        gas_box_radius = eval_expr('gas_box_radius')
        rmf_antenna_count = int(user_params.itemByName('rmf_antenna_count').value)
        rmf_antenna_radius = eval_expr('rmf_antenna_radius')
        rmf_antenna_thickness = eval_expr('rmf_antenna_thickness')
        rmf_antenna_length = eval_expr('rmf_antenna_length')
        rmf_antenna_start = eval_expr('rmf_antenna_start')
        rmf_antenna_spacing = eval_expr('rmf_antenna_spacing')
        bias_ring_count = int(user_params.itemByName('bias_ring_count').value)
        bias_ring_thickness = eval_expr('bias_ring_thickness')
        bias_ring_inner_radius = eval_expr('bias_ring_inner_radius')
        bias_ring_outer_radius = eval_expr('bias_ring_outer_radius')
        bias_ring_start = eval_expr('bias_ring_start')
        bias_ring_spacing = eval_expr('bias_ring_spacing')
        guard = new_component(dfd_comp, 'NozzleGuard')
        guard_inner = nozzle_exit_radius + nozzle_guard_clearance
        create_ring(
            guard,
            'NozzleGuard',
            guard_inner,
            nozzle_guard_outer_radius,
            outer_length - nozzle_guard_length,
            nozzle_guard_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        # Bias ring electrodes (rotation control rings)
        rings = new_component(dfd_comp, 'BiasRings')
        for i in range(bias_ring_count):
            z0 = bias_ring_start + i * bias_ring_spacing
            create_ring(
                rings,
                f'BiasRing_{i + 1}',
                bias_ring_inner_radius,
                bias_ring_outer_radius,
                z0,
                bias_ring_thickness,
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )

        # Gas box / SOL augmentation ring
        gas_box = new_component(dfd_comp, 'GasBox')
        create_ring(
            gas_box,
            'GasBox',
            gas_box_radius - gas_box_thickness,
            gas_box_radius,
            chamber_start - (gas_box_length * 0.5),
            gas_box_length,
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )

        # RMF antenna rings (odd-parity heating)
        rmf = new_component(dfd_comp, 'RMFAntennas')
        for i in range(rmf_antenna_count):
            z0 = rmf_antenna_start + i * rmf_antenna_spacing
            create_ring(
                rmf,
                f'RMFAntenna_{i + 1}',
                rmf_antenna_radius,
                rmf_antenna_radius + rmf_antenna_thickness,
                z0,
                rmf_antenna_length,
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )

        # Generate materials and stats sheet
        stats_path = os.path.join(os.path.dirname(__file__), 'DFD_Thruster_Materials_Stats.csv')
        with open(stats_path, 'w') as f:
            f.write('Component,Quantity,Material,Density (g/cm³),Volume (cm³),Mass (g),Notes\n')
            
            # Calculate volumes and masses (simplified estimates)
            housing_vol = 3.14159 * (outer_radius**2 - bore_radius**2) * outer_length / 1000  # cm³
            housing_mass = housing_vol * 7.85  # Steel density
            f.write(f'Housing,1,Stainless Steel 316L,7.85,{housing_vol:.2f},{housing_mass:.2f},Main structural body\n')
            
            liner_vol = 3.14159 * (bore_radius**2 - (bore_radius - liner_thickness)**2) * chamber_length / 1000
            liner_mass = liner_vol * 2.7  # Aluminum
            f.write(f'Inner Liner,1,Aluminum 6061,2.7,{liner_vol:.2f},{liner_mass:.2f},Plasma-facing surface\n')
            
            injector_vol = 3.14159 * (bore_radius**2 - (bore_radius - liner_thickness)**2) * injector_length / 1000
            injector_mass = injector_vol * 2.7
            f.write(f'Injector Ring,1,Aluminum 6061,2.7,{injector_vol:.2f},{injector_mass:.2f},{injector_port_count} ports\n')
            
            coil_vol_per = 3.14159 * (coil_outer_radius**2 - coil_inner_radius**2) * coil_main_thickness / 1000
            coil_total_vol = coil_vol_per * (coil_main_count + coil_nozzle_count)
            coil_total_mass = coil_total_vol * 8.96  # Copper
            f.write(f'Coils,{coil_main_count + coil_nozzle_count},Copper Wire,8.96,{coil_total_vol:.2f},{coil_total_mass:.2f},Magnetic field coils\n')
            
            nozzle_vol = 3.14159 * ((nozzle_exit_radius + nozzle_wall_thickness)**2 - nozzle_exit_radius**2) * nozzle_length / 1000
            nozzle_mass = nozzle_vol * 2.7
            f.write(f'Nozzle,1,Aluminum 6061,2.7,{nozzle_vol:.2f},{nozzle_mass:.2f},Convergent-divergent\n')
            
            strut_vol_per = strut_width * strut_thickness * strut_length / 1000
            strut_total_vol = strut_vol_per * strut_count
            strut_total_mass = strut_total_vol * 7.85
            f.write(f'Support Struts,{strut_count},Stainless Steel 316L,7.85,{strut_total_vol:.2f},{strut_total_mass:.2f},Internal supports\n')
            
            jacket_vol = 3.14159 * ((outer_radius + jacket_thickness)**2 - outer_radius**2) * jacket_length / 1000
            jacket_mass = jacket_vol * 2.7
            f.write(f'Cooling Jacket,1,Aluminum 6061,2.7,{jacket_vol:.2f},{jacket_mass:.2f},4 cooling ports\n')
            
            shield_vol = 3.14159 * ((shield_outer)**2 - shield_inner**2) * chamber_length / 1000
            shield_mass = shield_vol * 2.7
            f.write(f'Thermal Shield,1,Aluminum 6061,2.7,{shield_vol:.2f},{shield_mass:.2f},Radiation shield\n')
            
            rail_vol_per = rail_width * rail_thickness * rail_length / 1000
            rail_total_vol = rail_vol_per * rail_count
            rail_total_mass = rail_total_vol * 7.85
            f.write(f'Frame Rails,{rail_count},Stainless Steel 316L,7.85,{rail_total_vol:.2f},{rail_total_mass:.2f},Structural frame\n')
            
            foot_vol_per = foot_length * foot_width * foot_thickness / 1000
            foot_total_vol = foot_vol_per * rail_count
            foot_total_mass = foot_total_vol * 7.85
            f.write(f'Mounting Feet,{rail_count},Stainless Steel 316L,7.85,{foot_total_vol:.2f},{foot_total_mass:.2f},Mounting points\n')
            
            bay_vol = 3.14159 * (bay_radius**2 - (bay_radius - bay_wall_thickness)**2) * bay_length / 1000
            bay_mass = bay_vol * 2.7
            f.write(f'Electronics Bay,1,Aluminum 6061,2.7,{bay_vol:.2f},{bay_mass:.2f},Control electronics\n')
            
            guard_vol = 3.14159 * (nozzle_guard_outer_radius**2 - guard_inner**2) * nozzle_guard_length / 1000
            guard_mass = guard_vol * 2.7
            f.write(f'Nozzle Guard,1,Aluminum 6061,2.7,{guard_vol:.2f},{guard_mass:.2f},Exit protection\n')

            ring_vol_per = 3.14159 * (bias_ring_outer_radius**2 - bias_ring_inner_radius**2) * bias_ring_thickness / 1000
            ring_total_vol = ring_vol_per * bias_ring_count
            ring_total_mass = ring_total_vol * 8.96  # Copper
            f.write(f'Bias Ring Electrodes,{bias_ring_count},Copper,8.96,{ring_total_vol:.2f},{ring_total_mass:.2f},Rotation control rings\n')

            gas_box_vol = 3.14159 * (gas_box_radius**2 - (gas_box_radius - gas_box_thickness)**2) * gas_box_length / 1000
            gas_box_mass = gas_box_vol * 2.7
            f.write(f'Gas Box,1,Aluminum 6061,2.7,{gas_box_vol:.2f},{gas_box_mass:.2f},SOL thrust augmentation\n')

            rmf_vol_per = 3.14159 * ((rmf_antenna_radius + rmf_antenna_thickness)**2 - rmf_antenna_radius**2) * rmf_antenna_length / 1000
            rmf_total_vol = rmf_vol_per * rmf_antenna_count
            rmf_total_mass = rmf_total_vol * 8.96
            f.write(f'RMF Antennas,{rmf_antenna_count},Copper,8.96,{rmf_total_vol:.2f},{rmf_total_mass:.2f},Odd-parity RMF heating\n')

            mirror_vol_per = 3.14159 * ((mirror_coil_radius + mirror_coil_thickness * 0.6)**2 - mirror_coil_radius**2) * mirror_coil_thickness / 1000
            mirror_total_vol = mirror_vol_per * mirror_coil_count
            mirror_total_mass = mirror_total_vol * 8.96
            f.write(f'Mirror Coils,{mirror_coil_count},Copper,8.96,{mirror_total_vol:.2f},{mirror_total_mass:.2f},End field shaping\n')

            shaping_vol_per = 3.14159 * ((shaping_coil_radius + shaping_coil_thickness * 0.6)**2 - shaping_coil_radius**2) * shaping_coil_thickness / 1000
            shaping_total_vol = shaping_vol_per * shaping_coil_count
            shaping_total_mass = shaping_total_vol * 8.96
            f.write(f'Shaping Coils,{shaping_coil_count},Copper,8.96,{shaping_total_vol:.2f},{shaping_total_mass:.2f},Field shaping coils\n')
            
            total_mass = (housing_mass + liner_mass + injector_mass + coil_total_mass + nozzle_mass + 
                          strut_total_mass + jacket_mass + shield_mass + rail_total_mass + 
                          foot_total_mass + bay_mass + guard_mass + ring_total_mass + 
                          gas_box_mass + rmf_total_mass + mirror_total_mass + shaping_total_mass) / 1000  # kg
            f.write(f'\nTOTAL ASSEMBLY,1,Mixed Materials,N/A,N/A,{total_mass:.2f},Complete thruster assembly\n')
            target_thrust_val = user_params.itemByName('target_thrust').value
            target_power_val = user_params.itemByName('target_power').value
            target_voltage_val = user_params.itemByName('target_voltage').value
            target_mass_val = user_params.itemByName('target_mass').value
            f.write(f'\nTarget Constraints:\n')
            f.write(f'Target Thrust,{target_thrust_val:.1f} N\n')
            f.write(f'Target Power,{target_power_val:.1f} kW\n')
            f.write(f'Target Voltage,{target_voltage_val:.0f} V\n')
            f.write(f'Target Mass,{target_mass_val:.2f} kg\n')
            f.write(f'Actual Mass,{total_mass:.2f} kg\n')

        ui.messageBox(f'DFD thruster model created successfully!\n\nTotal Mass: {total_mass:.2f} kg\nMaterials sheet saved to:\n{stats_path}\n\nAdjust parameters and re-run to regenerate.')

    except Exception:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
