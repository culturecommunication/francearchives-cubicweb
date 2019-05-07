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
import os.path as osp

from functools import wraps
from lxml import etree
import unittest

from cubicweb import Binary
from cubicweb import __pkginfo__
from cubicweb.pyramid.test import PyramidCWTest

from cubicweb_francearchives.testutils import PostgresTextMixin, XMLCompMixin
from pgfixtures import setup_module, teardown_module  # noqa


class OAITestMixin(object):

    def oai_component(self, cnx):
        """Return the "oai" component"""
        return self.vreg['components'].select('oai', cnx)


CW_324 = __pkginfo__.numversion < (3, 25)


def no_validate_xml(method):
    """Disable XML schema validation, often because the underlying metadata
    part of the response (RDF, XSD) is not validable (or we don't know how to
    do it).
    """
    @wraps(method)
    def wrapper(self):
        self._validate_xml = False
        self._debug_xml = True
        return method(self)
    return wrapper


class OAIPMHViewsTC(PostgresTextMixin, PyramidCWTest, OAITestMixin):
    _validate_xml = True
    _debug_xml = True
    settings = {
        # to get clean traceback in tests (instead of in an html error page)
        'cubicweb.bwcompat': False,
        # avoid noise in test output (UserWarning: !! WARNING WARNING !! you
        # should stop this instance)
        'cubicweb.session.secret': 'x',
        'cubicweb.auth.authtkt.session.secret': 'x',
        'cubicweb.auth.authtkt.persistent.secret': 'x',
    }

    if CW_324:
        # webapp is initialized with https as url scheme, which trigger usage of https-url instead
        # of base-url in 3.24, but tests below rely in base-url being used.
        @classmethod
        def init_config(cls, config):
            super(PyramidCWTest, cls).init_config(config)
            config.global_set_option('https-url', config['base-url'])

    def assertXmlValid(self, xml_data, xsd_filename, debug=False):
        """Validate an XML file (.xml) according to an XML schema (.xsd)."""
        with open(xsd_filename) as xsd:
            xmlschema = etree.XMLSchema(etree.parse(xsd))
        # Pretty-print xml_data to get meaningfull line information.
        xml_data = etree.tostring(etree.fromstring(xml_data), pretty_print=True)
        root = etree.fromstring(xml_data)
        if debug and not xmlschema.validate(root):
            print(xml_data)
        xmlschema.assertValid(root)

    def oai_request(self, req, **formparams):
        response = self.webapp.get('/oai', formparams)
        self.assertEqual(response.headers['Content-Type'], 'text/xml; charset=UTF-8')
        if self._validate_xml:
            self.assertXmlValid(response.body, self.datapath('OAI-PMH.xsd'),
                                debug=self._debug_xml)
        return response.body

    def create_index(self, cnx, authority):
        ce = cnx.create_entity
        args = {}
        if authority.cw_etype == 'AgentAuthority':
            etype = 'AgentName'
            args['type'] = authority.label.split('_')[1]
        elif authority.cw_etype == 'SubjectAuthority':
            etype = 'Subject'
        else:
            etype = 'Geogname'
        return ce(etype, authority=authority, label=authority.label, **args)

    def create_pnia_agent(self, cnx, label):
        ce = cnx.create_entity
        return ce('AgentAuthority', label=label)

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            # create indexes
            self.fa_loc = ce('LocationAuthority', label=u'location')
            fa_loc_index = self.create_index(cnx, authority=self.fa_loc)
            self.fa_subj = ce('SubjectAuthority', label=u'subject')
            fa_subj_index = self.create_index(cnx, authority=self.fa_subj)
            # findingaid contributors
            self.fa_corpname = self.create_pnia_agent(cnx, u'fa_corpname')
            fa_corpname_index = self.create_index(cnx, authority=self.fa_corpname)
            self.fa_famname = self.create_pnia_agent(cnx, u'fa_famname')
            fa_famname_index = self.create_index(cnx, authority=self.fa_famname)
            self.fa_persname = self.create_pnia_agent(cnx, u'fa_persname')
            fa_persname_index = self.create_index(cnx, authority=self.fa_persname)
            # facomponent contributors
            self.facomp_corpname = self.create_pnia_agent(cnx, u'facomp_corpname')
            facomp_corpname_index = self.create_index(cnx,
                                                      authority=self.facomp_corpname)
            self.facomp_famname = self.create_pnia_agent(cnx, u'facomp_famname')
            facomp_famname_index = self.create_index(cnx,
                                                     authority=self.facomp_famname)
            self.facomp_persname = self.create_pnia_agent(cnx, u'facomp_persname')
            facomp_persname_index = self.create_index(cnx,
                                                      authority=self.facomp_persname)

            #
            service = ce('Service',
                         code=u'FRAD084',
                         name=u'fc_service',
                         category=u'test')
            fadid = ce('Did', unitid=u'maindid',
                       extptr=u'http://www.fa-url',
                       unitdate=u'1701-02-13',
                       startyear=1234,
                       stopyear=1245,
                       origination=u'fa-origination',
                       unittitle=u'maindid-title')
            fcdid = ce('Did', unitid=u'fcdid',
                       unittitle=u'fcdid-title',
                       startyear=1234,
                       stopyear=1245,
                       unitdate=u'1701-03-13',
                       extptr=u'http://www.fc-url',
                       origination=u'fc-origination',
                       repository=u'fc-repo')
            fa_header = ce('FAHeader',
                           titlestmt=u'<div>titlestmt</div>',
                           titleproper=u'titleproper',
                           author=u'<div>fa_author</div>')
            fa = ce('FindingAid', name=u'the-fa',
                    stable_id=u'FRAD084_xxx',
                    eadid=u'FRAD084_xxx',
                    publisher=u'FRAD084',
                    did=fadid,
                    fa_header=fa_header,
                    service=service,
                    fatype=u'fatype',
                    scopecontent=u'<div>fa-scoppecontent</div>',
                    reverse_index=[fa_loc_index, fa_subj_index,
                                   fa_corpname_index, fa_famname_index,
                                   fa_persname_index],
                    acquisition_info=u'acquisition_info')
            facomp = ce('FAComponent',
                        finding_aid=fa,
                        stable_id=u'fc-stable-id',
                        did=fcdid,
                        scopecontent=u'<div>fc-scoppecontent</div>',
                        description=u'<div>fc-descr</div>',
                        digitized_versions=ce(
                            'DigitizedVersion',
                            url=u'http://doa.fr',
                            illustration_url=u'http://doa_image.fr'),
                        reverse_index=[facomp_corpname_index,
                                       facomp_famname_index,
                                       facomp_persname_index])
            savanol = ce('SubjectAuthority', label=u'Jérôme Savonarole')
            ce('Subject', label=u'Jérôme Savonarole', authority=savanol, index=facomp)
            cnx.commit()
            self.fa_eid = fa.eid
            self.facomp_eid = facomp.eid


