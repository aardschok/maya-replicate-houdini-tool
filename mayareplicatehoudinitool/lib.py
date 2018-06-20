from contextlib import contextmanager
import logging

from avalon.maya import lib

from maya import cmds, mel

logger = logging.getLogger("Replicate")


@contextmanager
def maintain_connections(asset):
    """Keep all connection of the asset content to replicated nParticle

    Args:
        asset(str): name of the houdiniAsset node

    Returns:
        None

    """
    instance_connections = []
    connected_nparticles = cmds.listConnections(asset,
                                                destination=True,
                                                type="nParticle",
                                                exactType=True,
                                                shapes=True)
    descendents = cmds.listRelatives(asset, allDescendents=True)
    try:
        non_descendents = [p for p in connected_nparticles if
                           p not in descendents]
        for nparticle in non_descendents:

            # Check instance of nparticle
            instancers = cmds.listConnections(nparticle,
                                              destination=True,
                                              type="instancer") or []
            if not instancers:
                continue

            # List all connections
            for instancer in instancers:
                attr = "{}.inputHierarchy".format(instancer)
                hierarchy = cmds.listConnections(attr,
                                                 connections=True,
                                                 plugs=True)
                cons = len(hierarchy)
                instance_connections.extend([[hierarchy[i + 1], hierarchy[i]]
                                             for i in range(0, cons, 2)])

        # Break connections
        for connection in instance_connections:
            cmds.disconnectAttr(connection[0], connection[1])

        yield

    finally:
        for connection in instance_connections:
            cmds.connectAttr(connection[0], connection[1], force=True)


def get_houdini_assets(selected=False):
    """List all Houdini Asset nodes in the scene

    Args:
        selected(bool): toggle to retrieve selected

    Returns:
        list

    """

    if selected:
        return cmds.ls(selection=True, type="houdiniAsset")

    return cmds.ls(type="houdiniAsset")


def map_houdini_asset(asset):
    asset_mapping = {}

    # Get connected nodes
    hierarchy = set()
    instancers = get_instancers(asset)
    for inst in instancers:
        hierarchy.update(get_input_hierarchy(inst))

    particle_node = get_particle_system(asset)
    attributes = get_particle_attributes(particle_node)

    asset_mapping[asset] = {"particle_system": {particle_node: attributes},
                            "hierarchy": list(hierarchy)}

    return asset_mapping


def get_shape_transforms(houdini_asset):
    """Get the transforms of the connected meshes

    Args:
        houdini_asset(str): name of the Houdini Asset node

    Returns:
        set

    """
    if cmds.nodeType(houdini_asset) != "houdiniAsset":
        raise ValueError("Wrong node type")

    shapes = cmds.listConnections(houdini_asset, destination=True, type="mesh")
    return set(shapes)


def get_particle_system(houdini_asset):
    """Get Connected nParticle object

    Args:
        houdini_asset(str): name of the Houdini asset

    Returns:
        str

    """
    connections = cmds.listConnections(houdini_asset,
                                       destination=True,
                                       type="nParticle",
                                       shapes=True)

    # Get from descendents
    descendents = cmds.listRelatives(houdini_asset,
                                     allDescendents=True,
                                     type="nParticle")

    connections = [i for i in connections if i in descendents]

    # We need to check the if there is only one mParticle node connected
    # TODO: Ensure multiple particle systems can work as well
    particle_systems = list(set(connections))
    assert len(particle_systems) == 1, (
            "This tool does not support multiple nParticles, "
            "got %i nParticles" % len(particle_systems))

    return particle_systems[0]


def get_particle_attributes(node):
    """Get all dynamic attributes of the nParticle node

    Args:
        node(str): name of the nParticle node

    Returns:
        list

    """

    return cmds.particle(node, query=True, dynamicAttrList=True)


def get_instancers(houdini_asset):
    """Get all instancer nodes connected to the Houdini asset

    Args:
        houdini_asset(str): name of the Houdini asset

    Returns:
        list

    """
    return cmds.listConnections(houdini_asset,
                                destination=True,
                                type="instancer")


def get_input_hierarchy(instancer):
    """Get all input nodes if an instancer

    Args:
        instancer(str): name of an instancer node

    Returns:
        list

    """
    if cmds.nodeType(instancer) != "instancer":
        raise ValueError("Given node is not of type 'instancer'")

    return cmds.listConnections("{}.inputHierarchy".format(instancer))


