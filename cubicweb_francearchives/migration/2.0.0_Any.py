# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2019
# Contact http://www.logilab.fr -- mailto:contact@logilab.fr
#
# flake8: noqa
# -*- coding: utf-8 -*-
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

# this is the migration from cubicweb_file/migration/2.1.0_Any.py
# which we want not pass in order to not rewrite data_hash with {sha1}
# prefix but with the old data_sha1hex value

with cnx.allow_all_hooks_but("es", "sync", "varnish"):
    subclasses = False
    is_rel = "is"

    if confirm("Also handle entity types that inherit from File?"):
        subclasses = True
        is_rel = "is_instance_of"

    add_attribute("File", "data_hash")
    if subclasses:
        for etype in schema["File"].specialized_by(recursive=True):
            add_attribute(etype.type, "data_hash")

    # do not set {sha1} prefix unlike the cubicweb_file/migration/2.1.0_Any.py
    rql(
        "SET X data_hash H WHERE X %(rel)s File, "
        "X data_sha1hex H, "
        "NOT X data_sha1hex NULL" % {"rel": is_rel}
    )

    drop_attribute("File", "data_sha1hex")
    if subclasses:
        for etype in schema["File"].specialized_by(recursive=True):
            drop_attribute(etype.type, "data_sha1hex")

    commit()

change_relation_props("Circular", "attachment", "File", cardinality="*?")
