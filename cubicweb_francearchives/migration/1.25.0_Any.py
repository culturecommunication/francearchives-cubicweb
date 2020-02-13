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

add_attribute("Subject", "type")
add_attribute("Geogname", "type")

# do the drop attributes in the total reimport
for attr in ("genreform", "function", "occupation"):
    drop_attribute("FindingAid", attr)
    drop_attribute("FAComponent", attr)

rql('SET X type "subject" WHERE X is Subject, X type NULL')
rql('SET X role "index" WHERE X is Subject, X role NULL')
rql('SET X role "index" WHERE X is Geogname, X role NULL')
rql('SET X role "index" WHERE X is AgentName, X role NULL')

for etype in ("Subject", "Geogname", "AgentName"):
    sync_schema_props_perms(etype)
