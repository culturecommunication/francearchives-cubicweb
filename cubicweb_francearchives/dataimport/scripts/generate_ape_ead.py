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

import mimetypes
import os
import os.path as osp
from uuid import uuid4

from cubicweb import Binary


from cubicweb_francearchives import init_bfss

from cubicweb_francearchives.dataimport.ead import (
    generate_ape_ead_file_from_xml,
    decode_filepath,
    compute_ape_relpath,
)
from cubicweb_francearchives.dataimport.eadreader import preprocess_ead
from cubicweb_francearchives.dataimport import load_services_map


def create_file(cnx, filepath):
    cnx.transaction_data["fs_importing"] = True
    ufilepath = osp.abspath(decode_filepath(filepath))
    basepath = osp.basename(ufilepath)
    return cnx.create_entity(
        "File",
        **{
            "title": basepath,
            "data": Binary(ufilepath.encode("utf-8")),
            "data_format": str(mimetypes.guess_type(filepath)[0]),
            "data_name": basepath,
            "uuid": str(uuid4().hex),
        }
    )


def get_service_infos(services_map, service_code):
    infos = {
        "code": service_code,
        "name": service_code,
        "eid": None,
    }
    if service_code in services_map:
        service = services_map[service_code]
        infos.update(
            {"eid": service.eid, "name": service.publisher(),}
        )
    return infos


def regenerate_all_ape_ead_from_xml(cnx):
    """generate all ape_ead_files from xml"""
    rset = cnx.execute(
        "Any X, N, SI, FSPATH(D), FSPATH(AD), CS "
        "WHERE X findingaid_support F, "
        "X stable_id SI, X name N, F data D, "
        "X ape_ead_file AF?, AF data AD, "
        "X service S, S code CS, "
        'F data_format "application/xml"'
    )
    print("regenerate_all_ape_ead_from_xml", rset.rowcount)
    if rset:
        _generate_ape_ead_from_xml(cnx, rset)


def generate_ape_ead_from_xml(cnx):
    """generate only missing ape_ead_files from xml"""
    rset = cnx.execute(
        "Any X, N, SI, FSPATH(D), NULL, CS "
        "WHERE X findingaid_support F, "
        "X stable_id SI, X name N, F data D, "
        "NOT EXISTS(X ape_ead_file AF), "
        "X service S, S code CS, "
        'F data_format "application/xml"'
    )
    if rset:
        _generate_ape_ead_from_xml(cnx, rset)


def regenerate_all_ape_ead_xml_for_service(cnx, service_code):
    """generate all ape_ead_files for a given service from xml"""
    rset = cnx.execute(
        (
            "Any X, N, SI, FSPATH(D), FSPATH(AD), CS "
            "WHERE X findingaid_support F, "
            "X stable_id SI, X name N, F data D, "
            "X ape_ead_file AF?, AF data AD, "
            "X service S, S code CS, S code %(c)s, "
            'F data_format "application/xml"'
        ),
        {"c": service_code},
    )
    print("regenerate_all_ape_ead_xml_for_service", rset.rowcount)
    if rset:
        _generate_ape_ead_from_xml(cnx, rset)


def generate_ape_ead_xml_from_eids(cnx, eids):
    """generate all ape_ead_files for given eids from xml"""
    rset = cnx.execute(
        """
        (Any X, N, XID, NULL, CS
         WHERE X eadid XID, X name N,
         X eid IN (%(e)s),
         X service S?, S code CS,
         NOT EXISTS(X findingaid_support F))
        UNION
         (Any X, N, XID, NULL, CS
          WHERE X eadid XID,
          X eid IN (%(e)s),
          X findingaid_support F, X name N,
          X service S?, S code CS,
          NOT F data_format "application/xml")
    """
        % {"e": ", ".join(eids)}
    )
    if rset:
        _generate_ape_ead_from_other_sources(cnx, rset)
    rset = cnx.execute(
        (
            "Any X, N, SI, FSPATH(D), NULL, CS "
            "WHERE X eid IN (%(e)s),"
            "X findingaid_support F, "
            "X stable_id SI, X name N, F data D, "
            "X service S?, S code CS, "
            'F data_format "application/xml"'
        )
        % {"e": ", ".join(eids)}
    )
    if rset:
        _generate_ape_ead_from_xml(cnx, rset)


def _generate_ape_ead_from_xml(cnx, rset):
    services_map = load_services_map(cnx)
    appfiles = cnx.vreg.config["appfiles-dir"]
    for (fa_eid, fa_name, fa_stable_id, fspath, ape_ead_fspath, service_code) in rset:
        xml_path = fspath.getvalue()
        try:
            # if not (osp.exists(xml_path) and osp.isfile(xml_path)):
            tree = preprocess_ead(xml_path)
        except Exception as ex:
            print(
                "[ape_ead] Could not generate ape_ead_file for {f} : {e}".format(
                    e=ex, f=fa_stable_id
                )
            )
            continue
        service_infos = get_service_infos(services_map, service_code)
        ape_ead_fspath = ape_ead_fspath.getvalue() if ape_ead_fspath else None
        ape_filepath = ape_ead_fspath or osp.join(
            appfiles, compute_ape_relpath(cnx, fa_name, service_infos)
        )
        generate_ape_ead_file_from_xml(cnx, tree, service_infos, fa_stable_id, ape_filepath)
        if not ape_ead_fspath:
            ape_file = create_file(cnx, ape_filepath)
            cnx.execute(
                "SET X ape_ead_file F WHERE X eid %(x)s, F eid %(f)s",
                {"x": fa_eid, "f": ape_file.eid},
            )
            cnx.commit()


