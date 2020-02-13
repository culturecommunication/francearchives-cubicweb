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
from uuid import uuid4
from datetime import datetime

from glamconv.cli.commands import batch_ead2_to_ape

from cubicweb import Binary

from cubicweb_francearchives.dataimport.ead import compute_ape_relpath

add_cube("oaipmh")
add_attribute("FindingAid", "ape_ead_file")


def generate_ape_ead(cnx):
    appfiles_dir = cnx.vreg.config["appfiles-dir"]
    batch_arguments = []
    fa2apepath = {}
    for fa_eid, fspath, service_code in cnx.execute(
        "Any X, FSPATH(D), SC WHERE X findingaid_support F, F data D, "
        'F data_format "application/xml", X service S, S code SC'
    ):
        input_path = fspath.getvalue()
        output_path = osp.join(
            appfiles_dir, compute_ape_relpath(input_path, {"code": service_code})
        )
        fa2apepath[fa_eid] = output_path
        batch_arguments.append((input_path, output_path))
    batch_ead2_to_ape(batch_arguments)
    # now generate ape-XML for PDF, dc_based and OAI based finding aids
    other_fas = cnx.execute(
        """
      (Any X, XID WHERE X eadid XID, NOT EXISTS(X findingaid_support F))
    UNION
      (Any X, XID WHERE X eadid XID, X findingaid_support F, NOT F data_format "application/xml")
    """
    )
    for fa in other_fas.entities():
        service_code = fa.service[0].code
        output_path = osp.join(appfiles_dir, compute_ape_relpath(fa.eadid, {"code": service_code}))
        xml_dumper = fa.cw_adapt_to("OAI_EAD")
        if xml_dumper is not None:
            ape_xml = xml_dumper.dump()
            output_dir = osp.dirname(output_path)
            if not osp.isdir(output_dir):
                os.makedirs(output_dir)
            with open(output_path, "w") as outf:
                outf.write(ape_xml)
            fa2apepath[fa.eid] = output_path

    cnx.transaction_data["fs_importing"] = True
    # File must exist on disk, even if fs_importing is True because
    # ``source.storages.BFSS.entity_added()`` will try to read file from
    # disk to build the Binary object.
    with cnx.deny_all_hooks_but():
        _now = datetime.now()
        admin = cnx.find("CWUser", login="admin").one()
        for fa_eid, output_path in list(fa2apepath.items()):
            cnx.drop_entity_cache()
            if osp.isfile(output_path):
                uuid = str(uuid4().hex)
                ape_file = cnx.create_entity(
                    "File",
                    cwuri=uuid,
                    modification_date=_now,
                    creation_date=_now,
                    created_by=admin,
                    owned_by=admin,
                    data=Binary(output_path),
                    uuid=uuid,
                    data_format="application/xml",
                    data_name=osp.basename(output_path).decode("utf-8"),
                    reverse_ape_ead_file=fa_eid,
                )
    cnx.commit()


if confirm("generate ape ead files ?"):
    generate_ape_ead(cnx)
