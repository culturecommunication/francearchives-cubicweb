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

from functools import partial

import logging

from sickle.oaiexceptions import NoRecordsMatch
import urllib.parse

from cubicweb_francearchives import get_user_agent
from cubicweb_francearchives.dataimport import (
    log_in_db,
    load_services_map,
    service_infos_from_service_code,
    es_bulk_index,
)
from cubicweb_francearchives.dataimport.sqlutil import (
    no_trigger,
    ead_foreign_key_tables,
)
from cubicweb_francearchives.dataimport.stores import create_massive_store

from cubicweb_francearchives.dataimport.ead import readerconfig
from cubicweb_francearchives.dataimport import oai_ead, oai_dc
from cubicweb_francearchives.dataimport import oai_nomina
from cubicweb_francearchives.dataimport.oai_utils import OAIXMLError
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import (
    generate_ape_ead_from_other_sources,
)


def check_missing_service_infos(cnx, service_infos, base_url):
    missing = {"level", "code", "eid", "title"}.difference(service_infos.keys())
    if missing:
        services_map = load_services_map(cnx)
        if "code" not in service_infos:
            return service_infos
        services_map = load_services_map(cnx)
        service_infos = service_infos_from_service_code(service_infos["code"], services_map)
    if "oai_url" not in service_infos:
        # "oai_url" may be set in case of tests
        service_infos["oai_url"] = base_url
    return service_infos


@log_in_db
def harvest_oai_nomina(
    cnx,
    url,
    service_infos,
    store=None,
    dry_run=False,
    records_limit=None,
    csv_rows_limit=100000,
    rqtask_eid=None,
    log=None,
):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param str url: repository URL
    :param dict service_infos: service information
    :param RQLObjectStore store: store
    :param dict index_policy: indexing policy
    :param bool dry_run: create entities in database
    :param int records_limit: only import limit documents number
    :param int csv_rows_limit: rows limit in the harvested csv file
    :param int rqtask_eid: RqTask eid
    :param Logger log: logger
    """
    if log is None:
        log = logging.getLogger("rq.task")
    if not service_infos["code"]:
        log.exception("harvesting aborted: no service code found")
        return
    if url is None:
        log.error("Harvesting aborted: OAI repository URL is not defined.")
        return
    base_url, params = parse_oai_url(url.strip())
    assert params.pop("verb") == "ListRecords", "import_oai only handles `ListRecords` verb"
    service_infos = check_missing_service_infos(cnx, service_infos, base_url)
    if "code" not in service_infos:
        missing = {"level", "code", "eid", "title"}.difference(service_infos.keys())
        log.error(
            """harvesting aborted: no "{}" information found for service""".format(
                ", ".join(missing)
            )
        )
        return
    headers = {"User-Agent": get_user_agent()}
    if dry_run:
        msg = "Do not import harvested records."
    else:
        msg = "Import harvested records."
    if records_limit is None:
        msg = f"{msg} Harvest the whole repository."
    elif records_limit < 1:
        log.info(f"No record will be harvested: records_limit set to {records_limit}.")
        return []
    else:
        msg = f"{msg} Only harvest {records_limit} records."
    msg += f" Write {csv_rows_limit} rows per file."
    log.info(msg)
    return oai_nomina.OAINominaHarvester(cnx).harvest_records(
        service_infos, headers, records_limit=records_limit, csv_rows_limit=csv_rows_limit, **params
    )


@log_in_db
def import_oai(
    cnx,
    url,
    service_infos,
    store=None,
    index_policy=None,
    dry_run=False,
    records_limit=None,
    log=None,
):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param str url: repository URL
    :param dict service_infos: service information
    :param RQLObjectStore store: store
    :param dict index_policy: indexing policy
    :param bool dry_run: create entities in database
    :param int records_limit: only import limit documents number
    :param Logger log: logger
    """
    if log is None:
        log = logging.getLogger("rq.task")
    if not service_infos["code"]:
        log.exception("harvesting aborted: no service code found: %s", service_infos)
        return
    if not service_infos["eid"]:
        log.exception("harvesting aborted: no service eid found: %s", service_infos)
        return
    if index_policy is None:
        index_policy = {"autodedupe_authorities": "service/normalize"}
    if url is None:
        log.error("Harvesting aborted: OAI repository URL is not defined.")
        return
    base_url, params = parse_oai_url(url.strip())
    log.info(
        "Start harvesting %r with index policy: %r",
        url,
        index_policy["autodedupe_authorities"],
    )
    assert params.pop("verb") == "ListRecords", "import_oai only handles `ListRecords` verb"
    service_infos = check_missing_service_infos(cnx, service_infos, base_url)
    if "code" not in service_infos:
        missing = {"level", "code", "eid", "title"}.difference(service_infos.keys())
        log.error(
            """harvesting aborted: no "{}" information found for service""".format(
                ", ".join(missing)
            )
        )
        return
    headers = {"User-Agent": get_user_agent()}
    autodedupe_authorities = index_policy.get("autodedupe_authorities") if index_policy else None
    if store is None:
        store = create_massive_store(cnx, nodrop=True)
        notrigger_tables = ead_foreign_key_tables(cnx.vreg.schema)
    else:
        notrigger_tables = ()
    cwconfig = store._cnx.vreg.config
    config = readerconfig(
        cwconfig,
        cwconfig.appid,
        log=log,
        esonly=False,
        nodrop=True,
        reimport=True,
        force_delete=True,
        autodedupe_authorities=autodedupe_authorities,
    )
    prefix = params.get("metadataPrefix")
    if prefix == "oai_dc":
        importer = oai_dc.OAIDCImporter(store, config, service_infos, log=log)
    elif prefix in ("ead", "oai_ead"):
        importer = oai_ead.OAIEADImporter(store, config, service_infos, log=log)
    else:
        log.error(f'"{prefix}" harvesting is not available (must be "ead", "oai_ead" or "oai_dc"')
        return
    importer.harvest_records(headers=headers, **params)
    log.info("Start processing harvested documents.")
    with no_trigger(cnx, notrigger_tables, interactive=False):
        # try to reduce the no_trigger connection time
        es_docs = importer.import_records()
    if es_docs:
        log.info("%s IRs have been imported into Postgres.", len(es_docs))
        log.info("Start Es indexing.")
        es_bulk_index(importer.es, es_docs)
        log.info("End Es indexing.")
    else:
        log.info("No valid harvested IR found. No IR has been imported.")

    generate_ape_ead_from_other_sources(cnx)


