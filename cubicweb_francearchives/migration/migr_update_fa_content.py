# flake8: noqa
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
"""
This script updates <etype><attributes> :

 - FindingAid: "accessrestrict", "userestrict", "additional_resources"

 - FaComonent: "additional_resources"

"""


from cubicweb_francearchives.dataimport import ead
from cubicweb_francearchives.dataimport.importer import import_filepaths

from cubicweb_francearchives.dataimport.sqlutil import no_trigger


class FAReader(ead.Reader):
    """custom reader that skips all creation queries except for
    DigitizedVersions
    """

    def __init__(self, config, store):
        super(FAReader, self).__init__(config, store)
        self.add_rel = lambda self, eidfrom, rtype, eid_to: None

    def create_entity(self, etype, attrs):
        if "stable_id" in attrs:
            eid = self.stable_id_to_eid(attrs["stable_id"])
        if etype == "FindingAid":
            params = {
                k: attrs.get(k)
                for k in (
                    "accessrestrict",
                    "userestrict",
                    "additional_resources",
                    "description",
                    "stable_id",
                )
            }
            if any(params.values()):
                self.store.sql(
                    "UPDATE cw_findingaid "
                    "SET cw_additional_resources=%(additional_resources)s, "
                    "cw_userestrict=%(userestrict)s, "
                    "cw_accessrestrict=%(accessrestrict)s, "
                    "cw_description=%(description)s "
                    "WHERE cw_stable_id=%(stable_id)s",
                    params,
                )
        elif etype == "FAComponent":
            params = {k: attrs.get(k) for k in ("additional_resources", "description", "stable_id")}
            if any(params.values()):
                self.store.sql(
                    "UPDATE cw_facomponent "
                    "SET cw_additional_resources=%(additional_resources)s, "
                    "cw_description=%(description)s "
                    "WHERE cw_stable_id=%(stable_id)s",
                    params,
                )
        elif etype == "EsDocument":
            self.store.sql(
                "UPDATE cw_esdocument SET cw_doc = %(doc)s WHERE cw_entity = %(entity)s", attrs
            )
            eid = None
        else:
            eid = None
        attrs["eid"] = eid
        return attrs

    def create_index(self, infos, target):
        # override create_index and make it a noop
        pass

    def push_indices(self):
        # override push_indices and make it a noop
        pass


def files_to_reimport(cnx):
    rset = cnx.execute(
        "DISTINCT Any FSPATH(FID) "
        "WHERE F findingaid_support FI, FI data FID, "
        'FI data_format "application/xml"'
    )
    for (fspath,) in rset:
        fspath = fspath.getvalue()
        yield fspath


def reimport_content(cnx):
    importconfig = ead.readerconfig(
        cnx.vreg.config, cnx.vreg.config.appid, nodrop=True, esonly=False
    )
    importconfig["readercls"] = FAReader
    importconfig["update_imported"] = True
    filepaths = []
    print("analyzing database to extract which files should be reimported...")
    for fspath in files_to_reimport(cnx):
        filepaths.append(fspath)
    print("\t=> {} files must be reimported".format(len(filepaths)))
    if len(filepaths) == 0:
        return
    with no_trigger(cnx, tables=("cw_findingaid", "cw_facomponent"), interactive=False):
        import_filepaths(cnx, filepaths, importconfig)


if __name__ == "__main__":
    reimport_content(cnx)