class OAIEADViewsTC(XMLCompMixin, OAIPMHViewsTC):

    def setup_database(self):
        super(OAIEADViewsTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            fadid = ce('Did', unitid=u'maindid',
                       extptr=u'http://www.fa-url',
                       unitdate=u'1701-02-13',
                       unittitle=u'maindid-title')
            fa_header = ce('FAHeader',
                           titlestmt=u'<div>titlestmt</div>',
                           titleproper=u'titleproper',
                           author=u'<div>fa_author</div>')
            filepath = self.datapath('ir_data/v1/FRAD095_00374.xml')
            with open(filepath, 'r') as f:
                fa_content = f.read()
            fa = ce('FindingAid', name=u'the-fa',
                    stable_id=u'AD05_1563',
                    eadid=u'AD05_1563',
                    publisher=u'AD05',
                    did=fadid,
                    findingaid_support=ce(
                        'File',
                        data_format=u'application/xml',
                        data_name=u'FRAD095_00374.xml',
                        data=Binary(fa_content)),
                    ape_ead_file=ce(
                        'File',
                        data_format=u'application/xml',
                        data_name=u'FRAD095_00374.xml',
                        data=Binary(fa_content)),
                    fa_header=fa_header)
            cnx.commit()
            self.fa_xml_eid = fa.eid

    @no_validate_xml
    def test_identify(self):
        with self.admin_access.web_request() as req:
            result = self.oai_request(req, verb='Identify')
            self.assertIn('<repositoryName>FranceArchives</repositoryName>',
                          result)

    @no_validate_xml
    def test_listmetadaformats_by_identifier(self):
        with self.admin_access.web_request() as req:
            fa = req.find('FindingAid', eid=self.fa_xml_eid).one()
            result = self.oai_request(req, verb='ListMetadataFormats',
                                      identifier=fa.stable_id)
            self.assertIn('<metadataPrefix>ape_ead</metadataPrefix>', result)

    @no_validate_xml
    def test_fa_listrecords(self):
        with self.admin_access.web_request() as req:
            result = self.oai_request(req, verb='ListRecords',
                                      set='findingaid',
                                      metadataPrefix='ape_ead')
            for data in (
                    '<unitdate type="date_affinee">1791 (8 juillet)-1792 (11 mai) </unitdate>',
                    '<unitid countrycode="fr">c11</unitid>'):
                self.assertIn(data, result)

    @no_validate_xml
    def test_fa_ead__oai_ead(self):
        with self.admin_access.web_request() as req:
            fa = req.find('FindingAid', eid=self.fa_eid).one()
            result = etree.ElementTree(
                etree.XML(fa.cw_adapt_to('OAI_EAD').dump())
            ).getroot()
            with open(self.datapath(osp.join('ape_ead_data'), 'fa_ead_adapted.xml'),
                      'r') as expected:
                self.assertXMLEqual(
                    etree.parse(expected).getroot(), result
                )

    @no_validate_xml
    def test_fa_from_xml_export_oai_ead(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            fadid = ce('Did', unitid=u'maindid',
                       extptr=u'http://www.fa-url',
                       unitdate=u'1701-02-13',
                       unittitle=u'maindid-title')
            fa_header = ce('FAHeader',
                           titlestmt=u'<div>titlestmt</div>',
                           titleproper=u'titleproper',
                           author=u'<div>fa_author</div>')
            filepath = u'ape-FRAN_IR_050236.xml'
            with open(self.datapath(osp.join('ape_ead_data'), filepath), 'r') as f:
                fa_content = f.read()
            fa = ce('FindingAid', name=u'the-fa',
                    stable_id=u'FR-AN_FRAN_IR_050236',
                    eadid=u'FR-AN_FRAN_IR_050236',
                    publisher=u'AN',
                    did=fadid,
                    findingaid_support=ce(
                        'File',
                        data_format=u'application/xml',
                        data_name=filepath,
                        data=Binary(fa_content)),
                    ape_ead_file=ce(
                        'File',
                        data_format=u'application/xml',
                        data_name=filepath,
                        data=Binary(fa_content)),
                    fa_header=fa_header)
            cnx.commit()
        with self.admin_access.web_request() as req:
            fa = req.find('FindingAid', eid=fa.eid).one()
            result = fa.cw_adapt_to('OAI_EAD').dump()
            filepath = self.datapath(osp.join('ape_ead_data'), 'ape-FRAN_IR_050236_oai_ead.xml')
            with open(filepath, 'r') as expected:
                self.assertEqual(expected.read(), result)


if __name__ == '__main__':
    unittest.main()