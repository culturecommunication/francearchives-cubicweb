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
import traceback
import logging

from sickle.oaiexceptions import NoRecordsMatch
import urllib.parse

from cubicweb_francearchives import get_user_agent
from cubicweb_francearchives.dataimport import (
    log_in_db,
    ExtentityWithIndexImporter,
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.sqlutil import no_trigger, ead_foreign_key_tables
from cubicweb_francearchives.dataimport.stores import create_massive_store

from cubicweb_francearchives.dataimport.ead import readerconfig
from cubicweb_francearchives.dataimport import oai_ead, oai_dc, oai_nomina
from cubicweb_francearchives.dataimport.oai_utils import OAIXMLError
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import (
    generate_ape_ead_from_other_sources,
)


@log_in_db
def import_oai(cnx, url, service_infos, store=None, index_policy=None, log=None):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param str url: repository URL
    :param dict service_infos: service information
    :param RQLObjectStore store: store
    :param dict index_policy: indexing policy
    :param Logger log: logger
    """
    if log is None:
        log = logging.getLogger("rq.task")
    if not service_infos["code"]:
        log.exception("harvesting aborted: no service code found")
        return
    if index_policy is None:
        index_policy = {"autodedupe_authorities": "service/normalize"}
    base_url, params = parse_oai_url(url.strip())
    log.info(
        "Start harvesting %r with index policy: %r",
        url,
        index_policy["autodedupe_authorities"],
    )
    assert params.pop("verb") == "ListRecords", "import_oai only handles `ListRecords` verb"
    if store is None:
        store = create_massive_store(cnx, nodrop=True)
        notrigger_tables = ead_foreign_key_tables(cnx.vreg.schema)
    else:
        notrigger_tables = ()
    with no_trigger(cnx, notrigger_tables, interactive=False):
        prefix = params.get("metadataPrefix")
        missing = {"level", "code", "eid", "title"}.difference(service_infos.keys())
        if missing:
            services_map = load_services_map(store._cnx)
            if "code" not in service_infos:
                log.exception(
                    """harvesting aborted: no "{}" information found for service""".format(
                        ", ".join(missing)
                    )
                )
                return
            services_map = load_services_map(store._cnx)
            service_infos = service_infos_from_service_code(service_infos["code"], services_map)
        if "oai_url" not in service_infos:
            # "oai_url" may be set in case of tests
            service_infos["oai_url"] = base_url
        headers = {"User-Agent": get_user_agent()}
        if prefix == "nomina":
            try:
                extentities = oai_nomina.OAINominaImporter(store, log=log).import_records(
                    service_infos, headers, **params
                )
            except Exception:
                formatted_exc = traceback.format_exc()
                log.error(
                    ("Could not import record %s. Harvesting aborted."),
                    formatted_exc,
                )
            import_record_entities(
                cnx,
                extentities,
                store,
                service_infos=service_infos,
                index_policy=index_policy,
                log=log,
            )
        else:
            autodedupe_authorities = (
                index_policy.get("autodedupe_authorities") if index_policy else None
            )
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
        if prefix == "oai_dc":
            importer = oai_dc.OAIDCImporter(store, config, log=log)
        elif prefix in ("ead", "oai_ead"):
            importer = oai_ead.OAIEADImporter(store, config, log=log)
        importer.harvest_records(service_infos, headers=headers, **params)
        generate_ape_ead_from_other_sources(cnx)


def import_record_entities(
    cnx, extentities, store, service_infos=None, index_policy=None, log=None
):
    extid2eid = {}
    if service_infos is not None and service_infos.get("eid"):
        service_eid = service_infos["eid"]
        extid2eid["service-{}".format(service_eid)] = service_eid
    importer = ExtentityWithIndexImporter(
        cnx.vreg.schema, store, extid2eid, index_policy=index_policy, log=log
    )
    importer.import_entities(extentities)
    store.flush()
    store.finish()
    store.commit()


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
    log=None,
    reraise=False,
    rqtask_eid=None,
):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param int repo_eid: ID of an OAIRepository entity of interest
    :param bool ignore_last_import: toggle continuing from last successful
    :param dict index_policy: indexing policy
    import on/off
    :param Logger log: logger
    :param bool reraise: toggle exception re-raising on/off

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
    try:
        import_oai(
            cnx,
            url,
            service_infos=service_infos,
            index_policy=index_policy,
            log=log,
        )
    except NoRecordsMatch as exception:
        message = "Finished with message {} for {}".format(exception, url)
        log.info(message)
    except OAIXMLError as error:
        oaitask_failed = True
        log.error(error)
    except Exception as error:
        oaitask_failed = True
        log.error(error)
        log.error(traceback.format_exc())
    if oaitask_failed:
        wf.fire_transition("wft_faimport_fail", formatted_exc)
        log.exception('exception when importing "%s"', url)
        if reraise:
            raise
    else:
        wf.fire_transition("wft_faimport_complete")
    cnx.commit()
