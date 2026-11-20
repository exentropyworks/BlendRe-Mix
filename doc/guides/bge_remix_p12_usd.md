# BGE-Remix P12: OpenUSD and RTX Remix captures

BGE-Remix carries its own OpenUSD (25.11, the version RTX Remix 1.6.1
ships), in bge_remix_usd.dll beside blender.exe. It loads only when
something is imported or exported: a game that does neither never loads it.

## File > Import > RTX Remix Capture

An RTX Remix capture is the folder Remix writes when you capture a D3D9 game
(rtx-remix/captures beside the game): a stage file (capture_*.usd) and the
meshes, materials, lights and textures folders beside it. Pick the stage
file. It comes in as a new scene, named after it:

- **Meshes**: each Remix mesh becomes a Blender mesh, with its normals, UVs
  and vertex colours. Each place the game drew it becomes an object sharing
  that mesh (linked copies), so editing one edits them all, as in Remix.
  Each object has its own material (the material slot is linked to the
  object), so places of one mesh can differ, and the game shows each
  object's own.
- **Materials**: each becomes an RTX Remix material (the RTX Remix Material
  node), with Remix's values and textures. Values the node has no place for
  (Remix's texture filtering and wrapping, for instance) are kept with the
  material for the mod export.
- **Lights**: Remix's sphere lights become point lamps (spots when they
  have a cone), distant lights suns, rectangle lights area lamps, disk
  lights physical spots. Sent back to Remix they are the same lights. The
  sky dome is left out (the scene's world is the sky).
- **Camera**: the capture's camera becomes the scene camera.

A game in centimetres, or with Y up, comes in in metres with Z up. The
capture's own units, up axis and file stay with the scene, for the mod
export.

Every object and material keeps its Remix hash: the Object and Material tabs
show it in an RTX Remix Capture box.

### Textures

Remix's textures are DDS files. Each is decoded once to a PNG beside it
(name.dds.png), which Blender shows; the material keeps the DDS for Remix,
which is not re-encoded. Any DDS format reads, block-compressed or not.

### What is not brought in

The import reports, in the Info log, anything missing or left out: a
texture file that is not there (its material comes in without it), a mesh
whose file cannot be read (it and its places are left out), a shader that
is not Remix's AperturePBR (its values are read as they are), a light
Blender has no lamp for. A USD file that is not a capture is refused with a
message.

### Captures of BGE-Remix games

Remix cannot capture BGE-Remix games: its capturer skips everything drawn
through its API, which is how BGE-Remix draws. Captures come from D3D9
games; BGE-Remix games are changed in their .blend.

## File > Export > RTX Remix Mod

After importing a capture and changing it, File > Export > RTX Remix Mod
writes the changes as a Remix mod: a folder holding mod.usda and a textures
folder. It suggests the game's own mods folder, rtx-remix/mods/<scene name>
(found from the capture's path); any folder can be picked. Remix loads the
mods in rtx-remix/mods when the game starts.

Only what was changed goes in. At import, each mesh, material, lamp and
object keeps a fingerprint of how it came in, and the export compares
against it. With nothing changed, it says so and writes nothing. A scene
that did not come from a capture is refused with a message.

- **A mesh you edited** replaces that mesh wherever the game draws it, and
  the game's own mesh is switched off. Each place keeps its own material.
- **Objects and lamps parented to an imported object** are added to that
  object's mesh, wherever the game draws it, placed relative to it. Their
  modifiers are applied. Their materials go into the mod with them.
- **A material you changed** replaces that material everywhere it is used.
  Its pictures are written as DDS in the textures folder: a capture texture
  you did not touch is copied as it is, and a new or painted picture is
  encoded with the bridge's encoder (BC7 for colour, BC5 for normal maps,
  BC4 for one channel). Only pictures wired straight into the RTX Remix
  node go in.
- **A lamp you changed** replaces that light, in its new place too.

Everything goes back to the capture's own units and up axis, so the game
sees nothing moved.

### What a mod cannot carry

A mod changes how things look, not where the game puts them. The export
reports, in the Info log, what it left out: a place moved, deleted or
copied, another material or mesh given to one place (change the material or
the mesh itself), physics, logic and game properties, modifiers on an
imported object (apply them first), new objects not parented to an
imported one, a sun or hemi lamp under a mesh.

### Checked before it reports success

The mod is read back with BGE-Remix's own OpenUSD before the export reports
success, so a file Remix could not open is caught at once, with the reason.

### In the Remix View

In a scene imported from a capture, the Remix View's Remix layer (Check
mode) shows the mod as the export will write it, as you edit:

- each imported mesh, material and lamp has its capture hash on its line in
  the N panel, with what the mod does with it: the game's own (unchanged),
  the mod replaces it, or the mod adds objects to it;
- each object or lamp parented to an imported object says "added to mesh
  ... by the mod";
- what a mod cannot carry shows as notes, worded as the export's report
  words them (the same checks make both). Notes do not change the objects'
  colours: the game itself is fine.

A scene imported before this version (P12 round 5) shows everything as
changed: import its capture again.

## File > Export > RTX Remix Asset (for the Toolkit)

The RTX Remix Toolkit takes models in as FBX, OBJ, glTF or LXO and converts
them itself (its ingestion); it uses only assets it has ingested. This
export writes the selected meshes, from any scene, in a form it ingests,
into one folder (it suggests rtx_remix_assets/<name> beside the .blend):

- **<name>.fbx**: the meshes, through Blender's own FBX exporter, with
  their modifiers applied, in metres, placed relative to the world origin.