def replicate(name, asset_mapping, attribute_mapping=None):
    """Replicate the Houdini asset in Maya for publishing

    As a Houdini asset has each shape separated into its own instancer we
    need to merge the shapes back into one instancer. It is possible that
    the order of the instanced shapes differs from the Houdini asset.
    This will need to be update manually by the artist.

    Args:
        name(str): name of the asset
        asset_mapping(dict): data collection of Houdini Asset and its
                             instancers
        attribute_mapping(dict): data to link particle attributes to instancer
                        Example: {"scale": "radiusPP", "objectIndex": "index"}

    Returns:
        bool

    """

    # Debug mapping, will need to come from the UI
    # Discover houdini assets
    if not attribute_mapping:
        attribute_mapping = {}

    # Pre-flight check
    nuclea = cmds.ls(type="nucleus")
    if not nuclea:
        nucleus = cmds.createNode("nucleus")
    else:
        nucleus = nuclea[0]

    # Flight
    name += "_"  # add underscore as divider
    suffix = "_GRP"

    # suffix is not included in return value of lib.unique_name()
    unique_name = lib.unique_name(name, format="%03d", suffix=suffix)
    unique_name += suffix

    asset_group = cmds.group(empty=True, name=unique_name)
    for i, (asset, mapping) in enumerate(asset_mapping.items()):

        particle_data = mapping.get("particle_system", None)
        if particle_data is None:
            raise RuntimeError("Incomplete mapping of asset '%s',"
                               " missing particle_system" % asset)

        particle_system = particle_data.keys()[0]

        # Get connection to particleArrayData
        array_data_attr = "{}.cacheArrayData".format(particle_system)
        data_attrs = cmds.listConnections(array_data_attr, plugs=True) or []
        assert len(data_attrs) == 1, "This is a bug"
        data_attr = data_attrs[0]

        new_name = "{}{:03d}_PART".format(name, i)
        new_systems = cmds.duplicate(particle_system, name=new_name)
        assert len(new_systems) == 1, ("This is a bug, duplicated '%s' "
                                       "nParticle nodes" % len(new_systems))
        new_system = new_systems[0]

        # Connect particle array data to cache array data
        cmds.connectAttr(data_attr, "{}.cacheArrayData".format(new_system))

        # Link to nucleus
        cmds.select(clear=True)
        cmds.select(new_system)
        mel.eval("assignNSolver {}".format(nucleus))

        cmds.parent(new_system, asset_group)
        hierarchy = mapping.get("hierarchy", [])

        inst_name = "{}{:03d}_INST".format(name, i)
        kwargs = attribute_mapping

        new_instancer = cmds.particleInstancer(new_system,
                                               name=inst_name,
                                               object=hierarchy,
                                               **kwargs)

        # Force all types to True in UI ( no other way )
        cmds.checkBoxGrp("AEdisplayAllTypes", edit=True, v1=True)

        # Set rotation attributes
        cmds.setAttr("{}.rotationAngleUnits".format(new_instancer), 1)
        cmds.setAttr("{}.rotationOrder".format(new_instancer), 0)

        try:
            cmds.parent(new_instancer, asset_group)
        except RuntimeError:
            pass

    return True


def update_asset(asset):
    """Update the Houdini assets and there replica

    Args:
        asset(str): name of the Houdini assets

    Returns:
        bool

    """

    cmd = 'houdiniEngine_syncAsset "{node}";'

    before_update = get_shape_transforms(asset)
    asset_hierarchy = cmds.listRelatives(asset, allDescendents=True)

    # Get connected instancer
    transforms = list(before_update)
    instancers = cmds.listConnections(transforms[0],
                                      destination=True,
                                      type="instancer") or []
    instancers = [i for i in instancers if i not in asset_hierarchy]

    assert len(instancers), "This is a bug"
    instancer = instancers[0]

    logging.info("Updating %s ..." % asset)
    with maintain_connections(asset):
        mel.eval(cmd.format(node=asset))

    after_update = get_shape_transforms(asset)
    count = len(before_update)
    new_shapes = after_update - before_update
    for i, shape in enumerate(new_shapes, 1):
        idx = count + i
        cmds.connectAttr("{}.matrix".format(shape),
                         "{}.inputHierarchy[{:d}]".format(instancer, idx))

    return True
