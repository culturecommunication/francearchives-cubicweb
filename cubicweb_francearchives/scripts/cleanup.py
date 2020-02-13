# -*- coding: utf-8 -*-
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


# standard library imports
import csv
import sys

# third party imports
# CubicWeb specific imports
# library specific imports
from cubicweb_francearchives.dataimport import clean


"""Script to clean authority labels (related to #67658751).

Usage: cubicweb-ctl fa_ed cleanup.py [FILE]...[FILE]

Calling this script without any arguments leads to it generating
an output file for each authority type containing the cleaned
labels. Calling this script with one or more input files leads
to it updating the database with any labels it finds in the
CSV files.

The CSV file is comma-separated and contains the fields
'identifiant', 'URI_autorite', 'libelle_ancien', 'libelle_nouveau',
'autorite', of which 'identifiant', 'libelle_nouveau' and 'autorite'
are used when updating the database."""


AUTHORITIES = {
    "agent": "cw_agentauthority",
    "location": "cw_locationauthority",
    "subject": "cw_subjectauthority",
}


def read_out(cnx, authority):
    rows = cnx.system_sql(
        "SELECT cw_eid,cw_label FROM {authority}".format(authority=AUTHORITIES[authority])
    )
    return rows


def write_back(cnx, authority, rows):
    cnx.cnxset.cu.executemany(
        "UPDATE {authority} SET cw_label=%s WHERE cw_eid=%s".format(
            authority=AUTHORITIES[authority]
        ),
        rows,
    )
    cnx.commit()


def export_clean(cnx):
    base_url = cnx.base_url()
    for authority in AUTHORITIES:
        rows = list(read_out(cnx, authority))
        eids = [eid for eid, _ in rows]
        old = [label for _, label in rows]
        new = clean(*old)
        urls = [
            "{base_url}{authority}/{eid}".format(base_url=base_url, authority=authority, eid=eid)
            for eid in eids
        ]
        with open("/tmp/{}_clean.csv".format(authority), "w") as fp:
            writer = csv.writer(fp)
            writer.writerow(
                ("identifiant", "URI_autorite", "libelle_ancien", "libelle_nouveau", "autorite")
            )
            writer.writerows(
                row + (authority,) for row in zip(eids, urls, old, new) if row[2] != row[3]
            )


def import_clean(cnx, *args):
    for filename in args:
        with open(filename) as fp:
            reader = csv.reader(fp)
            rows = [row for row in reader][1:]
            authority = rows[0][4]
            rows = [(row[3], row[0]) for row in rows]
            write_back(cnx, authority, rows)


def main(cnx, *args):
    if args:
        import_clean(cnx, *args)
    else:
        export_clean(cnx)


if __name__ == "__main__":
    main(cnx, *sys.argv[4:])  # noqa
