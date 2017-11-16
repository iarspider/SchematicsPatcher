import argparse
import logging
import os
import shutil

import pymclevel
from pymclevel import mclevel

# :type: logging.Logger
logger = None

containers = []


# containers = [{'name': u'BiblioCraft:BiblioStuffs', 'meta': 2, 'inv': u'plateInventory', 'key': u'id'},
#               {'name': u'BiblioCraft:BiblioTable', 'inv': u'TableInventory', 'key': u'id'},
#               {'name': u'malisisdoors:null', 'meta': 4, 'key': u'topMaterial'},
#               {'name': u'malisisdoors:null', 'meta': 4, 'key': u'bottomMaterial'},
#               # {'name': u'GardenContainers:wood_window_box', 'inv': u'Items', 'key': u'Item'},
#               # {'name': u'GardenContainers:stone_window_box', 'inv': u'Items', 'key': u'Item'},
#               {'name': u'CarpentersBlocks:blockCarpentersSlope', 'inv': u'cbAttrList', 'key': u'id'},
#               {'name': u'CarpentersBlocks:blockCarpentersStairs', 'inv': u'cbAttrList', 'key': u'id'},
#               ]


def setup_logging():
    global logger

    # create logger with 'spam _application'
    logger = logging.getLogger('patcher')
    logger.setLevel(logging.DEBUG)

    # create file handler which logs even debug messages
    fh = logging.FileHandler('debug.log', mode='w')
    fh.setLevel(logging.INFO)

    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

    mclevel.log = logger


def load_idmap(world):
    # global idMap
    id_map = {}

    for itemData in world.root_tag['FML']['ItemData']:
        if ord(itemData['K'].value[0]) > 2:
            logger.warn('Skipped itemData key %s (%d)', itemData['K'].value, itemData['V'].value)
            continue

        name = itemData['K'].value[1:]
        entry_type = ('Stuff', 'Block', 'Item')[ord(itemData['K'].value[0])]
        entry_id = itemData['V'].value

        if not (name in id_map):
            id_map[name] = {'Block': -1, 'Item': -1, 'Stuff': -1}

        if id_map[name][entry_type] == -1:
            id_map[name][entry_type] = entry_id
        else:
            logger.error(
                "{0} id already registered! Old id: {1}, New id: {2}".format(entry_type, id_map[name][entry_type],
                                                                             entry_id))

    for k in id_map:
        logger.debug("%s -> %s", str(k), str(id_map[k]))

    return id_map


def create_remapper(source, target):
    remapper = {0: 0}

    all_names = set(source.keys())
    all_names.update(target.keys())

    for name in all_names:
        try:
            source_id = source[name]['Block']
        except (KeyError, IndexError):
            logger.warning("Block %s missing in source", name)
            source_id = -2

        # if source_id == -1:
        #     logger.warning("Name %s does not have block form", name)

        if source_id > 0:
            try:
                target_id = target[name]['Block']
            except (KeyError, IndexError):
                logger.warning("Block %s missing in target", name)
                target_id = -2

            remapper[source_id] = target_id

        try:
            source_id = source[name]['Item']
        except (KeyError, IndexError):
            logger.warning("Item %s missing in source", name)
            source_id = -2

        if source_id > 0:
            try:
                target_id = target[name]['Item']
            except (KeyError, IndexError):
                logger.warning("Item %s missing in target", name)
                target_id = -2

            remapper[source_id] = target_id

    return remapper


def remap_schematic(schematic, remapper):
    """

    :param schematic:
    :type schematic: pymclevel.schematic.MCSchematic
    :param remapper:
    :type remapper: dict
    :return:
    """
    for x in range(schematic.Width):
        for y in range(schematic.Height):
            for z in range(schematic.Length):
                block_id = schematic.blockAt(x, y, z)

                try:
                    new_id = max(remapper[block_id], 0)
                except KeyError:
                    logger.error("Id %d not found in remapper, replacing with air", block_id)
                    new_id = 0

                if block_id > 0:
                    logger.debug("%d %d %d: %d -> %d", x, y, z, block_id, new_id)

                schematic.setBlockAt(x, y, z, new_id)