def parse_oai_url(url):
    url = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(url.query)
    allowed = {"from", "until", "set", "metadataPrefix", "verb"}
    if set(qs) - allowed:
        raise ValueError(
            "Got invalid query parameter(s): {}".format(
                ", ".join(["'{}'".format(param) for param in set(qs) - allowed])
            )
        )
    base_url = url.scheme + "://" + url.netloc + url.path
    params = {k: v[0] for k, v in list(qs.items()) if len(v) == 1}
    return base_url, params


def import_delta(
    cnx,
    repo_eid,
    ignore_last_import=False,
    index_policy=None,
    dry_run=False,
    records_limit=None,
    csv_rows_limit=None,
    log=None,
    reraise=False,
    rqtask_eid=None,
):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param int repo_eid: ID of an OAIRepository entity of interest
    :param bool ignore_last_import: toggle continuing from last successful
    :param dict index_policy: indexing policy
    :param bool dry_run: create or not harvested entities in DB
    :param int records_limit: records limit number to import
    :param int csv_rows_limit: rows limit in the harvested csv file (only for nomina)
    :param Logger log: logger
    :param bool reraise: toggle exception re-raising on/off
    :param int rqtask_eid: RqTask eid

    :raises Exception: if import_oai raises Exception and reraise=True
    """
    repo = cnx.entity_from_eid(repo_eid)
    service = repo.service[0]
    url = repo.url
    if not ignore_last_import:
        _from = repo.last_successful_import
        if _from is not None:
            url += "&from={}".format(_from.strftime("%Y-%m-%d"))
    kwargs = {"oai_repository": repo_eid}
    if rqtask_eid:
        # oaiimport_task relation do not exists in cubicweb_francearchives schema
        kwargs["reverse_oaiimport_task"] = rqtask_eid
    oaitask = cnx.create_entity("OAIImportTask", **kwargs)
    wf = oaitask.cw_adapt_to("IWorkflowable")
    cnx.commit()
    oaitask_failed = False
    formatted_exc = None
    if log is None:
        log = logging.getLogger("rq.task")
    services_map = load_services_map(cnx)
    service_infos = service_infos_from_service_code(service.code, services_map)
    base_url, params = parse_oai_url(url.strip())
    kwargs = dict(
        service_infos=service_infos,
        dry_run=dry_run,
        records_limit=records_limit,
        csv_rows_limit=csv_rows_limit,
        log=log,
    )
    oai_prefix = params.get("metadataPrefix")
    if oai_prefix == "nomina":
        harvest_func = partial(harvest_oai_nomina, cnx, url)
        kwargs["rqtask_eid"] = rqtask_eid
    else:
        harvest_func = partial(import_oai, cnx, url)
        kwargs.pop("csv_rows_limit")
        kwargs["index_policy"] = index_policy
    results = None
    try:
        results = harvest_func(**kwargs)
    except NoRecordsMatch as exception:
        message = "Finished with message {} for {}".format(exception, url)
        log.info(message)
    except OAIXMLError as error:
        oaitask_failed = True
        log.error(error)
    except Exception as error:
        oaitask_failed = True
        log.error(error, exc_info=True)
        log.error("Harvesting aborted.")
    if oaitask_failed:
        wf.fire_transition("wft_faimport_fail", formatted_exc)
        if reraise:
            raise
    else:
        wf.fire_transition("wft_faimport_complete")
    cnx.commit()
    return results
