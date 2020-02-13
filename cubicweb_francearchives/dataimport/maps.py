# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2019
# Contact http://www.logilab.fr -- mailto:contact@logilab.fr
#
# This software is governed by the CeCILL-C license under French law and
# abiding by the rules of distribution of free software. You can use,
# modify and/ or redistribute the software under the terms of the CeCILL-C
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty and the software's author, the holder of the
# economic rights, and the successive licensors have only limited liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading, using, modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean that it is complicated to manipulate, and that also
# therefore means that it is reserved for developers and experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systemsand/or
# data to be ensured and, more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL-C license and that you accept its terms.
#
import os
import os.path as osp
import csv
import sys
from glob import glob

from collections import OrderedDict

from cubicweb.dataimport.importer import ExtEntity, ExtEntitiesImporter
from cubicweb.dataimport.stores import RQLObjectStore
from cubicweb_francearchives import init_bfss

META_MAPS = "maps.csv"


def get_extid(etype, value):
    return "{}-{}".format(etype, value)


def load_meta(filepath):
    fieldnames = OrderedDict(
        [
            ("Nom_csv", "fname"),
            ("Titre_document", "title"),
            ("Titre_carte", "map_title"),
            ("Rubrique", ("children", "object")),
        ]
    )
    data = {}
    with open(filepath) as csvfile:
        reader = csv.DictReader(csvfile, delimiter=",", fieldnames=list(fieldnames.keys()))
        for line in reader:
            entry = {fieldnames[key]: value if value else None for key, value in line.items()}
            fname = entry.pop("fname")
            data[fname] = entry
    return data


def build_extentities(directory, ref_data, maps_meta):
    extentities = []
    for idx, filepath in enumerate(glob(osp.join(directory, "*.csv"))):
        fname = osp.basename(filepath)
        if fname == META_MAPS:
            continue
        values = maps_meta.get(fname)
        if values is None:
            print('Skip "%s" file as no associated ' "entry found in maps.csv") % fname
            continue
        with open(filepath, "rb") as csvfile:
            filecontent = csvfile.read()
        extid = get_extid("Map", idx)
        meta_extid = get_extid("Metadata", idx)
        extentities.append(ExtEntity("Metadata", meta_extid, {"title": {values["title"]}}))
        section_extid = get_extid("Section", values[("children", "object")])
        values[("children", "object")] = section_extid
        values = {k: {v} for k, v in values.items()}
        values.update({"map_file": {filecontent}, "metadata": {meta_extid}})
        thumbnail = fname.replace("csv", "png")
        thumbnail_path = osp.join(directory, thumbnail)
        if osp.isfile(thumbnail_path):
            file_extid = "File-{}".format(extid)
            extentities.append(
                ExtEntity(
                    "File",
                    file_extid,
                    {
                        "title": {str(thumbnail)},
                        "data": {open(thumbnail_path, "rb").read()},
                        "data_name": {str(thumbnail)},
                        "data_format": {"image/png"},
                    },
                )
            )
            img_extid = "Image-{}".format(extid)
            extentities.append(
                ExtEntity(
                    "Image",
                    img_extid,
                    {
                        "image_file": {file_extid},
                        "caption_format": {"text/html"},
                        "caption": {"Vignette"},
                    },
                )
            )
            values["map_image"] = {img_extid}
        else:
            print('Thumbnail "%s" file does not exist.' % thumbnail_path)
        extentities.append(ExtEntity("Map", extid, values))
    return extentities


def import_maps(cnx, directory):
    meta_maps_filepath = osp.join(directory, META_MAPS)
    if not os.path.isfile(meta_maps_filepath):
        print('No "{}" found. Import aborted'.format(meta_maps_filepath))
        sys.exit(1)
    init_bfss(cnx.repo)
    maps_meta = load_meta(meta_maps_filepath)
    with cnx.allow_all_hooks_but("es"):
        ref_data = {}
        for title, eid in cnx.execute("Any L, X WHERE X is Section, X title L"):
            if title:
                ref_data[get_extid("Section", title)] = eid
        store = RQLObjectStore(cnx)
        importer = ExtEntitiesImporter(cnx.vreg.schema, store, ref_data)
        importer.import_entities(build_extentities(directory, ref_data, maps_meta))
        store.flush()
        store.commit()
        store.finish()