def fix_containers(schematic, remapper):
    """

    :type source: dict
    :param schematic:
    :type schematic: pymclevel.schematic.MCSchematic
    :param remapper:
    :type remapper: dict
    :return:
    """

    for entityTag in schematic.TileEntities:
        entityPos = pymclevel.entity.TileEntity.pos(entityTag)
        block_id = schematic.blockAt(*entityPos)
        for needle in containers:
            if block_id == needle['id']:
                logger.debug("Found container-like TE %s at %d, %d, %d", needle['name'], *entityPos)
                if needle['inv'] is not None:
                    inv = entityTag[needle['inv']]

                    for slot in inv:
                        logger.debug('slot: %s', slot)
                        logger.debug('type(slot): %s', type(slot))
                        try:
                            theslot = inv[slot]
                        except TypeError:
                            theslot = slot

                        if needle['key'] in theslot:
                            new_id = remapper[theslot[needle['key']].value]
                            logger.debug("Found key %s - patching %d -> %d", needle['key'],
                                         theslot[needle['key']].value, new_id)
                            theslot[needle['key']].value = new_id
                else:
                    new_id = remapper[entityTag[needle['key']].value]
                    entityTag[needle['key']].value = new_id


def mark_changed(schematic):
    for chunkX, chunkZ in schematic.allChunks:
        chunk = schematic.getChunk(chunkX, chunkZ)  # :type: pymclevel.FakeChunk
        chunk.chunkChanged()
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--source", help="Path to level.dat of world from which the schematics file was created",
                        dest="source", action="store",
                        default="/home/razumov/MultiMC/instances/BabyTigerServ/minecraft/saves/New World/level.dat")
    parser.add_argument("-t", "--target",
                        help="Path to level.dat of world to which the schematics file will be imported",
                        dest="target", action="store",
                        default="/home/razumov/MultiMC/instances/BabyTigerServ/minecraft/saves/Server World/level.dat")
    parser.add_argument("-B", "--no-backup", help="Don't backup schematics file before patching", dest="backup",
                        action="store_false")
    parser.add_argument("schematic", help="Path to schematics file to patch")

    args = parser.parse_args()

    # DEBUG
    args.schematic = "/home/razumov/.wine/drive_c/users/razumov/Documents/MCEdit/Schematics/Tower.schematic"

    setup_logging()
    logger.info("Loading source world from file {0}".format(args.source))
    source_world = mclevel.fromFile(args.source)
    logger.info("Mapping names to IDs")
    source_idmap = load_idmap(source_world)
    source_world.close()

    qqq = open("source.map", "w")
    import pprint
    qqq.write(pprint.pformat(source_idmap))
    qqq.close()

    logger.info("Loading target world from file {0}".format(args.target))
    target_world = mclevel.fromFile(args.target)
    logger.info("Mapping names to IDs")
    target_idmap = load_idmap(target_world)
    target_world.close()

    qqq = open("target.map", "w")
    import pprint
    qqq.write(pprint.pformat(target_idmap))
    qqq.close()

    logger.info("Building remapper")
    remapper = create_remapper(source_idmap, target_idmap)

    logger.info("Preparing list of containers")
    for c in containers:
        try:
            container_id = target_idmap[c['name']]['Block']
        except (IndexError, KeyError):
            logger.fatal("Container name %s not found in id map!", c['name'], exc_info=True)
            return

        if container_id == -1:
            logger.fatal("Container name %s not found in id map!", c['name'])
            return

        c['id'] = container_id
        if 'meta' not in c:
            c['meta'] = -1

        if 'inv' not in c:
            c['inv'] = None

    if os.path.isfile(args.schematic + '.backup'):
        # os.unlink(args.schematic+'.backup')
        shutil.copy(args.schematic + '.backup', args.schematic)

    sch = mclevel.fromFile(args.schematic)
    logger.info("Remapping blocks")
    remap_schematic(sch, remapper)

    if len(containers) > 0:
        logger.info("Remapping items in container-like objects")
        fix_containers(sch, remapper)

    logger.info("Marking all chunks as changed")
    mark_changed(sch)
    logger.info("Saving")
    sch.saveInPlace()
    logger.info("Done")
    sch.close()


if __name__ == "__main__":
    main()