- **<material>_albedo.png, _normal, _roughness, _metallic, _emissive,
  _height**: each RTX Remix material's pictures, named by what they are.
  A value with no picture (a plain roughness of 0.4, say) is written as a
  small one-colour picture, since the Toolkit builds its materials from
  pictures. Normal maps are OpenGL style (Blender's): pick "Normal - OpenGL"
  in the Toolkit.
- **<name>_readme.txt**: each material, its pictures and the Toolkit's
  texture type for each, so the texture sets are assigned in one pass.

Lamps (the Toolkit adds its own lights), cameras, empties and other objects
that are not meshes, logic and physics, and materials that are not RTX
Remix materials are named in the Info log as left out. With no mesh
selected the export says so.

## File > Export > Universal Scene Description (.usd, .usda, .usdc)

For other tools (Omniverse, Houdini, Maya, Blender 2.8 and later, any USD
viewer). It writes the whole scene, or with Selected Objects Only the
selected objects, in metres and Z up, as text (.usda) or USD's binary form
(.usdc, or .usd):

- **Meshes**, with their modifiers applied: faces, normals, UVs and vertex
  colours. A mesh with several materials is split by material (GeomSubsets).
  Curves, surfaces and text go out as the meshes they make.
- **Hierarchy**: each object's transform relative to its parent; empties
  as plain transforms. Names USD does not take (Leg.001) are kept as the
  prims' display names, so they come back as they were.
- **Materials**: every material as a UsdPreviewSurface, which any tool
  reads: colour, roughness, metallic, emission, opacity, normal map and IOR,
  with their pictures. RTX Remix materials also carry Remix's AperturePBR,
  so BGE-Remix and Remix get them exactly. Classic materials go out as their
  nearest preview surface: colour (times its intensity), opacity, roughness
  from the specular hardness, glow, their first colour picture and normal
  map. Pictures are copied into a textures folder beside the file (a
  picture made in Blender, or one that needs changing for other tools, such
  as a DirectX normal map, as a PNG).
- **Lamps** as UsdLux lights, by the mod export's rules: point and spot as
  sphere lights (the spot with its cone; a physical spot as a disk light),
  sun as a distant light, area as a rectangle light. A hemi lamp is listed
  as left out.
- **Cameras**: lens, sensor, clipping, perspective or orthographic.

- **Physics** (in USD's standard physics schema, UsdPhysics, which
  Omniverse, Isaac Sim and other PhysX tools read): the world's gravity;
  Rigid Body and Dynamic objects as rigid bodies with their mass, Static
  ones as colliders that do not move, No Collision as nothing; the
  collision shape (Convex Hull and Triangle Mesh on the mesh itself; Box,
  Sphere, Capsule, Cylinder and Cone as an invisible shape of that kind
  under the object); compound bodies with their children as their shapes;
  each first material's friction and bounce as a physics material; Rigid
  Body Joints (Ball and Cone Twist as spherical joints, Hinge as a revolute
  joint, Generic 6DOF as a joint with a limit for each axis it limits;
  Disable Linked Collision kept); articulation roots (Fixed to the World
  with its fixed joint to the world). What the standard has no place for
  goes in attributes of BGE-Remix's own (bgeRemix:...), which other tools
  keep and ignore: the physics type, bounds, margin, damping, speed limits,
  Ghost, compound, locked axes, the engine (Bullet, PhysX CPU or GPU), every
  joint limit as it was, and the settings of destructibles, fluid volumes
  and ragdoll capsules. Soft bodies, characters, sensors, occluders and
  navigation meshes are listed as left out. A Rigid Body Joint keeps no
  motor in the file (a script sets it in the game), so none is written.
- Only what the game plays: objects on hidden layers (such as a
  destructible's kept original on layer 20) are left out, and listed.

Before it reports success the file is read back the way the import reads
it, its physics with OpenUSD's own physics reader; if anything differs from
what was written, the export says what.

## File > Import > Universal Scene Description

Any tool's .usd, .usda or .usdc comes in as a new scene, named after the
file, read through BGE-Remix's own OpenUSD (references, payloads and
instancing included):

- meshes, with every way USD stores normals, UVs and colours (per vertex,
  per corner, per face, indexed); an instanced reference's copies share one
  mesh (linked copies), each keeping its own materials;
- the hierarchy: transforms become empties; a transform holding only a
  mesh (or a camera or light where it is) becomes that one object, as most
  tools write them;
- materials as RTX Remix materials: from Remix's AperturePBR when the file
  has it, otherwise from its UsdPreviewSurface (colour, roughness, metallic,
  emission, opacity, normal map, IOR and their pictures);
- lamps (by the capture import's rules: the reverse of how lamps are sent to
  Remix) and cameras;
- a Y-up or centimetre file comes in Z up and in metres.

- physics, read with OpenUSD's own physics reader (the one PhysX tools
  use): rigid bodies (their mass, or their density times their shape's
  volume when only that is given; 1000 kg/m³ when nothing is), static
  colliders, collision shapes as Collision Bounds (a convex decomposition as
  Convex Hull), physics materials as the material's friction and bounce,
  gravity; revolute joints as Hinges, spherical ones as Ball or Cone Twist,
  prismatic, fixed and D6 joints as Generic 6DOF, with their limits;
  articulation roots, and a fixed joint from an articulation to the world as
  its root's Fixed to the World. A file with physics but none on an object
  makes it No Collision; a file with physics and no engine of ours comes in
  with PhysX on the CPU (its physics is PhysX's). BGE-Remix's own files come
  back with every setting as it was.

Anything it cannot take is named in the Info log, never dropped silently:
a shader network that is neither a preview surface nor AperturePBR (the
material comes in plain), curves, points, point instancers, volumes and
USD's own shapes (cube, sphere), dome lights; distance and custom joints,
joint drives (motors), breaking forces, collision groups and filtered
pairs, kinematic bodies (they come in Static) and starting speeds.