def regenerate_all_ape_ead_from_other_sources(cnx):
    """regenerate all ape_ead_files from other sources"""
    rset = cnx.execute(
        """
        (Any X, N, XID, FSPATH(AD), CS
         WHERE X eadid XID, X name N,
         X ape_ead_file AF?, AF data AD,
         X service S, S code CS,
         NOT EXISTS(X findingaid_support F))
        UNION
         (Any X, N, XID, FSPATH(AD), CS
          WHERE X eadid XID,
          X findingaid_support F, X name N,
          X ape_ead_file AF?, AF data AD,
          X service S, S code CS,
          NOT F data_format "application/xml")
        """
    )
    print("regenerate_all_ape_ead_from_other_sources", rset.rowcount)
    if rset:
        _generate_ape_ead_from_other_sources(cnx, rset)


def regenerate_all_ape_ead_other_for_service(cnx, service_code):
    """regenerate all ape_ead_files for a given service from other sources"""
    rset = cnx.execute(
        """
        (Any X, N, XID, FSPATH(AD), CS
         WHERE X eadid XID, X name N,
         X service S, S code CS, S code %(c)s,
         X ape_ead_file AF?, AF data AD,
         NOT EXISTS(X findingaid_support F))
        UNION
         (Any X, N, XID, FSPATH(AD), CS
          WHERE X eadid XID, X name N,
          X ape_ead_file AF?, AF data AD,
          X findingaid_support F,
          NOT F data_format "application/xml",
          X service S, S code CS, S code %(c)s)
        """,
        {"c": service_code},
    )
    if rset:
        _generate_ape_ead_from_other_sources(cnx, rset)


def generate_ape_ead_from_other_sources(cnx):
    """generate only missing ape_ead_files from other sources"""
    rset = cnx.execute(
        """Any X, N, XID, NULL, CS
        WHERE X eadid XID,
        X findingaid_support F, X name N,
        NOT EXISTS(X ape_ead_file AF),
        X service S?, S code CS
        """
    )
    if rset:
        _generate_ape_ead_from_other_sources(cnx, rset)


def generate_ape_ead_other_sources_from_eids(cnx, eids):
    """generate all ape_ead_files for given eids from other source"""
    rset = cnx.execute(
        """
        (Any X, N, XID, NULL, CS
         WHERE X eadid XID, X name N,
         X eid IN (%(e)s),
         NOT EXISTS(X ape_ead_file AF),
         X service S?, S code CS,
         NOT EXISTS(X findingaid_support F))
        UNION
         (Any X, N, XID, NULL, CS
          WHERE X eadid XID,
          X eid IN (%(e)s),
          X findingaid_support F, X name N,
          NOT EXISTS(X ape_ead_file AF),
          X service S?, S code CS,
          NOT F data_format "application/xml")
    """
        % {"e": ", ".join(eids)}
    )
    if rset:
        _generate_ape_ead_from_other_sources(cnx, rset)


def _generate_ape_ead_from_other_sources(cnx, rset):
    services_map = load_services_map(cnx)
    appfiles = cnx.vreg.config["appfiles-dir"]
    for (fa, fa_name, fa_eadid, ape_ead_fspath, service_code) in rset.iter_rows_with_entities():
        service_infos = get_service_infos(services_map, service_code)
        ape_ead_fspath = ape_ead_fspath.getvalue() if ape_ead_fspath else None
        ape_filepath = ape_ead_fspath or osp.join(
            appfiles, compute_ape_relpath(cnx, fa_eadid, service_infos)
        )
        try:
            ape_xml = fa.cw_adapt_to("OAI_EAD").dump().decode("utf-8")
        except Exception as ex:
            print(
                "[ape-ead oai] Could not generate ape_ead_file for {f} : {e}".format(
                    e=ex, f=fa_eadid
                )
            )
            continue
        # important! release cw cache cache
        fa.cw_clear_all_caches()
        cnx.drop_entity_cache()
        try:
            output_dir = osp.dirname(ape_filepath)
            if not osp.isdir(output_dir):
                os.makedirs(output_dir)
            with open(ape_filepath, "w") as outf:
                outf.write(ape_xml)
        except Exception as ex:
            print("[generate_ape_ead_from_other_sources] Error {}".format(ex))
            continue
        if not ape_ead_fspath:
            ape_file = create_file(cnx, ape_filepath)
            cnx.execute(
                "SET X ape_ead_file F WHERE X eid %(x)s, F eid %(f)s",
                {"x": fa.eid, "f": ape_file.eid},
            )
            cnx.commit()


def generate_ape_ead_files(cnx, allfiles, service_code=None):
    init_bfss(cnx.repo)
    if service_code:
        regenerate_all_ape_ead_xml_for_service(cnx, service_code)
        regenerate_all_ape_ead_other_for_service(cnx, service_code)
        return
    if allfiles:
        regenerate_all_ape_ead_from_xml(cnx)
        regenerate_all_ape_ead_from_other_sources(cnx)
    else:
        generate_ape_ead_from_xml(cnx)
        generate_ape_ead_from_other_sources(cnx)
