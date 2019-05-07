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
from __future__ import print_function

import re
import csv
from collections import defaultdict
import unittest

from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.dataimport import normalize_entry


voie_rgx = re.compile(r'(?P<voie>.*?)\s*\(\s*(?P<type>.*?)(\s*;\s*(?P<num>.*?))?\)')
num_rgx = re.compile(r'(?P<num>\d+)\s*(?P<qual>bis|ter)?', re.I)


def extract_voie_num(label):
    match = voie_rgx.search(label)
    if match is None:
        return {'voie': label, 'num': None}
    infos = match.groupdict()
    num = infos.get('num')
    if num is not None:
        num_match = num_rgx.match(num)
        if num_match is None:
            num = None
        else:
            num = num_match.group('num')
            qual = num_match.group('qual')
            if qual:
                num = '{}{}'.format(num, qual.lower())
    return {'voie': u'{type} {voie}'.format(**infos), 'num': num}


def extract_nice_pnialocations(cnx):
    rset = cnx.execute(
        'Any P, PL WHERE P is PniaLocation, P preflabel PL, P same_as E, E uri %(uri)s',
        {'uri': 'http://www.geonames.org/2990440'}
    )
    for p, pl in rset:
        if ' -- ' in pl:
            voie = pl.split(' -- ')[1]
            infos = extract_voie_num(voie)
            yield p, pl, infos


def load_bano():
    with open('/srv/nfs/bano-nice-processed.csv') as banof:
        reader = csv.reader(banof)
        for bano_id, num, voie, __, __, __, lat, lng in reader:
            yield [bano_id, num.decode('utf-8'), voie.decode('utf-8'), float(lat), float(lng)]


def align(cnx):
    fa_labels = defaultdict(list)
    for eid, label, infos in extract_nice_pnialocations(cnx):
        normalized = normalize_entry(infos['voie'])
        fa_labels[normalized].append(merge_dicts({'eid': eid, 'label': label}, infos))
    bano_labels = defaultdict(list)
    for bano_id, num, voie, lat, lng in load_bano():
        normalized = normalize_entry(voie)
        bano_labels[normalized].append(
            {
                'bano_id': bano_id,
                'num': num,
                'voie': voie,
                'lat': lat,
                'lng': lng,
            }
        )

    unmatched = matched = 0
    unmatched_labels = []

    result = []
    for normalized, fainfos in fa_labels.items():
        if normalized in bano_labels:
            matched += 1
            for info in fainfos:
                bano_infos = bano_labels[normalized]
                bano_matched = [i for i in bano_infos if i['num'] == info['num']]
                if not bano_matched:
                    bano_matched = bano_infos[0]
                else:
                    bano_matched = bano_matched[0]
                result.append([
                    info['eid'],
                    bano_matched['bano_id'],
                    bano_matched['lat'],
                    bano_matched['lng'],
                ])
        else:
            unmatched += 1
            unmatched_labels.append(normalized)
    print('matched: {}, unmatched: {}'.format(matched, unmatched))
    with open('/tmp/unmatched.txt', 'w') as outf:
        outf.write('\n'.join(unmatched_labels) + '\n')
    with open('/tmp/bano-matched.csv', 'w') as outf:
        writer = csv.writer(outf)
        writer.writerow(['pnialocation-eid', 'bano-id', 'lat', 'lng'])
        writer.writerows(result)


class Tests(unittest.TestCase):

    def assertInfos(self, label, infos):
        self.assertDictEqual(extract_voie_num(label), infos)

    def test_extract_voie(self):
        ai = self.assertInfos
        ai('Borriglione (avenue ; 50)', {'voie': 'avenue Borriglione', 'num': '50'})
        ai('Borriglione (avenue)', {'voie': 'avenue Borriglione', 'num': None})
        ai('Borriglione (avenue ; 50-52)', {'voie': 'avenue Borriglione', 'num': '50'})
        ai('Boers (avenue ; 14, 16 et 18)', {'voie': 'avenue Boers', 'num': '14'})
        ai('Bois de Boulogne (lieu-dit)', {'voie': 'lieu-dit Bois de Boulogne', 'num': None})
        ai('Bellevue (avenue ; 33 bis)', {'voie': 'avenue Bellevue', 'num': '33bis'})


if __name__ == '__main__':
    align(cnx)  # noqa
