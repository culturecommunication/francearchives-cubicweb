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
import unittest

from cubicweb import Binary
from cubicweb.devtools import testlib


class EntitiesTC(testlib.CubicWebTC):

    def test_map(self):
        with self.admin_access.cnx() as cnx:
            title = (u'Etat civil et registres '
                     u'paroissiaux numérisés et mis en ligne')
            with open(self.datapath('maps', 'Carte_Etat-civil.csv')) as f:
                data = Binary(f.read())
                cw_map = cnx.create_entity(
                    'Map', title=title,
                    map_file=data,
                    top_content=u'<h1>Top</h1>')
                cnx.commit()
            data = cw_map.data()
            expected = {
                u'url': u'http://www.archives-numerisees.ain.fr/archives/recherche/etatcivil/n:88',
                u'color': u'#044694',
                u'code': u'01',
                u'legend': (u"Archives ayant mis en ligne l'\xe9tat civil, "
                            u"int\xe9gralement ou partiellement ")}

            self.assertItemsEqual(data[0], expected)

    def test_html_integrity(self):
        with self.admin_access.cnx() as cnx:
            content = u'''<div style="background: red"
            javascript="onclick('alert')">style</div>'''
            article = cnx.execute(
                'INSERT BaseContent X : X title %(t)s, '
                'X content %(c)s ', {'t': u'title', 'c': content}).one()
            cnx.commit()
            self.assertEqual(article.content,
                             u'''<div style="background: red">style</div>''')
            content = u'''<div style="color: red"
            javascript="onclick('alert')">style</div>'''
            cnx.execute('SET X content %(c)s WHERE X eid %(e)s',
                        {'e': article.eid, 'c': content})
            cnx.commit()
            article = cnx.find('BaseContent', eid=article.eid).one()
            self.assertEqual(article.content,
                             u'''<div style="color: red">style</div>''')

    def test_html_iframe_kept(self):
        """ensure <iframe> tags are kept"""
        with self.admin_access.cnx() as cnx:
            content = (u'<h1>Hello</h1>'
                       u'<iframe width="560" height="315" '
                       u'src="https://www.youtube.com/embed/T3nEhn4g1iU"'
                       u' frameborder="0" allowfullscreen></iframe>')
            article = cnx.execute(
                'INSERT BaseContent X : X title %(t)s, '
                'X content %(c)s ', {'t': u'title', 'c': content}).one()
            cnx.commit()
            self.assertEqual(article.content, content)

    def test_anom_bounce_url(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity('Did', unitid=u'maindid',
                                      unittitle=u'maindid-title')
            fcdid = cnx.create_entity('Did', unitid=u'fcdid',
                                      unittitle=u'fcdid-title',
                                      startyear=1234,
                                      stopyear=1245,
                                      origination=u'fc-origination',
                                      repository=u'fc-repo',
                                      extptr=u'ark:/61561/bo755dxx3y5z')
            fa = cnx.create_entity('FindingAid', name=u'the-fa',
                                   stable_id=u'FRANOM_xxx',
                                   eadid=u'FRANOM_xxx',
                                   publisher=u'FRAMP<',
                                   did=fadid,
                                   fa_header=cnx.create_entity('FAHeader'))
            facomp = cnx.create_entity('FAComponent',
                                       finding_aid=fa,
                                       stable_id=u'fc-stable-id',
                                       did=fcdid,
                                       scopecontent=u'fc-scoppecontent',
                                       description=u'fc-descr')
            self.assertEqual(
                facomp.bounce_url,
                u'http://anom.archivesnationales.culture.gouv.fr/ark:/61561/bo755dxx3y5z'
            )

    def test_bounce_url_unitid(self):
        with self.admin_access.cnx() as cnx:
            search_form_url = (u'http://archives.lille.fr/search?preset=6&query=&quot;'
                               u'%(unitid)s&quot&search-query=&view=classification&search-query=1')
            serviceid = cnx.create_entity(
                'Service', category=u's1',
                short_name=u'Commune de Lille', code=u'FRAM059350',
                search_form_url=search_form_url
            ).eid
            fadid = cnx.create_entity('Did', unitid=u'maindid',
                                      unittitle=u'maindid-title')
            fa = cnx.create_entity('FindingAid', name=u'the-fa',
                                   stable_id=u'FRANOM_xxx',
                                   eadid=u'FRANOM_xxx',
                                   publisher=u'FRAMP<',
                                   did=fadid, service=serviceid,
                                   fa_header=cnx.create_entity('FAHeader'))
            self.assertEqual(fa.bounce_url,
                             search_form_url % {'unitid': fadid.unitid})

    def test_bounce_url_eadid(self):
        with self.admin_access.cnx() as cnx:
            search_form_url = (u'https://www.archives71.fr/arkotheque/inventaires/'
                               u'ead_ir_consult.php?ref=%(eadid)s')
            serviceid = cnx.create_entity(
                'Service', category=u's1',
                short_name=u'CHALON-SUR-SAÔNE', code=u'FRAD071',
                search_form_url=search_form_url
            ).eid
            fadid = cnx.create_entity('Did', unitid=u'maindid',
                                      unittitle=u'maindid-title')
            fa = cnx.create_entity('FindingAid', name=u'the-fa',
                                   stable_id=u'FRAD071_2098W',
                                   eadid=u'FRAD071 1F 1-168_2F 1-568',
                                   publisher=u'FRAD071<',
                                   did=fadid, service=serviceid,
                                   fa_header=cnx.create_entity('FAHeader'))
            self.assertEqual(fa.bounce_url,
                             search_form_url % {'eadid': fa.eadid.replace(' ', '+')})

    def test_section(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            image = cnx.create_entity(
                'Image',
                caption=u'image-caption',
                description=u'alt',
                image_file=ce('File',
                              data=Binary('some-image-data'),
                              data_name=u'image-name.png',
                              data_format=u'image/png'))
            section = ce('Section', title=u'sect-1', name=u'sect-1',
                         section_image=image)
            cnx.commit()
            self.assertEqual(section.image.eid, image.eid)
            image_url = image.image_file[0].cw_adapt_to(
                "IDownloadable").download_url()
            self.assertEqual(section.illustration_url, image_url)
            self.assertEqual(section.illustration_alt, 'alt')

    def test_richstring_attrs(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            section = ce('Section', title=u'sect-1', name=u'sect-1',
                         content=u'<a href="www.toto.fr" title="toto">toto</a>')
            cnx.commit()
            self.assertEqual(section.richstring_attrs, ['content'])
            self.assertEqual(section.content,
                             u'<a href="www.toto.fr" rel="nofollow noopener '
                             u'noreferrer" target="_blank">toto</a>')
            self.assertEqual(section.printable_value('content'),
                             u'<a href="www.toto.fr" rel="nofollow noopener '
                             u'noreferrer" target="_blank" title="toto - New window">toto</a>')


class BreadcrumbTests(testlib.CubicWebTC):

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                'Service', category=u's1', short_name=u'AD de la Marne', code=u'FRAD051'
            ).eid
            cnx.commit()

    def test_person_breadcrumbs(self):
        with self.admin_access.cnx() as cnx:
            person = cnx.create_entity(
                'Person',
                name=u'Durand',
                forenames=u'Jean',
                publisher=u'FRAD051',
                service=self.service
            )
            ibc = person.cw_adapt_to('IBreadCrumbs')
            self.assertEqual(
                ibc.breadcrumbs(), [
                    ('http://testing.fr/cubicweb/', u'Home'),
                    ('http://testing.fr/cubicweb/inventaires/FRAD051',
                     u'AD de la Marne'), (None, u'Jean Durand')
                ]
            )

    def test_inventory_breadcrumbs(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity('Did', unitid=u'maindid', unittitle=u'maindid-title')
            fa = cnx.create_entity(
                'FindingAid',
                name=u'the-fa',
                stable_id=u'FRAD051_xxx',
                eadid=u'FRAD051_xxx',
                publisher=u'FRAD051',
                service=self.service,
                did=fadid,
                fa_header=cnx.create_entity('FAHeader')
            )
            ibc = fa.cw_adapt_to('IBreadCrumbs')
            self.assertEqual(
                ibc.breadcrumbs(), [
                    ('http://testing.fr/cubicweb/', u'Home'),
                    ('http://testing.fr/cubicweb/inventaires/FRAD051',
                     u'AD de la Marne'), (None, u'Inventory - maindid')
                ]
            )

    def test_inventory_breadcrumbs_noservice(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity('Did', unitid=u'maindid', unittitle=u'maindid-title')
            fa = cnx.create_entity(
                'FindingAid',
                name=u'the-fa',
                stable_id=u'FRAD051_xxx',
                eadid=u'FRAD051_xxx',
                publisher=u'FRAD051',
                did=fadid,
                fa_header=cnx.create_entity('FAHeader')
            )
            ibc = fa.cw_adapt_to('IBreadCrumbs')
            self.assertEqual(
                ibc.breadcrumbs(),
                [('http://testing.fr/cubicweb/', u'Home'), (None, u'Inventory - maindid')]
            )

    def test_facomponent_breadcrumbs(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity('Did', unitid=u'maindid', unittitle=u'maindid-title')
            fcdid = cnx.create_entity(
                'Did',
                unitid=u'fcdid',
                unittitle=u'fcdid-title',
                startyear=1234,
                stopyear=1245,
                origination=u'fc-origination',
                repository=u'fc-repo',
                extptr=u'ark:/61561/bo755dxx3y5z'
            )
            fa = cnx.create_entity(
                'FindingAid',
                name=u'the-fa',
                stable_id=u'FRAD051_xxx',
                eadid=u'FRAD051_xxx',
                publisher=u'FRAD051',
                service=self.service,
                did=fadid,
                fa_header=cnx.create_entity('FAHeader')
            )
            facomp = cnx.create_entity(
                'FAComponent',
                finding_aid=fa,
                stable_id=u'fc-stable-id',
                did=fcdid,
                scopecontent=u'fc-scoppecontent',
                description=u'fc-descr'
            )
            ibc = facomp.cw_adapt_to('IBreadCrumbs')
            self.assertEqual(
                ibc.breadcrumbs(), [
                    ('http://testing.fr/cubicweb/', u'Home'),
                    ('http://testing.fr/cubicweb/inventaires/FRAD051', u'AD de la Marne'),
                    ('http://testing.fr/cubicweb/findingaid/FRAD051_xxx',
                     u'Inventory - maindid'),
                    'fcdid-title',
                ]
            )


if __name__ == '__main__':
    unittest.main()
