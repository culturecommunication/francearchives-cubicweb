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
from PIL import Image

import unittest

from cubicweb import Binary
from cubicweb.devtools import testlib
from cubicweb_francearchives.cssimages import (static_css_dir,
                                               HERO_SIZES)


class ImageTests(testlib.CubicWebTC):

    def setup_database(self):
        self.static_dir = static_css_dir(self.config.static_directory)

    def tearDown(self):
        self.cleanup_static_css()
        super(ImageTests, self).tearDown()

    def cleanup_static_css(self):
        directory = static_css_dir(self.config.static_directory)
        for fname in os.listdir(directory):
            fullname = osp.join(directory, fname)
            os.unlink(fullname)

    def test_generate_thumbnails(self):
        """do not generate thumbnailes as cssid is specified"""
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            section = ce('Section', name=u'decouvrir',
                         title=u'Découvrir')
            filepth = osp.join(self.datadir, 'hero-decouvrir.jpg')
            orig_width, orig_height = Image.open(filepth).size
            with open(filepth, 'r') as stream:
                image_file = ce('File',
                                data_name=u'hero-decouvrir.jpg',
                                data_format=u'image/jpeg',
                                data=Binary(stream.read()))
                ce('CssImage', cssid=u'hero-decouvrir',
                   caption=u'Décourvir 15', order=2,
                   cssimage_of=section,
                   image_file=image_file)
                cnx.commit()
            for size, suffix in HERO_SIZES:
                image_path = u'hero-decouvrir-%s.jpg' % suffix
                image = Image.open(osp.join(self.static_dir, image_path))
                self.assertEqual(image.size[0], size['w'] or orig_width)

    def test_dont_generate_thumbnails(self):
        """do not generate thumbnailes as cssid is not specified"""
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            with open(osp.join(self.datadir,
                               'hero-decouvrir.jpg'), 'rb') as stream:
                image_file = ce('File',
                                data_name=u'hero-decouvrir.jpg',
                                data_format=u'image/jpeg',
                                data=Binary(stream.read()))
                ce('Image', caption=u'Décourvir 15',
                   image_file=image_file)
                cnx.commit()
            for size, suffix in HERO_SIZES:
                image_path = u'hero-decouvrir-%s.jpg' % suffix
                self.assertFalse(osp.isfile(
                    osp.join(self.static_dir, image_path)))

    def test_update_thumbnails(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            sm_filename = osp.join(self.static_dir,
                                   'hero-gerer-sm.jpg')
            with open(osp.join(self.datadir,
                               'hero-decouvrir.jpg'), 'rb') as stream:
                image_file = ce('File',
                                data_name=u'hero-decouvrir.jpg',
                                data_format=u'image/jpeg',
                                data=Binary(stream.read()))
                ce('CssImage', cssid=u'hero-gerer',
                   order=1, caption=u'Gerer',
                   image_file=image_file)
                cnx.commit()
                self.assertTrue(osp.isfile(sm_filename))
            self.cleanup_static_css()
            self.assertFalse(osp.isfile(sm_filename))
            image = cnx.find('CssImage', cssid=u'hero-gerer').one()
            with open(osp.join(self.datadir,
                               'hero-gerer.jpg'), 'rb') as stream:
                image.image_file[0].cw_set(data=Binary(stream.read()))
                cnx.commit()
            self.assertTrue(osp.isfile(sm_filename))

    def test_dont_update_thumbnails(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            sm_filename = osp.join(self.static_dir,
                                   'hero-gerer-sm.jpg')
            with open(osp.join(self.datadir,
                               'hero-decouvrir.jpg'), 'rb') as stream:
                image_file = ce('File',
                                data_name=u'hero-decouvrir.jpg',
                                data_format=u'image/jpeg',
                                data=Binary(stream.read()))
                ce('Image', caption=u'Gerer', image_file=image_file)
                cnx.commit()
                self.assertFalse(osp.isfile(sm_filename))
            image = cnx.find('Image').one()
            with open(osp.join(self.datadir,
                               'hero-gerer.jpg'), 'rb') as stream:
                image.image_file[0].cw_set(data=Binary(stream.read()))
                cnx.commit()
            self.assertFalse(osp.isfile(sm_filename))


if __name__ == '__main__':
    unittest.main()
